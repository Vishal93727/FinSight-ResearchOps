"""Compatibility import; shared response primitives live in finsight.core.schemas."""
import sys
from finsight.core import schemas as _implementation
sys.modules[__name__] = _implementation
