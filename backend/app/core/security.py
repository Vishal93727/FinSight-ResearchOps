"""Compatibility import; canonical security lives in finsight.core.security."""
import sys
from finsight.core import security as _implementation
sys.modules[__name__] = _implementation
