"""Financial ingestion route tests without relying on live external providers."""

from app.models.entities import Instrument
from app.core.security import hash_password


def analyst_token(client) -> str:
    client.post(
        "/api/v1/auth/register",
        json={"email": "data.analyst@example.com", "full_name": "Data Analyst", "password": "A-strong-password-2026"},
    )
    return client.post(
        "/api/v1/auth/login",
        data={"username": "data.analyst@example.com", "password": "A-strong-password-2026"},
    ).json()["access_token"]


def test_market_snapshot_manifest_and_audit_are_persisted(client, db_session, monkeypatch, tmp_path) -> None:
    from app.api.v1 import data as data_api

    db_session.add(Instrument(symbol="MSFT", name="Microsoft Corporation", exchange="NASDAQ"))
    db_session.commit()
    monkeypatch.setattr(
        data_api,
        "persist_market_snapshot",
        lambda **kwargs: (str(tmp_path / "msft-test.parquet"), "a" * 64, {"row_count": 2}, "b" * 64),
    )
    token = analyst_token(client)
    response = client.post(
        "/api/v1/data/ingestions/market",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "symbol": "msft",
            "provider_key": "manual_upload",
            "interval": "1d",
            "adjustment_policy": "split_and_dividend_adjusted",
            "rows": [
                {"date": "2025-01-02", "open": 100, "high": 105, "low": 99, "close": 103, "volume": 1000},
                {"date": "2025-01-03", "open": 103, "high": 106, "low": 102, "close": 105, "volume": 1200},
            ],
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["instrument_symbol"] == "MSFT"
    assert payload["row_count"] == 2
    assert payload["sha256"] == "a" * 64
    assert payload["storage_format"] == "parquet"
    assert payload["manifest"]["row_count"] == 2


def test_market_ingestion_rejects_invalid_ohlc(client) -> None:
    token = analyst_token(client)
    response = client.post(
        "/api/v1/data/ingestions/market",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "symbol": "MSFT",
            "rows": [{"date": "2025-01-02", "open": 100, "high": 98, "low": 99, "close": 101, "volume": 10}],
        },
    )
    assert response.status_code == 422


def test_sec_ingestion_persists_company_metadata(client, db_session, monkeypatch) -> None:
    from app.api.v1 import data as data_api

    class FakeSECClient:
        def __init__(self, user_agent: str):
            self.user_agent = user_agent

        async def fetch_company_submissions(self, cik: str):
            return {
                "cik": cik,
                "name": "Example Public Company",
                "filings": {"recent": {"accessionNumber": ["0001", "0002"]}},
            }

    monkeypatch.setattr(data_api, "SECEdgarClient", FakeSECClient)
    token = analyst_token(client)
    response = client.post(
        "/api/v1/data/ingestions/sec/1234", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["cik"] == "0000001234"
    assert payload["company_name"] == "Example Public Company"
    assert payload["filings_count"] == 2


def test_market_snapshot_writer_creates_content_hashed_parquet(tmp_path, monkeypatch) -> None:
    import hashlib

    import pandas as pd
    import pytest

    pytest.importorskip("pyarrow")
    from app.core.config import get_settings
    from app.schemas.ingestion import MarketBar
    from app.services.market_data import persist_market_snapshot

    original = get_settings()
    monkeypatch.setattr(original, "data_storage_path", str(tmp_path))
    monkeypatch.setattr("app.services.market_data.get_settings", lambda: original)
    path, digest, manifest, content_id = persist_market_snapshot(
        symbol="MSFT",
        provider_key="manual_upload",
        interval="1d",
        adjustment_policy="provider_defined",
        rows=[
            MarketBar(date="2025-01-02", open=100, high=105, low=99, close=103, volume=1000),
            MarketBar(date="2025-01-03", open=103, high=106, low=102, close=105, volume=1200),
        ],
    )
    from pathlib import Path

    data = Path(path).read_bytes()
    assert Path(path).suffix == ".parquet"
    assert hashlib.sha256(data).hexdigest() == digest
    assert manifest["sha256"] == digest
    assert manifest["row_count"] == 2
    assert content_id
    assert len(pd.read_parquet(path)) == 2


def test_market_csv_ingestion_creates_snapshot(client, db_session, monkeypatch, tmp_path) -> None:
    from app.api.v1 import data as data_api

    db_session.add(Instrument(symbol="AAPL", name="Apple Inc.", exchange="NASDAQ"))
    db_session.commit()
    monkeypatch.setattr(
        data_api,
        "persist_market_snapshot",
        lambda **kwargs: (str(tmp_path / "aapl-test.parquet"), "c" * 64, {"row_count": 2}, "d" * 64),
    )
    token = analyst_token(client)
    csv_bytes = (
        "date,open,high,low,close,volume\n"
        "2025-02-03,100,105,99,104,1100\n"
        "2025-02-04,104,108,103,107,1500\n"
    ).encode()
    response = client.post(
        "/api/v1/data/ingestions/market/csv",
        headers={"Authorization": f"Bearer {token}"},
        data={"symbol": "AAPL", "interval": "1d", "adjustment_policy": "provider_defined"},
        files={"file": ("aapl.csv", csv_bytes, "text/csv")},
    )
    assert response.status_code == 201, response.text
    assert response.json()["instrument_symbol"] == "AAPL"
    assert response.json()["row_count"] == 2


def test_market_csv_requires_required_columns(client) -> None:
    token = analyst_token(client)
    response = client.post(
        "/api/v1/data/ingestions/market/csv",
        headers={"Authorization": f"Bearer {token}"},
        data={"symbol": "AAPL"},
        files={"file": ("bad.csv", b"date,close\n2025-02-03,100\n", "text/csv")},
    )
    assert response.status_code == 422
    assert "Missing CSV columns" in response.text
