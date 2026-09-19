"""ZurixAI API Client — CLI → Engine communication."""

from __future__ import annotations

import json
from pathlib import Path

import httpx


class ZurixAPIClient:
    """Client for communicating with the ZurixAI Engine API."""

    def __init__(self, engine_url: str = "http://localhost:8000", api_key: str = ""):
        self.engine_url = engine_url.rstrip("/")
        self.api_key = api_key
        self._token: str | None = None

    def _headers(self) -> dict[str, str]:
        """Build request headers with auth."""
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        elif self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def health(self) -> dict:
        """Check engine health."""
        try:
            resp = httpx.get(f"{self.engine_url}/health", timeout=5.0)
            return resp.json()
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def authenticate(self) -> bool:
        """Exchange API key for JWT token."""
        if not self.api_key:
            return False
        try:
            resp = httpx.post(
                f"{self.engine_url}/api/v1/auth/token",
                json={"api_key": self.api_key},
                timeout=10.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                self._token = data.get("token")
                return True
        except Exception:
            pass
        return False

    def validate_key(self) -> dict:
        """Validate the current API key."""
        try:
            resp = httpx.post(
                f"{self.engine_url}/api/v1/auth/validate",
                headers=self._headers(),
                timeout=10.0,
            )
            return resp.json()
        except Exception as e:
            return {"valid": False, "error": str(e)}

    def generate_patch(self, file_path: str, diff_content: str, context: str = "") -> dict:
        """Request a patch from the engine."""
        try:
            resp = httpx.post(
                f"{self.engine_url}/api/v1/patch/generate",
                headers=self._headers(),
                json={
                    "file_path": file_path,
                    "diff_content": diff_content,
                    "project_context": context,
                },
                timeout=30.0,
            )
            return resp.json()
        except Exception as e:
            return {"error": str(e)}

    def generate_test(self, file_path: str, function_name: str, language: str = "python") -> dict:
        """Request a test from the engine."""
        try:
            resp = httpx.post(
                f"{self.engine_url}/api/v1/test/generate",
                headers=self._headers(),
                json={
                    "file_path": file_path,
                    "function_name": function_name,
                    "language": language,
                },
                timeout=30.0,
            )
            return resp.json()
        except Exception as e:
            return {"error": str(e)}

    def analyze_bug(self, stack_trace: str, error_type: str = "", language: str = "python") -> dict:
        """Request bug analysis from the engine."""
        try:
            resp = httpx.post(
                f"{self.engine_url}/api/v1/bug/analyze",
                headers=self._headers(),
                json={
                    "stack_trace": stack_trace,
                    "error_type": error_type,
                    "language": language,
                },
                timeout=30.0,
            )
            return resp.json()
        except Exception as e:
            return {"error": str(e)}

    def get_pricing(self, task_type: str, plan: str = "free") -> dict:
        """Get pricing info for a task."""
        try:
            resp = httpx.post(
                f"{self.engine_url}/api/v1/pricing/calculate",
                headers=self._headers(),
                json={"task_type": task_type, "plan": plan},
                timeout=10.0,
            )
            return resp.json()
        except Exception as e:
            return {"error": str(e)}

    def log_audit(self, event_type: str, details: dict = None) -> dict:
        """Log an audit event."""
        try:
            resp = httpx.post(
                f"{self.engine_url}/api/v1/audit/log",
                headers=self._headers(),
                json={"event_type": event_type, "details": details or {}},
                timeout=10.0,
            )
            return resp.json()
        except Exception as e:
            return {"error": str(e)}
