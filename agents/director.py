"""
Agente: Director de Contenido
Orquestador principal que coordina los 4 agentes especializados.
Recibe un objetivo de alto nivel y devuelve un paquete completo de contenido.

Flujo:
1. Deep Search      → tendencias + keywords virales
2. Channel Analyzer → análisis de competencia
3. Storytelling     → guión completo del video
4. Prompt Generator → prompts JSON para imágenes/thumbnails
"""
import os
import sys
import json
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

AGENTS_DIR = Path(__file__).parent
PYTHON = sys.executable

SYNTHESIS_PROMPT = """Eres el Director de Contenido de un canal de YouTube/TikTok.
Recibes los reportes de 4 agentes especializados y los sintetizas en un paquete ejecutivo de contenido.

Tu output tiene esta estructura:

---

# 🎯 PAQUETE DE CONTENIDO SEMANAL
## Tema: {tema}

---

## 📋 RESUMEN EJECUTIVO (2-3 párrafos)
[Síntesis de las oportunidades más importantes encontradas]

---

## ⚡ TOP 3 ACCIONES INMEDIATAS
1. [Acción concreta con deadline]
2. [Acción concreta con deadline]
3. [Acción concreta con deadline]

---

## 📅 CALENDARIO DE CONTENIDO (7 días)
| Día | Plataforma | Tipo | Título | Hora |
|-----|------------|------|--------|------|
[llena la tabla con el plan de la semana]

---

## 🎬 VIDEO PRIORITARIO
[Destaca el guión y prompts del video más importante de la semana]

---

## 📊 KPIs A MONITOREAR
- Retención objetivo: X%
- CTR miniatura objetivo: X%
- Views objetivo día 1: X
- Comentarios objetivo: X

---

Sé directo, accionable y específico. No repitas información entre secciones.
"""

def sanitize(text: str) -> str:
    """Elimina caracteres surrogate y problemáticos para JSON/HTTP."""
    return text.encode("utf-8", errors="replace").decode("utf-8").replace("\x00", "")


def run_agent(script_name: str, task: str, api_key: str, label: str) -> str:
    """Ejecuta un agente especializado y devuelve su output."""
    script_path = AGENTS_DIR / script_name
    print(f"\n{'='*60}", flush=True)
    print(f"🤖 Ejecutando: {label}...", flush=True)
    print(f"{'='*60}", flush=True)

    env = os.environ.copy()
    env["OPENROUTER_API_KEY"] = api_key
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        result = subprocess.run(
            [PYTHON, str(script_path)],
            input=sanitize(task),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            env=env
        )
        if result.returncode != 0:
            error_msg = result.stderr.strip()
            print(f"⚠️  {label} falló: {error_msg}", file=sys.stderr, flush=True)
            return f"[{label}: Error - {error_msg[:200]}]"

        output = sanitize(result.stdout.strip())
        print(f"✅ {label} completado ({len(output)} caracteres)", flush=True)
        return output

    except subprocess.TimeoutExpired:
        print(f"⏱️  {label} timeout (180s)", file=sys.stderr, flush=True)
        return f"[{label}: Timeout - el agente tardó demasiado]"
    except Exception as e:
        print(f"❌ {label} error: {e}", file=sys.stderr, flush=True)
        return f"[{label}: {str(e)}]"


def synthesize(tema: str, reports: dict, api_key: str) -> str:
    """Llama al LLM para sintetizar todos los reportes en un paquete ejecutivo."""
    content = f"""Tema del canal: {tema}

## REPORTE 1 - DEEP SEARCH (Tendencias y Keywords)
{reports['deep_search']}

## REPORTE 2 - CHANNEL ANALYZER (Competencia)
{reports['channel_analyzer']}

## REPORTE 3 - STORYTELLING DESIGNER (Guión)
{reports['storytelling']}

## REPORTE 4 - PROMPT GENERATOR (Imágenes)
{reports['prompt_generator']}

---
Con base en estos 4 reportes, crea el paquete ejecutivo de contenido semanal."""

    payload = {
        "model": "openai/gpt-oss-120b:free",
        "messages": [
            {"role": "system", "content": SYNTHESIS_PROMPT.format(tema=tema)},
            {"role": "user", "content": content}
        ],
        "max_tokens": 1500,
        "temperature": 0.6
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://127.0.0.1:3100",
            "X-Title": "Paperclip - Director de Contenido"
        },
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=90) as response:
        result = json.loads(response.read().decode("utf-8"))
        return result["choices"][0]["message"]["content"]


