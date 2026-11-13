"""Every path+method in contracts/openapi.yaml is implemented, and nothing else (except docs)."""
import re

from app import settings
from app.main import app


def contract_routes() -> set[tuple[str, str]]:
    out, path = set(), None
    for line in (settings.CONTRACTS_DIR / "openapi.yaml").read_text(encoding="utf-8").splitlines():
        if m := re.match(r"^  (/\S+):\s*$", line):
            path = m.group(1)
        elif path and (m := re.match(r"^    (get|post|put|patch|delete):", line)):
            out.add((m.group(1).upper(), path))
        elif re.match(r"^\S", line):
            path = None
    return out


def app_routes() -> set[tuple[str, str]]:
    out = set()
    for r in app.routes:
        for m in getattr(r, "methods", None) or ():
            if m in ("HEAD", "OPTIONS") or r.path.startswith(("/docs", "/redoc", "/openapi")):
                continue
            out.add((m, r.path.replace("{path:path}", "{path}")))
    return out


def test_routes_match_openapi_contract():
    assert len(contract_routes()) == 23  # v1.1: + transcript.txt, slides.pptx, slides.pdf; v1.2: + GET/POST chat; v1.4: + GET/PUT settings
    assert app_routes() == contract_routes()


def test_health_still_ok(client):
    assert client.get("/health").json() == {"status": "ok", "version": "1.0.0"}
