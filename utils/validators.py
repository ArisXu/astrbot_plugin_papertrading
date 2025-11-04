"""数据验证工具"""
import re
from typing import Optional


class Validators:
    """数据验证器"""

    @staticmethod
    def is_valid_stock_code(code: str) -> bool:
        """验证股票代码格式（支持A股、港股、美股）"""
        if not code or not isinstance(code, str):
            return False

        # 去除前后空格并转换为大写
        code = code.strip().upper()

        # 检查是否已经是完整格式（带市场后缀）
        if '.HK' in code or '.US' in code or '.A' in code:
            # 完整格式验证
            if '.HK' in code:
                # 港股: 数字.HK
                base_code = code.split('.')[0]
                return len(base_code) >= 4 and len(base_code) <= 5 and base_code.isdigit()
            elif '.US' in code:
                # 美股: 字母.US
                base_code = code.split('.')[0]
                return 1 <= len(base_code) <= 5 and base_code.replace('.', '').isalpha()
            elif '.A' in code:
                # A股: 数字.A
                base_code = code.split('.')[0]
                return re.match(r'^(00|30|60|68|43|83|87)\d{4}$', base_code)

        # A股股票代码格式: 6位数字
        # 上海A股: 60xxxx, 68xxxx
        # 深圳A股: 00xxxx, 30xxxx (创业板)
        # 北交所: 43xxxx, 83xxxx, 87xxxx
        a_stock_pattern = r'^(00|30|60|68|43|83|87)\d{4}$'
        if re.match(a_stock_pattern, code):
            # 排除指数代码（不允许交易指数）
            index_codes = {
                '399001',  # 深证成指
                '399005',  # 中小100/中小板
                '399006',  # 创业板指
            }
            return code not in index_codes

        # 港股：通常4-5位数字
        if code.isdigit() and 4 <= len(code) <= 5:
            return True

        # 美股：1-5个大写字母
        if code.isalpha() and 1 <= len(code) <= 5:
            return True

        return False
    
    @staticmethod
    def normalize_stock_code(code: str) -> Optional[str]:
        """标准化股票代码（仅对A股有效）"""
        if not code or not isinstance(code, str):
            return None

        code = code.strip().upper()

        # 只对A股进行标准化（因为A股的验证规则更严格）
        a_stock_pattern = r'^(00|30|60|68|43|83|87)\d{4}$'
        if re.match(a_stock_pattern, code):
            # 排除指数代码
            index_codes = {'399001', '399005', '399006'}
            if code in index_codes:
                return None
            return code

        # 港股和美股在StockDataService中处理标准化
        return code
    
    @staticmethod
    def is_valid_price(price: float) -> bool:
        """验证价格是否有效"""
        return price > 0 and price < 10000  # 假设股价不会超过10000元
    
    @staticmethod
    def is_valid_volume(volume: int) -> bool:
        """验证交易数量是否有效"""
        # A股最小交易单位是100股（1手）
        return volume > 0 and volume % 100 == 0
    
    @staticmethod
    def is_valid_amount(amount: float) -> bool:
        """验证交易金额是否有效"""
        return amount > 0 and amount < 100000000  # 不超过1亿
    
    @staticmethod
    def is_valid_user_id(user_id: str) -> bool:
        """验证用户ID格式"""
        return bool(user_id and isinstance(user_id, str) and len(user_id.strip()) > 0)
    
    @staticmethod
    def format_stock_code_with_exchange(code: str) -> Optional[str]:
        """为股票代码添加交易所前缀（akshare需要）"""
        code = Validators.normalize_stock_code(code)
        if not code:
            return None
        
        # 根据代码判断交易所
        if code.startswith(('60', '68')):
            return f'sh{code}'  # 上海证券交易所
        elif code.startswith(('00', '30')):
            return f'sz{code}'  # 深圳证券交易所
        elif code.startswith(('43', '83', '87')):
            return f'bj{code}'  # 北京证券交易所
        else:
            return None
    
    @staticmethod
    def parse_order_params(params: list) -> dict:
        """解析订单参数"""
        result = {
            'stock_code': None,
            'volume': None,
            'price': None,
            'is_market_order': True,
            'error': None
        }
        
        if len(params) < 2:
            result['error'] = "参数不足，至少需要股票代码和数量"
            return result
        
        # 解析股票代码
        stock_code = Validators.normalize_stock_code(params[0])
        if not stock_code:
            result['error'] = f"无效的股票代码: {params[0]}"
            return result
        result['stock_code'] = stock_code
        
        # 解析数量
        try:
            volume = int(params[1])
            if not Validators.is_valid_volume(volume):
                result['error'] = f"无效的交易数量: {volume}，必须是100的倍数"
                return result
            result['volume'] = volume
        except ValueError:
            result['error'] = f"无效的数量格式: {params[1]}"
            return result
        
        # 解析价格（可选）
        if len(params) >= 3:
            try:
                price = float(params[2])
                if not Validators.is_valid_price(price):
                    result['error'] = f"无效的价格: {price}"
                    return result
                result['price'] = price
                result['is_market_order'] = False
            except ValueError:
                result['error'] = f"无效的价格格式: {params[2]}"
                return result
        
        return result
    
    @staticmethod
    def validate_order_amount(volume: int, price: float, min_amount: float = 100) -> bool:
        """验证订单金额是否满足最小要求"""
        total_amount = volume * price
        return total_amount >= min_amount
