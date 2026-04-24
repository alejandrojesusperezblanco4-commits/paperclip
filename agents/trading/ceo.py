"""
Agente: CEO — Trading Orchestrator (Polymarket / DiscontrolsBags)
Orquesta el ciclo completo de análisis y ejecución de trades en Polymarket.

Flujo:
1. Market Scanner      → mercados con edge potencial (Gamma API)
2. Probability Estimator → P(evento) real vs precio mercado (LLM)
3. Risk Manager        → tamaño de posición (Kelly 1/4)
4. Executor            → coloca la orden en Polymarket (DRY_RUN por defecto)
5. Reporter            → Telegram + log SQLite

Se lanza vía Issue en Paperclip (manual o Routine automática).
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

# ── IDs de los agentes en DiscontrolsBags ────────────────────────────────────
AGENT_IDS = {
    "market_scanner":        "6f75364c-0ab2-48ac-9144-f40578435d67",
    "probability_estimator": "ff3e3f5f-118f-451d-b042-91ec19d0cf11",
    "risk_manager":          "149be654-dccb-4da3-a6c6-091c5b5fe1e6",
    "executor":              "61ced466-af5b-43be-a049-e94cf895274a",
    "reporter":              "74bc12a4-6928-4450-b472-2962c3516627",
}

CEO_AGENT_ID     = "41df12d7-71c4-494e-a503-d02ef88fb1d8"
TRADING_COMPANY  = "866b74e7-79a7-4166-9f9f-025faa751aa1"

# Pausa entre etapas para que los agentes terminen de procesar
STEP_WAIT = int(os.environ.get("TRADING_STEP_WAIT", "90"))  # segundos


# ── JWT + API ─────────────────────────────────────────────────────────────────

def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def make_jwt(secret: str) -> str:
    header  = json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":"))
    now     = int(time.time())
    payload = json.dumps({
        "sub":          CEO_AGENT_ID,
        "company_id":   TRADING_COMPANY,
        "adapter_type": "process",
        "run_id":       f"ceo-{now}",
        "iat":          now,
        "exp":          now + 172800,
        "iss":          "paperclip",
        "aud":          "paperclip-api",
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
        print(f"  ⚠️  API {method} {path} → HTTP {e.code}: {body[:300]}", flush=True)
        return None
    except Exception as e:
        print(f"  ⚠️  API {method} {path} → {e}", flush=True)
        return None


def create_sub_issue(title: str, description: str, agent_key: str,
                     parent_id: str, headers: dict) -> str | None:
    """Crea un sub-issue asignado al agente correspondiente."""
    agent_id = AGENT_IDS.get(agent_key, "")
    payload  = {
        "title":       title,
        "description": description[:4000],
        "status":      "backlog",
        "parentId":    parent_id,
    }
    if agent_id:
        payload["assigneeAgentId"] = agent_id

    result = api(
        "POST",
        f"/api/companies/{TRADING_COMPANY}/issues",
        payload,
        headers,
    )
    issue_id = (result or {}).get("id")
    if issue_id:
        print(f"  ✅ Sub-issue '{title}' → {issue_id}", flush=True)
    return issue_id


def get_issue_result(issue_id: str, headers: dict, max_wait: int = 120) -> str:
    """Espera hasta que el issue esté 'done' y devuelve su último comentario."""
    deadline = time.time() + max_wait
    interval = 10
    time.sleep(interval)

    while time.time() < deadline:
        data   = api("GET", f"/api/issues/{issue_id}", None, headers)
        status = (data or {}).get("status", "")
        print(f"  ⏳ Issue {issue_id[:8]}… → {status}", flush=True)

        if status == "done":
            # Obtener último comentario (el resultado del agente)
            comments = api("GET", f"/api/issues/{issue_id}/comments?limit=10", None, headers)
            if isinstance(comments, list) and comments:
                return comments[-1].get("body", "")
            return ""

        if status in ("canceled", "failed"):
            return ""

        time.sleep(interval)

    print(f"  ⏰ Timeout esperando issue {issue_id}", flush=True)
    return ""


# ── Pipeline ──────────────────────────────────────────────────────────────────

def run_pipeline(parent_issue_id: str, headers: dict, config: dict) -> str:
    """Ejecuta el pipeline completo de trading."""

    # ── PASO 1: Market Scanner ────────────────────────────────────────────────
    post_issue_comment("🔍 **Paso 1/5** — Escaneando mercados de Polymarket...")
    scanner_desc = json.dumps({
        "min_volume_usd": config.get("min_volume_usd", 10000),
        "categories":     config.get("categories", ["politics", "crypto", "economics"]),
    })
    scanner_issue = create_sub_issue(
        "Scan Polymarket Markets", scanner_desc, "market_scanner", parent_issue_id, headers
    )
    if not scanner_issue:
        return "❌ Falló al crear issue de Market Scanner"

    scanner_result = get_issue_result(scanner_issue, headers, max_wait=180)
    if not scanner_result:
        return "❌ Market Scanner no devolvió resultado"

    print(f"  📊 Scanner result: {scanner_result[:200]}...", flush=True)

    # ── PASO 2: Probability Estimator ─────────────────────────────────────────
    post_issue_comment("📊 **Paso 2/5** — Estimando probabilidades con LLM...")
    estimator_issue = create_sub_issue(
        "Estimate Market Probability", scanner_result, "probability_estimator", parent_issue_id, headers
    )
    if not estimator_issue:
        return "❌ Falló al crear issue de Probability Estimator"

    estimator_result = get_issue_result(estimator_issue, headers, max_wait=180)
    if not estimator_result:
        return "❌ Probability Estimator no devolvió resultado"

    # Verificar si hay edge
    if '"tradeable": false' in estimator_result or '"tradeable":false' in estimator_result:
        post_issue_comment("🟡 Sin edge suficiente esta vez. Ciclo completado sin trade.")
        return "✅ Análisis completado — No hay oportunidad de trade en este momento.\n\n" + estimator_result

    # ── PASO 3: Risk Manager ──────────────────────────────────────────────────
    post_issue_comment("⚖️ **Paso 3/5** — Calculando tamaño de posición (Kelly 1/4)...")
    risk_issue = create_sub_issue(
        "Calculate Position Size", estimator_result, "risk_manager", parent_issue_id, headers
    )
    if not risk_issue:
        return "❌ Falló al crear issue de Risk Manager"

    risk_result = get_issue_result(risk_issue, headers, max_wait=60)
    if not risk_result:
        return "❌ Risk Manager no devolvió resultado"

    if '"approved": false' in risk_result or '"approved":false' in risk_result:
        post_issue_comment("🔴 Risk Manager rechazó el trade. Ciclo completado.")
        return "✅ Risk Manager rechazó el trade (riesgo demasiado alto).\n\n" + risk_result

    # ── PASO 4: Executor ──────────────────────────────────────────────────────
    dry_run = os.environ.get("TRADING_DRY_RUN", "true").lower() != "false"
    mode    = "🧪 DRY RUN" if dry_run else "🔴 LIVE"
    post_issue_comment(f"⚡ **Paso 4/5** — Ejecutando orden... Modo: {mode}")
    executor_issue = create_sub_issue(
        f"Execute Trade {mode}", risk_result, "executor", parent_issue_id, headers
    )
    if not executor_issue:
        return "❌ Falló al crear issue de Executor"

    executor_result = get_issue_result(executor_issue, headers, max_wait=120)
    if not executor_result:
        return "❌ Executor no devolvió resultado"

    # ── PASO 5: Reporter ──────────────────────────────────────────────────────
    post_issue_comment("📣 **Paso 5/5** — Reportando resultado...")
    reporter_issue = create_sub_issue(
        "Report Trade Result", executor_result, "reporter", parent_issue_id, headers
    )
    if reporter_issue:
        get_issue_result(reporter_issue, headers, max_wait=60)

    return f"# ✅ CEO — Ciclo de Trading Completado\n\n{executor_result}"


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    secret = os.environ.get("BETTER_AUTH_SECRET", "").strip()
    if not secret:
        print("ERROR: BETTER_AUTH_SECRET no configurado", file=sys.stderr)
        sys.exit(1)

    issue_id    = os.environ.get("PAPERCLIP_ISSUE_ID", "").strip()
    issue_title, issue_body = resolve_issue_context()

    # Configuración desde el body del issue (opcional)
    config = {}
    if issue_body:
        try:
            config = json.loads(issue_body)
        except Exception:
            pass

    token   = make_jwt(secret)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }

    print("🤖 CEO TRADING — Polymarket", flush=True)
    print(f"   Issue: {issue_id}", flush=True)
    print(f"   Config: {config}", flush=True)

    post_issue_comment(
        "🤖 **CEO Trading** iniciando ciclo de análisis Polymarket...\n\n"
        "Pipeline: Market Scanner → Probability Estimator → Risk Manager → Executor → Reporter"
    )

    result = run_pipeline(issue_id, headers, config)
    post_issue_result(result)


if __name__ == "__main__":
    main()
