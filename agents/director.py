"""
Agente: Director de Contenido
Orquestador principal que coordina los 5 agentes especializados.
Recibe un objetivo de alto nivel y devuelve un paquete completo de contenido.

Flujo:
1. Deep Search      → tendencias + keywords virales
2. Channel Analyzer → análisis de competencia
3. Storytelling     → guión completo del video (4-5 escenas)
4. Prompt Generator → prompts JSON para 5-6 imágenes
5. Imagen Generator → imágenes reales con Higgsfield Soul

Cada agente crea un sub-issue visible en el inbox de Paperclip.
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

# ── IDs de los sub-agentes registrados en Paperclip ─────────────────────────
SUB_AGENT_IDS = {
    "deep_search":       "a1d8d0b8-9ada-4980-9b5f-663b34ba2c80",
    "channel_analyzer":  "0f784ca9-93b0-4384-ba7c-1e079bb8797b",
    "storytelling":      "061ed6b8-27b1-4a31-8758-19af856b45d3",
    "prompt_generator":  "64e2cb07-75e1-4ca2-8b6c-05a78b66613f",
    "imagen_generator":  "2492962a-b9f0-4611-90e2-c7ccca5aa281",
}

AGENTS_DIR = Path(__file__).parent
PYTHON = sys.executable

SYNTHESIS_PROMPT = """Eres el Director de Contenido del canal TikTok @historias.en.sombra.
El canal publica historias REALISTAS con emociones fuertes: traiciones, engaños, infidelidades, manipulaciones.
Estilo: narración en primera persona, tono íntimo y emocional, como si fuera real.
Audiencia: latinos 18-35 años que disfrutan drama relacional y se sienten identificados.

Recibes los reportes de los agentes y los sintetizas en un paquete diario — UN SOLO VIDEO listo para producir y publicar HOY.

---

# 🎬 PAQUETE DIARIO — @historias.en.sombra
## Historia del día: {tema}

---

## 📋 RESUMEN EJECUTIVO (3-4 líneas)
[Por qué esta historia va a viralizar HOY: emoción, identificación, factor sorpresa]

---

## ⚡ ACCIÓN INMEDIATA
1. Grabar hoy
2. Editar + subir antes de la hora pico
3. Responder comentarios en las primeras 2 horas

---

## 🎬 VIDEO DEL DÍA

**Título sugerido:** [título corto, emocional, con gancho]
**Duración:** 60-90 segundos
**Hora de publicación sugerida:** [hora óptima según la audiencia latina]
**Hashtags:** [5-7 hashtags relevantes]

### Hook (primeros 3 segundos)
[Frase exacta a decir]

### Guion listo
[Guion completo en primera persona, tal como debe grabarse]

### CTA final
[Pregunta o provocación al espectador]

---

## 🖼️ IMÁGENES A GENERAR (1 video = 1 thumbnail, máximo)
- **1 thumbnail vertical 9:16** para TikTok

> Solo se genera UNA imagen al día. No saturamos Higgsfield ni tokens.

---

## 📊 KPIs OBJETIVO
- Retención al segundo 3: >85%
- Comentarios esperados: "esto me pasó a mí" / "¿cómo se llama él/ella?"
- Shares objetivo: que lo manden a alguien conocido

---

Sé directo y emocional. Una sola historia bien contada > paquete saturado.
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


# ── Paperclip Sub-Issue Helpers ──────────────────────────────────────────────

def _api_request(method: str, url: str, payload, headers: dict):
    """Hace una llamada HTTP a la API de Paperclip y devuelve el JSON de respuesta."""
    try:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = ""
        try: body = e.read().decode("utf-8", errors="replace")
        except Exception: pass
        print(f"⚠️  API {method} {url} → HTTP {e.code}: {body[:300]}", flush=True)
        return None
    except Exception as e:
        print(f"⚠️  API {method} {url} → {e}", flush=True)
        return None


def create_sub_issue(title: str, agent_key: str, parent_issue_id: str,
                     api_url: str, auth_headers: dict, company_id: str = ""):
    """Crea un sub-issue en Paperclip asignado al sub-agente correspondiente.
    Devuelve el ID del sub-issue creado, o None si falla."""
    if not parent_issue_id or not api_url:
        return None

    sub_agent_id = SUB_AGENT_IDS.get(agent_key)
    payload = {
        "title":    title,
        "status":   "in_progress",
        "parentId": parent_issue_id,
    }
    if sub_agent_id:
        payload["assigneeAgentId"] = sub_agent_id

    # Ruta correcta: /api/companies/:companyId/issues
    url = f"{api_url}/api/companies/{company_id}/issues" if company_id else f"{api_url}/api/issues"
    print(f"  📋 Creando sub-issue: {title!r} (agente: {agent_key})", flush=True)
    result = _api_request("POST", url, payload, auth_headers)

    if result:
        sub_id = result.get("id") or result.get("issue", {}).get("id")
        if sub_id:
            print(f"  ✅ Sub-issue creado → ID: {sub_id}", flush=True)
            return sub_id
    print(f"  ⚠️  No se pudo crear sub-issue para {agent_key}", flush=True)
    return None


