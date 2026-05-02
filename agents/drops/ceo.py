"""
Agente: CEO — DiscontrolDrops Orchestrator
Coordina el pipeline completo de investigación y lanzamiento de productos.

Flujo:
1. Product Hunter  → busca productos ganadores
2. Ad Spy          → valida demanda con Facebook Ads Library
3. Lead Qualifier  → puntúa y filtra (LAUNCH/TEST/SKIP)
4. Web Designer    → genera estructura de landing Shopify
5. Marketing Creator → genera copy, scripts y emails

Input: nicho o producto a investigar
  "tactical gadgets"
  "home office accessories"
  {"niche": "pet accessories", "region": "ES"}
"""
import os
import sys
import json
import hmac
import hashlib
import base64
import time
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from api_client import post_issue_result, post_issue_comment, resolve_issue_context

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# ── Agent IDs — DiscontrolDrops ───────────────────────────────────────────────
AGENT_IDS = {
    "product_hunter":    "01a671f6-a303-4f74-90e2-914c63a2e34d",
    "ad_spy":            "9d3649ad-b902-495a-8330-8048d94ac20d",
    "lead_qualifier":    "fbf55d11-03cb-4d88-9132-7a04a9091d8c",
    "web_designer":      "e39f154b-0415-42f2-bd60-b79f66ecaca7",
    "marketing_creator": "f6fb0f5a-ea32-4a29-aac1-95e7c3db6335",
}

CEO_AGENT_ID    = "60dd4b7a-4ec3-4555-8e52-807ffcf15a7b"
DROPS_COMPANY   = "0b4751e7-24e7-4e8b-98e0-5b5ed73b6d7c"


# ── Auth ──────────────────────────────────────────────────────────────────────

def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def make_jwt(secret: str) -> str:
    header  = json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":"))
    now     = int(time.time())
    payload = json.dumps({
        "sub": CEO_AGENT_ID, "company_id": DROPS_COMPANY,
        "adapter_type": "process", "run_id": f"drops-ceo-{now}",
        "iat": now, "exp": now + 172800, "iss": "paperclip", "aud": "paperclip-api",
    }, separators=(",", ":"))
    si  = f"{b64url(header.encode())}.{b64url(payload.encode())}"
    sig = hmac.new(secret.encode(), si.encode(), hashlib.sha256).digest()
    return f"{si}.{b64url(sig)}"


def api(method: str, path: str, payload, headers: dict):
    api_url = os.environ.get("PAPERCLIP_API_URL", "http://localhost:3100").rstrip("/")
    url     = f"{api_url}{path}"
    data    = json.dumps(payload).encode("utf-8") if payload is not None else None
    req     = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = ""
        try: body = e.read().decode("utf-8", errors="replace")
        except Exception: pass
        print(f"  ⚠️  API {method} {path} → HTTP {e.code}: {body[:200]}", flush=True)
        return None
    except Exception as e:
        print(f"  ⚠️  API {method} {path} → {e}", flush=True)
        return None


def create_sub_issue(title: str, description: str, agent_key: str,
                     parent_id: str, headers: dict) -> str | None:
    agent_id = AGENT_IDS.get(agent_key, "")
    payload: dict = {
        "title":       title,
        "description": description[:3000],
        "status":      "backlog",
    }
    if parent_id:
        payload["parentId"] = parent_id
    if agent_id:
        payload["assigneeAgentId"] = agent_id

    result = api("POST", f"/api/companies/{DROPS_COMPANY}/issues", payload, headers)
    issue_id = (result or {}).get("id")

    # Fallback: intentar sin parentId si falla
    if not issue_id and parent_id:
        print(f"  ⚠️  Retry sin parentId...", flush=True)
        payload.pop("parentId", None)
        result   = api("POST", f"/api/companies/{DROPS_COMPANY}/issues", payload, headers)
        issue_id = (result or {}).get("id")

    if issue_id:
        print(f"  ✅ Issue '{title}' → {issue_id}", flush=True)
    else:
        print(f"  ❌ No se pudo crear issue '{title}': {result}", flush=True)
    return issue_id


def wait_for_issue(issue_id: str, headers: dict, max_wait: int = 300) -> str:
    """Espera que el issue termine y devuelve el último comentario."""
    deadline = time.time() + max_wait
    interval = 10
    time.sleep(interval)

    while time.time() < deadline:
        data   = api("GET", f"/api/issues/{issue_id}", None, headers)
        status = (data or {}).get("status", "")
        print(f"  ⏳ {issue_id[:8]}… → {status}", flush=True)

        if status == "done":
            comments = api("GET", f"/api/issues/{issue_id}/comments?limit=10", None, headers)
            if isinstance(comments, list) and comments:
                return comments[-1].get("body", "")
            return ""
        if status in ("canceled", "failed"):
            return ""
        time.sleep(interval)

    print(f"  ⏰ Timeout esperando {issue_id}", flush=True)
    return ""


# ── Pipeline ──────────────────────────────────────────────────────────────────

