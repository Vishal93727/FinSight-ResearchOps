"""Compatibility import; canonical SQLAlchemy base lives in finsight.infrastructure.database."""
import sys
from finsight.infrastructure.database import base as _implementation
sys.modules[__name__] = _implementation