def close_sub_issue(sub_issue_id: str, result_text: str,
                    api_url: str, auth_headers: dict) -> None:
    """Publica el resultado como comentario y cierra el sub-issue."""
    if not sub_issue_id:
        return

    # 1. Postear resultado como comentario en el sub-issue
    comment = result_text[:8000]  # límite prudente
    _api_request("POST", f"{api_url}/api/issues/{sub_issue_id}/comments",
                 {"body": comment}, auth_headers)

    # 2. Marcar sub-issue como done
    _api_request("PATCH", f"{api_url}/api/issues/{sub_issue_id}",
                 {"status": "done"}, auth_headers)

    print(f"  ✅ Sub-issue {sub_issue_id} cerrado con resultado", flush=True)


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

    # ── Configurar auth de Paperclip ──────────────────────────
    issue_id   = os.environ.get("PAPERCLIP_ISSUE_ID", "")
    api_url    = os.environ.get("PAPERCLIP_API_URL", "http://localhost:7777")
    agent_id   = os.environ.get("PAPERCLIP_AGENT_ID", "")
    company_id = os.environ.get("PAPERCLIP_COMPANY_ID", "")
    run_id     = os.environ.get("PAPERCLIP_RUN_ID", "director-run")

    api_key_token = os.environ.get("PAPERCLIP_API_KEY", "")
    jwt_secret    = (os.environ.get("PAPERCLIP_AGENT_JWT_SECRET") or os.environ.get("BETTER_AUTH_SECRET", "")).strip()

    print(f"🔍 issue_id={issue_id!r}  api_key={'SET' if api_key_token else 'EMPTY'}  jwt_secret={'SET' if jwt_secret else 'EMPTY'}", flush=True)

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
        print("⚠️  Sin token de autenticación disponible — sub-issues no se crearán", flush=True)

    # ── Helper: ejecuta un agente + gestiona su sub-issue ─────
    def run_tracked(script: str, task: str, label: str, agent_key: str,
                    env_override=None) -> str:
        """Crea sub-issue → ejecuta agente → cierra sub-issue con resultado."""
        sub_id = None
        if issue_id and "Authorization" in auth_headers:
            sub_id = create_sub_issue(
                title=f"🤖 {label}",
                agent_key=agent_key,
                parent_issue_id=issue_id,
                api_url=api_url,
                auth_headers=auth_headers,
                company_id=company_id,
            )

        if env_override is not None:
            result = run_agent_with_env(script, task, env_override, label)
        else:
            result = run_agent(script, task, api_key, label)

        if sub_id:
            close_sub_issue(sub_id, result, api_url, auth_headers)

        return result

    # ── Fase 1: Investigación en paralelo ──────────────────────
    search_task   = f"Busca tendencias virales y keywords de oportunidad para el tema: {objetivo}"
    analyzer_task = f"Analiza los canales más exitosos de YouTube y TikTok sobre: {objetivo}. Encuentra sus debilidades."

    deep_search_result = run_tracked("deep_search.py", search_task,
                                     "Deep Search — Tendencias", "deep_search")
    channel_result     = run_tracked("channel_analyzer.py", analyzer_task,
                                     "Channel Analyzer — Competencia", "channel_analyzer")

    # ── Fase 2: Creación de contenido ──────────────────────────
    storytelling_task = sanitize(f"""Crea un guion viral con 4-5 escenas para el tema: {objetivo}

Contexto de tendencias encontradas:
{deep_search_result[:400]}

Diferenciacion vs competencia:
{channel_result[:250]}""")

    storytelling_result = run_tracked("storytelling.py", storytelling_task,
                                      "Storytelling — Guión 4-5 escenas", "storytelling")

    prompt_task = sanitize(f"""Genera 5-6 prompts JSON (uno por escena) para el guión de: {objetivo}

Guión completo:
{storytelling_result[:800]}""")

    prompt_result = run_tracked("prompt_generator.py", prompt_task,
                                "Prompt Generator — 5-6 imágenes", "prompt_generator")

    # ── Fase 2b: Generación de imágenes reales con Higgsfield ──
    imagen_result  = "[Imagen Generator: HIGGSFIELD_API_KEY no configurada — omitido]"
    higgsfield_key = os.environ.get("HIGGSFIELD_API_KEY", "")
    if higgsfield_key:
        imagen_env = os.environ.copy()
        imagen_env["HIGGSFIELD_API_KEY"] = higgsfield_key
        imagen_result = run_tracked("imagen.py", prompt_result,
                                    "Imagen Generator — Higgsfield Soul", "imagen_generator",
                                    env_override=imagen_env)
    else:
        print("⚠️  HIGGSFIELD_API_KEY no encontrada — saltando Imagen Generator", flush=True)

    # ── Fase 3: Síntesis ejecutiva ─────────────────────────────
    print(f"\n{'='*60}", flush=True)
    print(f"🧠 Sintetizando paquete ejecutivo...", flush=True)
    print(f"{'='*60}", flush=True)

    reports = {
        "deep_search":     deep_search_result,
        "channel_analyzer": channel_result,
        "storytelling":    storytelling_result,
        "prompt_generator": prompt_result,
        "imagen":          imagen_result,
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
<summary>✨ Storytelling - Guión completo (4-5 escenas)</summary>

{storytelling_result}
</details>

<details>
<summary>🪄 Prompt Generator - Prompts de imágenes (5-6)</summary>

{prompt_result}
</details>

<details>
<summary>🖼️ Imagen Generator - Imágenes generadas con Higgsfield Soul</summary>

{imagen_result}
</details>
"""
    print(output, flush=True)

    # ── Publicar resultado en el issue principal ───────────────
    if issue_id and "Authorization" in auth_headers:
        # 1. Cerrar el issue principal
        _api_request("PATCH", f"{api_url}/api/issues/{issue_id}",
                     {"status": "done"}, auth_headers)
        print("✅ Issue principal cerrado", flush=True)

        # 2. Postear el resultado como comentario
        _api_request("POST", f"{api_url}/api/issues/{issue_id}/comments",
                     {"body": output}, auth_headers)
        print("✅ Resultado publicado en el inbox", flush=True)
    elif issue_id:
        print("⚠️  Sin auth — issue no se pudo cerrar", flush=True)


if __name__ == "__main__":
    main()
