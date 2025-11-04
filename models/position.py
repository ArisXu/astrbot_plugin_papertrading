"""持仓数据模型"""
from dataclasses import dataclass, asdict
from typing import Dict, Any
import time


@dataclass
class Position:
    """持仓模型"""
    user_id: str                    # 用户ID
    stock_code: str                 # 股票代码
    stock_name: str                 # 股票名称
    total_volume: int               # 总持仓数量
    available_volume: int           # 可用数量（T+1限制）
    avg_cost: float                 # 平均成本价（原始货币）
    total_cost: float               # 总成本（原始货币）
    market_value: float             # 市值（原始货币）
    profit_loss: float              # 盈亏（原始货币）
    profit_loss_percent: float      # 盈亏比例
    last_price: float               # 最新价格（原始货币）
    update_time: int                # 更新时间
    market: str = "A"               # 市场类型：'A' (A股), 'HK' (港股), 'US' (美股)
    
    def __post_init__(self):
        """初始化后处理"""
        if self.update_time == 0:
            self.update_time = int(time.time())
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Position':
        """从字典创建持仓对象"""
        return cls(**data)
    
    def add_position(self, volume: int, price: float):
        """增加持仓"""
        # 计算新的平均成本
        new_total_cost = self.total_cost + volume * price
        new_total_volume = self.total_volume + volume
        
        if new_total_volume > 0:
            self.avg_cost = new_total_cost / new_total_volume
        
        self.total_volume = new_total_volume
        self.total_cost = new_total_cost
        self.update_time = int(time.time())
        
        # 买入当日不可卖出（T+1）
        # available_volume 不变，第二天才能卖出
    
    def reduce_position(self, volume: int) -> bool:
        """减少持仓"""
        if volume > self.available_volume:
            return False
        
        # 减少持仓数量
        self.total_volume -= volume
        self.available_volume -= volume
        
        # 更稳健的成本计算：直接使用平均成本扣减，避免精度累积问题
        if self.total_volume > 0:
            self.total_cost -= self.avg_cost * volume
        else:
            self.total_cost = 0
            self.avg_cost = 0
        
        self.update_time = int(time.time())
        return True
    
    def update_market_data(self, current_price: float):
        """更新市场数据"""
        self.last_price = current_price
        self.market_value = self.total_volume * current_price
        self.profit_loss = self.market_value - self.total_cost
        
        if self.total_cost > 0:
            self.profit_loss_percent = (self.profit_loss / self.total_cost) * 100
        else:
            self.profit_loss_percent = 0
            
        self.update_time = int(time.time())
    
    def make_available_for_sale(self):
        """使持仓可卖出（T+1后调用）"""
        self.available_volume = self.total_volume
        self.update_time = int(time.time())
    
    def can_sell(self, volume: int) -> bool:
        """检查是否可以卖出指定数量"""
        return volume <= self.available_volume
    
    def is_empty(self) -> bool:
        """是否空仓"""
        return self.total_volume <= 0
    
    def get_profit_loss_rate(self) -> float:
        """获取盈亏比例"""
        return self.profit_loss_percent
