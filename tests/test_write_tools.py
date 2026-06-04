"""
Tests for the Phase 3 write tools in server.py.

We avoid extra test deps: respx is NOT installed, and neither is
pytest-asyncio / anyio. So we mock the network with httpx.MockTransport and
drive the async helpers/tools with asyncio.run(...) inside plain sync tests.

The seam: _http_get / _http_post accept an optional `transport=` kwarg that is
forwarded to httpx.AsyncClient(transport=...). Default None == production
behavior unchanged (a real network client is built). The MCP tool functions
keep clean public signatures (no transport arg leaking into the tool schema);
their tests inject the mock transport by monkeypatching the relevant helper
with a thin wrapper that forces transport=.
"""

import asyncio
import functools
import json
from typing import Any, Dict, List

import httpx
import pytest

import server


def _run(coro):
    return asyncio.run(coro)


class _Recorder:
    """Captures the outgoing request(s) and returns a canned JSON response."""

    def __init__(self, status_code: int = 200, payload: Dict[str, Any] | None = None):
        self.status_code = status_code
        self.payload = payload if payload is not None else {"success": True, "data": {"ok": True}}
        self.requests: List[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status_code, json=self.payload)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]

    def last_body(self) -> Dict[str, Any]:
        return json.loads(self.last.content.decode())

    @staticmethod
    def header_names(request: httpx.Request) -> set:
        return {k.lower() for k in request.headers.keys()}


def _patch_post(monkeypatch, rec: "_Recorder"):
    """Force server._http_post to run against rec's MockTransport."""
    real = server._http_post

    @functools.wraps(real)
    async def wrapper(path, body, api_key=None):
        return await real(path, body, api_key=api_key, transport=rec.transport)

    monkeypatch.setattr(server, "_http_post", wrapper)


# ---------------------------------------------------------------------------
# 3.1 — _http_post auth header
# ---------------------------------------------------------------------------


def test_http_post_no_auth_header_by_default():
    rec = _Recorder()
    _run(server._http_post("/quote-request", {"a": 1}, transport=rec.transport))
    assert "authorization" not in rec.header_names(rec.last)


def test_http_post_adds_bearer_when_api_key_passed():
    rec = _Recorder()
    _run(server._http_post("/bookings", {"a": 1}, api_key="ta_live_abc123", transport=rec.transport))
    assert rec.last.headers["Authorization"] == "Bearer ta_live_abc123"


# ---------------------------------------------------------------------------
# 3.2 — submit_quote_request
# ---------------------------------------------------------------------------


def test_submit_quote_request_posts_required_fields_only(monkeypatch):
    rec = _Recorder(payload={"success": True, "data": {"lead_id": 42}})
    _patch_post(monkeypatch, rec)

    result = _run(
        server.tintatlanta_submit_quote_request(
            first_name="Jane",
            phone="404-555-0100",
            email="jane@example.com",
            service_type="residential",
        )
    )

    assert rec.last.method == "POST"
    assert str(rec.last.url).endswith("/quote-request")
    body = rec.last_body()
    assert body == {
        "first_name": "Jane",
        "phone": "404-555-0100",
        "email": "jane@example.com",
        "service_type": "residential",
    }
    assert "authorization" not in rec.header_names(rec.last)
    assert result == {"lead_id": 42}


def test_submit_quote_request_includes_only_provided_optionals(monkeypatch):
    rec = _Recorder()
    _patch_post(monkeypatch, rec)

    _run(
        server.tintatlanta_submit_quote_request(
            first_name="Jane",
            phone="404-555-0100",
            email="jane@example.com",
            service_type="commercial",
            company_name="Acme",
            square_footage=1200.5,
            window_count=40,
            needs_ladder=True,
        )
    )

    body = rec.last_body()
    assert body["company_name"] == "Acme"
    assert body["square_footage"] == 1200.5
    assert body["window_count"] == 40
    assert body["needs_ladder"] is True
    for absent in ("last_name", "property_info", "message", "building_type", "floors"):
        assert absent not in body


