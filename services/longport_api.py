"""长桥SDK API服务类 - 支持港股和美股"""
import asyncio
import time
from typing import Optional, Dict, Any, List
from astrbot.api import logger

# 导入时间管理模块
try:
    from ..utils.market_time import is_pre_market_time, is_after_hours_time, is_overnight_trading_time, is_trading_time
    MARKET_TIME_AVAILABLE = True
except ImportError:
    MARKET_TIME_AVAILABLE = False
    logger.warning("市场时间模块不可用，无法正确判断交易时段")

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
            logger.error("[长桥API] SDK未安装，无法初始化港股和美股服务")
            logger.error("[长桥API] 请运行: pip install longport")
            return False

        try:
            # 从配置获取长桥凭证
            if not self.storage:
                logger.error("[长桥API] storage未初始化")
                return False

            logger.info("[长桥API] 正在初始化...")
            app_key = self.storage.get_plugin_config_value('longport_app_key', '')
            app_secret = self.storage.get_plugin_config_value('longport_app_secret', '')
            access_token = self.storage.get_plugin_config_value('longport_access_token', '')

            if not all([app_key, app_secret, access_token]):
                logger.warning("[长桥API] 凭证未完整配置，无法使用港股和美股功能")
                logger.info("[长桥API] 需要的配置项:")
                logger.info("[长桥API]   - longport_app_key")
                logger.info("[长桥API]   - longport_app_secret")
                logger.info("[长桥API]   - longport_access_token")
                logger.info("[长桥API] 请在AstrBot插件配置中填写这些凭证")
                return False

            logger.info("[长桥API] 凭证检查通过，App Key: %s***", app_key[:8])

            # 设置环境变量
            import os
            os.environ['LONGPORT_APP_KEY'] = app_key
            os.environ['LONGPORT_APP_SECRET'] = app_secret
            os.environ['LONGPORT_ACCESS_TOKEN'] = access_token

            logger.info("[长桥API] 正在创建配置...")

            # 创建配置
            config = openapi.Config.from_env()
            logger.info("[长桥API] 配置创建成功")

            # 创建行情上下文
            logger.info("[长桥API] 正在创建行情上下文...")
            self.quote_ctx = openapi.QuoteContext(config)
            logger.info("[长桥API] 行情上下文创建成功")

            # 创建交易上下文（如果需要）
            # self.trade_ctx = openapi.TradeContext(config)

            self._initialized = True
            logger.info("[长桥API] ✅ 初始化成功！现在可以使用港股和美股功能")
            return True

        except Exception as e:
            logger.error("[长桥API] ❌ 初始化失败: %s", str(e))
            import traceback
            logger.error("[长桥API] 详细错误:\n%s", traceback.format_exc())
            return False

    async def close(self):
        """关闭连接"""
        try:
            if self.quote_ctx:
                self.quote_ctx.close()
            if self.trade_ctx:
                self.trade_ctx.close()
            self._initialized = False
        except Exception as e:
            logger.error(f"关闭长桥API连接失败: {e}")

    async def ensure_initialized(self):
        """确保API已初始化"""
        if not self._initialized:
            logger.debug("[长桥API] API未初始化，正在尝试初始化...")
            result = await self.initialize()
            if not result:
                logger.error("[长桥API] 初始化失败，将无法获取港股美股数据")
            return result

    def get_us_trading_session(self) -> Dict[str, Any]:
        """
        获取当前美股交易时段信息

        Returns:
            包含交易时段类型和数据源的字典
        """
        if not MARKET_TIME_AVAILABLE:
            # 如果时间模块不可用，默认返回正常交易时间
            return {
                'session_type': 'regular',
                'data_source': 'main',
                'description': '正常交易时间',
                'use_prev_close': False
            }

        try:
            # 检查各个交易时段
            if is_overnight_trading_time(market='US'):
                return {
                    'session_type': 'overnight',
                    'data_source': 'over_night_quote',
                    'description': '夜盘交易时间（长桥）',
                    'use_prev_close': True  # 夜盘使用前一日收盘价作为参考
                }
            elif is_pre_market_time(market='US'):
                return {
                    'session_type': 'pre_market',
                    'data_source': 'pre_market_quote',
                    'description': '盘前交易时间',
                    'use_prev_close': True  # 盘前使用前一日收盘价作为参考
                }
            elif is_trading_time(market='US'):
                return {
                    'session_type': 'regular',
                    'data_source': 'main',
                    'description': '正常交易时间',
                    'use_prev_close': False
                }
            elif is_after_hours_time(market='US'):
                return {
                    'session_type': 'after_hours',
                    'data_source': 'post_market_quote',
                    'description': '盘后交易时间',
                    'use_prev_close': True  # 盘后使用前一日收盘价作为参考
                }
            else:
                # 非交易时间，返回正常交易数据（可能为空）
                return {
                    'session_type': 'closed',
                    'data_source': 'main',
                    'description': '市场休市',
                    'use_prev_close': True
                }
        except Exception as e:
            logger.warning(f"获取美股交易时段失败: {e}，使用默认设置")
            return {
                'session_type': 'regular',
                'data_source': 'main',
                'description': '正常交易时间',
                'use_prev_close': False
            }

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
            logger.info("[长桥API] 开始获取股票报价: %s", symbol)

            # 确保API已初始化
            init_result = await self.ensure_initialized()
            if not self._initialized or not self.quote_ctx:
                logger.error("[长桥API] API未初始化，无法获取股票: %s", symbol)
                return None

            normalized_symbol = self.normalize_symbol(symbol)
            logger.info("[长桥API] 标准化后的代码: %s", normalized_symbol)

            # 获取实时报价
            logger.info("[长桥API] 正在调用quote API...")
            quotes = self.quote_ctx.quote([normalized_symbol])
            logger.info("[长桥API] quote API返回: %s", type(quotes))

            if not quotes:
                logger.warning("[长桥API] 未获取到股票数据: %s", symbol)
                logger.warning("[长桥API] 可能的原因:")
                logger.warning("[长桥API]   - 股票代码错误")
                logger.warning("[长桥API]   - 网络连接问题")
                logger.warning("[长桥API]   - API凭证无效")
                logger.warning("[长桥API]   - 股票不存在或已停牌")
                return None

            logger.info("[长桥API] 获取到 %d 条报价数据", len(quotes))

            quote = quotes[0]

            # 判断市场类型和交易时段
            market = self.get_market_name(normalized_symbol)
            trading_session = None
            active_quote = quote  # 默认使用主报价数据

            logger.info("[长桥API] 交易时段分析:")
            logger.info("[长桥API]   - 市场类型: %s", market)

            # 美股需要根据时间选择不同的数据源
            if market == '美股':
                trading_session = self.get_us_trading_session()
                session_type = trading_session['session_type']
                data_source = trading_session['data_source']
                use_prev_close = trading_session['use_prev_close']

                logger.info("[长桥API]   - 交易时段: %s", trading_session['description'])
                logger.info("[长桥API]   - 数据源: %s", data_source)

                # 根据数据源选择不同的报价数据
                if data_source == 'pre_market_quote' and hasattr(quote, 'pre_market_quote'):
                    active_quote = quote.pre_market_quote
                    logger.info("[长桥API]   - 使用盘前交易数据")
                elif data_source == 'post_market_quote' and hasattr(quote, 'post_market_quote'):
                    active_quote = quote.post_market_quote
                    logger.info("[长桥API]   - 使用盘后交易数据")
                elif data_source == 'over_night_quote' and hasattr(quote, 'over_night_quote'):
                    active_quote = quote.over_night_quote
                    logger.info("[长桥API]   - 使用夜盘交易数据")
                else:
                    # 正常交易时间或数据不可用，使用主数据
                    logger.info("[长桥API]   - 使用正常交易数据")
            else:
                # A股和港股直接使用主报价数据
                trading_session = {
                    'session_type': 'regular',
                    'description': '正常交易时间',
                    'use_prev_close': False
                }
                logger.info("[长桥API]   - 交易时段: 正常交易时间")

            logger.info("[长桥API] 原始报价数据:")
            logger.info("[长桥API]   - symbol: %s", quote.symbol)
            logger.info("[长桥API]   - last_done: %s", active_quote.last_done)
            logger.info("[长桥API]   - open: %s", quote.open)
            logger.info("[长桥API]   - high: %s", active_quote.high)
            logger.info("[长桥API]   - low: %s", active_quote.low)
            logger.info("[长桥API]   - volume: %s", active_quote.volume)
            logger.info("[长桥API]   - turnover: %s", active_quote.turnover)
            if hasattr(quote, 'trade_status'):
                logger.info("[长桥API]   - trade_status: %s", quote.trade_status)

            # 获取股票基本信息（名称和昨收价等）
            stock_name = symbol
            prev_close = 0  # 初始化昨收价

            try:
                logger.info("[长桥API] 正在获取股票基本信息...")
                static_infos = self.quote_ctx.static_info([normalized_symbol])
                logger.info("[长桥API] static_info API返回: %d 条记录", len(static_infos) if static_infos else 0)

                if static_infos and len(static_infos) > 0:
                    info = static_infos[0]
                    stock_name = (info.name_cn or
                                info.name_en or
                                info.name_hk or
                                symbol)

                    logger.info("[长桥API] 股票信息获取成功:")
                    logger.info("[长桥API]   - 股票代码: %s", info.symbol)
                    logger.info("[长桥API]   - 中文名: %s", info.name_cn)
                    logger.info("[长桥API]   - 英文名: %s", info.name_en)
                    logger.info("[长桥API]   - 港式名: %s", info.name_hk)
                    logger.info("[长桥API]   - 交易所: %s", info.exchange)
                    logger.info("[长桥API]   - 币种: %s", info.currency)

                    # SecurityStaticInfo确实没有prev_close属性，我们使用open作为昨收价的近似
                    prev_close = float(quote.open or 0)
                    logger.info("[长桥API] 使用开盘价作为昨收价: %s", prev_close)
                else:
                    logger.warning("[长桥API] 未获取到股票基本信息，将使用代码作为名称")
                    prev_close = float(quote.open or 0)
            except Exception as e:
                logger.warning("[长桥API] 获取股票信息失败: %s", str(e))
                logger.warning("[长桥API] 将使用代码作为名称，开盘价作为昨收价")
                prev_close = float(quote.open or 0)

            # 计算涨跌幅（根据交易时段调整计算逻辑）
            change_amount = 0.0
            change_percent = 0.0

            # 转换为float以避免Decimal和float之间的类型冲突
            current_price = float(active_quote.last_done or 0)

            # 根据交易时段选择昨收价
            if trading_session and trading_session.get('use_prev_close', False):
                # 盘前、盘后、夜盘：使用各自的prev_close字段
                if hasattr(active_quote, 'prev_close') and active_quote.prev_close:
                    prev_close_float = float(active_quote.prev_close)
                else:
                    # 如果没有单独的prev_close，使用默认的prev_close
                    prev_close_float = float(prev_close)
            else:
                # 正常交易时间：使用默认的prev_close
                prev_close_float = float(prev_close)

            if prev_close_float > 0 and current_price > 0:
                change_amount = current_price - prev_close_float
                change_percent = (change_amount / prev_close_float) * 100
                logger.info("[长桥API] 涨跌幅计算:")
                logger.info("[长桥API]   - 当前价: %s", current_price)
                logger.info("[长桥API]   - 昨收价: %s", prev_close_float)
                logger.info("[长桥API]   - 涨跌额: %s", change_amount)
                logger.info("[长桥API]   - 涨跌幅: %s%%", change_percent)
            else:
                logger.warning("[长桥API] 无法计算涨跌幅: 当前价=%s, 昨收价=%s", current_price, prev_close_float)

            # 转换为统一格式
            # 注意：盘前/盘后/夜盘数据没有open_price字段，只有last_done, prev_close, volume, turnover, high, low
            result = {
                'code': symbol,
                'name': stock_name,
                'current_price': current_price,
                'open_price': float(quote.open or 0),  # 开盘价只能从主数据获取
                'close_price': prev_close_float,
                'high_price': float(active_quote.high if hasattr(active_quote, 'high') and active_quote.high else quote.high or 0),
                'low_price': float(active_quote.low if hasattr(active_quote, 'low') and active_quote.low else quote.low or 0),
                'volume': int(active_quote.volume or 0),
                'turnover': float(active_quote.turnover or 0),
                'bid1_price': current_price,  # 长桥API不提供盘口价，统一使用最新价
                'ask1_price': current_price,
                'change_amount': float(change_amount),
                'change_percent': float(change_percent),
                'limit_up': 0,  # 长桥API不直接提供涨跌停价
                'limit_down': 0,  # 需要根据市场规则计算
                'is_suspended': quote.trade_status == 'HALT',  # 交易状态只能从主数据获取
                'timestamp': int(time.time()),
                # 添加交易时段信息
                'trading_session': {
                    'session_type': trading_session['session_type'] if trading_session else 'regular',
                    'description': trading_session['description'] if trading_session else '正常交易时间',
                    'market': market
                }
            }

            # 计算涨跌停价（简化处理）
            market = self.get_market_name(symbol)
            logger.info("[长桥API] 交易状态分析:")
            logger.info("[长桥API]   - 交易状态: %s", quote.trade_status)
            logger.info("[长桥API]   - 市场类型: %s", market)
            logger.info("[长桥API]   - 是否停牌: %s", quote.trade_status == 'HALT')

            if result['close_price'] > 0:
                if market == '港股':
                    # 港股没有涨跌停限制
                    result['limit_up'] = result['current_price'] * 2  # 理论最大
                    result['limit_down'] = 0
                    logger.info("[长桥API] 涨跌停设置 (港股): 无涨跌停限制，理论最大: %s", result['limit_up'])
                elif market == '美股':
                    # 美股有盘前盘后交易限制，这里简化处理
                    result['limit_up'] = result['current_price'] * 1.2  # 20%涨跌幅
                    result['limit_down'] = result['current_price'] * 0.8
                    logger.info("[长桥API] 涨跌停设置 (美股): 理论上下限: %s / %s", result['limit_up'], result['limit_down'])

            logger.info("[长桥API] ✅ 股票数据获取成功!")
            logger.info("[长桥API] 最终结果:")
            logger.info("[长桥API]   - 代码: %s", result['code'])
            logger.info("[长桥API]   - 名称: %s", result['name'])
            logger.info("[长桥API]   - 当前价: %s", result['current_price'])
            logger.info("[长桥API]   - 涨跌额: %s", result['change_amount'])
            logger.info("[长桥API]   - 涨跌幅: %s%%", result['change_percent'])

            return result

        except Exception as e:
            logger.error("[长桥API] ❌ 获取股票报价失败: %s", symbol)
            logger.error("[长桥API] 错误类型: %s", type(e).__name__)
            logger.error("[长桥API] 错误信息: %s", str(e))
            import traceback
            logger.error("[长桥API] 详细错误追踪:\n%s", traceback.format_exc())
            logger.error("[长桥API] 如果问题持续，请检查:")
            logger.error("[长桥API]   1. 网络连接是否正常")
            logger.error("[长桥API]   2. API凭证是否有效")
            logger.error("[长桥API]   3. 股票代码是否正确")
            return None

    async def search_stocks_fuzzy(self, keyword: str, limit: int = 8) -> List[Dict[str, Any]]:
        """搜索股票"""
        try:
            logger.info("[长桥API] 开始搜索股票，关键词: %s", keyword)

            init_result = await self.ensure_initialized()
            if not self._initialized or not self.quote_ctx:
                logger.error("[长桥API] API未初始化，无法搜索股票")
                return []

            logger.info("[长桥API] API已初始化，开始搜索...")

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
            logger.info("[长桥API] 搜索港股，匹配结果:")
            for code, name in hk_stocks.items():
                if keyword.upper() in code or keyword in name or keyword.upper() in name.upper():
                    candidates.append({
                        'code': code,
                        'name': name,
                        'market': '港股'
                    })
                    logger.info("[长桥API]   - %s (%s)", code, name)
                    if len(candidates) >= limit:
                        break

            # 搜索美股
            if len(candidates) < limit:
                logger.info("[长桥API] 搜索美股，匹配结果:")
                for code, name in us_stocks.items():
                    if keyword.upper() in code or keyword in name or keyword.upper() in name.upper():
                        candidates.append({
                            'code': code,
                            'name': name,
                            'market': '美股'
                        })
                        logger.info("[长桥API]   - %s (%s)", code, name)
                        if len(candidates) >= limit:
                            break

            logger.info("[长桥API] 搜索完成，找到 %d 个匹配结果", len(candidates))
            return candidates

        except Exception as e:
            logger.error("[长桥API] ❌ 搜索股票失败: %s", str(e))
            import traceback
            logger.error("[长桥API] 详细错误:\n%s", traceback.format_exc())
            return []

    async def get_multiple_quotes(self, symbols: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """批量获取股票报价"""
        results = {}

        try:
            logger.info("[长桥API] 开始批量获取 %d 只股票报价", len(symbols))

            init_result = await self.ensure_initialized()
            if not self._initialized or not self.quote_ctx:
                logger.error("[长桥API] API未初始化，无法获取股票报价")
                return {symbol: None for symbol in symbols}

            # 标准化所有股票代码
            normalized_symbols = [self.normalize_symbol(symbol) for symbol in symbols]
            logger.info("[长桥API] 标准化后的代码: %s", normalized_symbols)

            # 批量获取报价
            logger.info("[长桥API] 正在调用quote API批量获取报价...")
            quotes = self.quote_ctx.quote(normalized_symbols)
            logger.info("[长桥API] quote API返回 %d 条数据", len(quotes) if quotes else 0)

            # 构建结果字典
            success_count = 0
            failed_count = 0

            for i, symbol in enumerate(symbols):
                try:
                    if i < len(quotes) and quotes[i]:
                        quote = quotes[i]
                        logger.debug("[长桥API] 处理股票 %s (第%d个)", symbol, i + 1)

                        # 判断市场类型和交易时段
                        market = self.get_market_name(symbol)
                        trading_session = None
                        active_quote = quote  # 默认使用主报价数据

                        # 美股需要根据时间选择不同的数据源
                        if market == '美股':
                            trading_session = self.get_us_trading_session()
                            session_type = trading_session['session_type']
                            data_source = trading_session['data_source']
                            use_prev_close = trading_session['use_prev_close']

                            logger.debug(f"[长桥API] {symbol} 交易时段: {trading_session['description']}")

                            # 根据数据源选择不同的报价数据
                            if data_source == 'pre_market_quote' and hasattr(quote, 'pre_market_quote'):
                                active_quote = quote.pre_market_quote
                            elif data_source == 'post_market_quote' and hasattr(quote, 'post_market_quote'):
                                active_quote = quote.post_market_quote
                            elif data_source == 'over_night_quote' and hasattr(quote, 'over_night_quote'):
                                active_quote = quote.over_night_quote
                            else:
                                # 正常交易时间或数据不可用，使用主数据
                                pass
                        else:
                            # A股和港股直接使用主报价数据
                            trading_session = {
                                'session_type': 'regular',
                                'description': '正常交易时间',
                                'use_prev_close': False
                            }

                        # 确保类型转换一致，避免Decimal和float的冲突
                        current_price = float(active_quote.last_done or 0)

                        # 根据交易时段选择昨收价
                        if trading_session and trading_session.get('use_prev_close', False):
                            # 盘前、盘后、夜盘：使用各自的prev_close字段
                            if hasattr(active_quote, 'prev_close') and active_quote.prev_close:
                                prev_close_float = float(active_quote.prev_close)
                            else:
                                # 如果没有单独的prev_close，使用默认的prev_close
                                prev_close_float = float(active_quote.open or 0)
                        else:
                            # 正常交易时间：使用默认的prev_close
                            prev_close_float = float(active_quote.open or 0)

                        # 计算涨跌幅
                        change_amount = 0.0
                        change_percent = 0.0
                        if prev_close_float > 0 and current_price > 0:
                            change_amount = current_price - prev_close_float
                            change_percent = (change_amount / prev_close_float) * 100

                        result = {
                            'code': symbol,
                            'name': symbol,
                            'current_price': current_price,
                            'open_price': float(quote.open or 0),  # 开盘价只能从主数据获取
                            'close_price': prev_close_float,
                            'high_price': float(active_quote.high if hasattr(active_quote, 'high') and active_quote.high else quote.high or 0),
                            'low_price': float(active_quote.low if hasattr(active_quote, 'low') and active_quote.low else quote.low or 0),
                            'volume': int(active_quote.volume or 0),
                            'turnover': float(active_quote.turnover or 0),
                            'bid1_price': current_price,  # 统一使用最新价
                            'ask1_price': current_price,
                            'change_amount': float(change_amount),
                            'change_percent': float(change_percent),
                            'limit_up': 0,
                            'limit_down': 0,
                            'is_suspended': quote.trade_status == 'HALT',  # 交易状态只能从主数据获取
                            'timestamp': int(time.time()),
                            # 添加交易时段信息
                            'trading_session': {
                                'session_type': trading_session['session_type'] if trading_session else 'regular',
                                'description': trading_session['description'] if trading_session else '正常交易时间',
                                'market': market
                            }
                        }
                        results[symbol] = result
                        success_count += 1

                        if success_count <= 3:  # 只记录前3个成功的，避免日志太多
                            logger.info("[长桥API] ✅ 成功获取 %s: 价格=%s", symbol, result['current_price'])
                    else:
                        logger.warning("[长桥API] ❌ 未获取到股票数据: %s (索引=%d)", symbol, i)
                        results[symbol] = None
                        failed_count += 1
                except Exception as e:
                    logger.error("[长桥API] ❌ 处理股票 %s 失败: %s", symbol, str(e))
                    results[symbol] = None
                    failed_count += 1

            logger.info("[长桥API] 批量获取完成:")
            logger.info("[长桥API]   - 总数量: %d", len(symbols))
            logger.info("[长桥API]   - 成功: %d", success_count)
            logger.info("[长桥API]   - 失败: %d", failed_count)

        except Exception as e:
            logger.error("[长桥API] ❌ 批量获取股票报价失败: %s", str(e))
            import traceback
            logger.error("[长桥API] 详细错误:\n%s", traceback.format_exc())
            for symbol in symbols:
                if symbol not in results:
                    results[symbol] = None

        logger.info("[长桥API] 返回结果字典，键数量: %d", len(results))
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
                'sessions': {
                    'regular': '09:30-12:00, 13:00-16:00',
                }
            },
            '美股': {
                'name': '美股市场',
                'trading_hours': '09:30-16:00',
                'timezone': 'America/New_York',
                'currency': 'USD',
                'has_limit': True,  # 美股有涨跌停
                'limit_percent': 0.2,  # 20%涨跌幅限制
                'sessions': {
                    'overnight': '20:00-04:00 (夜盘, 长桥)',
                    'pre_market': '04:00-09:30 (盘前)',
                    'regular': '09:30-16:00 (正常)',
                    'after_hours': '16:00-20:00 (盘后)'
                },
                'longport_features': {
                    'overnight_trading': True,  # 长桥支持夜盘
                    'pre_market_trading': True,
                    'after_hours_trading': True
                }
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
