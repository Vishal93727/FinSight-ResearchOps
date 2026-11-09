"""Compatibility import; SEC EDGAR provider lives in finsight.market_data.providers."""
import sys
from finsight.market_data.providers import sec_edgar as _implementation
sys.modules[__name__] = _implementation