def run_pipeline(niche: str, parent_issue_id: str, headers: dict) -> str:

    # ── PASO 1: Product Hunter ────────────────────────────────────────────────
    post_issue_comment("🔍 **Paso 1/5** — Buscando productos ganadores...")
    hunter_id = create_sub_issue(
        f"Product Hunt: {niche}",
        json.dumps({"niche": niche, "region": "ES", "limit": 15}),
        "product_hunter", parent_issue_id, headers
    )
    if not hunter_id:
        return "❌ Falló Product Hunter"

    hunter_result = wait_for_issue(hunter_id, headers, max_wait=300)
    if not hunter_result:
        return "❌ Product Hunter no devolvió resultados"

    print(f"  📦 Hunter: {len(hunter_result)} chars", flush=True)

    # ── PASO 2: Ad Spy ────────────────────────────────────────────────────────
    post_issue_comment("🕵️ **Paso 2/5** — Validando demanda en Facebook Ads...")
    spy_id = create_sub_issue(
        f"Ad Spy: {niche}",
        hunter_result,
        "ad_spy", parent_issue_id, headers
    )
    if not spy_id:
        return "❌ Falló Ad Spy"

    spy_result = wait_for_issue(spy_id, headers, max_wait=300)
    if not spy_result:
        spy_result = hunter_result  # fallback: continuar sin Ad Spy
        print("  ⚠️  Ad Spy falló — continuando sin validación de anuncios", flush=True)

    # ── PASO 3: Lead Qualifier ────────────────────────────────────────────────
    post_issue_comment("🎯 **Paso 3/5** — Calificando y puntuando productos...")
    # Combinar outputs de Hunter + Spy
    combined = f"{hunter_result}\n\n---AD SPY---\n{spy_result}"
    qualifier_id = create_sub_issue(
        f"Qualify: {niche}",
        combined,
        "lead_qualifier", parent_issue_id, headers
    )
    if not qualifier_id:
        return "❌ Falló Lead Qualifier"

    qualifier_result = wait_for_issue(qualifier_id, headers, max_wait=180)
    if not qualifier_result:
        return "❌ Lead Qualifier no devolvió resultados"

    # Verificar si hay productos LAUNCH
    if '"recommendation": "SKIP"' in qualifier_result and '"recommendation": "LAUNCH"' not in qualifier_result:
        post_issue_comment("⚠️ Ningún producto alcanzó score LAUNCH. Ciclo completado.")
        return f"✅ Análisis completado — ningún producto recomendado para lanzar ahora.\n\n{qualifier_result}"

    # ── PASO 4: Web Designer ──────────────────────────────────────────────────
    post_issue_comment("🎨 **Paso 4/5** — Generando estructura de landing Shopify...")
    web_id = create_sub_issue(
        f"Web Design: {niche}",
        qualifier_result,
        "web_designer", parent_issue_id, headers
    )
    if not web_id:
        return "❌ Falló Web Designer"

    web_result = wait_for_issue(web_id, headers, max_wait=180)

    # ── PASO 5: Marketing Creator ─────────────────────────────────────────────
    post_issue_comment("📣 **Paso 5/5** — Generando copy, scripts y emails...")
    marketing_input = f"{qualifier_result}\n\n---WEB DESIGN---\n{web_result or ''}"
    marketing_id = create_sub_issue(
        f"Marketing: {niche}",
        marketing_input,
        "marketing_creator", parent_issue_id, headers
    )
    if not marketing_id:
        return "❌ Falló Marketing Creator"

    marketing_result = wait_for_issue(marketing_id, headers, max_wait=180)

    # ── Resumen final ─────────────────────────────────────────────────────────
    return (
        f"# ✅ DISCONTROLDROPS — Pipeline Completado\n\n"
        f"**Nicho:** {niche}\n\n"
        f"## 🎯 Productos calificados\n{qualifier_result[:1500]}\n\n"
        f"## 🎨 Landing Shopify\n{(web_result or '_No generada_')[:800]}\n\n"
        f"## 📣 Marketing Assets\n{(marketing_result or '_No generados_')[:800]}"
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    secret = os.environ.get("BETTER_AUTH_SECRET", "").strip()
    if not secret:
        print("ERROR: BETTER_AUTH_SECRET no configurado", file=sys.stderr)
        sys.exit(1)

    issue_id    = os.environ.get("PAPERCLIP_ISSUE_ID", "").strip()
    issue_title, issue_body = resolve_issue_context()

    # Extraer nicho del input
    raw = issue_body if issue_body else (issue_title or "")
    if len(sys.argv) > 1:
        raw = " ".join(sys.argv[1:])

    niche = raw.strip() or "tactical gadgets"

    # Extraer de JSON si viene así
    try:
        data = json.loads(raw)
        niche = data.get("niche", data.get("query", niche))
    except Exception:
        pass

    token   = make_jwt(secret)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    print(f"🚀 CEO DROPS — Nicho: {niche}", flush=True)

    post_issue_comment(
        f"🚀 **CEO DiscontrolDrops** iniciando pipeline para: **{niche}**\n\n"
        f"Pipeline: Product Hunter → Ad Spy → Lead Qualifier → Web Designer → Marketing Creator"
    )

    result = run_pipeline(niche, issue_id, headers)
    post_issue_result(result)


if __name__ == "__main__":
    main()
