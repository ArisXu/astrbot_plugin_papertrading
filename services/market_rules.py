"""A股市场规则引擎"""
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from astrbot.api import logger
from ..models.stock import StockInfo
from ..models.order import Order, OrderType
from ..models.position import Position
from ..utils.data_storage import DataStorage
from ..utils.market_time import market_time_manager
from .currency_service import get_currency_service


class MarketRulesEngine:
    """A股市场规则引擎"""

    def __init__(self, storage: DataStorage):
        self.storage = storage
        self.currency_service = get_currency_service(storage)  # 汇率服务
    
    def validate_trading_time(self, stock_info: StockInfo = None) -> Tuple[bool, str]:
        """验证交易时间（使用统一的市场时间管理器）

        Args:
            stock_info: 股票信息，用于确定市场类型
        """
        if stock_info:
            # 根据股票信息确定市场
            market = stock_info.market
            logger.info(f"[交易时间验证] 股票市场: {market}, 股票代码: {stock_info.code}")

            result = market_time_manager.can_place_order(market=market)
            logger.info(f"[交易时间验证] 结果: {result}")
            return result
        else:
            # 如果没有股票信息，默认使用A股
            logger.warning("[交易时间验证] 没有股票信息，使用默认A股验证")
            return market_time_manager.can_place_order()
    
    def validate_buy_order(self, stock_info: StockInfo, order: Order, user_balance: float) -> Tuple[bool, str]:
        """验证买入订单"""
        # 1. 检查交易时间（限价单可以在任何时候下单）
        if order.is_market_order():
            # 市价单需要在交易时间内
            time_valid, time_msg = self.validate_trading_time(stock_info)
            if not time_valid:
                return False, time_msg + "（市价单需要在交易时间内下单）"

        # 2. 检查股票是否停牌
        if stock_info.is_suspended:
            return False, f"{stock_info.name}当前停牌，无法交易"

        # 3. 检查涨跌停限制：涨停时不能买入
        if stock_info.is_limit_up():
            return False, f"{stock_info.name}已涨停，无法买入"

        # 4. 检查价格是否超出涨跌停
        if not stock_info.can_buy_at_price(order.order_price):
            return False, f"买入价格{order.order_price:.2f}超出涨停价{stock_info.limit_up:.2f}"

        # 5. 检查资金是否充足（考虑汇率）
        total_amount_cny = self.calculate_buy_amount(order.order_volume, order.order_price, stock_info.market)
        if user_balance < total_amount_cny:
            # 获取货币符号以显示正确的币种
            currency = self.currency_service.get_currency_by_market(stock_info.market)
            formatted_needed = self.currency_service.format_currency(total_amount_cny, 'CNY')
            formatted_balance = self.currency_service.format_currency(user_balance, 'CNY')
            market_name = 'A股' if stock_info.market == 'A' else ('港股' if stock_info.market == 'HK' else '美股')
            return False, f"资金不足，需要{formatted_needed}（{market_name}），可用余额{formatted_balance}"

        # 6. 检查最小交易单位（A股100股，港股美股1股）
        min_volume = 100 if stock_info.market == 'A' else 1
        if order.order_volume % min_volume != 0:
            market_unit = "100股" if stock_info.market == 'A' else "1股"
            return False, f"交易数量必须是{min_volume}股的整数倍（{market_unit}）"

        # 7. 检查最小交易金额
        min_amount = 100 if stock_info.market == 'A' else (1000 if stock_info.market == 'HK' else 100)
        if total_amount_cny < min_amount:
            market_name = 'A股' if stock_info.market == 'A' else ('港股' if stock_info.market == 'HK' else '美股')
            formatted_amount = self.currency_service.format_currency(min_amount, 'CNY')
            return False, f"单笔交易金额不能少于{formatted_amount}（{market_name}）"

        return True, ""
    
    def validate_sell_order(self, stock_info: StockInfo, order: Order, position: Optional[Position]) -> Tuple[bool, str]:
        """验证卖出订单"""
        # 1. 检查交易时间（限价单可以在任何时候下单）
        if order.is_market_order():
            # 市价单需要在交易时间内
            time_valid, time_msg = self.validate_trading_time(stock_info)
            if not time_valid:
                return False, time_msg + "（市价单需要在交易时间内下单）"

        # 2. 检查是否有持仓
        if not position or position.is_empty():
            return False, f"您没有持有{stock_info.name}，无法卖出"

        # 3. 检查股票是否停牌
        if stock_info.is_suspended:
            return False, f"{stock_info.name}当前停牌，无法交易"

        # 4. 检查涨跌停限制：跌停时不能卖出
        if stock_info.is_limit_down():
            return False, f"{stock_info.name}已跌停，无法卖出"

        # 5. 检查价格是否超出涨跌停
        if not stock_info.can_sell_at_price(order.order_price):
            return False, f"卖出价格{order.order_price:.2f}超出跌停价{stock_info.limit_down:.2f}"

        # 6. 检查可卖数量（T+1限制）
        if not position.can_sell(order.order_volume):
            return False, f"可卖数量不足，持有{position.total_volume}股，可卖{position.available_volume}股（T+1限制）"

        # 7. 检查最小交易单位（A股100股，港股美股1股）
        min_volume = 100 if stock_info.market == 'A' else 1
        if order.order_volume % min_volume != 0:
            market_unit = "100股" if stock_info.market == 'A' else "1股"
            return False, f"交易数量必须是{min_volume}股的整数倍（{market_unit}）"

        return True, ""
    
    def calculate_buy_amount(self, volume: int, price: float, market: str = 'A') -> float:
        """计算买入所需金额（含手续费）

        Args:
            volume: 股票数量
            price: 股票价格（原始货币）
            market: 市场类型（'A', 'HK', 'US'）

        Returns:
            所需金额（人民币）
        """
        # 原始货币金额
        stock_amount_local = volume * price

        # 手续费计算（使用原始货币）
        commission_local = self.calculate_commission(stock_amount_local, market)

        # 印花税（A股买入免征，港股美股没有）
        stamp_tax_local = 0 if market == 'A' else 0

        # 过户费（仅A股有）
        transfer_fee_local = 0
        if market == 'A':
            transfer_fee_rate = self.storage.get_plugin_config_value('transfer_fee_rate', 0.00002)
            transfer_fee_local = max(1, stock_amount_local * transfer_fee_rate)

        # 计算总费用（原始货币）
        total_local = stock_amount_local + commission_local + stamp_tax_local + transfer_fee_local

        # 转换为人民币
        return self.currency_service.convert_to_cny(total_local, market)

    def calculate_sell_amount(self, volume: int, price: float, market: str = 'A') -> float:
        """计算卖出所得金额（扣除手续费）

        Args:
            volume: 股票数量
            price: 股票价格（原始货币）
            market: 市场类型（'A', 'HK', 'US'）

        Returns:
            所得金额（人民币）
        """
        # 原始货币金额
        stock_amount_local = volume * price

        # 手续费计算（使用原始货币）
        commission_local = self.calculate_commission(stock_amount_local, market)

        # 印花税（A股卖出征收，港股征收，美股免征）
        stamp_tax_local = 0
        if market == 'A':
            # A股印花税0.1%
            stamp_tax_rate = self.storage.get_plugin_config_value('stamp_tax_rate', 0.001)
            stamp_tax_local = stock_amount_local * stamp_tax_rate
        elif market == 'HK':
            # 港股印花税0.1%
            stamp_tax_rate = 0.001
            stamp_tax_local = stock_amount_local * stamp_tax_rate
        # 美股没有印花税

        # 过户费（仅A股有）
        transfer_fee_local = 0
        if market == 'A':
            transfer_fee_rate = self.storage.get_plugin_config_value('transfer_fee_rate', 0.00002)
            transfer_fee_local = max(1, stock_amount_local * transfer_fee_rate)

        # 计算净收入（原始货币）
        net_local = stock_amount_local - commission_local - stamp_tax_local - transfer_fee_local

        # 转换为人民币
        return self.currency_service.convert_to_cny(net_local, market)

    def calculate_commission(self, amount: float, market: str = 'A') -> float:
        """计算手续费（支持多市场）

        Args:
            amount: 交易金额（原始货币）
            market: 市场类型

        Returns:
            手续费（原始货币）
        """
        commission_rate = self.storage.get_plugin_config_value('commission_rate', 0.0003)  # 默认0.03%

        # 不同市场的最低手续费不同（人民币）
        min_commission_cny = {
            'A': 5.0,    # A股最低5元
            'HK': 50.0,  # 港股最低50港元
            'US': 1.0    # 美股最低1美元
        }
        min_commission_local = min_commission_cny.get(market, 5.0)

        # 转换为原始货币
        min_commission_local = min_commission_local / self.currency_service.get_exchange_rate('CNY', market)

        commission = amount * commission_rate
        return max(commission, min_commission_local)
    
    def check_price_limit(self, stock_info: StockInfo, price: float, order_type: OrderType) -> Tuple[bool, str]:
        """检查价格是否触及涨跌停"""
        if order_type == OrderType.BUY:
            if price > stock_info.limit_up:
                return False, f"买入价格{price:.2f}不能超过涨停价{stock_info.limit_up:.2f}"
        else:
            if price < stock_info.limit_down:
                return False, f"卖出价格{price:.2f}不能低于跌停价{stock_info.limit_down:.2f}"
        
        return True, ""
    
    def check_trading_suspension(self, stock_info: StockInfo) -> Tuple[bool, str]:
        """检查交易是否暂停"""
        if stock_info.is_suspended:
            return False, f"{stock_info.name}({stock_info.code})当前停牌，暂停交易"
        
        return True, ""
    

    
    def make_positions_available_for_next_day(self, user_id: str):
        """使持仓可在下一交易日卖出（T+1规则）"""
        positions = self.storage.get_positions(user_id)
        
        for pos_data in positions:
            if pos_data['total_volume'] > pos_data['available_volume']:
                # 有新买入的股票，使其可卖
                pos_data['available_volume'] = pos_data['total_volume']
                
                # 保存更新
                position = Position.from_dict(pos_data)
                self.storage.save_position(user_id, position.stock_code, position.to_dict())
    
    def is_call_auction_period(self) -> bool:
        """检查是否在集合竞价期间（使用统一的市场时间管理器）"""
        return market_time_manager.is_call_auction_time()
    
    def validate_order_in_auction(self, order: Order) -> Tuple[bool, str]:
        """验证集合竞价期间的订单"""
        if self.is_call_auction_period():
            # 集合竞价期间只能使用限价单
            if order.is_market_order():
                return False, "集合竞价期间只能使用限价委托"
        
        return True, ""
    
    def check_st_stock_rules(self, stock_code: str, stock_name: str) -> Tuple[bool, str]:
        """检查ST股票特殊规则"""
        # ST股票涨跌幅限制为5%
        if 'ST' in stock_name or '*ST' in stock_name:
            return True, "ST股票涨跌幅限制为5%"
        
        return True, ""
    
    def get_price_precision(self, price: float) -> float:
        """获取价格精度"""
        # A股价格精度为0.01元
        return round(price, 2)
    
    def validate_order_price(self, price: float) -> Tuple[bool, str]:
        """验证订单价格格式"""
        # 检查价格精度
        if round(price, 2) != price:
            return False, "价格精度不能超过2位小数"
        
        # 检查价格范围
        if price <= 0:
            return False, "价格必须大于0"
        
        if price > 10000:
            return False, "价格不能超过10000元"
        
        return True, ""
