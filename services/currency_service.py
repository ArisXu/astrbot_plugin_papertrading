"""汇率服务 - 支持港股和美股交易的货币转换"""
from typing import Dict, Optional
from ..utils.data_storage import DataStorage


class CurrencyService:
    """汇率服务"""

    def __init__(self, storage: DataStorage):
        self.storage = storage

    def get_exchange_rate(self, from_currency: str, to_currency: str = "CNY") -> float:
        """
        获取汇率

        Args:
            from_currency: 源货币 (HKD, USD)
            to_currency: 目标货币 (CNY，默认人民币)

        Returns:
            汇率（1单位源货币等于多少目标货币）
        """
        from_currency = from_currency.upper()
        to_currency = to_currency.upper()

        # 如果是同一种货币，汇率为1
        if from_currency == to_currency:
            return 1.0

        # 港币转人民币
        if from_currency == "HKD" and to_currency == "CNY":
            rate = self.storage.get_plugin_config_value('hkd_to_cny_rate', 0.9200)
            rate = float(rate) if rate is not None else 0.9200
            return max(rate, 0.0001)  # 防止为0

        # 美元转人民币
        if from_currency == "USD" and to_currency == "CNY":
            rate = self.storage.get_plugin_config_value('usd_to_cny_rate', 7.2000)
            rate = float(rate) if rate is not None else 7.2000
            return max(rate, 0.0001)  # 防止为0

        # 人民币转港币
        if from_currency == "CNY" and to_currency == "HKD":
            hkd_rate = self.storage.get_plugin_config_value('hkd_to_cny_rate', 0.9200)
            hkd_rate = float(hkd_rate) if hkd_rate is not None else 0.9200
            if hkd_rate <= 0:
                hkd_rate = 0.9200  # 使用默认值
            return 1.0 / hkd_rate

        # 人民币转美元
        if from_currency == "CNY" and to_currency == "USD":
            usd_rate = self.storage.get_plugin_config_value('usd_to_cny_rate', 7.2000)
            usd_rate = float(usd_rate) if usd_rate is not None else 7.2000
            if usd_rate <= 0:
                usd_rate = 7.2000  # 使用默认值
            return 1.0 / usd_rate

        # 不支持的货币对
        return 1.0

    def convert_amount(self, amount: float, from_currency: str, to_currency: str = "CNY") -> float:
        """
        转换金额

        Args:
            amount: 金额
            from_currency: 源货币
            to_currency: 目标货币

        Returns:
            转换后的金额
        """
        rate = self.get_exchange_rate(from_currency, to_currency)
        return amount * rate

    def get_currency_by_market(self, market: str) -> str:
        """
        根据市场类型获取货币单位

        Args:
            market: 市场类型 ('A', 'HK', 'US')

        Returns:
            货币单位 ('CNY', 'HKD', 'USD')
        """
        currency_mapping = {
            'A': 'CNY',   # A股使用人民币
            'HK': 'HKD',  # 港股使用港币
            'US': 'USD'   # 美股使用美元
        }
        return currency_mapping.get(market.upper(), 'CNY')

    def convert_to_cny(self, amount: float, market: str) -> float:
        """
        将指定市场的金额转换为人民币

        Args:
            amount: 金额
            market: 市场类型

        Returns:
            对应的人民币金额
        """
        currency = self.get_currency_by_market(market)
        return self.convert_amount(amount, currency, 'CNY')

    def format_currency(self, amount: float, currency: str) -> str:
        """
        格式化货币显示

        Args:
            amount: 金额
            currency: 货币单位

        Returns:
            格式化的货币字符串
        """
        currency_symbols = {
            'CNY': '¥',
            'HKD': 'HK$',
            'USD': '$'
        }

        symbol = currency_symbols.get(currency.upper(), currency.upper())

        # 根据金额大小选择小数位数
        if amount >= 10000:
            # 大于等于1万，使用0位小数
            return f"{symbol}{amount:,.0f}"
        elif amount >= 1:
            # 大于等于1，使用2位小数
            return f"{symbol}{amount:,.2f}"
        else:
            # 小于1，使用4位小数
            return f"{symbol}{amount:,.4f}"

    def format_cny_with_currency(self, amount: float, market: str) -> str:
        """
        格式化货币显示（根据市场类型）

        Args:
            amount: 金额
            market: 市场类型

        Returns:
            格式化的货币字符串
        """
        currency = self.get_currency_by_market(market)
        return self.format_currency(amount, currency)


# 全局汇率服务实例
_currency_instance = None

def get_currency_service(storage: DataStorage) -> CurrencyService:
    """获取汇率服务实例"""
    global _currency_instance
    if _currency_instance is None:
        _currency_instance = CurrencyService(storage)
    return _currency_instance
