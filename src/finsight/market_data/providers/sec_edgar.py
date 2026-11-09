"""Narrow SEC EDGAR submissions adapter. SEC content is treated as untrusted data."""

from typing import Any

import httpx


class SECEdgarClient:
    BASE_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

    def __init__(self, user_agent: str, timeout_seconds: float = 20.0) -> None:
        if not user_agent.strip() or "example.com" in user_agent.lower() or "yourdomain" in user_agent.lower():
            raise ValueError("Configure SEC_EDGAR_USER_AGENT with a monitored contact address")
        self.headers = {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}
        self.timeout_seconds = timeout_seconds

    async def fetch_company_submissions(self, cik: str) -> dict[str, Any]:
        normalized_cik = cik.strip().zfill(10)
        if not normalized_cik.isdigit() or len(normalized_cik) != 10:
            raise ValueError("CIK must be a numeric value of at most 10 digits")
        async with httpx.AsyncClient(timeout=self.timeout_seconds, headers=self.headers) as client:
            response = await client.get(self.BASE_URL.format(cik=normalized_cik))
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict) or not payload.get("name"):
            raise ValueError("SEC returned an unexpected company submissions payload")
        return payload
