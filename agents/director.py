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
from api_client import call_llm, post_issue_comment

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# ── IDs de los sub-agentes registrados en Paperclip ─────────────────────────
SUB_AGENT_IDS = {
    "source_reader":     "a6cc7b6e-cde3-4464-9cbf-3241b979dc6b",
    "deep_search":       "a1d8d0b8-9ada-4980-9b5f-663b34ba2c80",
    "channel_analyzer":  "0f784ca9-93b0-4384-ba7c-1e079bb8797b",
    "storytelling":      "061ed6b8-27b1-4a31-8758-19af856b45d3",
    "prompt_generator":  "64e2cb07-75e1-4ca2-8b6c-05a78b66613f",
    "imagen_generator":  "2492962a-b9f0-4611-90e2-c7ccca5aa281",
    "tts":               "0d43b313-77b5-481b-83cc-a41485823f8e",
    "video_assembler":   "28f0a4aa-a230-4d82-aedf-4c327ab4a506",
}

AGENTS_DIR = Path(__file__).parent
PYTHON = sys.executable

SYNTHESIS_PROMPT = """Eres el Director Creativo de un canal de TikTok/YouTube en español que ya tiene millones de vistas. Recibes los reportes completos de 4 agentes especializados (tendencias, análisis de competencia, guión y referencias visuales) y los conviertes en un brief de producción listo para ejecutar ahora mismo.

Tu síntesis no es un resumen burocrático. Es un documento de guerra creativa — conciso, específico, sin relleno, con el guión completo y las instrucciones exactas para que cualquier editor o creador lo tome y sepa exactamente qué hacer.

REGLAS ABSOLUTAS:
- CERO placeholders. Nada de [NOMBRE], [CIUDAD], [HASHTAG]. Escribe el contenido real.
- El HOOK son las primeras palabras EXACTAS que se dicen en cámara — no "algo que genere curiosidad", las palabras textuales.
- El GUIÓN completo viene del Reporte 3 (Storytelling). Cópialo íntegro, todas las escenas con su narración. No lo resumas.
- Adapta ABSOLUTAMENTE TODO al nicho: el tono del ejecutivo cambia entre drama personal, finanzas, tech o fitness.
- Los HASHTAGS son específicos para este video y nicho — no los genéricos de siempre.

## ESTRUCTURA OBLIGATORIA:

## 🎯 POR QUÉ ESTE VIDEO VA A FUNCIONAR
[3 razones específicas basadas en los datos de los reportes: qué tendencia aprovecha, qué emoción dominante activa, qué hace diferente a lo que ya existe en el nicho. Sin generalidades.]

## 🎬 BRIEF DE PRODUCCIÓN

**Título del video:** [exacto, máximo 8 palabras, que genere intriga o curiosidad irresistible]
**Duración objetivo:** [segundos exactos según el nicho y los datos del Channel Analyzer]
**Plataforma prioritaria:** [TikTok / YouTube Shorts / ambas — con justificación de 1 línea]
**Publicar a las:** [hora exacta en LATAM según el nicho y la audiencia]

---

### ⚡ HOOK — Las primeras palabras exactas
[Escribe literalmente las 2-3 primeras frases que abren el video. El espectador las oye antes de poder decidir si se queda. Deben ser las más fuertes del video entero.]

---

### 📜 GUIÓN COMPLETO
[Transcribe aquí el guión completo del Reporte 3 — Storytelling. Escena por escena, con la narración completa tal como se grabará. No resumas, no cambies la estructura. Si el storytelling agent no está disponible, escribe el guión completo desde cero basándote en los otros reportes.]

---

### 💬 CTA FINAL
[La frase exacta de cierre que dispara comentarios. Debe ser una pregunta personal, fácil de responder, que conecte la historia del video con la vida del espectador.]

---

## 📱 ESTRATEGIA DE PUBLICACIÓN

**Hashtags:** [10 hashtags específicos — mezcla de grandes (#viral, #parati) y de nicho (#dramasrelaciones, #historiasverdaderas)]
**Miniatura:** [descripción exacta de la imagen del thumbnail: qué se ve, expresión facial, texto overlay, colores]
**Primer comentario fijado:** [el comentario que el creador debe fijar para disparar la conversación]
**Respuesta a los primeros 3 comentarios:** [qué tipo de respuesta maximiza el engagement en la primera hora]

## 📊 INDICADORES DE ÉXITO
- Retención en segundo 3: objetivo >80%
- Drop-off crítico a vigilar: segundo [X según la estructura del guión]
- Comentario tipo que indica que el video está funcionando: "[frase que la audiencia usará]"
- Si en 2 horas no tiene [N] comentarios, considerar: [ajuste específico]
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
                     api_url: str, auth_headers: dict, company_id: str = "",
                     description: str = "", assignee_agent_id: str = ""):
    """Crea un sub-issue en Paperclip.
    - description: tarea del agente (inyectada como PAPERCLIP_ISSUE_BODY)
    - assignee_agent_id: ID del agente Paperclip que lo ejecutará
    Devuelve el ID del sub-issue creado, o None si falla."""
    if not parent_issue_id or not api_url:
        return None

    payload = {
        "title":    title,
        "status":   "backlog",
        "parentId": parent_issue_id,
    }
    if description:
        payload["description"] = description[:4000]
    if assignee_agent_id:
        payload["assigneeAgentId"] = assignee_agent_id

    url = f"{api_url}/api/companies/{company_id}/issues" if company_id else f"{api_url}/api/issues"
    print(f"  📋 Creando sub-issue: {title!r}", flush=True)
    result = _api_request("POST", url, payload, auth_headers)

    if result:
        sub_id = result.get("id") or result.get("issue", {}).get("id")
        if sub_id:
            print(f"  ✅ Sub-issue creado → ID: {sub_id}", flush=True)
            return sub_id
    print(f"  ⚠️  No se pudo crear sub-issue para {agent_key}", flush=True)
    return None


def _wait_for_sub_agent(sub_id: str, label: str, api_url: str,
                        auth_headers: dict, timeout: int = 240) -> str | None:
    """Espera a que Paperclip despache y complete el sub-agente.
    Devuelve el resultado (último comentario) o None si hay timeout."""
    deadline = time.time() + timeout
    last_log  = 0
    while time.time() < deadline:
        time.sleep(7)
        data = _api_request("GET", f"{api_url}/api/issues/{sub_id}", None, auth_headers)
        if data:
            status = data.get("status", "")
            if status == "done":
                comments = _api_request("GET", f"{api_url}/api/issues/{sub_id}/comments",
                                        None, auth_headers)
                if comments:
                    items = (comments if isinstance(comments, list)
                             else comments.get("comments") or comments.get("items") or [])
                    if items:
                        # Tomar el comentario más largo: es el resultado real del agente.
                        # La API puede devolver newest-first o oldest-first; el JSON/markdown
                        # del resultado siempre será mucho más largo que el mensaje de confirmación.
                        best = max(items, key=lambda c: len(c.get("body", "") or ""))
                        return best.get("body", "") or "[sin contenido]"
                return "[Agente terminó sin comentario de resultado]"
            elif status == "cancelled":
                return f"[{label}: cancelado]"
        if time.time() - last_log > 30:
            elapsed = int(time.time() - (deadline - timeout))
            print(f"  ⏳ Esperando {label}... ({elapsed}s/{timeout}s)", flush=True)
            last_log = time.time()
    return None  # timeout → activar fallback subprocess


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


def run_agent_with_env(script_name: str, task: str, env: dict, label: str,
                       timeout: int = 120) -> str:
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
            timeout=timeout,
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

## REPORTE 3 - STORYTELLING DESIGNER (Guión completo — transcríbelo en el output)
{truncate_report(reports['storytelling'], 3500)}

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
        max_tokens=2000,
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

    # Leer objetivo desde stdin o args (fallback)
    if len(sys.argv) > 1:
        objetivo = " ".join(sys.argv[1:])
    else:
        objetivo = sys.stdin.read().strip()

    # Leer contexto desde env (proceso local o adapter que los inyecta)
    issue_title = os.environ.get("PAPERCLIP_ISSUE_TITLE", "").strip()
    issue_body  = os.environ.get("PAPERCLIP_ISSUE_BODY", "").strip()

    print(f"🎯 DIRECTOR DE CONTENIDO INICIANDO", flush=True)

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

    # ── Obtener título del issue desde la API si no llegó por env ─
    # El wakeup de Paperclip solo pasa issueId en el payload, no el título.
    # PAPERCLIP_ISSUE_TITLE queda vacío → el Director siempre usaba el objetivo
    # por defecto. Solución: hacer GET del issue y leer su título real.
    if not issue_title and issue_id and "Authorization" in auth_headers:
        _issue_data = _api_request("GET", f"{api_url}/api/issues/{issue_id}", None, auth_headers)
        if _issue_data:
            issue_title = (_issue_data.get("title") or "").strip()
            issue_body  = (_issue_data.get("description") or "").strip()
            if issue_title:
                print(f"📥 Título obtenido de la API: {issue_title!r}", flush=True)

    # ── Construir objetivo final ───────────────────────────────
    import re as _re  # importar aquí para que esté disponible en todo el scope de main()

    if issue_title:
        objetivo = f"{issue_title}\n\n{issue_body}" if issue_body else issue_title
        has_tts = bool(os.environ.get("ELEVENLABS_API_KEY", ""))
        has_hf  = bool(os.environ.get("HIGGSFIELD_API_KEY", ""))

        # Detectar URLs en el body para saber si hay source ingestion
        _body_urls = _re.findall(r"https?://[^\s<>\"'\)\]]+", issue_body) if issue_body else []
        _has_src   = len(_body_urls) > 0
        _total_agents = (1 if _has_src else 0) + (7 if has_tts and has_hf else 5)

        # ── Kickoff message ──────────────────────────────────────
        _phase  = 1
        _phases = ""
        if _has_src:
            _src_types = []
            for _u in _body_urls:
                if "youtube.com" in _u or "youtu.be" in _u:
                    _src_types.append("YouTube")
                elif _u.endswith(".pdf"):
                    _src_types.append("PDF")
                else:
                    _src_types.append("web")
            _src_label = ", ".join(dict.fromkeys(_src_types)) or "web"
            _phases += f"{_phase}️⃣ **Source Reader** — extraigo contenido real de {len(_body_urls)} fuente(s) ({_src_label})\n"
            _phase += 1
        _phases += f"{_phase}️⃣ **Deep Search** — tendencias virales del nicho\n"; _phase += 1
        _phases += f"{_phase}️⃣ **Channel Analyzer** — análisis de la competencia\n"; _phase += 1
        _phases += f"{_phase}️⃣ **Storytelling** — guión {'basado en tus fuentes' if _has_src else 'adaptado al nicho'}\n"; _phase += 1
        if has_tts:
            _phases += f"{_phase}️⃣ **TTS** — voz en off con ElevenLabs\n"; _phase += 1
        _phases += f"{_phase}️⃣ **Prompt Generator** — prompts de imagen por escena\n"; _phase += 1
        if has_hf:
            _phases += f"{_phase}️⃣ **Imagen Generator** — imágenes con Higgsfield Soul\n"; _phase += 1
        if has_tts and has_hf:
            _phases += f"{_phase}️⃣ **Video Assembler** — MP4 final con voz en off\n"; _phase += 1

        _eta = 10 if _has_src and has_tts and has_hf else (8 if has_tts and has_hf else 5)

        _src_tip = (
            f"\n\n📌 **Fuentes detectadas ({len(_body_urls)}):**\n"
            + "\n".join(f"  - `{u[:70]}`" for u in _body_urls[:5])
            + ("\n  - ..." if len(_body_urls) > 5 else "")
        ) if _has_src else (
            "\n\n💡 **Tip:** Pega URLs en la descripción del issue para activar el **Source Reader**"
            " — artículos web, videos de YouTube o PDFs se convierten en la base factual del video."
        )

        post_issue_comment(
            f"🎬 Perfecto, me pongo en marcha con: **{issue_title}**\n\n"
            f"Coordino **{_total_agents} agentes** en secuencia:\n"
            + _phases
            + f"\n⏱️ Listo en ~{_eta} minutos."
            + _src_tip
        )
    elif not objetivo:
        objetivo = "crea contenido viral para TikTok y YouTube en español"

    print(f"📌 Objetivo: {objetivo[:120]}", flush=True)

    # ── Guardia: salir si el issue ya está cerrado ────────────
    # Previene re-runs de getWakeableParentAfterChildCompletion: cuando todos los
    # sub-issues terminan, Paperclip re-despierta al Director. Si el issue ya está
    # done (el Director ya terminó), salimos inmediatamente.
    if issue_id and "Authorization" in auth_headers:
        _guard = _api_request("GET", f"{api_url}/api/issues/{issue_id}", None, auth_headers)
        if _guard and _guard.get("status") in ("done", "cancelled"):
            print(f"⛔ Issue ya está '{_guard.get('status')}' — saliendo para evitar re-run duplicado", flush=True)
            sys.exit(0)

    # ── Checkout del issue al inicio ─────────────────────────
    # Usar POST /checkout en vez de PATCH directo: esto setea TANTO status=in_progress
    # COMO checkoutRunId=<run_id del JWT>, lo que permite que los comentarios y el
    # PATCH final funcionen sin 409. El PATCH final será in_progress→done, que NO
    # dispara statusChangedFromBacklog → sin re-run extra.
    if issue_id and agent_id and "Authorization" in auth_headers:
        try:
            _api_request(
                "POST",
                f"{api_url}/api/issues/{issue_id}/checkout",
                {
                    "agentId": agent_id,
                    "expectedStatuses": ["backlog", "todo", "in_review", "blocked", "in_progress"],
                },
                auth_headers,
            )
            print("✅ Checkout exitoso — issue en in_progress con runId registrado", flush=True)
        except Exception as _e:
            print(f"⚠️  Checkout falló (continuando de todas formas): {_e}", flush=True)

    # Agentes que históricamente fallan el dispatch de Paperclip y deben correr
    # directo como subprocess para no desperdiciar tiempo en el timeout de 240s.
    # El Director tiene un límite de ~300s en Railway — si TTS espera 240s, muere todo.
    # Estos agentes se crean como sub-issue (visibilidad en inbox) pero se ejecutan localmente.
    SUBPROCESS_ONLY = {"tts", "video_assembler", "source_reader"}

    # ── Helper: orquesta un sub-agente vía Paperclip ──────────
    def run_tracked(script: str, task: str, label: str, agent_key: str,
                    extra_env: dict = None, paperclip_timeout: int = 180) -> str:
        """
        Estrategia de orquestación real:
        1. Crea sub-issue con assigneeAgentId + description (tarea) → visible en inbox
        2. Si el agente responde a statusChangedFromBacklog → espera resultado (polling)
        3. Si timeout o SUBPROCESS_ONLY → fallback a subprocess local
        4. Cierra el sub-issue con el resultado
        """
        assignee_id = SUB_AGENT_IDS.get(agent_key, "")
        sub_id = None

        if issue_id and "Authorization" in auth_headers:
            sub_id = create_sub_issue(
                title=f"🤖 {label}",
                agent_key=agent_key,
                description=task,
                assignee_agent_id=assignee_id,
                parent_issue_id=issue_id,
                api_url=api_url,
                auth_headers=auth_headers,
                company_id=company_id,
            )

        # Agentes que van directo a subprocess (sin esperar dispatch de Paperclip)
        use_subprocess_directly = agent_key in SUBPROCESS_ONLY or not assignee_id

        if sub_id and assignee_id and not use_subprocess_directly:
            # PATCH a 'todo' → statusChangedFromBacklog → Paperclip despacha el sub-agente
            _api_request("PATCH", f"{api_url}/api/issues/{sub_id}", {"status": "todo"}, auth_headers)
            print(f"  🚀 {label} despachado — esperando que Paperclip lo complete...", flush=True)

            result = _wait_for_sub_agent(sub_id, label, api_url, auth_headers,
                                         timeout=paperclip_timeout)
            if result is not None:
                print(f"  ✅ {label} completado vía Paperclip ({len(result)} caracteres)", flush=True)
                return result

            print(f"  ⚠️  Timeout esperando {label} — usando subprocess como fallback...", flush=True)
            _api_request("PATCH", f"{api_url}/api/issues/{sub_id}", {"status": "in_progress"}, auth_headers)

        elif sub_id:
            # Sub-issue visible pero ejecución local inmediata
            _api_request("PATCH", f"{api_url}/api/issues/{sub_id}", {"status": "in_progress"}, auth_headers)

        # ── Subprocess (directo o fallback) ──────────────────
        sub_env = {**os.environ}
        if extra_env:
            sub_env.update(extra_env)
        if sub_id:
            sub_env["PAPERCLIP_ISSUE_ID"] = sub_id
        else:
            sub_env.pop("PAPERCLIP_ISSUE_ID", None)
        sub_env.pop("PAPERCLIP_ISSUE_TITLE", None)
        sub_env.pop("PAPERCLIP_ISSUE_BODY", None)

        # Video Assembler necesita hasta 270s (ffmpeg por imagen a ultrafast).
        # TTS necesita ~90s (ElevenLabs + upload).
        if agent_key == "video_assembler":
            _subprocess_timeout = 270
        elif agent_key == "tts":
            _subprocess_timeout = 120
        else:
            _subprocess_timeout = 90
        result = run_agent_with_env(script, task, sub_env, label, timeout=_subprocess_timeout)

        # Cerrar el sub-issue con el resultado
        if sub_id:
            if result and not (result.startswith('[') and 'Error' in result):
                close_sub_issue(sub_id, result, api_url, auth_headers)
            else:
                close_sub_issue(sub_id, result or '[Sin resultado]', api_url, auth_headers)

        return result

    import re as _re

    # ── Fase 0: Source Reader (solo si hay URLs en el body) ───
    source_context  = ""
    source_result   = ""
    _urls_in_body   = _re.findall(r"https?://[^\s<>\"'\)\]]+", issue_body) if issue_body else []
    has_sources     = len(_urls_in_body) > 0

    if has_sources:
        _src_count = len(_urls_in_body)
        post_issue_comment(
            f"📚 **Fase 0 — Source Reader** en progreso…\n\n"
            f"Detecté {_src_count} fuente(s) en la descripción. "
            f"Extraigo el contenido real para basar el video en información verificada."
        )
        source_result = run_tracked(
            "source_reader.py", issue_body,
            "Source Reader — Ingesta de fuentes", "source_reader"
        )
        # Extraer la síntesis del JSON de resultado
        try:
            _src_m = _re.search(r'\{[\s\S]*?"synthesis"[\s\S]*?\}', source_result)
            if _src_m:
                _src_data    = json.loads(_src_m.group(0))
                source_context = _src_data.get("synthesis", "")
                # Si el topic extraído es más específico, úsalo
                _src_topic   = _src_data.get("topic", "")
                if _src_topic and len(_src_topic) > 5:
                    objetivo = f"{objetivo} — basado en fuentes: {_src_topic}"
        except Exception:
            source_context = source_result[:2000]
        print(f"📚 Source context: {len(source_context)} chars", flush=True)

    # ── Fase 1: Investigación ──────────────────────────────────
    _source_hint  = f"\n\nFUENTES REALES PROCESADAS:\n{source_context[:800]}" if source_context else ""
    search_task   = f"Busca tendencias virales y keywords de oportunidad para el tema: {objetivo}{_source_hint}"
    analyzer_task = f"Analiza los canales más exitosos de YouTube y TikTok sobre: {objetivo}. Encuentra sus debilidades.{_source_hint}"

    post_issue_comment(f"🔍 **Fase {'2' if has_sources else '1'} — Deep Search** en progreso…")
    deep_search_result = run_tracked("deep_search.py", search_task,
                                     "Deep Search — Tendencias", "deep_search")

    post_issue_comment(f"📊 **Fase {'3' if has_sources else '2'} — Channel Analyzer** en progreso…")
    channel_result     = run_tracked("channel_analyzer.py", analyzer_task,
                                     "Channel Analyzer — Competencia", "channel_analyzer")

    # ── Fase 2: Guión ─────────────────────────────────────────
    _source_block = ""
    if source_context:
        _source_block = f"\n\nCONTENIDO REAL DE LAS FUENTES (úsalo como base factual del guión):\n{source_context[:1500]}"

    storytelling_task = sanitize(f"""Crea un guion viral con 4-5 escenas para el tema: {objetivo}
{_source_block}

