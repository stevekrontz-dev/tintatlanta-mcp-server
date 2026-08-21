from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_atlas_image_is_locked_hardened_and_health_checked() -> None:
    dockerfile = (ROOT / "Dockerfile.atlas").read_text(encoding="utf-8")
    assert "requirements.lock" in dockerfile
    assert "USER app" in dockerfile
    assert "HEALTHCHECK" in dockerfile


def test_mcp_uses_atlas_proxy_and_accepts_only_the_atlas_public_host() -> None:
    compose = (ROOT / "docker-compose.atlas.yml").read_text(encoding="utf-8")
    server = (ROOT / "server.py").read_text(encoding="utf-8")
    assert "read_only: true" in compose
    assert "cap_drop:\n      - ALL" in compose
    assert "no-new-privileges:true" in compose
    assert "\n    ports:" not in compose
    assert "UPSTREAM_URL=https://tintatlanta-api.askboswell.com" in compose
    assert "ALLOWED_MCP_HOSTS=tintatlanta-mcp.askboswell.com" in compose
    assert "Host(`tintatlanta-mcp.askboswell.com`)" in compose
    assert "https://tintatlanta-api.askboswell.com" in server
    assert "up.railway.app" not in server
