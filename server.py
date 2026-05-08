"""
Tint Atlanta MCP Server — wraps https://tintatlanta.com/api/v1 as MCP tools.

LocalGEO Phase 2 Layer 3 (tool execution layer of the protocol stack).
One MCP server reaches three runtimes: Claude.ai (native), ChatGPT (Apps SDK
is built on MCP), Perplexity (custom remote connectors).

Transport: Streamable HTTP for remote use (Railway-deployed). Stateless JSON
per recommended pattern in the MCP spec.

Tonight's scope (v0.1):
  - tintatlanta_list_services       (GET /api/v1/services)
  - tintatlanta_business_location   (GET /api/v1/location)
  - tintatlanta_list_faq            (GET /api/v1/faq)
  - tintatlanta_get_estimate        (POST /api/v1/estimates)

Roadmapped for v0.2 (multi-session):
  - tintatlanta_check_availability
  - tintatlanta_flat_glass_estimate
  - tintatlanta_submit_quote_request   (side_effect=creates_lead, consent gate)
  - tintatlanta_register_api_key
  - tintatlanta_book_appointment       (side_effect=books_appointment + charges_deposit, consent gate, requires API key)

The upstream API itself is documented at:
  - https://tintatlanta.com/api/v1/capabilities  (canonical capability manifest)
  - https://tintatlanta.com/api/v1/docs-md       (Markdown agent docs)
  - https://tintatlanta.com/.well-known/openapi.json
"""

import os
from typing import Any, Dict, List, Optional

import httpx
from mcp.server.fastmcp import FastMCP

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

# UPSTREAM_URL points to the Railway proxy by default (which itself rewrites
# the User-Agent and forwards to https://tintatlanta.com/api/v1). The proxy
# bypasses Hostgator's mod_security UA-blocking. Override via env var.
UPSTREAM_URL = os.environ.get(
    "UPSTREAM_URL",
    "https://inspiring-tenderness-production.up.railway.app",
)
SERVER_USER_AGENT = "TintAtlanta-MCP/0.1.0"
HTTP_TIMEOUT_SECONDS = 30.0

# -----------------------------------------------------------------------------
# Server initialization
# -----------------------------------------------------------------------------

mcp = FastMCP("tintatlanta_mcp")


# -----------------------------------------------------------------------------
# Shared HTTP client + error helpers
# -----------------------------------------------------------------------------


