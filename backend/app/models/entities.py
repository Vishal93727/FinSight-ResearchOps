"""Compatibility import; ORM models live in their domain and infrastructure packages."""
import sys
from finsight.infrastructure.database import models as _implementation
sys.modules[__name__] = _implementation
