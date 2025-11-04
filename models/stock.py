"""股票数据模型"""
import math
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional
import time


@dataclass
class StockInfo:
    """股票信息模型"""
    code: str                       # 股票代码
    name: str                       # 股票名称
    current_price: float            # 当前价格（原始货币）
    open_price: float               # 开盘价
    close_price: float              # 收盘价
    high_price: float               # 最高价
    low_price: float                # 最低价
    volume: int                     # 成交量
    turnover: float                 # 成交额
    bid1_price: float               # 买一价
    ask1_price: float               # 卖一价
    change_percent: float           # 涨跌幅
    change_amount: float            # 涨跌额
    limit_up: float                 # 涨停价
    limit_down: float               # 跌停价
    is_suspended: bool              # 是否停牌
    update_time: int                # 更新时间戳
    market: str = "A"               # 市场类型：'A' (A股), 'HK' (港股), 'US' (美股)
    
    def __post_init__(self):
        """初始化后处理"""
        if self.update_time == 0:
            self.update_time = int(time.time())
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StockInfo':
        """从字典创建股票信息对象"""
        return cls(**data)
    
    def is_limit_up(self) -> bool:
        """是否涨停"""
        # 使用math.isclose进行更精确的浮点数比较
        return math.isclose(self.current_price, self.limit_up, abs_tol=0.01)
    
    def is_limit_down(self) -> bool:
        """是否跌停"""
        # 使用math.isclose进行更精确的浮点数比较
        return math.isclose(self.current_price, self.limit_down, abs_tol=0.01)
    
    def can_buy_at_price(self, price: float) -> bool:
        """检查是否可以以指定价格买入"""
        if self.is_suspended:
            return False
        
        # 涨停时不能买入（单边交易规则）
        if self.is_limit_up():
            return False
            
        return price <= self.limit_up
    
    def can_sell_at_price(self, price: float) -> bool:
        """检查是否可以以指定价格卖出"""
        if self.is_suspended:
            return False
        
        # 跌停时不能卖出（单边交易规则）
        if self.is_limit_down():
            return False
            
        return price >= self.limit_down
    
    def get_market_buy_price(self) -> float:
        """获取市价买入价格（统一使用当前价格）"""
        return self.current_price
    
    def get_market_sell_price(self) -> float:
        """获取市价卖出价格（统一使用当前价格）"""
        return self.current_price
    
    def is_data_fresh(self, max_age_seconds: int = 30) -> bool:
        """检查数据是否新鲜"""
        return (int(time.time()) - self.update_time) <= max_age_seconds
    
    def can_buy_market_order(self) -> tuple[bool, str]:
        """检查是否可以进行市价买单"""
        if self.is_suspended:
            return False, "股票已停牌，无法交易"
        
        if self.is_limit_up():
            return False, "股票已涨停，无法买入"
        
        return True, "可以买入"
    
    def can_sell_market_order(self) -> tuple[bool, str]:
        """检查是否可以进行市价卖单"""
        if self.is_suspended:
            return False, "股票已停牌，无法交易"
        
        if self.is_limit_down():
            return False, "股票已跌停，无法卖出"
        
        return True, "可以卖出"
    
    def can_place_limit_order(self, price: float, order_type: str) -> tuple[bool, str]:
        """
        检查是否可以进行限价单
        
        Args:
            price: 委托价格
            order_type: 订单类型 ('buy' 或 'sell')
            
        Returns:
            (是否可以下单, 原因说明)
        """
        if self.is_suspended:
            return False, "股票已停牌，无法交易"
        
        if order_type == 'buy':
            if self.is_limit_up():
                return False, "股票已涨停，无法买入"
            
            if price > self.limit_up:
                return False, f"买入价格 {price:.2f} 超过涨停价 {self.limit_up:.2f}"
            
            if price <= 0:
                return False, "买入价格必须大于0"
                
        elif order_type == 'sell':
            if self.is_limit_down():
                return False, "股票已跌停，无法卖出"
            
            if price < self.limit_down:
                return False, f"卖出价格 {price:.2f} 低于跌停价 {self.limit_down:.2f}"
            
            if price <= 0:
                return False, "卖出价格必须大于0"
        else:
            return False, "无效的订单类型"
        
        return True, "可以下单"
    
    def get_trading_status(self) -> str:
        """获取交易状态描述"""
        if self.is_suspended:
            return "停牌"
        elif self.is_limit_up():
            return "涨停"
        elif self.is_limit_down():
            return "跌停"
        elif self.change_percent > 0:
            return "上涨"
        elif self.change_percent < 0:
            return "下跌"
        else:
            return "平盘"
