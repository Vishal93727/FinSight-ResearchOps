"""Compatibility import; ingestion implementation lives in finsight.market_data.ingestion."""
import sys
from finsight.market_data.ingestion import service as _implementation
sys.modules[__name__] = _implementation
