"""BaseAPIClient.request_json: HTTP status → 도메인 예외 매핑.

requests.Session을 monkeypatch하지 않고도, urllib3 Retry 정책이 거치는
실제 동작과 같은 경로로 4xx/5xx가 도메인 예외로 변환되는지 검증한다.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from core.errors import (
    AuthenticationError,
    DataSourceUnavailableError,
    RateLimitError,
)
from data.base_client import BaseAPIClient


def _mock_response(status_code: int, json_body: object | None = None, text: str = "") -> MagicMock:
    """requests.Response를 닮은 MagicMock. ok는 status_code로 결정."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.ok = 200 <= status_code < 400
    resp.text = text
    if json_body is not None:
        resp.json.return_value = json_body
    else:
        resp.json.side_effect = ValueError("no body")
    return resp


class TestRequestJsonStatusMapping:
    def test_2xx_returns_decoded_json(self):
        client = BaseAPIClient()
        with patch.object(client.session, "request", return_value=_mock_response(200, {"k": 1})):
            assert client.request_json("GET", "https://example.com") == {"k": 1}

    def test_401_raises_authentication_error(self):
        client = BaseAPIClient()
        with (
            patch.object(client.session, "request", return_value=_mock_response(401)),
            pytest.raises(AuthenticationError),
        ):
            client.request_json("GET", "https://example.com")

    def test_403_raises_authentication_error(self):
        client = BaseAPIClient()
        with (
            patch.object(client.session, "request", return_value=_mock_response(403)),
            pytest.raises(AuthenticationError),
        ):
            client.request_json("GET", "https://example.com")

    def test_429_raises_rate_limit_error(self):
        client = BaseAPIClient()
        with (
            patch.object(client.session, "request", return_value=_mock_response(429)),
            pytest.raises(RateLimitError),
        ):
            client.request_json("GET", "https://example.com")

    def test_5xx_raises_unavailable_error(self):
        client = BaseAPIClient()
        with (
            patch.object(client.session, "request", return_value=_mock_response(503)),
            pytest.raises(DataSourceUnavailableError),
        ):
            client.request_json("GET", "https://example.com")

    def test_connection_error_wrapped_as_unavailable(self):
        client = BaseAPIClient()
        with (
            patch.object(client.session, "request", side_effect=requests.ConnectionError("dns fail")),
            pytest.raises(DataSourceUnavailableError),
        ):
            client.request_json("GET", "https://example.com")

    def test_timeout_wrapped_as_unavailable(self):
        client = BaseAPIClient()
        with (
            patch.object(client.session, "request", side_effect=requests.Timeout("slow")),
            pytest.raises(DataSourceUnavailableError),
        ):
            client.request_json("GET", "https://example.com")

    def test_non_json_response_wrapped_as_unavailable(self):
        client = BaseAPIClient()
        # 200인데 본문이 JSON 아님 (예: 이상한 HTML 에러 페이지)
        with (
            patch.object(
                client.session, "request", return_value=_mock_response(200, text="<html>oops</html>")
            ),
            pytest.raises(DataSourceUnavailableError),
        ):
            client.request_json("GET", "https://example.com")


class TestRetryPolicyMounted:
    """urllib3 Retry가 두 어댑터(http/https)에 모두 mount됐는지 확인."""

    def test_both_adapters_mounted_with_retry(self):
        client = BaseAPIClient()
        for prefix in ("http://", "https://"):
            adapter = client.session.get_adapter(prefix + "example.com")
            assert adapter.max_retries.total == BaseAPIClient.RETRY_TOTAL
            assert set(adapter.max_retries.status_forcelist) == set(BaseAPIClient.RETRY_STATUS)
