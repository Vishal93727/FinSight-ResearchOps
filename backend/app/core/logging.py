"""Compatibility import; canonical logging lives in finsight.core.logging."""
import sys
from finsight.core import logging as _implementation
sys.modules[__name__] = _implementation