async def _http_get(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """GET helper. Returns the parsed JSON body or raises a clean error."""
    url = f"{UPSTREAM_URL.rstrip('/')}{path}"
    headers = {
        "Accept": "application/json",
        "User-Agent": SERVER_USER_AGENT,
    }
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        resp = await client.get(url, headers=headers, params=params)
    return _unwrap(resp, url)


async def _http_post(path: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """POST helper for endpoints that take a JSON body."""
    url = f"{UPSTREAM_URL.rstrip('/')}{path}"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": SERVER_USER_AGENT,
    }
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        resp = await client.post(url, headers=headers, json=body)
    return _unwrap(resp, url)


def _unwrap(resp: httpx.Response, url: str) -> Dict[str, Any]:
    """
    Decode the upstream response. The upstream API uses the friendly-strict
    error shape {success, error_code, message, recoverable, ...} so we surface
    actionable messages back to the MCP client when something goes wrong.
    """
    try:
        body = resp.json()
    except ValueError:
        raise RuntimeError(
            f"Upstream {url} returned non-JSON (status {resp.status_code}). "
            f"First 200 chars: {resp.text[:200]!r}"
        )

    if resp.status_code >= 400 or body.get("success") is False:
        code = body.get("error_code", f"HTTP_{resp.status_code}")
        msg = body.get("message") or body.get("error") or "Unknown error"
        # Fold actionable hints into the exception message so the MCP client
        # surfaces them to the agent runtime.
        hint_parts: List[str] = []
        if body.get("agent_instruction"):
            hint_parts.append(body["agent_instruction"])
        if body.get("usage", {}).get("sample_request"):
            hint_parts.append(f"Sample request: {body['usage']['sample_request']}")
        if body.get("missing_fields"):
            hint_parts.append(f"Missing fields: {body['missing_fields']}")
        hint = (" | " + " | ".join(hint_parts)) if hint_parts else ""
        raise RuntimeError(f"[{code}] {msg}{hint}")

    # Conform to the api_v1 envelope: {success: true, data: {...}, next_actions: [...]}
    return body.get("data", body)


# -----------------------------------------------------------------------------
# Tool: list_services
# -----------------------------------------------------------------------------


@mcp.tool(
    name="tintatlanta_list_services",
    annotations={
        "title": "List Tint Atlanta services + pricing",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def tintatlanta_list_services() -> Dict[str, Any]:
    """
    Return Tint Atlanta's full service catalog with pricing tiers, film
    products, and add-ons. Covers automotive (standard + ceramic film),
    flat glass (residential / commercial), security film, ClearPlex
    windshield protection, and ceramic coating.

    Use this to give a user an overview of available services before they
    pick one. For a vehicle-specific quote, call tintatlanta_get_estimate.
    For flat glass, call tintatlanta_flat_glass_estimate (when available).
    """
    return await _http_get("/services")


# -----------------------------------------------------------------------------
# Tool: business_location
# -----------------------------------------------------------------------------


@mcp.tool(
    name="tintatlanta_business_location",
    annotations={
        "title": "Tint Atlanta location, hours, service area",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def tintatlanta_business_location() -> Dict[str, Any]:
    """
    Return the shop's address, phone, hours, GPS coordinates, and service
    area. The shop is at 9585 Main St, Woodstock, GA 30188. Automotive
    service is in-shop; flat glass installation travels statewide in
    Georgia. Use this to answer "where are they / when are they open / do
    they serve [city]?" without needing to call any other tool.
    """
    return await _http_get("/location")


# -----------------------------------------------------------------------------
# Tool: list_faq
# -----------------------------------------------------------------------------


@mcp.tool(
    name="tintatlanta_list_faq",
    annotations={
        "title": "Tint Atlanta FAQs",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def tintatlanta_list_faq(category: Optional[str] = None) -> Dict[str, Any]:
    """
    Return frequently-asked questions for Tint Atlanta. Optionally filter by
    category ('automotive', 'commercial', 'residential', 'security').

    Useful for answering common product / process / policy questions
    ("how long does ceramic last?", "is darker tint legal in GA?",
    "what's the warranty?") without needing to scrape the public site.

    Args:
        category: Optional category filter. Leave unset to receive all FAQs.
    """
    query: Dict[str, Any] = {}
    if category:
        query["category"] = category
    return await _http_get("/faq", params=query or None)


# -----------------------------------------------------------------------------
# Tool: get_estimate (automotive)
# -----------------------------------------------------------------------------


@mcp.tool(
    name="tintatlanta_get_estimate",
    annotations={
        "title": "Get an automotive tint estimate",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def tintatlanta_get_estimate(
    vehicle_type: str,
    vehicle_year: Optional[int] = None,
    vehicle_make: Optional[str] = None,
    vehicle_model: Optional[str] = None,
    service: str = "automotive",
    film_type: Optional[str] = None,
    coverage: str = "full",
    shade: Optional[int] = None,
    windshield_shade: Optional[int] = None,
    addons: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Get an automotive window-tint price estimate for a specific vehicle.
    Returns line-item pricing for standard and/or ceramic film, GA tint-law
    legality notes for the requested shade, available add-ons, and
    next-action suggestions (book, request a formal quote, etc.).

    No side effects — does not create a lead, does not commit a booking.
    Safe to call without user consent.

    For service jobs (residential / commercial / security flat glass), use
    tintatlanta_flat_glass_estimate (when available) instead.

    Args:
        vehicle_type: Body style. One of: sedan, coupe, suv, truck, extended_cab,
            wagon, crossover, van.
        vehicle_year: Vehicle model year (e.g. 2026). Triggers model-aware notes
            (e.g. existing-tint-removal upsell for older vehicles).
        vehicle_make: Vehicle make (e.g. 'Tesla', 'BMW', 'Ford').
        vehicle_model: Vehicle model (e.g. 'Model Y', 'M3', 'F-150').
        service: Service flavor. Default 'automotive'. Other valid values:
            'clearplex' (windshield protection), 'film_removal'.
        film_type: Film tier. 'standard' (Madico Black Pearl NR, 55% IR) or
            'ceramic' (Madico Black Pearl Nano, 93% IR). Omit to receive BOTH
            options with a comparison note.
        coverage: 'full' (all windows) or 'front2' (driver + passenger only).
        shade: Requested VLT in percent (e.g. 5, 20, 35, 55, 75). Triggers
            Georgia tint-law legality check.
        windshield_shade: Optional windshield ceramic shade (35, 55, or 75).
        addons: Optional add-ons (e.g. ['sunroof', 'windshield_strip']).
    """
    body: Dict[str, Any] = {"vehicle_type": vehicle_type}
    for k, v in {
        "vehicle_year": vehicle_year,
        "vehicle_make": vehicle_make,
        "vehicle_model": vehicle_model,
        "service": service,
        "film_type": film_type,
        "coverage": coverage,
        "shade": shade,
        "windshield_shade": windshield_shade,
        "addons": addons,
    }.items():
        if v is not None:
            body[k] = v
    return await _http_post("/estimates", body)


# -----------------------------------------------------------------------------
# Health check (Railway uses this to confirm the container is up)
# -----------------------------------------------------------------------------


@mcp.custom_route("/health", methods=["GET"])
async def health(_request) -> Any:  # type: ignore[no-untyped-def]
    """Plain HTTP health endpoint at /health for Railway's healthcheck."""
    from starlette.responses import JSONResponse

    return JSONResponse(
        {
            "status": "ok",
            "server": "tintatlanta_mcp",
            "version": "0.1.0",
            "upstream": UPSTREAM_URL,
            "tools": [
                "tintatlanta_list_services",
                "tintatlanta_business_location",
                "tintatlanta_list_faq",
                "tintatlanta_get_estimate",
            ],
        }
    )


# -----------------------------------------------------------------------------
# Entrypoint
# -----------------------------------------------------------------------------


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    # streamable-http transport: single endpoint, stateless JSON. Compatible
    # with Claude.ai's remote MCP, Perplexity custom remote connectors, and
    # ChatGPT Apps SDK (which is built on MCP).
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = port
    mcp.run(transport="streamable-http")
