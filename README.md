# tintatlanta-mcp-server

A remote MCP (Model Context Protocol) server that wraps the Tint Atlanta
public API at `https://tintatlanta.com/api/v1/*` as MCP tools. Layer 3 of
the LocalGEO Phase 2 protocol stack.

**One MCP server reaches three runtimes:**
- **Claude.ai** — native MCP client (custom remote connector)
- **ChatGPT (Apps SDK)** — Apps SDK is built on MCP
- **Perplexity** — custom remote MCP connectors (per Perplexity Round 1
  in the LocalGEO 4-round AI relay, Boswell `34a8a275`)

## Architecture

```
[ChatGPT / Claude.ai / Perplexity] ←→ MCP (Streamable HTTP)
                                       │
                                       ▼
                               [tintatlanta-mcp-server]
                                       │
                                       │ HTTP (JSON, with TintAtlanta-MCP UA)
                                       ▼
                  [tintatlanta-api-proxy on Railway]
                                       │
                                       │ HTTP (UA stripped, mod_security bypass)
                                       ▼
                     [tintatlanta.com/api/v1/* on Hostgator]
                                       │
                                       │ MySQL
                                       ▼
                                [tint_tintcrm DB]
```

## Tools (v0.1 — tonight)

| Tool | Side effect | Auth | Purpose |
|---|---|---|---|
| `tintatlanta_list_services` | none | none | Full service catalog with pricing |
| `tintatlanta_business_location` | none | none | Address, hours, GPS, service area |
| `tintatlanta_list_faq` | none | none | FAQs, optional category filter |
| `tintatlanta_get_estimate` | none | none | Automotive price estimate (POST /estimates) |

## Tools (roadmapped — v0.2 multi-session)

| Tool | Side effect | Auth | Purpose |
|---|---|---|---|
| `tintatlanta_check_availability` | none | none | Open appointment slots |
| `tintatlanta_flat_glass_estimate` | none | none | Residential/commercial Good/Better/Best |
| `tintatlanta_submit_quote_request` | **creates_lead** | none | Lead capture for jobs needing a site visit |
| `tintatlanta_register_api_key` | none | none | Issue API key for booking access |
| `tintatlanta_book_appointment` | **books_appointment** | **api_key** | Actual booking (calls /api/v1/bookings) |

The two write-side tools (`submit_quote_request`, `book_appointment`) need
a consent-gate annotation so MCP runtimes prompt the user before the agent
calls them. v0.2 work.

## Deploy to Railway

The repo is shaped to mirror `tintatlanta-api-proxy`:
- `Dockerfile` — Python 3.11-slim, single-file server, `EXPOSE 8080`
- `railway.json` — build via Dockerfile, healthcheck at `/health`
- `requirements.txt` — `mcp`, `httpx`, `pydantic`, `uvicorn`
- `server.py` — the FastMCP server

Steps (mirror what was done for `tintatlanta-api-proxy`):
1. Push this repo to GitHub at `stevekrontz-dev/tintatlanta-mcp-server`
   (or `Tint-Atlanta/tintatlanta-mcp-server` if Steve prefers the org).
2. In Railway: New Project → Deploy from GitHub repo → select this repo.
3. Railway auto-detects the Dockerfile and railway.json.
4. (Optional) Set `UPSTREAM_URL` env var if you want the MCP server to hit
   the direct PHP API (`https://tintatlanta.com/api/v1`) instead of the
   default of going through the proxy.
5. Railway assigns a public URL like
   `https://tintatlanta-mcp-server-production.up.railway.app` — the MCP
   endpoint is at the root path (Streamable HTTP single-endpoint pattern).

## Wire it into the runtimes

### Claude.ai (custom remote MCP)

Settings → Connectors → Add custom connector:
- Type: Remote MCP
- URL: `https://<railway-url>/`

### ChatGPT (Apps SDK)

Apps SDK is built on MCP. Register the same Railway URL as a custom MCP
endpoint. The 4 tools appear in the Apps SDK tool roster automatically —
their input schemas, descriptions, and annotations come from the FastMCP
decorators.

### Perplexity (custom remote connector)

Perplexity → Connectors → Add custom remote → URL: same Railway URL.
Auth: none for v0.1 (the server passes through the upstream API which
also has no auth for the four tools). When `book_appointment` ships in
v0.2, add bearer-token passthrough.

## Local development

```sh
pip install -r requirements.txt
python server.py
# server starts on http://0.0.0.0:8080
```

Test with the MCP Inspector:
```sh
npx @modelcontextprotocol/inspector
# Then point it at http://localhost:8080
```

### Verified end-to-end on Linux/Python 3.11 (2026-05-08)

Built and run in Docker:
```sh
docker build -t tintatlanta-mcp .
docker run -p 8080:8080 tintatlanta-mcp
```

All four tools call through correctly. `tintatlanta_get_estimate` for
a 2026 Tesla Model Y / ceramic / full coverage returns live pricing
($600 base) via the full chain: MCP server → Railway proxy → tintatlanta.com.

### Known Windows local-test quirk

On **Windows + Python 3.14 + FastMCP 1.27** the StreamableHTTP transport
wraps the inputSchema fields under a single `params` key (visible via
`tools/list` over HTTP, even though direct module introspection shows
the correct flat schema). This is a Python-3.14 typing/introspection
edge case — does NOT affect Docker (Python 3.11) or Railway. If you're
testing locally on Windows, use the Docker workflow above instead of
running `python server.py` directly.

## Discovery via /.well-known/mcp.json

(Roadmapped) Publish `https://tintatlanta.com/.well-known/mcp.json`
pointing at the Railway URL so MCP-aware crawlers can find this server
the same way they find `/.well-known/agent.json` (A2A) and
`/.well-known/agents.json` (OpenAI lineage). For now the URL is
discoverable via Tint Atlanta's OpenAPI manifest's `x_tintatlanta`
sibling-documents block at `/api/v1/capabilities`.

## Source of truth

The capability ontology lives in
`tintatlanta-website/api/v1/_capabilities.php`. This MCP server's tool set
is one **adapter** into that ontology — others (A2A AgentCard, UCP profile,
OpenAPI 3.0 spec, llms.txt, /api/v1/index agent landing pad) are sibling
adapters into the same source.

> *"The business logic belongs to you. Protocols are export formats."*
> — ChatGPT, LocalGEO Phase 2 R2.

## Plan + lineage

- Plan: `tintatlanta-website/.claude/plans/fancy-noodling-wombat.md` (root
  copy at `~/.claude/plans/`).
- Boswell commits:
  - `34a8a275` — locked Phase 2 v0.1 plan
  - `49b4f8e7` — staging deploy
  - `43cf3717` — production deploy
  - `b2c384cd` — 8-layer protocol stack reference (this server is Layer 3)
- LocalGEO writeups: `tintatlanta-website/docs/localgeo/`