Contexto de tendencias encontradas:
{deep_search_result[:400]}

Diferenciacion vs competencia:
{channel_result[:250]}""")

    post_issue_comment("✍️ **Fase 3 — Storytelling** en progreso…")
    storytelling_result = run_tracked("storytelling.py", storytelling_task,
                                      "Storytelling — Guión 4-5 escenas", "storytelling")

    # ── Fase 3: TTS (voz en off) ──────────────────────────────
    tts_result      = ""
    audio_path      = ""
    audio_url_tts   = ""
    elevenlabs_key  = os.environ.get("ELEVENLABS_API_KEY", "")
    if elevenlabs_key:
        post_issue_comment("🎙️ **Fase 4 — TTS (voz en off)** en progreso…")
        tts_result = run_tracked(
            "tts.py", storytelling_result,
            "TTS — Voz en off", "tts",
            extra_env={"ELEVENLABS_API_KEY": elevenlabs_key},
            paperclip_timeout=90,  # falla rápido → subprocess directo
        )
        # Extraer audio_path y audio_url del JSON que devuelve tts.py.
        # tts_result mezcla logs + JSON en stdout → buscar el JSON con regex.
        try:
            _m = _re.search(r'\{[\s\S]*?"audio_(?:path|url)"[\s\S]*?\}', tts_result)
            if _m:
                _tts_data = json.loads(_m.group(0))
                audio_path    = _tts_data.get("audio_path", "")
                audio_url_tts = _tts_data.get("audio_url", "")
        except Exception:
            pass
        # Fallback: buscar el MP3 más reciente en /tmp si el parsing falló
        if not audio_path or not os.path.exists(audio_path):
            import glob as _glob
            _mp3s = sorted(_glob.glob("/tmp/narration_*.mp3"), key=os.path.getmtime, reverse=True)
            audio_path = _mp3s[0] if _mp3s else ""
        print(f"🎙️ Audio path: {audio_path or 'no disponible'}", flush=True)
        print(f"🔗 Audio URL TTS: {audio_url_tts[:80] if audio_url_tts else 'no disponible'}", flush=True)
    else:
        print("⚠️  ELEVENLABS_API_KEY no encontrada — saltando TTS", flush=True)

    # ── Fase 4: Imágenes ──────────────────────────────────────
    prompt_task = sanitize(f"""Genera 5-6 prompts JSON (uno por escena) para el guión de: {objetivo}

