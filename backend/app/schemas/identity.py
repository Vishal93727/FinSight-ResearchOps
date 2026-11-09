"""Compatibility import; identity contracts live in finsight.identity.contracts."""
import sys
from finsight.identity import contracts as _implementation
sys.modules[__name__] = _implementation
