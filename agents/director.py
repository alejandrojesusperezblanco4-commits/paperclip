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
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from api_client import call_llm

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

AGENTS_DIR = Path(__file__).parent
PYTHON = sys.executable

SYNTHESIS_PROMPT = """Eres el Director de Contenido del canal TikTok @historias.en.sombra.
El canal publica historias REALISTAS con emociones fuertes: traiciones, engaños, infidelidades, manipulaciones.
Estilo: narración en primera persona, tono íntimo y emocional, como si fuera real.
Audiencia: latinos 18-35 años que disfrutan drama relacional y se sienten identificados.

Recibes los reportes de 4 agentes y los sintetizas en un paquete ejecutivo listo para producir.

---

# 🎯 PAQUETE SEMANAL — @historias.en.sombra
## Historia seleccionada: {tema}

---

## 📋 RESUMEN EJECUTIVO
[Por qué esta historia va a viralizar: emoción, identificación, factor sorpresa]

---

## ⚡ TOP 3 ACCIONES ESTA SEMANA
1. [Acción concreta hoy]
2. [Acción concreta mañana]
3. [Acción para el fin de semana]

---

## 📅 CALENDARIO (7 días)
| Día | Historia/Ángulo | Emoción principal | Hora sugerida |
|-----|-----------------|-------------------|---------------|
[Plan con 3-5 posts, variando entre traición, engaño, manipulación]

---

## 🎬 VIDEO PRIORITARIO DE LA SEMANA
[El guión listo para grabar, con el hook más fuerte]

---

## 📊 KPIs OBJETIVO
- Retención al segundo 3: >85%
- Comentarios esperados: "esto me pasó a mí" / "¿cómo se llama él/ella?"
- Shares objetivo: que lo manden a alguien conocido
- CTR del thumbnail: >8%

---

Sé directo y emocional. El contenido debe hacer que la gente sienta rabia, tristeza o identificación.
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
            # stdout también para que aparezca en el log de la UI
            print(f"⚠️  {label} falló (exit {result.returncode}): {error_msg[:300]}", flush=True)
            return f"[{label}: Error - {error_msg[:200]}]"

        output = sanitize(result.stdout.strip())
        if not output:
            print(f"⚠️  {label} devolvió respuesta vacía. Stderr: {result.stderr.strip()[:200]}", flush=True)
            return f"[{label}: respuesta vacía]"
        print(f"✅ {label} completado ({len(output)} caracteres)", flush=True)
        return output

    except subprocess.TimeoutExpired:
        print(f"⏱️  {label} timeout (180s)", flush=True)
        return f"[{label}: Timeout - el agente tardó demasiado]"
    except Exception as e:
        print(f"❌ {label} error inesperado: {e}", flush=True)
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

    return call_llm(
        messages=[
            {"role": "system", "content": SYNTHESIS_PROMPT.format(tema=tema)},
            {"role": "user", "content": content}
        ],
        api_key=api_key,
        max_tokens=1500,
        temperature=0.6,
        title="Paperclip - Director de Contenido",
    )


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
        objetivo = "historias realistas de traición, engaño e infidelidad para el canal @historias.en.sombra de TikTok en español"

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

    # ── Publicar resultado como comentario en el issue (aparece en el inbox) ──
    issue_id = os.environ.get("PAPERCLIP_ISSUE_ID", "")
    api_url  = os.environ.get("PAPERCLIP_API_URL", "http://localhost:7777")

    if issue_id:
        # 1. Postear el resultado como comentario → aparece en el chat del issue
        try:
            comment_data = json.dumps({"body": output}).encode("utf-8")
            comment_req = urllib.request.Request(
                f"{api_url}/api/issues/{issue_id}/comments",
                data=comment_data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(comment_req, timeout=15) as r:
                print(f"✅ Resultado publicado como comentario (HTTP {r.status})", flush=True)
        except Exception as e:
            print(f"⚠️  No se pudo publicar el comentario: {e}", flush=True)

        # 2. Marcar issue como done para evitar re-ejecución
        try:
            patch_data = json.dumps({"status": "done"}).encode("utf-8")
            patch_req = urllib.request.Request(
                f"{api_url}/api/issues/{issue_id}",
                data=patch_data,
                headers={"Content-Type": "application/json"},
                method="PATCH"
            )
            with urllib.request.urlopen(patch_req, timeout=10) as r:
                print(f"✅ Issue marcado como done (HTTP {r.status})", flush=True)
        except Exception as e:
            print(f"⚠️  No se pudo cerrar el issue: {e}", flush=True)


if __name__ == "__main__":
    main()
