"""股票市场交易时间判断工具"""
import asyncio
from datetime import datetime, time as dt_time, date, timezone, timedelta
from typing import List, Optional, Tuple, Dict, Any
from astrbot.api import logger


class MarketTimeManager:
    """市场交易时间管理器 - 支持A股、港股、美股"""

    # 定义时区
    UTC8 = timezone(timedelta(hours=8))  # 北京时间（A 股、港股）
    UTC5 = timezone(timedelta(hours=-5))  # 美国东部时间（美股）
    EST = timezone(timedelta(hours=-5))   # 东部标准时间
    EDT = timezone(timedelta(hours=-4))   # 东部夏令时

    def __init__(self):
        # 定义各市场的交易时间（均为当地时间）
        self.market_configs = {
            'A': {  # A股
                'timezone': UTC8,
                'trading_sessions': [
                    (dt_time(9, 30), dt_time(11, 30)),   # 上午交易时间
                    (dt_time(13, 0), dt_time(15, 0))     # 下午交易时间
                ],
                'call_auction_sessions': [
                    (dt_time(9, 15), dt_time(9, 25)),    # 开盘集合竞价
                    (dt_time(14, 57), dt_time(15, 0))    # 收盘集合竞价
                ],
                'holidays': self._get_chinese_holidays()
            },
            'HK': {  # 港股
                'timezone': UTC8,
                'trading_sessions': [
                    (dt_time(9, 30), dt_time(12, 0)),    # 上午交易时间
                    (dt_time(13, 0), dt_time(16, 0))     # 下午交易时间
                ],
                'call_auction_sessions': [
                    (dt_time(9, 30), dt_time(10, 0)),    # 开盘前
                    (dt_time(12, 0), dt_time(13, 0))     # 午间休息
                ],
                'holidays': self._get_hk_holidays()
            },
            'US': {  # 美股
                'timezone': EDT,  # 美股使用东部夏令时（3-11月）
                'trading_sessions': [
                    (dt_time(9, 30), dt_time(16, 0))     # 正常交易时间（美东时间）
                ],
                'pre_market_sessions': [
                    (dt_time(4, 0), dt_time(9, 30))      # 盘前交易（美东时间）
                ],
                'after_hours_sessions': [
                    (dt_time(16, 0), dt_time(20, 0))     # 盘后交易（美东时间）
                ],
                'overnight_sessions': [
                    (dt_time(20, 0), dt_time(23, 59)),   # 夜盘交易上半场（美东时间）
                    (dt_time(0, 0), dt_time(4, 0))       # 夜盘交易下半场（美东时间）
                ],
                'holidays': self._get_us_holidays()
            }
        }

        # 默认市场为A股（保持向后兼容）
        self.default_market = 'A'

    def _get_chinese_holidays(self) -> List[date]:
        """获取A股节假日列表（中国法定节假日）"""
        current_year = datetime.now().year
        holidays = []

        # 元旦
        holidays.append(date(current_year, 1, 1))

        # 春节假期（简化处理，实际应该根据农历计算）
        chinese_new_year_days = [
            # 2024年春节示例
            date(2024, 2, 10), date(2024, 2, 11), date(2024, 2, 12),
            date(2024, 2, 13), date(2024, 2, 14), date(2024, 2, 15), date(2024, 2, 16),
            # 2025年春节示例（简化）
            date(2025, 1, 29), date(2025, 1, 30), date(2025, 1, 31),
            date(2025, 2, 1), date(2025, 2, 2), date(2025, 2, 3), date(2025, 2, 4)
        ]
        holidays.extend(chinese_new_year_days)

        # 清明节
        holidays.extend([
            date(current_year, 4, 4), date(current_year, 4, 5), date(current_year, 4, 6)
        ])

        # 劳动节
        holidays.extend([
            date(current_year, 5, 1), date(current_year, 5, 2), date(current_year, 5, 3)
        ])

        # 端午节
        holidays.extend([
            date(current_year, 6, 10)  # 2024年端午节示例
        ])

        # 中秋节
        holidays.extend([
            date(current_year, 9, 15), date(current_year, 9, 16), date(current_year, 9, 17)  # 2024年中秋示例
        ])

        # 国庆节
        for day in range(1, 8):  # 10月1-7日
            holidays.append(date(current_year, 10, day))

        return holidays

    def _get_hk_holidays(self) -> List[date]:
        """获取港股节假日列表（香港公众假期）"""
        current_year = datetime.now().year
        holidays = []

        # 香港与内地共同的节假日
        holidays.extend(self._get_chinese_holidays())

        # 香港独有节假日
        holidays.extend([
            date(current_year, 4, 1),   # 复活节清明节假期
            date(current_year, 4, 2),   # 复活节假期
            date(current_year, 7, 1),   # 香港特别行政区成立纪念日
            date(current_year, 12, 25), # 圣诞节
            date(current_year, 12, 26), # 圣诞节翌日
        ])

        return holidays

    def _get_us_holidays(self) -> List[date]:
        """获取美股节假日列表（美国联邦假日）"""
        current_year = datetime.now().year
        holidays = []

        # 美股节假日（固定日期）
        holidays.extend([
            date(current_year, 1, 1),   # New Year's Day
            date(current_year, 7, 4),   # Independence Day
            date(current_year, 11, 11), # Veterans Day
            date(current_year, 12, 25), # Christmas Day
        ])

        # 浮动节假日（需要根据具体年份计算，这里简化为常见日期）
        # Martin Luther King Jr. Day（1月第三个周一）
        if current_year == 2024:
            holidays.append(date(2024, 1, 15))
        elif current_year == 2025:
            holidays.append(date(2025, 1, 20))

        # Presidents' Day（2月第三个周一）
        if current_year == 2024:
            holidays.append(date(2024, 2, 19))
        elif current_year == 2025:
            holidays.append(date(2025, 2, 17))

        # Memorial Day（5月最后一个周一）
        if current_year == 2024:
            holidays.append(date(2024, 5, 27))
        elif current_year == 2025:
            holidays.append(date(2025, 5, 26))

        # Labor Day（9月第一个周一）
        if current_year == 2024:
            holidays.append(date(2024, 9, 2))
        elif current_year == 2025:
            holidays.append(date(2025, 9, 1))

        # Columbus Day（10月第二个周一）
        if current_year == 2024:
            holidays.append(date(2024, 10, 14))
        elif current_year == 2025:
            holidays.append(date(2025, 10, 13))

        return holidays

    def _get_default_holidays(self) -> List[date]:
        """
        获取默认节假日列表（保持向后兼容）
        简化实现，包含主要法定节假日
        实际项目中建议对接专业的节假日API
        """
        # 默认返回A股节假日
        return self._get_chinese_holidays()
    
    def is_weekday(self, target_date: Optional[date] = None) -> bool:
        """
        判断是否为工作日（周一到周五）
        港股美股同样适用

        Args:
            target_date: 目标日期，默认为今天

        Returns:
            是否为工作日
        """
        if target_date is None:
            target_date = datetime.now().date()

        return target_date.weekday() < 5  # 0-4 是周一到周五

    def is_holiday(self, target_date: Optional[date] = None, market: str = None) -> bool:
        """
        判断是否为法定节假日

        Args:
            target_date: 目标日期，默认为今天
            market: 市场类型（'A', 'HK', 'US'），默认为A股

        Returns:
            是否为法定节假日
        """
        if target_date is None:
            target_date = datetime.now().date()

        if market is None:
            market = self.default_market

        holidays = self.market_configs[market]['holidays']
        return target_date in holidays

    def is_trading_day(self, target_date: Optional[date] = None, market: str = None) -> bool:
        """
        判断是否为交易日

        Args:
            target_date: 目标日期，默认为今天
            market: 市场类型（'A', 'HK', 'US'），默认为A股

        Returns:
            是否为交易日（工作日且非节假日）
        """
        if target_date is None:
            target_date = datetime.now().date()

        if market is None:
            market = self.default_market

        return self.is_weekday(target_date) and not self.is_holiday(target_date, market)

    def _convert_to_market_time(self, target_time: datetime, market: str) -> datetime:
        """
        将指定时间转换为目标市场的本地时间

        Args:
            target_time: 要转换的时间（UTC或任意时区）
            market: 目标市场（'A', 'HK', 'US'）

        Returns:
            目标市场的本地时间
        """
        if market is None:
            market = self.default_market

        market_timezone = self.market_configs[market]['timezone']

        # 如果目标时间没有时区信息，假设是UTC时间
        if target_time.tzinfo is None:
            target_time = target_time.replace(tzinfo=timezone.utc)

        # 转换为目标市场的时区
        market_time = target_time.astimezone(market_timezone)
        return market_time
    
    def is_trading_time(self, target_time: Optional[datetime] = None, market: str = None) -> bool:
        """
        判断是否在交易时间内

        Args:
            target_time: 目标时间，默认为当前时间（UTC时间）
            market: 市场类型（'A', 'HK', 'US'），默认为A股

        Returns:
            是否在交易时间内
        """
        if target_time is None:
            target_time = datetime.now(timezone.utc)

        if market is None:
            market = self.default_market

        # 转换为目标市场的本地时间
        market_time = self._convert_to_market_time(target_time, market)

        # 首先检查是否为交易日
        if not self.is_trading_day(market_time.date(), market):
            return False

        market_config = self.market_configs[market]
        trading_sessions = market_config['trading_sessions']
        current_time = market_time.time()

        # 检查是否在任一交易时间段内
        for start_time, end_time in trading_sessions:
            if start_time <= current_time <= end_time:
                return True

        return False

    def is_pre_market_time(self, target_time: Optional[datetime] = None, market: str = None) -> bool:
        """
        判断是否在盘前交易时间（仅美股有盘前交易）

        Args:
            target_time: 目标时间，默认为当前时间（UTC时间）
            market: 市场类型（'A', 'HK', 'US'），默认为A股

        Returns:
            是否在盘前交易时间内
        """
        if target_time is None:
            target_time = datetime.now(timezone.utc)

        if market is None:
            market = self.default_market

        # 只有美股有盘前交易
        if market != 'US':
            return False

        # 转换为美东时间
        market_time = self._convert_to_market_time(target_time, market)

        # 检查是否为交易日
        if not self.is_trading_day(market_time.date(), market):
            return False

        market_config = self.market_configs[market]
        pre_market_sessions = market_config.get('pre_market_sessions', [])
        current_time = market_time.time()

        # 检查是否在盘前交易时间段内
        for start_time, end_time in pre_market_sessions:
            if start_time <= current_time <= end_time:
                return True

        return False

    def is_after_hours_time(self, target_time: Optional[datetime] = None, market: str = None) -> bool:
        """
        判断是否在盘后交易时间（仅美股有盘后交易）

        Args:
            target_time: 目标时间，默认为当前时间（UTC时间）
            market: 市场类型（'A', 'HK', 'US'），默认为A股

        Returns:
            是否在盘后交易时间内
        """
        if target_time is None:
            target_time = datetime.now(timezone.utc)

        if market is None:
            market = self.default_market

        # 只有美股有盘后交易
        if market != 'US':
            return False

        # 转换为美东时间
        market_time = self._convert_to_market_time(target_time, market)

        # 检查是否为交易日
        if not self.is_trading_day(market_time.date(), market):
            return False

        market_config = self.market_configs[market]
        after_hours_sessions = market_config.get('after_hours_sessions', [])
        current_time = market_time.time()

        # 检查是否在盘后交易时间段内
        for start_time, end_time in after_hours_sessions:
            if start_time <= current_time <= end_time:
                return True

        return False

    def is_overnight_trading_time(self, target_time: Optional[datetime] = None, market: str = None) -> bool:
        """
        判断是否在夜盘交易时间（长桥美股专有，支持跨天交易）

        Args:
            target_time: 目标时间，默认为当前时间（UTC时间）
            market: 市场类型（'A', 'HK', 'US'），默认为A股

        Returns:
            是否在夜盘交易时间内
        """
        if target_time is None:
            target_time = datetime.now(timezone.utc)

        if market is None:
            market = self.default_market

        # 只有美股有夜盘交易
        if market != 'US':
            return False

        # 转换为美东时间
        market_time = self._convert_to_market_time(target_time, market)

        # 检查是否为交易日（注意夜盘可能跨越两个日期）
        # 夜盘20:00-23:59属于前一个交易日，00:00-04:00属于下一个交易日
        current_time = market_time.time()

        # 获取前一交易日和后一交易日
        prev_trading_day = market_time.date()
        next_trading_day = date.fromordinal(market_time.date().toordinal() + 1)

        # 检查前一交易日是否有效（夜盘上半场20:00-23:59）
        if current_time >= dt_time(20, 0) and current_time <= dt_time(23, 59):
            if self.is_trading_day(prev_trading_day, market):
                market_config = self.market_configs[market]
                overnight_sessions = market_config.get('overnight_sessions', [])
                # 检查夜盘上半场
                if len(overnight_sessions) > 0:
                    start_time, end_time = overnight_sessions[0]  # (20:00, 23:59)
                    if start_time <= current_time <= end_time:
                        return True
        # 检查下一交易日是否有效（夜盘下半场00:00-04:00）
        elif current_time >= dt_time(0, 0) and current_time <= dt_time(4, 0):
            if self.is_trading_day(next_trading_day, market):
                market_config = self.market_configs[market]
                overnight_sessions = market_config.get('overnight_sessions', [])
                # 检查夜盘下半场
                if len(overnight_sessions) > 1:
                    start_time, end_time = overnight_sessions[1]  # (00:00, 04:00)
                    if start_time <= current_time <= end_time:
                        return True

        return False

    def is_call_auction_time(self, target_time: Optional[datetime] = None, market: str = None) -> bool:
        """
        判断是否在集合竞价时间内

        Args:
            target_time: 目标时间，默认为当前时间（UTC时间）
            market: 市场类型（'A', 'HK', 'US'），默认为A股

        Returns:
            是否在集合竞价时间内
        """
        if target_time is None:
            target_time = datetime.now(timezone.utc)

        if market is None:
            market = self.default_market

        # 转换为目标市场的本地时间
        market_time = self._convert_to_market_time(target_time, market)

        # 首先检查是否为交易日
        if not self.is_trading_day(market_time.date(), market):
            return False

        market_config = self.market_configs[market]
        call_auction_sessions = market_config.get('call_auction_sessions', [])
        current_time = market_time.time()

        # 检查是否在任一集合竞价时间段内
        for start_time, end_time in call_auction_sessions:
            if start_time <= current_time <= end_time:
                return True

        return False

    def is_market_open(self, target_time: Optional[datetime] = None, market: str = None) -> bool:
        """
        判断市场是否开放（支持所有交易时段：正常、集合竞价、盘前盘后、夜盘）

        Args:
            target_time: 目标时间，默认为当前时间（UTC时间）
            market: 市场类型（'A', 'HK', 'US'），默认为A股

        Returns:
            市场是否开放
        """
        if target_time is None:
            target_time = datetime.now(timezone.utc)

        if market is None:
            market = self.default_market

        # 基本交易时间
        if self.is_trading_time(target_time, market):
            return True

        # 集合竞价时间（A股、港股）
        if self.is_call_auction_time(target_time, market):
            return True

        # 美股的特殊交易时段
        if market == 'US':
            # 盘前交易
            if self.is_pre_market_time(target_time, market):
                return True
            # 盘后交易
            if self.is_after_hours_time(target_time, market):
                return True
            # 夜盘交易（长桥专有）
            if self.is_overnight_trading_time(target_time, market):
                return True

        return False

    def get_next_trading_time(self, from_time: Optional[datetime] = None, market: str = None) -> Optional[datetime]:
        """
        获取下一个交易时间点

        Args:
            from_time: 起始时间，默认为当前时间（UTC时间）
            market: 市场类型（'A', 'HK', 'US'），默认为A股

        Returns:
            下一个交易时间点或None
        """
        if from_time is None:
            from_time = datetime.now(timezone.utc)

        if market is None:
            market = self.default_market

        market_timezone = self.market_configs[market]['timezone']
        market_config = self.market_configs[market]

        # 转换为目标市场的时间
        from_market_time = self._convert_to_market_time(from_time, market)
        current_date = from_market_time.date()
        current_time = from_market_time.time()

        # 如果是交易日
        if self.is_trading_day(current_date, market):
            trading_sessions = market_config['trading_sessions']
            # 检查今日剩余的交易时间段
            for start_time, _ in trading_sessions:
                if current_time < start_time:
                    # 返回目标市场的开盘时间
                    return datetime.combine(current_date, start_time).replace(tzinfo=market_timezone)

        # 寻找下一个交易日的开盘时间
        for i in range(1, 15):  # 最多向前查找15天
            next_date = date.fromordinal(current_date.toordinal() + i)
            if self.is_trading_day(next_date, market):
                next_market_time = datetime.combine(next_date, market_config['trading_sessions'][0][0])
                return next_market_time.replace(tzinfo=market_timezone)

        return None

    def get_trading_sessions_info(self, target_date: Optional[date] = None, market: str = None) -> Dict[str, Any]:
        """
        获取指定日期的交易时间段信息

        Args:
            target_date: 目标日期，默认为今天
            market: 市场类型（'A', 'HK', 'US'），默认为A股

        Returns:
            交易时间段信息字典
        """
        if target_date is None:
            target_date = datetime.now().date()

        if market is None:
            market = self.default_market

        market_config = self.market_configs[market]
        trading_sessions = market_config['trading_sessions']
        call_auction_sessions = market_config.get('call_auction_sessions', [])
        pre_market_sessions = market_config.get('pre_market_sessions', [])
        after_hours_sessions = market_config.get('after_hours_sessions', [])

        result = {
            'date': target_date,
            'market': market,
            'timezone': str(market_config['timezone']),
            'is_trading_day': self.is_trading_day(target_date, market),
            'is_weekday': self.is_weekday(target_date),
            'is_holiday': self.is_holiday(target_date, market),
            'trading_sessions': [
                {
                    'start': session[0].strftime('%H:%M'),
                    'end': session[1].strftime('%H:%M')
                }
                for session in trading_sessions
            ]
        }

        # 添加集合竞价时间（A股、港股）
        if call_auction_sessions:
            result['call_auction_sessions'] = [
                {
                    'start': session[0].strftime('%H:%M'),
                    'end': session[1].strftime('%H:%M')
                }
                for session in call_auction_sessions
            ]

        # 添加美股特殊时段
        if market == 'US':
            if pre_market_sessions:
                result['pre_market_sessions'] = [
                    {
                        'start': session[0].strftime('%H:%M'),
                        'end': session[1].strftime('%H:%M')
                    }
                    for session in pre_market_sessions
                ]
            if after_hours_sessions:
                result['after_hours_sessions'] = [
                    {
                        'start': session[0].strftime('%H:%M'),
                        'end': session[1].strftime('%H:%M')
                    }
                    for session in after_hours_sessions
                ]
            # 添加夜盘交易时段（长桥专有）
            overnight_sessions = market_config.get('overnight_sessions', [])
            if overnight_sessions:
                result['overnight_sessions'] = [
                    {
                        'start': session[0].strftime('%H:%M'),
                        'end': session[1].strftime('%H:%M')
                    }
                    for session in overnight_sessions
                ]

        return result
    
    def can_place_order(self, target_time: Optional[datetime] = None, market: str = None) -> Tuple[bool, str]:
        """
        判断是否可以下单，返回详细原因

        Args:
            target_time: 目标时间，默认为当前时间（UTC时间）
            market: 市场类型（'A', 'HK', 'US'），默认为A股

        Returns:
            (是否可以下单, 原因说明)
        """
        if target_time is None:
            target_time = datetime.now(timezone.utc)

        if market is None:
            market = self.default_market

        # 转换为目标市场的本地时间
        market_time = self._convert_to_market_time(target_time, market)

        # 检查是否为交易日
        if not self.is_trading_day(market_time.date(), market):
            if not self.is_weekday(market_time.date()):
                return False, f"{market}市场今日为周末，不可交易"
            else:
                return False, f"{market}市场今日为法定节假日，不可交易"

        # 检查具体时间
        market_config = self.market_configs[market]
        current_time = market_time.time()

        # 基本交易时间
        if self.is_trading_time(target_time, market):
            return True, f"{market}市场正常交易时间"
        elif self.is_call_auction_time(target_time, market):
            return True, f"{market}市场集合竞价时间"
        elif market == 'US':
            # 美股特殊时段检查（包含夜盘）
            if self.is_pre_market_time(target_time, market):
                return True, "美股盘前交易时间"
            elif self.is_after_hours_time(target_time, market):
                return True, "美股盘后交易时间"
            elif self.is_overnight_trading_time(target_time, market):
                return True, "美股夜盘交易时间（长桥）"

        # A股和港股的时间段判断
        if market in ['A', 'HK']:
            # 根据各市场的具体时间安排判断
            if market == 'A':
                if current_time < dt_time(9, 15):
                    return False, "A股尚未到开盘时间"
                elif dt_time(9, 25) < current_time < dt_time(9, 30):
                    return False, "A股开盘前准备时间"
                elif dt_time(11, 30) < current_time < dt_time(13, 0):
                    return False, "A股午间休市时间"
                elif current_time > dt_time(15, 0):
                    return False, "A股已过收盘时间"
            elif market == 'HK':
                if current_time < dt_time(9, 30):
                    return False, "港股尚未到开盘时间"
                elif dt_time(12, 0) < current_time < dt_time(13, 0):
                    return False, "港股午间休市时间"
                elif current_time > dt_time(16, 0):
                    return False, "港股已过收盘时间"

        return False, f"{market}市场非交易时间"


