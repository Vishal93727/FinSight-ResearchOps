"""Deterministic experiment configuration serialization and content hashing."""
import hashlib
import json
from pydantic import BaseModel


def canonical_json(value: BaseModel | dict) -> str:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def configuration_sha256(value: BaseModel | dict) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
