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
                   [tintatlanta-api-proxy on Atlas]
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

## Additional tools (v0.2 multi-session)

| Tool | Side effect | Auth | Purpose |
|---|---|---|---|
| `tintatlanta_check_availability` | none | none | Open appointment slots |
| `tintatlanta_flat_glass_estimate` | none | none | Residential/commercial Good/Better/Best |
| `tintatlanta_submit_quote_request` | **creates_lead** | none | Lead capture for jobs needing a site visit |
| `tintatlanta_register_api_key` | none | none | Issue API key for booking access |
| `tintatlanta_book_appointment` | **books_appointment** | **api_key** | Actual booking (calls /api/v1/bookings) |

The two write-side tools (`submit_quote_request`, `book_appointment`) carry
consent-gate annotations so MCP runtimes can prompt before the agent calls them.

## Deploy to Atlas

The Atlas release uses:
- `Dockerfile.atlas` — digest-pinned Python 3.11, locked dependencies,
  unprivileged runtime user, and `/health` healthcheck
- `docker-compose.atlas.yml` — read-only filesystem, dropped capabilities,
  no published host ports, and Traefik TLS routing
- `requirements.lock` — reproducible Linux dependency resolution
- `server.py` — the FastMCP server

The canonical public endpoint is
`https://tintatlanta-mcp.askboswell.com/mcp`. Its default upstream is the
Atlas proxy at `https://tintatlanta-api.askboswell.com`.

## Wire it into the runtimes

### Claude.ai (custom remote MCP)

Settings → Connectors → Add custom connector:
- Type: Remote MCP
- URL: `https://tintatlanta-mcp.askboswell.com/mcp`

### ChatGPT (Apps SDK)

Apps SDK is built on MCP. Register the same Atlas URL as a custom MCP
endpoint. The 9 tools appear in the Apps SDK tool roster automatically —
their input schemas, descriptions, and annotations come from the FastMCP
decorators.

### Perplexity (custom remote connector)

Perplexity → Connectors → Add custom remote → URL: the same Atlas URL.

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

All nine tools are registered. `tintatlanta_get_estimate` for
a 2026 Tesla Model Y / ceramic / full coverage returns live pricing
($600 base) via the full chain: Atlas MCP server → Atlas proxy → tintatlanta.com.

### Known Windows local-test quirk

On **Windows + Python 3.14 + FastMCP 1.27** the StreamableHTTP transport
wraps the inputSchema fields under a single `params` key (visible via
`tools/list` over HTTP, even though direct module introspection shows
the correct flat schema). This is a Python-3.14 typing/introspection
edge case — does NOT affect Docker (Python 3.11) or Atlas. If you're
testing locally on Windows, use the Docker workflow above instead of
running `python server.py` directly.

## Discovery via /.well-known/mcp.json

(Roadmapped) Publish `https://tintatlanta.com/.well-known/mcp.json`
pointing at `https://tintatlanta-mcp.askboswell.com/mcp` so MCP-aware crawlers can find this server
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