# 全局市场时间管理器实例
market_time_manager = MarketTimeManager()


def is_trading_time(target_time: Optional[datetime] = None, market: str = None) -> bool:
    """
    便捷函数：判断是否在交易时间内

    Args:
        target_time: 目标时间，默认为当前时间（UTC时间）
        market: 市场类型（'A', 'HK', 'US'），默认为A股

    Returns:
        是否在交易时间内
    """
    return market_time_manager.is_trading_time(target_time, market)


def is_pre_market_time(target_time: Optional[datetime] = None, market: str = 'US') -> bool:
    """
    便捷函数：判断是否在盘前交易时间

    Args:
        target_time: 目标时间，默认为当前时间（UTC时间）
        market: 市场类型，默认为美股

    Returns:
        是否在盘前交易时间内
    """
    return market_time_manager.is_pre_market_time(target_time, market)


def is_after_hours_time(target_time: Optional[datetime] = None, market: str = 'US') -> bool:
    """
    便捷函数：判断是否在盘后交易时间

    Args:
        target_time: 目标时间，默认为当前时间（UTC时间）
        market: 市场类型，默认为美股

    Returns:
        是否在盘后交易时间内
    """
    return market_time_manager.is_after_hours_time(target_time, market)


def is_overnight_trading_time(target_time: Optional[datetime] = None, market: str = 'US') -> bool:
    """
    便捷函数：判断是否在夜盘交易时间（长桥美股专有）

    Args:
        target_time: 目标时间，默认为当前时间（UTC时间）
        market: 市场类型，默认为美股

    Returns:
        是否在夜盘交易时间内
    """
    return market_time_manager.is_overnight_trading_time(target_time, market)


