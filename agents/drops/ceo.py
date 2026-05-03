"""
Agente: CEO — DiscontrolDrops Orchestrator
Coordina el pipeline de investigación y lanzamiento de productos.
Mismo patrón que el Director de DiscontrolCreator.

Flujo:
1. Product Hunter  → busca productos ganadores
2. Ad Spy          → valida demanda con Facebook Ads Library
3. Lead Qualifier  → puntúa y filtra (LAUNCH/TEST/SKIP)
4. Web Designer    → genera estructura de landing Shopify
5. Marketing Creator → genera copy, scripts y emails
"""
import os
import sys
import json
import re
import time
import hmac
import hashlib
import base64
import urllib.request
import urllib.error
from pathlib import Path


def extract_json_block(text: str, key: str = "") -> str:
    """Extrae el primer bloque JSON válido de un texto markdown."""
    if "```json" in text:
        for block in text.split("```json")[1:]:
            candidate = block.split("```")[0].strip()
            try:
                data = json.loads(candidate)
                if not key or key in data:
                    return candidate
            except Exception:
                continue
    # Buscar JSON con la clave buscada
    pattern = r'\{[\s\S]*?"' + (key or r'\w+') + r'"[\s\S]*?\}'
    m = re.search(pattern, text)
    if m:
        try:
            json.loads(m.group(0))
            return m.group(0)
        except Exception:
            pass
    return text[:3000]

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


# ── Auth — igual que el Director ─────────────────────────────────────────────

def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def make_jwt(agent_id: str, company_id: str, run_id: str, secret: str) -> str:
    now     = int(time.time())
    header  = json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":"))
    payload = json.dumps({
        "sub": agent_id, "company_id": company_id,
        "adapter_type": "process", "run_id": run_id,
        "iat": now, "exp": now + 172800,
        "iss": "paperclip", "aud": "paperclip-api",
    }, separators=(",", ":"))
    si  = f"{b64url(header.encode())}.{b64url(payload.encode())}"
    sig = hmac.new(secret.encode(), si.encode(), hashlib.sha256).digest()
    return f"{si}.{b64url(sig)}"


def api_request(method: str, url: str, payload, headers: dict):
    try:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req  = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = ""
        try: body = e.read().decode("utf-8", errors="replace")
        except Exception: pass
        print(f"  ⚠️  API {method} → HTTP {e.code}: {body[:300]}", flush=True)
        return None
    except Exception as e:
        print(f"  ⚠️  API {method} → {e}", flush=True)
        return None


def get_project_id(api_url: str, company_id: str, headers: dict,
                   name: str = "product 1") -> str:
    """Busca el ID de un proyecto por nombre."""
    try:
        result = api_request("GET", f"{api_url}/api/companies/{company_id}/projects", None, headers)
        projects = result if isinstance(result, list) else (result or {}).get("projects", [])
        for p in projects:
            if isinstance(p, dict) and name.lower() in p.get("name", "").lower():
                return p.get("id", "")
    except Exception as e:
        print(f"  ⚠️  get_project_id error: {e}", flush=True)
    return ""


def create_sub_issue(title: str, description: str, agent_key: str,
                     parent_id: str, api_url: str, company_id: str,
                     headers: dict, project_id: str = "") -> str | None:
    agent_id = AGENT_IDS.get(agent_key, "")
    payload: dict  = {
        "title":    title,
        "status":   "todo",
        "parentId": parent_id,
    }
    if project_id:
        payload["projectId"] = project_id
    if description:
        payload["description"] = description[:4000]
    if agent_id:
        payload["assigneeAgentId"] = agent_id

    url    = f"{api_url}/api/companies/{company_id}/issues"
    result = api_request("POST", url, payload, headers)
    if result:
        sub_id = result.get("id") or result.get("issue", {}).get("id")
        if sub_id:
            print(f"  ✅ Sub-issue '{title}' → {sub_id}", flush=True)
            return sub_id
    print(f"  ⚠️  No se pudo crear sub-issue: {result}", flush=True)
    return None


