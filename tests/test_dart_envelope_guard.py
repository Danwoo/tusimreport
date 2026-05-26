"""DARTAPIClient._make_request envelope validation 단위 테스트.

requests 호출은 mock하고, _make_request 내부의 schema gate가 정확히
status 키 미존재/타입 오류를 잡아내는지 검증.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests

from data.dart_api_client import DARTAPIClient


def _mock_response(json_body: object) -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = 200
    resp.ok = True
    resp.json.return_value = json_body
    resp.raise_for_status.return_value = None
    return resp


def _make_client() -> DARTAPIClient:
    """Test용 클라이언트. API 키는 임의값 (request는 mock되므로 영향 없음)."""
    c = DARTAPIClient.__new__(DARTAPIClient)
    c.api_key = "fake"
    c.base_url = "https://opendart.fss.or.kr/api"
    c.session = requests.Session()
    return c


def test_valid_envelope_passes_through(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client()
    monkeypatch.setattr(
        client.session,
        "get",
        lambda *a, **kw: _mock_response({"status": "000", "message": "정상", "corp_name": "x"}),
    )

    result = client._make_request("company.json", {"corp_code": "00126380"})
    assert result["status"] == "000"
    assert result["corp_name"] == "x"


def test_business_error_envelope_passes_through(monkeypatch: pytest.MonkeyPatch) -> None:
    """status가 '013' (조회 결과 없음)이어도 envelope 유효 → 호출자가 status 보고 분기."""
    client = _make_client()
    monkeypatch.setattr(
        client.session,
        "get",
        lambda *a, **kw: _mock_response({"status": "013", "message": "조회된 데이터가 없습니다"}),
    )

    result = client._make_request("fnlttSinglAcnt.json", {"corp_code": "x"})
    assert result["status"] == "013"


def test_missing_status_returns_schema_error_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    """status 키가 사라지면 schema_error envelope로 변환 (raise하지 않음).

    회귀 시나리오: DART가 응답 포맷을 바꿔서 status 키가 다른 이름이 됐을 때
    silent break 대신 명시적 schema_error."""
    client = _make_client()
    monkeypatch.setattr(
        client.session,
        "get",
        lambda *a, **kw: _mock_response({"result": "weird new format"}),
    )

    result = client._make_request("company.json", {"corp_code": "x"})
    assert result["status"] == "schema_error"
    assert "DART/company.json" in result["message"]


def test_network_error_wrapped_in_error_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    """network 실패는 기존대로 status='error' envelope."""
    client = _make_client()

    def boom(*_a, **_kw):
        raise requests.ConnectionError("dns failed")

    monkeypatch.setattr(client.session, "get", boom)

    result = client._make_request("company.json", {"corp_code": "x"})
    assert result["status"] == "error"
    assert "dns" in result["message"]