# ---------------------------------------------------------------------------
# 3.3 — register_api_key
# ---------------------------------------------------------------------------


def test_register_api_key_posts_required_fields(monkeypatch):
    rec = _Recorder(payload={"success": True, "data": {"api_key": "ta_live_deadbeef"}})
    _patch_post(monkeypatch, rec)

    result = _run(
        server.tintatlanta_register_api_key(
            name="Angela Agent",
            email="agent@example.com",
            use_case="booking on behalf of customers",
        )
    )

    assert rec.last.method == "POST"
    assert str(rec.last.url).endswith("/register")
    body = rec.last_body()
    assert body == {
        "name": "Angela Agent",
        "email": "agent@example.com",
        "use_case": "booking on behalf of customers",
    }
    assert "authorization" not in rec.header_names(rec.last)
    assert result == {"api_key": "ta_live_deadbeef"}


# ---------------------------------------------------------------------------
# 3.4 — book_appointment forwards Bearer
# ---------------------------------------------------------------------------


def test_book_appointment_forwards_bearer_and_required_fields(monkeypatch):
    rec = _Recorder(payload={"success": True, "data": {"booking_id": "bk_1"}})
    _patch_post(monkeypatch, rec)

    result = _run(
        server.tintatlanta_book_appointment(
            api_key="ta_live_xyz",
            date="2026-06-10",
            time="10:00",
            customer_name="Bob",
            customer_phone="404-555-0199",
            customer_email="bob@example.com",
        )
    )

    assert rec.last.method == "POST"
    assert str(rec.last.url).endswith("/bookings")
    assert rec.last.headers["Authorization"] == "Bearer ta_live_xyz"
    body = rec.last_body()
    assert body["date"] == "2026-06-10"
    assert body["time"] == "10:00"
    assert body["customer_name"] == "Bob"
    assert body["customer_phone"] == "404-555-0199"
    assert body["customer_email"] == "bob@example.com"
    assert body["service_type"] == "automotive"  # default
    # api_key is a transport-level concern; must not leak into the JSON body
    assert "api_key" not in body
    assert result == {"booking_id": "bk_1"}


def test_book_appointment_includes_only_provided_vehicle_optionals(monkeypatch):
    rec = _Recorder()
    _patch_post(monkeypatch, rec)

    _run(
        server.tintatlanta_book_appointment(
            api_key="ta_live_xyz",
            date="2026-06-10",
            time="10:00",
            customer_name="Bob",
            customer_phone="404-555-0199",
            customer_email="bob@example.com",
            vehicle_year=2026,
            vehicle_make="Tesla",
            vehicle_model="Model Y",
        )
    )

    body = rec.last_body()
    assert body["vehicle_year"] == 2026
    assert body["vehicle_make"] == "Tesla"
    assert body["vehicle_model"] == "Model Y"
    for absent in ("vehicle_type", "coverage", "film_type", "special_requests"):
        assert absent not in body


# ---------------------------------------------------------------------------
# Error path — friendly-strict 400 surfaces via _unwrap as a clean RuntimeError
# ---------------------------------------------------------------------------


def test_friendly_strict_error_raises_runtimeerror(monkeypatch):
    rec = _Recorder(
        status_code=400,
        payload={
            "success": False,
            "error_code": "MISSING_FIELDS",
            "message": "phone is required",
            "missing_fields": ["phone"],
        },
    )
    _patch_post(monkeypatch, rec)

    with pytest.raises(RuntimeError) as exc:
        _run(
            server.tintatlanta_submit_quote_request(
                first_name="Jane",
                phone="",
                email="jane@example.com",
                service_type="residential",
            )
        )

    msg = str(exc.value)
    assert "MISSING_FIELDS" in msg
    assert "phone is required" in msg
    assert "Missing fields" in msg