def wait_for_issue(sub_id: str, api_url: str, headers: dict,
                   max_wait: int = 300) -> str:
    deadline = time.time() + max_wait
    time.sleep(8)
    while time.time() < deadline:
        data   = api_request("GET", f"{api_url}/api/issues/{sub_id}", None, headers)
        status = (data or {}).get("status", "")
        print(f"  ⏳ {sub_id[:8]}… → {status}", flush=True)
        if status == "done":
            comments = api_request("GET", f"{api_url}/api/issues/{sub_id}/comments", None, headers)
            if comments:
                items = (comments if isinstance(comments, list)
                         else comments.get("comments") or comments.get("items") or [])
                if items:
                    best = max(items, key=lambda c: len(c.get("body", "") or ""))
                    return best.get("body", "") or ""
            return ""
        if status in ("cancelled", "failed"):
            return ""
        time.sleep(8)
    print(f"  ⏰ Timeout {sub_id}", flush=True)
    return ""


def parse_niche(raw: str) -> str:
    try:
        data = json.loads(raw)
        return data.get("niche", data.get("query", raw.strip()))
    except Exception:
        return raw.strip() or "trending products"


def main():
    # ── Usar env vars de Paperclip (igual que el Director) ────────────────────
    api_url    = os.environ.get("PAPERCLIP_API_URL", "http://localhost:3100").rstrip("/")
    agent_id   = os.environ.get("PAPERCLIP_AGENT_ID", "")
    company_id = os.environ.get("PAPERCLIP_COMPANY_ID", "")
    run_id     = os.environ.get("PAPERCLIP_RUN_ID", "")  # ← FK a heartbeatRuns, crítico
    issue_id   = os.environ.get("PAPERCLIP_ISSUE_ID", "")
    api_key    = os.environ.get("PAPERCLIP_API_KEY", "")
    jwt_secret = (os.environ.get("PAPERCLIP_AGENT_JWT_SECRET") or
                  os.environ.get("BETTER_AUTH_SECRET", "")).strip()

    print(f"🔍 agent_id={agent_id!r} company_id={company_id!r} run_id={run_id!r}", flush=True)

    # Construir headers de auth — run_id debe ser el PAPERCLIP_RUN_ID real
    headers: dict = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    elif jwt_secret and agent_id and run_id:
        token = make_jwt(agent_id, company_id, run_id, jwt_secret)
        headers["Authorization"] = f"Bearer {token}"
        print("🔑 JWT generado con BETTER_AUTH_SECRET", flush=True)
    elif jwt_secret and agent_id:
        # Sin run_id válido — intentar con string vacío (puede fallar en logActivity)
        token = make_jwt(agent_id, company_id, "", jwt_secret)
        headers["Authorization"] = f"Bearer {token}"
        print("⚠️  JWT sin run_id válido", flush=True)
    else:
        print("⚠️  Sin credenciales", flush=True)

    issue_title, issue_body = resolve_issue_context()
    raw   = issue_body if issue_body else (issue_title or "")
    niche = parse_niche(raw)

    # Buscar proyecto "product 1"
    project_id = get_project_id(api_url, company_id, headers, "product 1")
    if project_id:
        print(f"  📁 Proyecto: product 1 → {project_id}", flush=True)
    else:
        print("  ⚠️  Proyecto 'product 1' no encontrado — sin projectId", flush=True)

    print(f"🚀 CEO DROPS — Nicho: {niche}", flush=True)
    post_issue_comment(
        f"🚀 **CEO DiscontrolDrops** iniciando para: **{niche}**\n\n"
        f"Pipeline: Product Hunter → Ad Spy → Lead Qualifier → Web Designer → Marketing Creator"
    )

    # ── PASO 1: Product Hunter ────────────────────────────────────────────────
    post_issue_comment("🔍 **Paso 1/5** — Buscando productos ganadores...")
    hunter_desc = json.dumps({"niche": niche, "region": "ES", "limit": 15})
    hunter_id   = create_sub_issue(
        f"Product Hunt: {niche}", hunter_desc,
        "product_hunter", issue_id, api_url, company_id, headers, project_id
    )
    if not hunter_id:
        post_issue_result("❌ No se pudo crear issue de Product Hunter.")
        return
    hunter_result = wait_for_issue(hunter_id, api_url, headers, max_wait=300)
    if not hunter_result:
        post_issue_result("❌ Product Hunter no completó.")
        return

    # Extraer JSON del Product Hunter para pasar a los siguientes agentes
    hunter_json = extract_json_block(hunter_result, "products")
    print(f"  📦 hunter_json: {hunter_json[:100]}...", flush=True)

    # ── PASO 2: Ad Spy ────────────────────────────────────────────────────────
    post_issue_comment("🕵️ **Paso 2/5** — Validando demanda en Facebook Ads...")
    spy_id = create_sub_issue(
        f"Ad Spy: {niche}", hunter_json,
        "ad_spy", issue_id, api_url, company_id, headers, project_id
    )
    spy_result     = wait_for_issue(spy_id, api_url, headers, max_wait=180) if spy_id else ""
    spy_json       = extract_json_block(spy_result, "results") if spy_result else ""

    # Combinar hunter + spy para el qualifier
    try:
        h = json.loads(hunter_json)
        s = json.loads(spy_json) if spy_json else {}
        combined_json = json.dumps({
            "products":   h.get("products", []),
            "ad_results": s.get("results", []),
            "niche":      h.get("niche", niche),
        }, ensure_ascii=False)
    except Exception:
        combined_json = hunter_json

    # ── PASO 3: Lead Qualifier ────────────────────────────────────────────────
    post_issue_comment("🎯 **Paso 3/5** — Calificando productos...")
    qualifier_id = create_sub_issue(
        f"Qualify: {niche}", combined_json,
        "lead_qualifier", issue_id, api_url, company_id, headers, project_id
    )
    if not qualifier_id:
        post_issue_result("❌ No se pudo crear issue de Lead Qualifier.")
        return
    qualifier_result = wait_for_issue(qualifier_id, api_url, headers, max_wait=180)
    if not qualifier_result:
        post_issue_result("❌ Lead Qualifier no completó.")
        return
    qualifier_json = extract_json_block(qualifier_result, "qualified")

    # ── PASO 4: Web Designer ──────────────────────────────────────────────────
    post_issue_comment("🎨 **Paso 4/5** — Generando landing Shopify...")
    web_id     = create_sub_issue(
        f"Web Design: {niche}", qualifier_json,
        "web_designer", issue_id, api_url, company_id, headers, project_id
    )
    web_result = wait_for_issue(web_id, api_url, headers, max_wait=180) if web_id else ""

    # ── PASO 5: Marketing Creator ─────────────────────────────────────────────
    post_issue_comment("📣 **Paso 5/5** — Generando copy y assets...")
    mkt_id     = create_sub_issue(
        f"Marketing: {niche}", qualifier_json,
        "marketing_creator", issue_id, api_url, company_id, headers, project_id
    )
    mkt_result = wait_for_issue(mkt_id, api_url, headers, max_wait=180) if mkt_id else ""

    # ── Resumen ───────────────────────────────────────────────────────────────
    post_issue_result(
        f"# ✅ DiscontrolDrops — Pipeline Completado\n\n"
        f"**Nicho:** {niche}\n\n"
        f"## 🎯 Calificación\n{qualifier_result[:1500]}\n\n"
        f"## 🎨 Landing\n{(web_result or '_No generada_')[:800]}\n\n"
        f"## 📣 Marketing\n{(mkt_result or '_No generado_')[:800]}"
    )


if __name__ == "__main__":
    main()
