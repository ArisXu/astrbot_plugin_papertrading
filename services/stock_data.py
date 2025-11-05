"""股票数据服务 - 支持A股、港股、美股"""
import time
import re
from typing import Optional, Dict, Any
from datetime import datetime, time as dt_time
from astrbot.api import logger

from ..models.stock import StockInfo
from ..utils.validators import Validators
from ..utils.data_storage import DataStorage
from ..utils.market_time import is_trading_time, is_call_auction_time, can_place_order
from .eastmoney_api import EastMoneyAPIService
from .longport_api import LongPortAPIService


class StockDataService:
    """股票数据服务 - 支持A股、港股、美股"""

    def __init__(self, storage: DataStorage):
        self.storage = storage
        self._cache_ttl = 30  # 缓存30秒
        self.eastmoney_api = None
        self.longport_api = None

    async def _initialize_apis(self):
        """初始化API服务"""
        if self.eastmoney_api is None:
            self.eastmoney_api = EastMoneyAPIService(self.storage)

        if self.longport_api is None:
            self.longport_api = LongPortAPIService(self.storage)
            await self.longport_api.initialize()
    
    def _detect_market(self, stock_code: str) -> str:
        """
        检测股票市场类型

        Args:
            stock_code: 股票代码

        Returns:
            市场类型: 'A', 'HK', 'US', 'UNKNOWN'
        """
        stock_code = stock_code.upper().strip()

        # 检查是否已经是完整格式（带市场后缀）
        if '.HK' in stock_code or '.US' in stock_code or '.A' in stock_code:
            if '.HK' in stock_code:
                return 'HK'
            elif '.US' in stock_code:
                return 'US'
            else:
                return 'A'

        # A股：6位数字
        if re.match(r'^(00|30|60|68|43|83|87)\d{4}$', stock_code):
            return 'A'

        # 港股：5位数字（通常）
        if stock_code.isdigit() and 4 <= len(stock_code) <= 5:
            # 需要额外判断，但这里假设5位数字可能是港股
            return 'HK'

        # 美股：通常是大写字母，1-5个字符
        if stock_code.isalpha() and 1 <= len(stock_code) <= 5:
            return 'US'

        return 'UNKNOWN'

    def _normalize_stock_code(self, stock_code: str) -> tuple[str, Optional[str]]:
        """
        标准化股票代码并返回市场和标准代码

        Args:
            stock_code: 原始股票代码

        Returns:
            (market, normalized_code)
        """
        market = self._detect_market(stock_code)

        if market == 'A':
            # A股使用东方财富API
            normalized = Validators.normalize_stock_code(stock_code)
            return 'A', normalized

        elif market == 'HK' or market == 'US':
            # 港股美股使用长桥API
            if '.' not in stock_code:
                if market == 'HK':
                    return 'HK', f"{stock_code}.HK"
                elif market == 'US':
                    return 'US', f"{stock_code}.US"
            return market, stock_code

        return market, None

    async def get_stock_info(self, stock_code: str, use_cache: bool = True, skip_limit_calculation: bool = False) -> Optional[StockInfo]:
        """
        获取股票实时信息

        Args:
            stock_code: 股票代码
            use_cache: 是否使用缓存

        Returns:
            股票信息对象或None
        """
        # 标准化股票代码并识别市场
        market, normalized_code = self._normalize_stock_code(stock_code)

        if market == 'UNKNOWN' or normalized_code is None:
            logger.error(f"无法识别或标准化股票代码: {stock_code}")
            return None

        # 检查缓存
        if use_cache:
            cached_data = self.storage.get_market_cache(normalized_code)
            if cached_data and self._is_cache_valid(cached_data):
                return StockInfo.from_dict(cached_data)

        # 根据市场选择API
        try:
            if market == 'A':
                # A股使用东方财富API
                stock_data = await self._fetch_stock_data_from_eastmoney(normalized_code, skip_limit_calculation, market)
            elif market in ['HK', 'US']:
                # 港股美股使用长桥API
                stock_data = await self._fetch_stock_data_from_longport(normalized_code, market)
            else:
                logger.error(f"不支持的市场类型: {market}")
                return None

            if stock_data:
                # 保存到缓存
                self.storage.save_market_cache(normalized_code, stock_data.to_dict())
                return stock_data
                
        except Exception as e:
            logger.error(f"获取股票数据失败 {normalized_code}: {e}")

        return None

    async def _fetch_stock_data_from_longport(self, stock_code: str, market: str) -> Optional[StockInfo]:
        """
        从长桥API获取股票数据

        Args:
            stock_code: 股票代码（完整格式，如00700.HK或AAPL.US）
            market: 市场类型（HK或US）

        Returns:
            股票信息对象或None
        """
        try:
            await self._initialize_apis()

            if not self.longport_api or not self.longport_api._initialized:
                logger.warning(f"长桥API未初始化，无法获取{market}市场数据")
                return None

            raw_data = await self.longport_api.get_stock_quote(stock_code)

            if not raw_data:
                logger.warning(f"未获取到股票数据: {stock_code}")
                return None

            # 构建StockInfo对象
            stock_info = StockInfo(
                code=raw_data.get('code', ''),
                name=raw_data.get('name', ''),
                current_price=raw_data.get('current_price', 0),
                open_price=raw_data.get('open_price', 0),
                close_price=raw_data.get('close_price', 0),
                high_price=raw_data.get('high_price', 0),
                low_price=raw_data.get('low_price', 0),
                volume=raw_data.get('volume', 0),
                turnover=raw_data.get('turnover', 0),
                bid1_price=raw_data.get('bid1_price', 0),
                ask1_price=raw_data.get('ask1_price', 0),
                change_percent=raw_data.get('change_percent', 0),
                change_amount=raw_data.get('change_amount', 0),
                limit_up=raw_data.get('limit_up', 0),
                limit_down=raw_data.get('limit_down', 0),
                is_suspended=raw_data.get('is_suspended', False),
                update_time=int(time.time()),
                market=market  # 添加市场类型
            )

            return stock_info

        except Exception as e:
            logger.error(f"从长桥API获取数据失败 {stock_code}: {e}")
            return None
    
    async def _fetch_stock_data_from_eastmoney(self, stock_code: str, skip_limit_calculation: bool = False, market: str = 'A') -> Optional[StockInfo]:
        """
        从东方财富API获取股票数据

        Args:
            stock_code: 股票代码
            skip_limit_calculation: 是否跳过涨跌停计算
            market: 市场类型

        Returns:
            股票信息对象或None
        """
        try:
            async with EastMoneyAPIService(self.storage) as api:
                raw_data = await api.get_stock_realtime_data(stock_code)

                if not raw_data:
                    logger.warning(f"未获取到股票数据: {stock_code}")
                    return None

                # 构造StockInfo对象
                return await self._build_stock_info(raw_data, skip_limit_calculation, market)
                
        except Exception as e:
            logger.error(f"从东方财富API获取数据失败 {stock_code}: {e}")
            return None
    
    async def _build_stock_info(self, raw_data: Dict[str, Any], skip_limit_calculation: bool = False, market: str = 'A') -> StockInfo:
        """
        从原始数据构建StockInfo对象

        Args:
            raw_data: API返回的原始数据
            skip_limit_calculation: 是否跳过涨跌停计算
            market: 市场类型 ('A', 'HK', 'US')

        Returns:
            StockInfo对象
        """
        current_price = raw_data.get('current_price', 0)
        close_price = raw_data.get('close_price', current_price)
        stock_code = raw_data.get('code', '')
        stock_name = raw_data.get('name', '')

        # 设置买卖价格 - 统一使用当前价格，不再使用买1卖1
        # 模拟交易简化处理，所有交易都按当前价格进行
        trade_price = current_price if current_price > 0 else close_price

        # 检查股票是否停牌
        is_suspended = self._check_if_suspended(raw_data)

        # 获取涨跌停价格
        if skip_limit_calculation:
            # 跳过涨跌停计算，直接使用API数据（防止递归调用）
            limit_up = raw_data.get('limit_up', 0)
            limit_down = raw_data.get('limit_down', 0)
        else:
            from .price_service import get_price_limit_service
            price_service = get_price_limit_service(self.storage)
            limit_up, limit_down = await price_service.get_limit_prices(raw_data, stock_code, stock_name)

        # 构建StockInfo对象
        stock_info = StockInfo(
            code=stock_code,
            name=stock_name,
            current_price=current_price,
            open_price=raw_data.get('open_price', current_price),
            close_price=close_price,
            high_price=raw_data.get('high_price', current_price),
            low_price=raw_data.get('low_price', current_price),
            volume=raw_data.get('volume', 0),
            turnover=raw_data.get('turnover', 0),
            bid1_price=trade_price,  # 统一使用当前价格
            ask1_price=trade_price,  # 统一使用当前价格
            change_percent=raw_data.get('change_percent', 0),
            change_amount=raw_data.get('change_amount', 0),
            limit_up=limit_up,
            limit_down=limit_down,
            is_suspended=is_suspended,
            update_time=int(time.time()),
            market=market  # 添加市场类型
        )

        return stock_info
    
    def _check_if_suspended(self, raw_data: Dict[str, Any]) -> bool:
        """
        检查股票是否停牌
        
        Args:
            raw_data: 原始数据
            
        Returns:
            是否停牌
        """
        # 简单判断：如果当前价格为0或者成交量为0且涨跌幅为0，可能是停牌
        current_price = raw_data.get('current_price', 0)
        volume = raw_data.get('volume', 0)
        change_percent = raw_data.get('change_percent', 0)
        
        # 如果当前价格为0，肯定是停牌
        if current_price <= 0:
            return True
        
        # 如果在交易时间内，成交量为0且价格没有变化，可能是停牌
        if is_trading_time():
            return volume == 0 and change_percent == 0
        
        return False
    
    def _is_cache_valid(self, cache_data: Dict) -> bool:
        """
        检查缓存是否有效
        
        Args:
            cache_data: 缓存数据
            
        Returns:
            缓存是否有效
        """
        if 'update_time' not in cache_data:
            return False
        
        current_time = int(time.time())
        cache_time = cache_data['update_time']
        
        return (current_time - cache_time) <= self._cache_ttl
    
    def is_trading_time(self) -> bool:
        """
        检查是否在交易时间
        
        Returns:
            是否在交易时间
        """
        return is_trading_time()
    
    def is_call_auction_time(self) -> bool:
        """
        检查是否在集合竞价时间
        
        Returns:
            是否在集合竞价时间
        """
        return is_call_auction_time()
    
    def can_place_order(self, stock_info: StockInfo = None) -> tuple[bool, str]:
        """
        检查是否可以下单

        Args:
            stock_info: 股票信息，用于确定市场类型

        Returns:
            (是否可以下单, 原因说明)
        """
        if stock_info and hasattr(stock_info, 'market'):
            return can_place_order(market=stock_info.market)
        else:
            return can_place_order()
    
    async def search_stock(self, keyword: str) -> list:
        """
        搜索股票（支持多市场）

        Args:
            keyword: 搜索关键词

        Returns:
            股票列表
        """
        try:
            keyword_upper = keyword.upper().strip()

            # 如果 keyword 包含市场后缀，进行精确搜索
            if '.HK' in keyword_upper or '.US' in keyword_upper:
                return await self._search_exact_market_stock(keyword)
            elif '.' in keyword_upper and '.A' in keyword_upper:
                # A股的完整格式（如000001.A）
                base_code = keyword_upper.replace('.A', '')
                return await self._search_exact_market_stock(base_code)
            else:
                # 没有后缀，进行模糊搜索
                return await self._search_fuzzy_stock(keyword)

        except Exception as e:
            logger.error(f"搜索股票失败: {e}")
            return []

    async def _search_exact_market_stock(self, keyword: str) -> list:
        """
        精确搜索股票（带市场后缀的情况）

        Args:
            keyword: 搜索关键词（可能包含市场后缀）

        Returns:
            股票列表
        """
        keyword_upper = keyword.upper().strip()

        try:
            # 港股精确搜索
            if '.HK' in keyword_upper:
                stock_code = keyword_upper.replace('.HK', '')
                await self._initialize_apis()
                if self.longport_api and self.longport_api._initialized:
                    # 标准化为长桥格式
                    normalized_code = f"{stock_code}.HK"
                    stock_data = await self.longport_api.get_stock_quote(normalized_code)
                    if stock_data:
                        return [{
                            'code': stock_data['code'],
                            'name': stock_data['name'],
                            'price': stock_data['current_price'],
                            'market': '港股'
                        }]
                return []

            # 美股精确搜索
            elif '.US' in keyword_upper:
                stock_code = keyword_upper.replace('.US', '')
                await self._initialize_apis()
                if self.longport_api and self.longport_api._initialized:
                    # 标准化为长桥格式
                    normalized_code = f"{stock_code}.US"
                    stock_data = await self.longport_api.get_stock_quote(normalized_code)
                    if stock_data:
                        return [{
                            'code': stock_data['code'],
                            'name': stock_data['name'],
                            'price': stock_data['current_price'],
                            'market': '美股'
                        }]
                return []

            # A股精确搜索（不带后缀或带.A后缀）
            else:
                async with EastMoneyAPIService(self.storage) as api:
                    stock_info = await api.get_stock_realtime_data(keyword)
                    if stock_info:
                        return [{
                            'code': stock_info['code'],
                            'name': stock_info['name'],
                            'price': stock_info['current_price'],
                            'market': 'A股'
                        }]
                return []

        except Exception as e:
            logger.error(f"精确搜索股票失败 {keyword}: {e}")
            return []

    async def _search_fuzzy_stock(self, keyword: str) -> list:
        """
        模糊搜索股票（不带市场后缀的情况）

        Args:
            keyword: 搜索关键词

        Returns:
            股票列表
        """
        try:
            # 首先尝试A股搜索
            async with EastMoneyAPIService(self.storage) as api:
                stock_info = await api.get_stock_realtime_data(keyword)
                if stock_info:
                    return [{
                        'code': stock_info['code'],
                        'name': stock_info['name'],
                        'price': stock_info['current_price'],
                        'market': 'A股'
                    }]

            # 如果A股搜索失败，尝试港股美股模糊搜索
            await self._initialize_apis()
            if self.longport_api and self.longport_api._initialized:
                hk_us_results = await self.longport_api.search_stocks_fuzzy(keyword, limit=5)
                if hk_us_results:
                    return hk_us_results

            return []

        except Exception as e:
            logger.error(f"模糊搜索股票失败: {e}")
            return []

    async def search_stocks_fuzzy(self, keyword: str) -> list:
        """
        模糊搜索股票，支持中文、拼音、代码等（支持多市场）

        Args:
            keyword: 搜索关键词

        Returns:
            股票候选列表: [{'code', 'name', 'market'}]
        """
        results = []

        try:
            # 搜索A股
            async with EastMoneyAPIService(self.storage) as api:
                a_stock_results = await api.search_stocks_fuzzy(keyword)
                results.extend(a_stock_results)

            # 搜索港股美股
            await self._initialize_apis()
            if self.longport_api and self.longport_api._initialized:
                hk_us_results = await self.longport_api.search_stocks_fuzzy(keyword, limit=5)
                results.extend(hk_us_results)

            return results

        except Exception as e:
            logger.error(f"模糊搜索股票失败: {e}")
            return results
    
    async def batch_get_stocks(self, stock_codes: list) -> Dict[str, Optional[StockInfo]]:
        """
        批量获取股票信息（支持多市场）

        Args:
            stock_codes: 股票代码列表

        Returns:
            {stock_code: StockInfo} 字典
        """
        results = {}

        # 按市场分组股票代码
        a_stock_codes = []
        hk_us_stock_codes = []

        for code in stock_codes:
            market, normalized = self._normalize_stock_code(code)
            if market == 'A' and normalized:
                a_stock_codes.append(code)
            elif market in ['HK', 'US'] and normalized:
                hk_us_stock_codes.append(code)

        try:
            # 批量获取A股数据
            if a_stock_codes:
                async with EastMoneyAPIService(self.storage) as api:
                    raw_data_dict = await api.batch_get_stocks_data(a_stock_codes)

                    for code, raw_data in raw_data_dict.items():
                        try:
                            stock_info = await self._build_stock_info(raw_data, skip_limit_calculation=False)
                            results[code] = stock_info

                            # 保存到缓存
                            self.storage.save_market_cache(code, stock_info.to_dict())

                        except Exception as e:
                            logger.error(f"构建A股信息失败 {code}: {e}")
                            results[code] = None

            # 批量获取港股美股数据
            if hk_us_stock_codes:
                await self._initialize_apis()
                if self.longport_api and self.longport_api._initialized:
                    # 标准化股票代码，过滤掉无效代码
                    normalized_list = [self._normalize_stock_code(code) for code in hk_us_stock_codes]
                    normalized_codes = [normalized_code for _, normalized_code in normalized_list if normalized_code is not None]

                    if normalized_codes:
                        raw_data_dict = await self.longport_api.get_multiple_quotes(normalized_codes)

                        # 创建映射表，从标准化代码映射回原始代码
                        code_mapping = {normalized: original for original, normalized in normalized_list if normalized is not None}

                        for normalized_code, raw_data in raw_data_dict.items():
                            original_code = code_mapping.get(normalized_code, normalized_code)
                            try:
                                if raw_data:
                                    stock_info = StockInfo(
                                        code=raw_data.get('code', ''),
                                        name=raw_data.get('name', ''),
                                        current_price=raw_data.get('current_price', 0),
                                        open_price=raw_data.get('open_price', 0),
                                        close_price=raw_data.get('close_price', 0),
                                        high_price=raw_data.get('high_price', 0),
                                        low_price=raw_data.get('low_price', 0),
                                        volume=raw_data.get('volume', 0),
                                        turnover=raw_data.get('turnover', 0),
                                        bid1_price=raw_data.get('bid1_price', 0),
                                        ask1_price=raw_data.get('ask1_price', 0),
                                        change_percent=raw_data.get('change_percent', 0),
                                        change_amount=raw_data.get('change_amount', 0),
                                        limit_up=raw_data.get('limit_up', 0),
                                        limit_down=raw_data.get('limit_down', 0),
                                        is_suspended=raw_data.get('is_suspended', False),
                                        update_time=int(time.time())
                                    )
                                    results[original_code] = stock_info

                                    # 保存到缓存
                                    self.storage.save_market_cache(normalized_code, stock_info.to_dict())
                                else:
                                    results[original_code] = None

                            except Exception as e:
                                logger.error(f"构建港股美股信息失败 {original_code}: {e}")
                                results[original_code] = None

        except Exception as e:
            logger.error(f"批量获取股票数据失败: {e}")

        return results
    
    def get_market_status(self, market: str = None) -> Dict[str, Any]:
        """
        获取市场状态信息

        Args:
            market: 市场类型（'A', 'HK', 'US'），默认为A股

        Returns:
            市场状态字典
        """
        current_time = datetime.now()
        can_order, reason = can_place_order(current_time, market)

        return {
            'current_time': current_time.strftime('%Y-%m-%d %H:%M:%S'),
            'market': market or 'A',
            'is_trading_time': is_trading_time(current_time, market),
            'is_call_auction_time': is_call_auction_time(current_time, market),
            'can_place_order': can_order,
            'reason': reason,
            'cache_ttl': self._cache_ttl
        }