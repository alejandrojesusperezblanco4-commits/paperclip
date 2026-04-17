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
import hmac
import hashlib
import base64
import time
import urllib.request
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

def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def create_agent_jwt(agent_id: str, company_id: str, run_id: str, secret: str) -> str:
    """Genera un JWT local firmado con HMAC-SHA256 para autenticar contra la API de Paperclip."""
    header  = json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":"))
    now     = int(time.time())
    payload = json.dumps({
        "sub":          agent_id,
        "company_id":   company_id,
        "adapter_type": "process",
        "run_id":       run_id,
        "iat":          now,
        "exp":          now + 172800,  # 48 h
        "iss":          "paperclip",
        "aud":          "paperclip-api",
    }, separators=(",", ":"))
    signing_input = f"{b64url(header.encode())}.{b64url(payload.encode())}"
    sig = hmac.new(secret.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256).digest()
    return f"{signing_input}.{b64url(sig)}"


def sanitize(text: str) -> str:
    """Elimina caracteres surrogate y problemáticos para JSON/HTTP."""
    return text.encode("utf-8", errors="replace").decode("utf-8").replace("\x00", "")


def run_agent_with_env(script_name: str, task: str, env: dict, label: str) -> str:
    """Ejecuta un agente especializado con un env personalizado."""
    script_path = AGENTS_DIR / script_name
    print(f"\n{'='*60}", flush=True)
    print(f"🤖 Ejecutando: {label}...", flush=True)
    print(f"{'='*60}", flush=True)

    env = {**env, "PYTHONIOENCODING": "utf-8"}

    try:
        result = subprocess.run(
            [PYTHON, str(script_path)],
            input=sanitize(task),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=240,
            env=env
        )
        if result.returncode != 0:
            error_msg = result.stderr.strip()
            print(f"⚠️  {label} falló (exit {result.returncode}): {error_msg[:300]}", flush=True)
            return f"[{label}: Error - {error_msg[:200]}]"

        output = sanitize(result.stdout.strip())
        if not output:
            return f"[{label}: respuesta vacía]"
        print(f"✅ {label} completado ({len(output)} caracteres)", flush=True)
        return output

    except subprocess.TimeoutExpired:
        print(f"⏱️  {label} timeout (240s)", flush=True)
        return f"[{label}: Timeout]"
    except Exception as e:
        print(f"❌ {label} error inesperado: {e}", flush=True)
        return f"[{label}: {str(e)}]"


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


def truncate_report(text: str, max_chars: int = 1500) -> str:
    """Recorta un reporte a max_chars, manteniendo inicio útil."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n\n[... {len(text) - max_chars} caracteres omitidos para síntesis ...]"


def synthesize(tema: str, reports: dict, api_key: str) -> str:
    """Llama al LLM para sintetizar todos los reportes en un paquete ejecutivo.
    Trunca cada reporte para no saturar el contexto del LLM y evitar timeouts."""
    content = f"""Tema del canal: {tema}

## REPORTE 1 - DEEP SEARCH (Tendencias y Keywords)
{truncate_report(reports['deep_search'], 1500)}

## REPORTE 2 - CHANNEL ANALYZER (Competencia)
{truncate_report(reports['channel_analyzer'], 1500)}

## REPORTE 3 - STORYTELLING DESIGNER (Guión)
{truncate_report(reports['storytelling'], 2000)}

## REPORTE 4 - PROMPT GENERATOR (Imágenes)
{truncate_report(reports['prompt_generator'], 800)}

