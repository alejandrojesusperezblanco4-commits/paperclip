"""
Agente: CEO — DiscontrolDrops Orchestrator
Coordina el pipeline completo ejecutando sub-agentes como subprocesses.

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
import subprocess
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from api_client import post_issue_result, post_issue_comment, resolve_issue_context

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

AGENTS_DIR = Path(__file__).parent
PYTHON     = sys.executable


def run_agent(script: str, input_data: str, timeout: int = 300) -> str:
    """Ejecuta un sub-agente como subprocess y devuelve su stdout."""
    script_path = AGENTS_DIR / script
    print(f"\n▶ Ejecutando {script}...", flush=True)
    try:
        result = subprocess.run(
            [PYTHON, str(script_path)],
            input=input_data.encode("utf-8"),
            capture_output=True,
            timeout=timeout,
            env={**os.environ},
        )
        stdout = result.stdout.decode("utf-8", errors="replace").strip()
        stderr = result.stderr.decode("utf-8", errors="replace").strip()

        if result.returncode != 0:
            print(f"  ⚠️  {script} salió con código {result.returncode}", flush=True)
            if stderr:
                print(f"  stderr: {stderr[:300]}", flush=True)
            return stdout or ""

        print(f"  ✅ {script} completado ({len(stdout)} chars)", flush=True)
        return stdout

    except subprocess.TimeoutExpired:
        print(f"  ⏰ {script} timeout ({timeout}s)", flush=True)
        return ""
    except Exception as e:
        print(f"  ❌ {script} error: {e}", flush=True)
        return ""


def parse_niche(raw: str) -> str:
    """Extrae el nicho del input."""
    try:
        data = json.loads(raw)
        return data.get("niche", data.get("query", raw.strip()))
    except Exception:
        return raw.strip() or "trending products"


def main():
    issue_title, issue_body = resolve_issue_context()
    raw = issue_body if issue_body else (issue_title or "")
    if len(sys.argv) > 1:
        raw = " ".join(sys.argv[1:])

    niche = parse_niche(raw)
    print(f"🚀 CEO DROPS — Nicho: {niche}", flush=True)

    post_issue_comment(
        f"🚀 **CEO DiscontrolDrops** iniciando pipeline para: **{niche}**\n\n"
        f"Pipeline: Product Hunter → Ad Spy → Lead Qualifier → Web Designer → Marketing Creator"
    )

    # ── PASO 1: Product Hunter ────────────────────────────────────────────────
    post_issue_comment("🔍 **Paso 1/5** — Buscando productos ganadores...")
    hunter_input  = json.dumps({"niche": niche, "region": "ES", "limit": 15})
    hunter_result = run_agent("product_hunter.py", hunter_input, timeout=300)

    if not hunter_result:
        post_issue_result("❌ Product Hunter no devolvió resultados.")
        return

    # ── PASO 2: Ad Spy ────────────────────────────────────────────────────────
    post_issue_comment("🕵️ **Paso 2/5** — Validando demanda en Facebook Ads...")
    spy_result = run_agent("ad_spy.py", hunter_result, timeout=180)
    if not spy_result:
        spy_result = hunter_result  # fallback
        print("  ⚠️  Ad Spy sin resultados — continuando", flush=True)

    # ── PASO 3: Lead Qualifier ────────────────────────────────────────────────
    post_issue_comment("🎯 **Paso 3/5** — Calificando y puntuando productos...")
    combined         = f"{hunter_result}\n\n---AD SPY---\n{spy_result}"
    qualifier_result = run_agent("lead_qualifier.py", combined, timeout=180)

    if not qualifier_result:
        post_issue_result("❌ Lead Qualifier no devolvió resultados.")
        return

    # Verificar si hay productos LAUNCH
    if "LAUNCH" not in qualifier_result and "TEST" not in qualifier_result:
        post_issue_comment("⚠️ Ningún producto recomendado. Ciclo completado.")
        post_issue_result(f"✅ Análisis completado — sin productos recomendados ahora.\n\n{qualifier_result}")
        return

    # ── PASO 4: Web Designer ──────────────────────────────────────────────────
    post_issue_comment("🎨 **Paso 4/5** — Generando estructura landing Shopify...")
    web_result = run_agent("web_designer.py", qualifier_result, timeout=180)

    # ── PASO 5: Marketing Creator ─────────────────────────────────────────────
    post_issue_comment("📣 **Paso 5/5** — Generando copy, scripts y emails...")
    marketing_input  = f"{qualifier_result}\n\n---WEB---\n{web_result or ''}"
    marketing_result = run_agent("marketing_creator.py", marketing_input, timeout=180)

    # ── Resumen final ─────────────────────────────────────────────────────────
    # Extraer top producto
    top_name = "producto analizado"
    m = re.search(r'###.*?🟢.*?\*\*(.*?)\*\*', qualifier_result)
    if m:
        top_name = m.group(1).strip()

    output = (
        f"# ✅ DiscontrolDrops — Pipeline Completado\n\n"
        f"**Nicho:** {niche} | **Top producto:** {top_name}\n\n"
        f"## 🎯 Productos calificados\n{qualifier_result[:2000]}\n\n"
        f"## 🎨 Landing Shopify\n{(web_result or '_No generada_')[:1000]}\n\n"
        f"## 📣 Marketing Assets\n{(marketing_result or '_No generados_')[:1000]}"
    )
    post_issue_result(output)
    print("\n✅ Pipeline completado", flush=True)


if __name__ == "__main__":
    main()
