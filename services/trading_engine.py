"""交易引擎"""
import time
from typing import Optional, Tuple, Dict, Any
from astrbot.api import logger
from ..models.user import User
from ..models.stock import StockInfo
from ..models.order import Order, OrderType, OrderStatus, PriceType
from ..models.position import Position
from ..utils.data_storage import DataStorage
from ..utils.market_time import market_time_manager
from .market_rules import MarketRulesEngine
from .currency_service import get_currency_service


class TradingEngine:
    """交易引擎"""

    def __init__(self, storage: DataStorage, stock_service=None):
        self.storage = storage
        self.market_rules = MarketRulesEngine(storage)
        self.stock_service = stock_service  # 依赖注入，避免循环依赖
        self.currency_service = get_currency_service(storage)  # 汇率服务
    
    async def place_buy_order(self, user_id: str, stock_code: str, volume: int,
                            price: Optional[float] = None) -> Tuple[bool, str, Optional[Order]]:
        """下买单"""
        logger.info(f"[place_buy_order] 开始下单: user={user_id}, stock={stock_code}, volume={volume}, price={price}")

        try:
            # 1. 获取用户信息
            logger.info("[place_buy_order] 步骤1: 获取用户信息")
            user_data = self.storage.get_user(user_id)
            if not user_data:
                logger.warning("[place_buy_order] 用户未注册")
                return False, "用户未注册，请先使用 /股票注册 注册账户", None

            user = User.from_dict(user_data)
            logger.info(f"[place_buy_order] 用户余额: {user.balance}")

            # 2. 获取股票信息
            logger.info("[place_buy_order] 步骤2: 获取股票信息")
            if not self.stock_service:
                logger.info("[place_buy_order] 初始化股票服务")
                from .stock_data import StockDataService
                self.stock_service = StockDataService(self.storage)

            stock_info = await self.stock_service.get_stock_info(stock_code)
            logger.info(f"[place_buy_order] 股票信息: {stock_info}")

            if not stock_info:
                logger.warning(f"[place_buy_order] 无法获取股票信息: {stock_code}")
                return False, f"无法获取股票{stock_code}的信息", None

            logger.info(f"[place_buy_order] 股票市场: {stock_info.market}, 当前价格: {stock_info.current_price}")

            # 3. 确定订单价格和类型
            logger.info("[place_buy_order] 步骤3: 确定订单价格和类型")
            if price is None:
                # 市价单
                order_price = stock_info.get_market_buy_price()
                price_type = PriceType.MARKET
                logger.info(f"[place_buy_order] 市价单，价格: {order_price}")
            else:
                # 限价单
                order_price = price
                price_type = PriceType.LIMIT
                logger.info(f"[place_buy_order] 限价单，价格: {order_price}")

            # 4. 创建订单（暂不生成订单号）
            logger.info("[place_buy_order] 步骤4: 创建订单对象")
            order = Order(
                order_id="",  # 验证通过后再生成
                user_id=user_id,
                stock_code=stock_code,
                stock_name=stock_info.name,
                order_type=OrderType.BUY,
                price_type=price_type,
                order_price=order_price,
                order_volume=volume,
                filled_volume=0,
                filled_amount=0,
                status=OrderStatus.PENDING,
                create_time=0,  # 将在__post_init__中生成
                update_time=0   # 将在__post_init__中生成
            )
            logger.info(f"[place_buy_order] 订单创建完成: {order.order_type}, {order.price_type}")

            # 5. 市场规则验证（包含涨停跌停检查）
            logger.info("[place_buy_order] 步骤5: 市场规则验证")
            is_valid, error_msg = self.market_rules.validate_buy_order(stock_info, order, user.balance)

            if not is_valid:
                logger.warning(f"[place_buy_order] 验证失败: {error_msg}")
                return False, error_msg, None

            logger.info("[place_buy_order] 验证通过")

            # 验证通过后生成订单号
            if hasattr(self.storage, 'get_next_order_number'):
                order.order_id = self.storage.get_next_order_number()
            else:
                # 兜底方案：使用时间戳+随机数
                import uuid
                order.order_id = str(int(time.time() * 1000))[-8:] + str(uuid.uuid4())[-4:]

            # 6. 检查交易时间
            logger.info("[place_buy_order] 步骤6: 检查交易时间")
            can_trade, trade_msg = market_time_manager.can_place_order(market=stock_info.market)
            logger.info(f"[place_buy_order] {stock_info.market}市场是否可以交易: {can_trade}, 原因: {trade_msg}")

            # 7. 处理订单
            logger.info("[place_buy_order] 步骤7: 处理订单")
            if order.is_market_order():
                # 市价单必须在可交易时间内立即成交
                if not can_trade:
                    logger.warning(f"[place_buy_order] 市价单只能在可交易时间内下单，当前市场: {stock_info.market}")
                    return False, "市价单只能在交易时间内下单", None
                order.order_price = stock_info.current_price
                logger.info(f"[place_buy_order] 执行市价买单，价格: {order.order_price}")
                return await self._execute_buy_order_immediately(user, order, stock_info)
            else:
                # 限价单处理
                # 对于限价单，即使不在交易时间也可以下单（挂单）
                # 所以这里不需要检查 can_trade，直接判断是否可立即成交
                if can_trade and order.order_price >= stock_info.current_price:
                    # 可交易且价格满足，使用当前价格立即成交
                    order.order_price = stock_info.current_price
                    logger.info(f"[place_buy_order] 执行限价买单（立即成交），价格: {order.order_price}")
                    return await self._execute_buy_order_immediately(user, order, stock_info)
                else:
                    # 非交易时间或价格不满足立即成交条件，挂单等待
                    logger.info("[place_buy_order] 挂单等待")
                    return await self._place_pending_buy_order(user, order, stock_info)

        except Exception as e:
            logger.error(f"[place_buy_order] 下单过程出错: {e}", exc_info=True)
            return False, f"下单失败: {str(e)}", None
    
    async def place_sell_order(self, user_id: str, stock_code: str, volume: int,
                             price: Optional[float] = None) -> Tuple[bool, str, Optional[Order]]:
        """下卖单"""
        # 1. 获取用户信息
        user_data = self.storage.get_user(user_id)
        if not user_data:
            return False, "用户未注册，请先使用 /股票注册 注册账户", None
        
        user = User.from_dict(user_data)
        
        # 2. 获取持仓信息
        position_data = self.storage.get_position(user_id, stock_code)
        position = Position.from_dict(position_data) if position_data else None
        
        # 3. 获取股票信息
        if not self.stock_service:
            from .stock_data import StockDataService
            self.stock_service = StockDataService(self.storage)
        stock_info = await self.stock_service.get_stock_info(stock_code)
        
        if not stock_info:
            return False, f"无法获取股票{stock_code}的信息", None
        
        # 4. 确定订单价格和类型
        if price is None:
            # 市价单
            order_price = stock_info.get_market_sell_price()
            price_type = PriceType.MARKET
        else:
            # 限价单
            order_price = price
            price_type = PriceType.LIMIT
        
        # 5. 创建订单（暂不生成订单号）
        order = Order(
            order_id="",
            user_id=user_id,
            stock_code=stock_code,
            stock_name=stock_info.name,
            order_type=OrderType.SELL,
            price_type=price_type,
            order_price=order_price,
            order_volume=volume,
            filled_volume=0,
            filled_amount=0,
            status=OrderStatus.PENDING,
            create_time=0,
            update_time=0
        )
        
        # 6. 市场规则验证（包含涨停跌停检查）
        is_valid, error_msg = self.market_rules.validate_sell_order(stock_info, order, position)
        if not is_valid:
            return False, error_msg, None
        
        # 验证通过后生成订单号
        if hasattr(self.storage, 'get_next_order_number'):
            order.order_id = self.storage.get_next_order_number()
        else:
            # 兜底方案：使用时间戳+随机数
            import uuid
            order.order_id = str(int(time.time() * 1000))[-8:] + str(uuid.uuid4())[-4:]
        
        # 7. 检查交易时间
        is_trading_time = market_time_manager.is_trading_time(market=stock_info.market)

        # 8. 处理订单（确保position不为None）
        if not position:
            return False, "您没有持有该股票，无法卖出", None

        if order.is_market_order():
            # 市价单必须在交易时间内立即成交
            if not is_trading_time:
                return False, "市价单只能在交易时间内下单", None
            order.order_price = stock_info.current_price
            return await self._execute_sell_order_immediately(user, order, position, stock_info)
        else:
            # 限价单处理
            if is_trading_time and order.order_price <= stock_info.current_price:
                # 交易时间内且可以立即成交，使用当前价格
                order.order_price = stock_info.current_price
                return await self._execute_sell_order_immediately(user, order, position, stock_info)
            else:
                # 非交易时间或价格不满足立即成交条件，挂单等待
                return await self._place_pending_sell_order(user, order, position, stock_info)
    
    async def _execute_buy_order_immediately(self, user: User, order: Order,
                                           stock_info: StockInfo) -> Tuple[bool, str, Order]:
        """立即执行买入订单"""
        # 1. 计算实际费用（考虑汇率）
        total_cost_cny = self.market_rules.calculate_buy_amount(order.order_volume, order.order_price, stock_info.market)

        # 2. 检查资金
        if not user.can_buy(total_cost_cny):
            # 格式化金额显示
            market_name = 'A股' if stock_info.market == 'A' else ('港股' if stock_info.market == 'HK' else '美股')
            formatted_cost = self.currency_service.format_currency(total_cost_cny, 'CNY')
            formatted_balance = self.currency_service.format_currency(user.balance, 'CNY')
            return False, f"资金不足，需要{formatted_cost}（{market_name}），可用余额{formatted_balance}", order

        # 3. 扣除资金
        user.deduct_balance(total_cost_cny)
        
        # 4. 更新订单状态
        order.fill_order(order.order_volume, order.order_price)
        
        # 5. 更新或创建持仓
        position_data = self.storage.get_position(user.user_id, order.stock_code)
        if position_data:
            position = Position.from_dict(position_data)
            position.add_position(order.order_volume, order.order_price)
        else:
            position = Position(
                user_id=user.user_id,
                stock_code=order.stock_code,
                stock_name=order.stock_name,
                total_volume=order.order_volume,
                available_volume=0,  # T+1，当日买入不可卖出
                avg_cost=order.order_price,
                total_cost=order.order_volume * order.order_price,
                market_value=order.order_volume * stock_info.current_price,
                profit_loss=0,
                profit_loss_percent=0,
                last_price=stock_info.current_price,
                update_time=int(time.time()),
                market=stock_info.market  # 保存市场类型
            )
        
        # 6. 更新持仓市值
        position.update_market_data(stock_info.current_price)
        
        # 7. 保存数据
        self.storage.save_user(user.user_id, user.to_dict())
        self.storage.save_position(user.user_id, order.stock_code, position.to_dict())
        self.storage.save_order(order.order_id, order.to_dict())

        # 8. 更新总资产（校正）
        await self.update_user_assets(user.user_id)

        # 格式化金额显示
        formatted_cost = self.currency_service.format_currency(total_cost_cny, 'CNY')
        price_display = f"{order.order_price:.2f}"

        # 根据市场显示正确的价格单位
        if stock_info.market == 'HK':
            price_display += f" HKD (≈{formatted_cost})"
        elif stock_info.market == 'US':
            price_display += f" USD (≈{formatted_cost})"
        else:
            price_display = f"{formatted_cost} CNY"

        return True, f"买入成功！{order.stock_name} {order.order_volume}股，价格{price_display}，总费用{formatted_cost}", order
    
    async def _execute_sell_order_immediately(self, user: User, order: Order, position: Position,
                                            stock_info: StockInfo) -> Tuple[bool, str, Order]:
        """立即执行卖出订单"""
        # 1. 计算实际收入（考虑汇率）
        total_income_cny = self.market_rules.calculate_sell_amount(order.order_volume, order.order_price, stock_info.market)

        # 2. 减少持仓
        success = position.reduce_position(order.order_volume)
        if not success:
            return False, "减少持仓失败", order

        # 3. 增加资金（以人民币结算）
        user.add_balance(total_income_cny)

        # 4. 更新订单状态
        order.fill_order(order.order_volume, order.order_price)

        # 5. 更新持仓市值
        if not position.is_empty():
            position.update_market_data(stock_info.current_price)

        # 6. 保存数据
        self.storage.save_user(user.user_id, user.to_dict())

        if position.is_empty():
            self.storage.delete_position(user.user_id, order.stock_code)
        else:
            self.storage.save_position(user.user_id, order.stock_code, position.to_dict())

        self.storage.save_order(order.order_id, order.to_dict())

        # 7. 更新总资产（校正）
        await self.update_user_assets(user.user_id)

        # 格式化金额显示
        market_name = 'A股' if stock_info.market == 'A' else ('港股' if stock_info.market == 'HK' else '美股')
        formatted_income = self.currency_service.format_currency(total_income_cny, 'CNY')
        price_display = f"{order.order_price:.2f}"

        # 根据市场显示正确的价格单位
        if stock_info.market == 'HK':
            price_display += f" HKD (≈{formatted_income})"
        elif stock_info.market == 'US':
            price_display += f" USD (≈{formatted_income})"
        else:
            price_display = f"{formatted_income} CNY"

        return True, f"卖出成功！{order.stock_name} {order.order_volume}股，价格{price_display}，到账{formatted_income}", order
    
    async def _place_pending_buy_order(self, user: User, order: Order, stock_info: StockInfo) -> Tuple[bool, str, Order]:
        """挂买单"""
        # 1. 冻结资金（考虑汇率）
        total_cost_cny = self.market_rules.calculate_buy_amount(order.order_volume, order.order_price, stock_info.market)

        if not user.can_buy(total_cost_cny):
            formatted_cost = self.currency_service.format_currency(total_cost_cny, 'CNY')
            formatted_balance = self.currency_service.format_currency(user.balance, 'CNY')
            return False, f"资金不足，需要{formatted_cost}，可用余额{formatted_balance}", order

        user.deduct_balance(total_cost_cny)

        # 2. 保存挂单
        self.storage.save_order(order.order_id, order.to_dict())
        self.storage.save_user(user.user_id, user.to_dict())

        # 3. 更新总资产（校正）
        await self.update_user_assets(user.user_id)

        # 根据交易时间给出不同的提示信息
        is_trading_time = market_time_manager.is_trading_time(market=stock_info.market)
        if is_trading_time:
            message = f"买入挂单成功！{order.stock_name} {order.order_volume}股，价格{order.order_price:.2f}元，订单号{order.order_id}"
        else:
            message = f"隔夜买单挂单成功！{order.stock_name} {order.order_volume}股，价格{order.order_price:.2f}元，将在交易时间成交，订单号{order.order_id}"
        
        return True, message, order
    
    async def _place_pending_sell_order(self, user: User, order: Order, position: Position, stock_info: StockInfo) -> Tuple[bool, str, Order]:
        """挂卖单"""
        # 1. 冻结股票（这里简化处理，实际应该单独记录冻结数量）
        # 为简化，我们不实际冻结，在成交时再次检查

        # 2. 保存挂单
        self.storage.save_order(order.order_id, order.to_dict())

        # 根据交易时间给出不同的提示信息
        is_trading_time = market_time_manager.is_trading_time(market=stock_info.market)
        if is_trading_time:
            message = f"卖出挂单成功！{order.stock_name} {order.order_volume}股，价格{order.order_price:.2f}元，订单号{order.order_id}"
        else:
            message = f"隔夜卖单挂单成功！{order.stock_name} {order.order_volume}股，价格{order.order_price:.2f}元，将在交易时间成交，订单号{order.order_id}"

        return True, message, order
    
    async def cancel_order(self, user_id: str, order_id: str) -> Tuple[bool, str]:
        """撤销订单"""
        # 1. 获取订单
        order_data = self.storage.get_order(order_id)
        if not order_data:
            return False, "订单不存在"
        
        order = Order.from_dict(order_data)
        
        # 2. 检查权限
        if order.user_id != user_id:
            return False, "无权撤销此订单"
        
        # 3. 检查状态
        if not order.is_pending():
            return False, f"订单状态为{order.status.value}，无法撤销"
        
        # 4. 撤销订单
        order.cancel_order()
        
        # 5. 退还资金（如果是买单）
        if order.is_buy_order():
            user_data = self.storage.get_user(user_id)
            if user_data:
                user = User.from_dict(user_data)
                total_cost = self.market_rules.calculate_buy_amount(order.order_volume, order.order_price)
                user.add_balance(total_cost)
                self.storage.save_user(user_id, user.to_dict())
                # 更新总资产（校正）
                await self.update_user_assets(user_id)

        # 6. 保存订单
        self.storage.save_order(order.order_id, order.to_dict())
        
        return True, f"订单撤销成功！{order.stock_name} {order.order_volume}股"
    
    async def update_user_assets(self, user_id: str):
        """更新用户总资产

        计算并更新用户的总资产（包含持仓市值）

        注意：总资产 = 可用余额 + 持仓市值
        - 可用余额(balance)已经扣除了冻结资金
        - 冻结资金是买入挂单时从balance中扣除的
        - 因此不能重复加上冻结资金
        """
        user_data = self.storage.get_user(user_id)
        if not user_data:
            return

        user = User.from_dict(user_data)
        positions = self.storage.get_positions(user_id)

        # 计算持仓市值（考虑汇率转换为人民币）
        total_market_value = 0
        for pos_data in positions:
            market = pos_data.get('market', 'A')
            market_value_local = pos_data.get('market_value', 0)
            # 将市值转换为人民币
            if market == 'A':
                # A股直接用人民币计价
                total_market_value += market_value_local
            else:
                # 港股美股需要汇率转换
                rate = self.currency_service.get_exchange_rate(
                    self.currency_service.get_currency_by_market(market), 'CNY'
                )
                total_market_value += market_value_local * rate

        # 更新总资产：可用余额 + 持仓市值（人民币）
        # 注意：不加冻结资金,因为冻结资金已经从balance中扣除
        total_assets = user.balance + total_market_value
        user.update_total_assets(total_assets)
        self.storage.save_user(user_id, user.to_dict())
    
    def get_user_trading_summary(self, user_id: str) -> Dict[str, Any]:
        """获取用户交易汇总"""
        user_data = self.storage.get_user(user_id)
        if not user_data:
            return {}

        user = User.from_dict(user_data)
        positions = self.storage.get_positions(user_id)
        orders = self.storage.get_orders(user_id)

        # 计算统计数据（考虑汇率转换为人民币）
        total_market_value_cny = 0
        total_profit_loss_cny = 0
        for pos in positions:
            market = pos.get('market', 'A')
            market_value_local = pos.get('market_value', 0)
            profit_loss_local = pos.get('profit_loss', 0)

            # 将市值和盈亏转换为人民币
            if market == 'A':
                # A股直接用人民币计价
                total_market_value_cny += market_value_local
                total_profit_loss_cny += profit_loss_local
            else:
                # 港股美股需要汇率转换
                rate = self.currency_service.get_exchange_rate(
                    self.currency_service.get_currency_by_market(market), 'CNY'
                )
                total_market_value_cny += market_value_local * rate
                total_profit_loss_cny += profit_loss_local * rate

        total_positions = len([pos for pos in positions if pos.get('total_volume', 0) > 0])
        pending_orders = len([order for order in orders if order.get('status') == 'pending'])

        return {
            'user': user.to_dict(),
            'total_market_value': total_market_value_cny,
            'total_profit_loss': total_profit_loss_cny,
            'total_positions': total_positions,
            'pending_orders': pending_orders,
            'positions': positions,
            'recent_orders': sorted(orders, key=lambda x: x.get('create_time', 0), reverse=True)[:5]
        }