---
Con base en estos 4 reportes, crea el paquete ejecutivo de contenido semanal.
Los reportes completos se adjuntarán al resultado final; aquí solo sintetiza lo esencial."""

    return call_llm(
        messages=[
            {"role": "system", "content": SYNTHESIS_PROMPT.format(tema=tema)},
            {"role": "user", "content": content}
        ],
        api_key=api_key,
        max_tokens=1200,
        temperature=0.6,
        title="Paperclip - Director de Contenido",
        model="anthropic/claude-3-5-haiku",  # mejor calidad para síntesis
        timeout=60,
        retries=1,
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

    # ── Fase 2b: Generación de imágenes reales con Higgsfield ──
    # Pasa el JSON del prompt_generator → imagen.py extrae los prompts Higgsfield optimizados
    imagen_result = "[Imagen Generator: HIGGSFIELD_API_KEY no configurada — omitido]"
    higgsfield_key = os.environ.get("HIGGSFIELD_API_KEY", "")
    if higgsfield_key:
        imagen_env = os.environ.copy()
        imagen_env["HIGGSFIELD_API_KEY"] = higgsfield_key
        imagen_result = run_agent_with_env("imagen.py", prompt_result, imagen_env, "Imagen Generator")
    else:
        print("⚠️  HIGGSFIELD_API_KEY no encontrada — saltando Imagen Generator", flush=True)

    # ── Fase 3: Síntesis ejecutiva ─────────────────────────────
    print(f"\n{'='*60}", flush=True)
    print(f"🧠 Sintetizando paquete ejecutivo...", flush=True)
    print(f"{'='*60}", flush=True)

    reports = {
        "deep_search": deep_search_result,
        "channel_analyzer": channel_result,
        "storytelling": storytelling_result,
        "prompt_generator": prompt_result,
        "imagen": imagen_result,
    }

    try:
        synthesis = synthesize(objetivo, reports, api_key)
    except Exception as e:
        synthesis = f"[Error en síntesis: {e}]"

    # ── Output final ───────────────────────────────────────────
    output = f"""# 🎬 PAQUETE COMPLETO DE CONTENIDO
**Tema:** {objetivo}
**Generado por:** Director de Contenido (5 agentes coordinados)

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

<details>
<summary>🖼️ Imagen Generator - Imágenes generadas con Higgsfield</summary>

{imagen_result}
</details>
"""
    print(output, flush=True)

    # ── Publicar resultado como comentario en el issue (aparece en el inbox) ──
    issue_id   = os.environ.get("PAPERCLIP_ISSUE_ID", "")
    api_url    = os.environ.get("PAPERCLIP_API_URL", "http://localhost:7777")
    agent_id   = os.environ.get("PAPERCLIP_AGENT_ID", "")
    company_id = os.environ.get("PAPERCLIP_COMPANY_ID", "")
    run_id     = os.environ.get("PAPERCLIP_RUN_ID", "director-run")

    # Auth: preferir PAPERCLIP_API_KEY (JWT inyectado por Paperclip),
    # luego generar uno con BETTER_AUTH_SECRET si no está disponible
    api_key_token = os.environ.get("PAPERCLIP_API_KEY", "")
    jwt_secret    = (os.environ.get("PAPERCLIP_AGENT_JWT_SECRET") or os.environ.get("BETTER_AUTH_SECRET", "")).strip()

    print(f"🔍 issue_id={issue_id!r}  api_key={'SET' if api_key_token else 'EMPTY'}  jwt_secret={'SET' if jwt_secret else 'EMPTY'}", flush=True)

    if issue_id:
        auth_headers: dict = {"Content-Type": "application/json"}
        if api_key_token:
            auth_headers["Authorization"] = f"Bearer {api_key_token}"
            print("🔑 Usando PAPERCLIP_API_KEY para autenticación", flush=True)
        elif jwt_secret and agent_id:
            try:
                token = create_agent_jwt(agent_id, company_id, run_id, jwt_secret)
                auth_headers["Authorization"] = f"Bearer {token}"
                print("🔑 JWT generado con BETTER_AUTH_SECRET", flush=True)
            except Exception as e:
                print(f"⚠️  No se pudo generar JWT: {e}", flush=True)
        else:
            print("⚠️  Sin token de autenticación disponible", flush=True)

        # 1. Cerrar el issue PRIMERO → así el check de run_id se omite al postear comentario
        try:
            patch_data = json.dumps({"status": "done"}).encode("utf-8")
            patch_req = urllib.request.Request(
                f"{api_url}/api/issues/{issue_id}",
                data=patch_data,
                headers=auth_headers,
                method="PATCH"
            )
            with urllib.request.urlopen(patch_req, timeout=10) as r:
                print(f"✅ Issue cerrado (HTTP {r.status})", flush=True)
        except Exception as e:
            print(f"⚠️  No se pudo cerrar el issue: {e}", flush=True)

        # 2. Postear el resultado como comentario → aparece en el chat del issue
        try:
            comment_data = json.dumps({"body": output}).encode("utf-8")
            comment_req = urllib.request.Request(
                f"{api_url}/api/issues/{issue_id}/comments",
                data=comment_data,
                headers=auth_headers,
                method="POST"
            )
            with urllib.request.urlopen(comment_req, timeout=15) as r:
                print(f"✅ Resultado publicado en el inbox (HTTP {r.status})", flush=True)
        except Exception as e:
            print(f"⚠️  No se pudo publicar el comentario: {e}", flush=True)


if __name__ == "__main__":
    main()