def main():
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY no configurada", file=sys.stderr)
        sys.exit(1)

    # Leer objetivo desde stdin, args o env de Paperclip
    if len(sys.argv) > 1:
        objetivo = " ".join(sys.argv[1:])
    else:
        objetivo = sys.stdin.read().strip()

    issue_title = os.environ.get("PAPERCLIP_ISSUE_TITLE", "")
    issue_body = os.environ.get("PAPERCLIP_ISSUE_BODY", "")
    if issue_title:
        objetivo = f"{issue_title}\n\n{issue_body or ''}"

    if not objetivo:
        objetivo = "Inteligencia artificial y automatización para creadores de contenido hispanos"

    print(f"🎯 DIRECTOR DE CONTENIDO INICIANDO", flush=True)
    print(f"📌 Objetivo: {objetivo[:100]}...", flush=True)

    # ── Fase 1: Investigación en paralelo ──────────────────────
    search_task = f"Busca tendencias virales y keywords de oportunidad para el tema: {objetivo}"
    analyzer_task = f"Analiza los canales más exitosos de YouTube y TikTok sobre: {objetivo}. Encuentra sus debilidades."

    deep_search_result = run_agent("deep_search.py", search_task, api_key, "Deep Search")
    channel_result = run_agent("channel_analyzer.py", analyzer_task, api_key, "Channel Analyzer")

    # ── Fase 2: Creación de contenido ──────────────────────────
    storytelling_task = sanitize(f"""Crea un guion viral para el tema: {objetivo}

Contexto de tendencias encontradas:
{deep_search_result[:400]}

Diferenciacion vs competencia:
{channel_result[:250]}""")

    storytelling_result = run_agent("storytelling.py", storytelling_task, api_key, "Storytelling Designer")

    prompt_task = sanitize(f"""Genera prompts JSON para thumbnail de YouTube y cover de TikTok sobre: {objetivo}

El video tiene este concepto:
{storytelling_result[:250]}""")

    prompt_result = run_agent("prompt_generator.py", prompt_task, api_key, "Prompt Generator")

    # ── Fase 3: Síntesis ejecutiva ─────────────────────────────
    print(f"\n{'='*60}", flush=True)
    print(f"🧠 Sintetizando paquete ejecutivo...", flush=True)
    print(f"{'='*60}", flush=True)

    reports = {
        "deep_search": deep_search_result,
        "channel_analyzer": channel_result,
        "storytelling": storytelling_result,
        "prompt_generator": prompt_result
    }

    try:
        synthesis = synthesize(objetivo, reports, api_key)
    except Exception as e:
        synthesis = f"[Error en síntesis: {e}]"

    # ── Output final ───────────────────────────────────────────
    output = f"""# 🎬 PAQUETE COMPLETO DE CONTENIDO
**Tema:** {objetivo}
**Generado por:** Director de Contenido (4 agentes coordinados)

{synthesis}

---

## 📎 REPORTES DETALLADOS

<details>
<summary>🔍 Deep Search - Tendencias completas</summary>

{deep_search_result}
</details>

<details>
<summary>🔭 Channel Analyzer - Análisis competencia</summary>

{channel_result}
</details>

<details>
<summary>✨ Storytelling - Guión completo</summary>

{storytelling_result}
</details>

<details>
<summary>🪄 Prompt Generator - Prompts de imágenes</summary>

{prompt_result}
</details>
"""
    print(output, flush=True)


if __name__ == "__main__":
    main()
