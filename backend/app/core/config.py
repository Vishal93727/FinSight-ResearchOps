"""Compatibility import; canonical settings live in finsight.core.config."""
import sys
from finsight.core import config as _implementation
sys.modules[__name__] = _implementation
