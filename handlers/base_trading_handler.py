"""交易命令基类 - 抽取公共的用户检查、参数解析逻辑"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, AsyncGenerator
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageEventResult

from ..models.stock import StockInfo
from ..models.user import User
from ..services.trade_coordinator import TradeCoordinator
from ..services.user_interaction import UserInteractionService
from ..services.trading_engine import TradingEngine


class BaseTradingHandler(ABC):
    """
    交易命令基类
    提供所有交易命令的公共功能
    """
    
    def __init__(self, trade_coordinator: TradeCoordinator, user_interaction: UserInteractionService, trading_engine: TradingEngine):
        self.trade_coordinator = trade_coordinator
        self.user_interaction = user_interaction
        self.trading_engine = trading_engine
        self._action_description = "交易操作"  # 默认描述
    
    def set_action_description(self, description: str):
        """设置操作描述（用于用户提示）"""
        self._action_description = description
    
    async def validate_user_and_parse_params(self, event: AstrMessageEvent, 
                                           require_price: bool = False) -> AsyncGenerator[Any, None]:
        """
        验证用户并解析参数的统一入口
        
        Yields:
            MessageEventResult: 错误消息（如有）
            tuple: (处理成功, 用户对象, 解析的参数)
        """
        # 1. 验证用户注册
        is_registered, error_msg, user = await self.trade_coordinator.validate_user_registration(event)
        if not is_registered:
            yield MessageEventResult().message(error_msg)
            yield (False, None, None)
            return
        
        # 2. 解析参数
        params = event.message_str.strip().split()[1:]  # 移除命令本身
        success, error_msg, parsed_params = self.trade_coordinator.parse_trading_parameters(params, require_price)
        if not success:
            yield MessageEventResult().message(error_msg)
            yield (False, None, None)
            return
        
        yield (True, user, parsed_params)
    
    async def search_and_select_stock(self, event: AstrMessageEvent, keyword: str) -> AsyncGenerator[Any, None]:
        """
        搜索并选择股票的统一流程
        
        Yields:
            MessageEventResult: 消息结果
            Dict[str, str]: 选择的股票信息 {'code', 'name', 'market'}
        """
        # 搜索股票
        success, error_msg, result = await self.trade_coordinator.search_and_validate_stock(keyword)
        if not success:
            yield MessageEventResult().message(error_msg)
            yield None
            return
        
        # 检查是否需要用户选择
        if result.get("multiple"):
            candidates = result["candidates"]
            selected_stock, error_msg = await self.user_interaction.wait_for_stock_selection(
                event, candidates, self._action_description
            )
            if error_msg:
                yield MessageEventResult().message(error_msg)
                yield None
                return
            if selected_stock:
                yield MessageEventResult().message(
                    f"✅ 已选择: {selected_stock['name']} ({selected_stock['code']})"
                )
            yield selected_stock
        else:
            yield result
    
    async def parse_and_validate_price(self, price_text: Optional[str], stock_code: str, stock_name: str) -> AsyncGenerator[Any, None]:
        """
        解析和验证价格的统一流程
        
        Yields:
            MessageEventResult: 错误消息（如有）
            float: 解析的价格值
        """
        success, error_msg, price = await self.trade_coordinator.parse_and_validate_price(
            price_text, stock_code, stock_name
        )
        if not success:
            yield MessageEventResult().message(error_msg)
            yield None
            return
        
        yield price
    
    async def get_stock_info_with_validation(self, stock_code: str) -> AsyncGenerator[Any, None]:
        """
        获取股票信息并验证的统一流程
        
        Yields:
            MessageEventResult: 错误消息（如有）
            StockInfo: 股票信息对象
        """
        success, error_msg, stock_info = await self.trade_coordinator.get_stock_realtime_info(stock_code)
        if not success:
            yield MessageEventResult().message(error_msg)
            yield None
            return
        
        yield stock_info
    
    async def confirm_trade_with_user(self, event: AstrMessageEvent, stock_name: str, stock_code: str,
                                    trade_type: str, volume: int, price: Optional[float],
                                    current_price: float, market: str = 'A') -> AsyncGenerator[Any, None]:
        """
        与用户确认交易的统一流程

        Args:
            stock_name: 股票名称
            stock_code: 股票代码
            trade_type: 交易类型
            volume: 数量
            price: 价格
            current_price: 当前价格
            market: 市场类型

        Yields:
            MessageEventResult: 错误消息（如有）
            bool: 用户确认结果
        """
        confirmation_message = self.trade_coordinator.format_trading_confirmation(
            stock_name, stock_code, trade_type, volume, price, current_price, market
        )
        
        trade_info = {
            'confirmation_message': confirmation_message,
            'stock_name': stock_name,
            'stock_code': stock_code,
            'trade_type': trade_type,
            'volume': volume,
            'price': price
        }
        
        confirmation_result, error_msg = await self.user_interaction.wait_for_trade_confirmation(event, trade_info)
        if error_msg:
            yield MessageEventResult().message(error_msg)
            yield None
            return
        yield confirmation_result
    
    async def execute_trade_flow(self, event: AstrMessageEvent, require_price: bool = False) -> AsyncGenerator[MessageEventResult, None]:
        """
        完整交易流程的模板方法
        """
        # 1. 验证用户并解析参数
        success, user, params = None, None, None
        async for result in self.validate_user_and_parse_params(event, require_price):
            if isinstance(result, MessageEventResult):
                yield result  # 转发错误消息
            else:
                success, user, params = result
                break
        
        if not success:
            return
        
        # 2. 搜索并选择股票
        selected_stock = None
        async for result in self.search_and_select_stock(event, params['keyword']):
            if isinstance(result, MessageEventResult):
                yield result  # 转发消息
            else:
                selected_stock = result
                break
        
        if not selected_stock:
            yield MessageEventResult().message("❌ 股票选择已取消")
            return
        
        stock_code = selected_stock['code']
        stock_name = selected_stock['name']
        
        # 3. 获取股票实时信息
        stock_info = None
        async for result in self.get_stock_info_with_validation(stock_code):
            if isinstance(result, MessageEventResult):
                yield result  # 转发错误消息
            else:
                stock_info = result
                break
        
        if not stock_info:
            return

        # 3.5. 验证交易数量是否符合市场规则
        from ..utils.validators import Validators
        if not Validators.is_valid_volume(params['volume'], stock_info.market):
            if stock_info.market == 'US':
                error_msg = f"❌ 无效的交易数量: {params['volume']}，必须是正整数"
            else:
                market_name = 'A股' if stock_info.market == 'A' else '港股'
                error_msg = f"❌ 无效的交易数量: {params['volume']}，{market_name}必须是100的倍数"
            yield MessageEventResult().message(error_msg)
            return

        # 4. 解析价格（如果有）
        price = None
        if params.get('price_text'):
            async for result in self.parse_and_validate_price(
                params['price_text'], stock_code, stock_name
            ):
                if isinstance(result, MessageEventResult):
                    yield result  # 转发错误消息
                else:
                    price = result
                    break
            
            if price is None:
                return
        
        # 5. 执行具体交易逻辑（由子类实现）
        async for result in self.execute_specific_trade(
            event, user, stock_info, params['volume'], price
        ):
            yield result
    
    @abstractmethod
    async def execute_specific_trade(self, event: AstrMessageEvent, user: User, 
                                   stock_info: StockInfo, volume: int, 
                                   price: Optional[float]) -> AsyncGenerator[MessageEventResult, None]:
        """
        执行具体的交易逻辑（由子类实现）
        
        Args:
            event: 原始事件
            user: 用户对象
            stock_info: 股票信息
            volume: 交易数量
            price: 交易价格（None表示市价）
        """
        pass
    
    def get_action_description(self) -> str:
        """获取操作描述（用于用户提示）"""
        return self._action_description
    
    def format_success_result(self, message: str) -> MessageEventResult:
        """格式化成功结果"""
        return MessageEventResult().message(f"✅ {message}")
    
    def format_error_result(self, message: str) -> MessageEventResult:
        """格式化错误结果"""
        return MessageEventResult().message(f"❌ {message}")
    
    def format_info_result(self, message: str) -> MessageEventResult:
        """格式化信息结果"""
        return MessageEventResult().message(message)


class BuyOrderHandler(BaseTradingHandler):
    """买入订单处理器基类"""
    
    async def execute_specific_trade(self, event: AstrMessageEvent, user: User, 
                                   stock_info: StockInfo, volume: int, 
                                   price: Optional[float]) -> AsyncGenerator[MessageEventResult, None]:
        """执行买入交易"""
        # 确定交易类型
        trade_type = "限价买入" if price else "市价买入"
        current_price = stock_info.current_price
        
        # 与用户确认交易
        confirmation = None
        async for result in self.confirm_trade_with_user(
            event, stock_info.name, stock_info.code, trade_type, volume, price, current_price, stock_info.market
        ):
            if isinstance(result, MessageEventResult):
                yield result  # 转发错误消息
            else:
                confirmation = result
                break
        
        if confirmation is None:  # 超时
            return
        elif not confirmation:  # 取消
            yield self.format_info_result("💭 交易已取消")
            return
        
        # 执行买入交易（使用注入的trading_engine，避免局部导入）
        try:
            success, message, order = await self.trading_engine.place_buy_order(
                user.user_id, stock_info.code, volume, price
            )
            
            if success:
                yield self.format_success_result(message)
            else:
                yield self.format_error_result(message)
                
        except Exception as e:
            logger.error(f"执行买入交易失败: {e}")
            yield self.format_error_result("交易失败，请稍后重试")


class SellOrderHandler(BaseTradingHandler):
    """卖出订单处理器基类"""
    
    async def execute_specific_trade(self, event: AstrMessageEvent, user: User, 
                                   stock_info: StockInfo, volume: int, 
                                   price: Optional[float]) -> AsyncGenerator[MessageEventResult, None]:
        """执行卖出交易"""
        # 确定交易类型
        trade_type = "限价卖出" if price else "市价卖出"
        current_price = stock_info.current_price
        
        # 与用户确认交易
        confirmation = None
        async for result in self.confirm_trade_with_user(
            event, stock_info.name, stock_info.code, trade_type, volume, price, current_price, stock_info.market
        ):
            if isinstance(result, MessageEventResult):
                yield result  # 转发错误消息
            else:
                confirmation = result
                break
        
        if confirmation is None:  # 超时
            return
        elif not confirmation:  # 取消
            yield self.format_info_result("💭 交易已取消")
            return
        
        # 执行卖出交易（使用注入的trading_engine，避免局部导入）
        try:
            success, message, order = await self.trading_engine.place_sell_order(
                user.user_id, stock_info.code, volume, price
            )
            
            if success:
                yield self.format_success_result(message)
            else:
                yield self.format_error_result(message)
                
        except Exception as e:
            logger.error(f"执行卖出交易失败: {e}")
            yield self.format_error_result("交易失败，请稍后重试")
