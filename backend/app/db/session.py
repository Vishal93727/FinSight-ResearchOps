"""Compatibility import; canonical database session lives in finsight.infrastructure.database."""
import sys
from finsight.infrastructure.database import session as _implementation
sys.modules[__name__] = _implementation