Guión completo:
{storytelling_result[:4500]}""")

    post_issue_comment("🎨 **Fase 5 — Prompt Generator** en progreso…")
    prompt_result = run_tracked("prompt_generator.py", prompt_task,
                                "Prompt Generator — 5-6 imágenes", "prompt_generator")

    imagen_result  = "[Imagen Generator: HIGGSFIELD_API_KEY no configurada — omitido]"
    higgsfield_key = os.environ.get("HIGGSFIELD_API_KEY", "")
    if higgsfield_key:
        post_issue_comment("🖼️ **Fase 6 — Imagen Generator** en progreso… (puede tardar 2-3 min)")
        imagen_result = run_tracked("imagen.py", prompt_result,
                                    "Imagen Generator — Higgsfield Soul", "imagen_generator",
                                    extra_env={"HIGGSFIELD_API_KEY": higgsfield_key})
    else:
        print("⚠️  HIGGSFIELD_API_KEY no encontrada — saltando Imagen Generator", flush=True)

    # ── Fase 5: Video (imágenes + voz) ───────────────────────
    video_result = ""
    video_url    = ""
    if elevenlabs_key and higgsfield_key:
        # Extraer URLs de imágenes para pasarlas al video assembler
        # 1. URLs con extensión conocida (.png/.jpg/.jpeg/.webp)
        _ext_urls  = _re.findall(r"https?://[^\s\"')]+\.(?:png|jpg|jpeg|webp)", imagen_result)
        # 2. **URL:** formato que imagen.py escribe explícitamente — más fiable que markdown
        _bold_urls = _re.findall(r"\*\*URL:\*\*\s*(https?://\S+)", imagen_result)
        # 3. URLs en sintaxis markdown ](url) — permisivo, no depende del label
        _md_urls   = _re.findall(r"\]\((https?://[^\s)]+)\)", imagen_result)
        _img_urls  = list(dict.fromkeys(_ext_urls + _bold_urls + _md_urls))
        print(f"  🖼️  URLs de imágenes detectadas: {len(_img_urls)}", flush=True)
        for _u in _img_urls[:6]:
            print(f"     • {_u[:90]}", flush=True)
        if _img_urls:
            video_task = sanitize(json.dumps({
                "image_urls": _img_urls,
                "audio_path": audio_path,
                "audio_url":  audio_url_tts,   # fallback si audio_path no existe en el contenedor
                "tema": objetivo[:100],
            }, ensure_ascii=False))
            post_issue_comment("🎬 **Fase 7 — Video Assembler** en progreso… ensamblando MP4 final…")
            video_result = run_tracked("video_assembler.py", video_task,
                                       "Video Assembler — MP4 final", "video_assembler",
                                       paperclip_timeout=60)
            try:
                # video_result es stdout mixto — extraer bloque JSON
                _vid_match = _re.search(r'\{[\s\S]*?"video_url"[\s\S]*?\}', video_result)
                if _vid_match:
                    _vid_data = json.loads(_vid_match.group(0))
                    video_url = _vid_data.get("video_url", "")
            except Exception:
                pass
        else:
            print("⚠️  Sin imágenes o audio — saltando Video Assembler", flush=True)

    # ── Síntesis ejecutiva ────────────────────────────────────
    print(f"\n{'='*60}", flush=True)
    print("🧠 Sintetizando paquete ejecutivo...", flush=True)
    print(f"{'='*60}", flush=True)

    reports = {
        "deep_search":      deep_search_result,
        "channel_analyzer": channel_result,
        "storytelling":     storytelling_result,
        "prompt_generator": prompt_result,
        "imagen":           imagen_result,
    }

    try:
        synthesis = synthesize(objetivo, reports, api_key)
    except Exception as e:
        synthesis = f"[Error en síntesis: {e}]"

    # ── Extraer URLs de imágenes para galería ────────────────
    _raw_ext   = _re.findall(r"https?://[^\s\"')]+\.(?:png|jpg|jpeg|webp)", imagen_result)
    _raw_bold  = _re.findall(r"\*\*URL:\*\*\s*(https?://\S+)", imagen_result)
    _raw_md    = _re.findall(r"\]\((https?://[^\s)]+)\)", imagen_result)
    imagen_urls = list(dict.fromkeys(_raw_ext + _raw_bold + _raw_md))

    # ── Construir output final ────────────────────────────────
    imagen_gallery = ""
    if imagen_urls:
        imagen_gallery = "\n## 🖼️ IMÁGENES GENERADAS\n"
        for i, url in enumerate(imagen_urls, 1):
            imagen_gallery += f"![Imagen {i}]({url})\n"
        imagen_gallery += "\n"

    source_section = ""
    if source_result:
        try:
            _sd = json.loads(_re.search(r'\{[\s\S]*?\}', source_result).group(0))
            _src_urls = _sd.get("sources", [])
            if _src_urls:
                source_section = "\n## 📚 FUENTES UTILIZADAS\n"
                for _su in _src_urls:
                    source_section += f"- {_su}\n"
                source_section += "\n"
        except Exception:
            pass

    video_section = ""
    if video_url:
        video_section = f"\n## 🎬 VIDEO GENERADO\n📥 [Descargar MP4]({video_url})\n\n"

    tts_section = ""
    if tts_result:
        try:
            # tts_result es stdout mixto (logs + JSON al final) — extraer el bloque JSON
            _tts_match = _re.search(r'\{[\s\S]*?"audio_url"[\s\S]*?\}', tts_result)
            if _tts_match:
                _tts = json.loads(_tts_match.group(0))
                if _tts.get("audio_url"):
                    tts_section = f"\n## 🎙️ VOZ EN OFF\n📥 [Descargar MP3]({_tts['audio_url']}) — {_tts.get('duration_estimate','')}\n\n"
        except Exception:
            pass

    output = f"""# 🎬 PAQUETE COMPLETO DE CONTENIDO
