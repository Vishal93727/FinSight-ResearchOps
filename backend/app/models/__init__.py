"""Compatibility export for the canonical FinSight ORM model registry."""
from finsight.infrastructure.database.models import AuditEvent, DataProvider, DataSnapshot, Instrument, JobRecord, Role, SECCompanyRecord, User

__all__ = ["AuditEvent", "DataProvider", "DataSnapshot", "Instrument", "JobRecord", "Role", "SECCompanyRecord", "User"]
