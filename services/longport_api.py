"""长桥SDK API服务类 - 支持港股和美股"""
import asyncio
import time
from typing import Optional, Dict, Any, List
from astrbot.api import logger

try:
    from longport import openapi
    LONGPORT_AVAILABLE = True
except ImportError:
    LONGPORT_AVAILABLE = False
    logger.warning("LongPort SDK未安装，无法使用港股和美股功能")


class LongPortAPIService:
    """长桥API服务 - 支持港股和美股"""

    def __init__(self, storage=None):
        self.storage = storage
        self.quote_ctx = None
        self.trade_ctx = None
        self._initialized = False

        # 股票市场映射
        self.market_mapping = {
            'HK': '港股',
            'US': '美股'
        }

        # 常用指数代码
        self.index_codes = {
            '恒生指数': 'HSI',
            '恒生科技指数': 'HSTECH',
            '道琼斯': 'DJI',
            '纳斯达克': 'IXIC',
            '标普500': 'SPX'
        }

    async def initialize(self) -> bool:
        """初始化长桥API"""
        if not LONGPORT_AVAILABLE:
            logger.error("LongPort SDK未安装，无法初始化港股和美股服务")
            return False

        try:
            # 从配置获取长桥凭证
            if not self.storage:
                logger.warning("长桥API storage未初始化")
                return False

            app_key = self.storage.get_plugin_config_value('longport_app_key', '')
            app_secret = self.storage.get_plugin_config_value('longport_app_secret', '')
            access_token = self.storage.get_plugin_config_value('longport_access_token', '')

            if not all([app_key, app_secret, access_token]):
                logger.warning("长桥API凭证未配置，无法使用港股和美股功能")
                logger.info("请在插件配置中设置 longport_app_key, longport_app_secret, longport_access_token")
                return False

            # 设置环境变量
            import os
            os.environ['LONGPORT_APP_KEY'] = app_key
            os.environ['LONGPORT_APP_SECRET'] = app_secret
            os.environ['LONGPORT_ACCESS_TOKEN'] = access_token

            # 创建配置
            config = openapi.Config.from_env()

            # 创建行情上下文
            self.quote_ctx = openapi.QuoteContext(config)

            # 创建交易上下文（如果需要）
            # self.trade_ctx = openapi.TradeContext(config)

            self._initialized = True
            logger.info("长桥API初始化成功")
            return True

        except Exception as e:
            logger.error(f"长桥API初始化失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    async def close(self):
        """关闭连接"""
        try:
            if self.quote_ctx:
                await self.quote_ctx.close()
            if self.trade_ctx:
                await self.trade_ctx.close()
            self._initialized = False
        except Exception as e:
            logger.error(f"关闭长桥API连接失败: {e}")

    async def ensure_initialized(self):
        """确保API已初始化"""
        if not self._initialized:
            return await self.initialize()

    def normalize_symbol(self, symbol: str) -> str:
        """
        标准化股票代码
        支持格式：
        - 港股: 00700 (自动添加.HK)
        - 美股: AAPL (自动添加.US)
        - 完整格式: 00700.HK, AAPL.US
        """
        symbol = symbol.upper().strip()

        # 如果已经是完整格式
        if '.' in symbol:
            return symbol

        # 判断市场并添加后缀
        if symbol.startswith(('0', '6', '8')):
            # 港股通常以数字开头，添加.HK
            return f"{symbol}.HK"
        elif len(symbol) <= 5 and symbol.isalpha():
            # 美股通常是字母，最多5个字符
            return f"{symbol}.US"

        # 默认按美股处理
        return f"{symbol}.US"

    def get_market_name(self, symbol: str) -> str:
        """获取市场名称"""
        normalized = self.normalize_symbol(symbol)
        if '.HK' in normalized:
            return '港股'
        elif '.US' in normalized:
            return '美股'
        return '未知'

    async def get_stock_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取股票报价"""
        try:
            await self.ensure_initialized()
            if not self._initialized or not self.quote_ctx:
                return None

            normalized_symbol = self.normalize_symbol(symbol)
            logger.info(f"获取股票报价: {normalized_symbol}")

            # 获取实时报价
            quotes = await self.quote_ctx.quote([normalized_symbol])

            if not quotes:
                logger.warning(f"未获取到股票数据: {symbol}")
                return None

            quote = quotes[0]

            # 获取股票基本信息（名称等）
            stock_name = symbol
            try:
                static_infos = await self.quote_ctx.static_info([normalized_symbol])
                if static_infos and len(static_infos) > 0:
                    stock_name = (static_infos[0].name_cn or
                                static_infos[0].name_en or
                                static_infos[0].name_hk or
                                symbol)
            except Exception as e:
                logger.warning(f"获取股票名称失败 {symbol}: {e}")

            # 计算涨跌幅
            change_amount = 0
            change_percent = 0
            if quote.prev_close > 0 and quote.last_done > 0:
                change_amount = quote.last_done - quote.prev_close
                change_percent = (change_amount / quote.prev_close) * 100

            # 转换为统一格式
            result = {
                'code': symbol,
                'name': stock_name,
                'current_price': float(quote.last_done or 0),
                'open_price': float(quote.open or 0),
                'close_price': float(quote.prev_close),
                'high_price': float(quote.high or 0),
                'low_price': float(quote.low or 0),
                'volume': int(quote.volume or 0),
                'turnover': float(quote.turnover or 0),
                'bid1_price': float(quote.last_done or 0),  # 长桥API不提供盘口价，统一使用最新价
                'ask1_price': float(quote.last_done or 0),
                'change_amount': float(change_amount),
                'change_percent': float(change_percent),
                'limit_up': 0,  # 长桥API不直接提供涨跌停价
                'limit_down': 0,  # 需要根据市场规则计算
                'is_suspended': quote.trade_status == 'HALT',  # 根据交易状态判断
                'timestamp': int(time.time()),
            }

            # 计算涨跌停价（简化处理）
            if result['close_price'] > 0:
                market = self.get_market_name(symbol)
                if market == '港股':
                    # 港股没有涨跌停限制
                    result['limit_up'] = result['current_price'] * 2  # 理论最大
                    result['limit_down'] = 0
                elif market == '美股':
                    # 美股有盘前盘后交易限制，这里简化处理
                    result['limit_up'] = result['current_price'] * 1.2  # 20%涨跌幅
                    result['limit_down'] = result['current_price'] * 0.8

            return result

        except Exception as e:
            logger.error(f"获取股票报价失败 {symbol}: {e}")
            return None

    async def search_stocks_fuzzy(self, keyword: str, limit: int = 8) -> List[Dict[str, Any]]:
        """搜索股票"""
        try:
            await self.ensure_initialized()
            if not self._initialized or not self.quote_ctx:
                return []

            # 长桥API的搜索功能需要额外实现
            # 这里提供基本的股票搜索
            candidates = []

            # 常用股票代码示例（实际应用中应该调用长桥的搜索API）
            hk_stocks = {
                '00700': '腾讯控股',
                '09988': '阿里巴巴-SW',
                '03690': '美团-W',
                '09618': '京东集团-SW',
                '01810': '小米集团-W',
                '01299': '友邦保险',
                '00941': '中国移动',
                '01288': '农业银行'
            }

            us_stocks = {
                'AAPL': '苹果公司',
                'MSFT': '微软公司',
                'GOOGL': '谷歌A',
                'AMZN': '亚马逊',
                'TSLA': '特斯拉',
                'NVDA': '英伟达',
                'META': 'Meta平台',
                'NFLX': '奈飞'
            }

            # 搜索港股
            for code, name in hk_stocks.items():
                if keyword.upper() in code or keyword in name or keyword.upper() in name.upper():
                    candidates.append({
                        'code': code,
                        'name': name,
                        'market': '港股'
                    })
                    if len(candidates) >= limit:
                        break

            # 搜索美股
            if len(candidates) < limit:
                for code, name in us_stocks.items():
                    if keyword.upper() in code or keyword in name or keyword.upper() in name.upper():
                        candidates.append({
                            'code': code,
                            'name': name,
                            'market': '美股'
                        })
                        if len(candidates) >= limit:
                            break

            return candidates

        except Exception as e:
            logger.error(f"搜索股票失败: {e}")
            return []

    async def get_multiple_quotes(self, symbols: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """批量获取股票报价"""
        results = {}

        try:
            await self.ensure_initialized()
            if not self._initialized or not self.quote_ctx:
                return {symbol: None for symbol in symbols}

            # 标准化所有股票代码
            normalized_symbols = [self.normalize_symbol(symbol) for symbol in symbols]

            # 批量获取报价
            quotes = await self.quote_ctx.quote(normalized_symbols)

            # 构建结果字典
            for i, symbol in enumerate(symbols):
                try:
                    if i < len(quotes) and quotes[i]:
                        quote = quotes[i]

                        # 获取昨收价（简化处理，使用开盘价）
                        prev_close = float(quote.open or 0)

                        # 计算涨跌幅
                        change_amount = 0
                        change_percent = 0
                        if prev_close > 0 and quote.last_done > 0:
                            change_amount = quote.last_done - prev_close
                            change_percent = (change_amount / prev_close) * 100

                        result = {
                            'code': symbol,
                            'name': symbol,
                            'current_price': float(quote.last_done or 0),
                            'open_price': float(quote.open or 0),
                            'close_price': float(prev_close),
                            'high_price': float(quote.high or 0),
                            'low_price': float(quote.low or 0),
                            'volume': int(quote.volume or 0),
                            'turnover': float(quote.turnover or 0),
                            'bid1_price': float(quote.last_done or 0),  # 统一使用最新价
                            'ask1_price': float(quote.last_done or 0),
                            'change_amount': float(change_amount),
                            'change_percent': float(change_percent),
                            'limit_up': 0,
                            'limit_down': 0,
                            'is_suspended': quote.trade_status == 'HALT',
                            'timestamp': int(time.time()),
                        }
                        results[symbol] = result
                    else:
                        results[symbol] = None
                except Exception as e:
                    logger.error(f"处理股票 {symbol} 数据失败: {e}")
                    results[symbol] = None

        except Exception as e:
            logger.error(f"批量获取股票报价失败: {e}")
            for symbol in symbols:
                if symbol not in results:
                    results[symbol] = None

        return results

    def get_market_trading_session(self, symbol: str) -> Dict[str, Any]:
        """
        获取市场交易时间信息
        """
        market = self.get_market_name(symbol)

        sessions = {
            '港股': {
                'name': '港股市场',
                'trading_hours': '09:30-12:00, 13:00-16:00',
                'timezone': 'Asia/Hong_Kong',
                'currency': 'HKD',
                'has_limit': False,  # 港股无涨跌停
            },
            '美股': {
                'name': '美股市场',
                'trading_hours': '09:30-16:00 (盘前: 04:00-09:30, 盘后: 16:00-20:00)',
                'timezone': 'America/New_York',
                'currency': 'USD',
                'has_limit': True,  # 美股有涨跌停
                'limit_percent': 0.2,  # 20%涨跌幅限制
            }
        }

        return sessions.get(market, {
            'name': '未知市场',
            'trading_hours': '未知',
            'timezone': 'UTC',
            'currency': 'USD',
            'has_limit': False,
        })


# 全局长桥API实例
_longport_instance = None

async def get_longport_api(storage=None) -> LongPortAPIService:
    """获取长桥API实例"""
    global _longport_instance
    if _longport_instance is None:
        _longport_instance = LongPortAPIService(storage)
    return _longport_instance