def is_call_auction_time(target_time: Optional[datetime] = None, market: str = None) -> bool:
    """
    便捷函数：判断是否在集合竞价时间内

    Args:
        target_time: 目标时间，默认为当前时间（UTC时间）
        market: 市场类型（'A', 'HK', 'US'），默认为A股

    Returns:
        是否在集合竞价时间内
    """
    return market_time_manager.is_call_auction_time(target_time, market)


def is_market_open(target_time: Optional[datetime] = None, market: str = None) -> bool:
    """
    便捷函数：判断市场是否开放

    Args:
        target_time: 目标时间，默认为当前时间（UTC时间）
        market: 市场类型（'A', 'HK', 'US'），默认为A股

    Returns:
        市场是否开放
    """
    return market_time_manager.is_market_open(target_time, market)


def can_place_order(target_time: Optional[datetime] = None, market: str = None) -> Tuple[bool, str]:
    """
    便捷函数：判断是否可以下单

    Args:
        target_time: 目标时间，默认为当前时间（UTC时间）
        market: 市场类型（'A', 'HK', 'US'），默认为A股

    Returns:
        (是否可以下单, 原因说明)
    """
    return market_time_manager.can_place_order(target_time, market)


def get_next_trading_time(from_time: Optional[datetime] = None, market: str = None) -> Optional[datetime]:
    """
    便捷函数：获取下一个交易时间点

    Args:
        from_time: 起始时间，默认为当前时间（UTC时间）
        market: 市场类型（'A', 'HK', 'US'），默认为A股

    Returns:
        下一个交易时间点或None
    """
    return market_time_manager.get_next_trading_time(from_time, market)


def get_market_trading_info(market: str = None) -> Dict[str, Any]:
    """
    便捷函数：获取市场交易信息

    Args:
        market: 市场类型（'A', 'HK', 'US'），默认为A股

    Returns:
        市场交易信息字典
    """
    return market_time_manager.get_trading_sessions_info(market=market)
