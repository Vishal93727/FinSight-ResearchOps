"""Compatibility import; market-data contracts live in finsight.market_data.contracts."""
import sys
from finsight.market_data.contracts import ingestion as _implementation
sys.modules[__name__] = _implementation