**Tema:** {objetivo}
**Generado por:** Director de Contenido ({(1 if has_sources else 0) + (7 if elevenlabs_key and higgsfield_key else 5)} agentes coordinados)
{source_section}{video_section}{tts_section}{imagen_gallery}
{synthesis}

---

## 📎 REPORTES DETALLADOS

<details>
<summary>🔍 Deep Search - Tendencias completas</summary>

{deep_search_result[:3000]}
</details>

<details>
<summary>🔭 Channel Analyzer - Análisis competencia</summary>

{channel_result[:2000]}
</details>

<details>
<summary>✨ Storytelling - Guión completo (4-5 escenas)</summary>

{storytelling_result[:3500]}
</details>

<details>
<summary>🪄 Prompt Generator - Prompts de imágenes (5-6)</summary>

{prompt_result[:3500]}
</details>

<details>
<summary>🖼️ Imagen Generator - Imágenes generadas con Higgsfield Soul</summary>

{imagen_result[:3000]}
</details>
{("<details><summary>🎙️ TTS - Audio narración</summary>" + chr(10) + tts_result[-2000:] + chr(10) + "</details>") if tts_result else ""}
{("<details><summary>🎬 Video Assembler - Video final</summary>" + chr(10) + video_result[-2000:] + chr(10) + "</details>") if video_result else ""}
{("<details><summary>📚 Source Reader - Fuentes procesadas</summary>" + chr(10) + source_result[-2000:] + chr(10) + "</details>") if source_result else ""}
"""
    print(output, flush=True)

    # ── Publicar resultado en el issue principal ───────────────
    if issue_id and "Authorization" in auth_headers:
        # 1. Postear el resultado PRIMERO como comentario
        _api_request("POST", f"{api_url}/api/issues/{issue_id}/comments",
                     {"body": output}, auth_headers)
        print("✅ Resultado publicado en el inbox", flush=True)

        # 2. Cerrar el issue DESPUÉS (el frontend detecta 'done' y ya hay comentario)
        _api_request("PATCH", f"{api_url}/api/issues/{issue_id}",
                     {"status": "done"}, auth_headers)
        print("✅ Issue principal cerrado", flush=True)
    elif issue_id:
        print("⚠️  Sin auth — issue no se pudo cerrar", flush=True)


if __name__ == "__main__":
    main()
