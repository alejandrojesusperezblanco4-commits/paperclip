"""
Agente: TTS (Text-to-Speech)
Convierte el guión del storytelling en audio narrado con ElevenLabs.
Extrae las narraciones de voz en off de cada escena y genera un MP3.
"""
import os
import sys
import re
import json
import time
import urllib.request
import urllib.error
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from api_client import post_issue_result, post_issue_comment, resolve_issue_context

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ELEVENLABS_API  = "https://api.elevenlabs.io/v1"
DEFAULT_VOICE   = "ErXwobaYiN019PkySvjV"   # Antoni — multilingual, dramático
MODEL_ID        = "eleven_multilingual_v2"  # mejor para español


def _clean_narration_text(text: str) -> str:
    """
    Limpia el texto narrado de instrucciones de dirección que no deben leerse en voz alta.
    Elimina:
      - Acotaciones entre paréntesis: (voz en off), (emocionado), (pausa dramática)...
      - Acotaciones entre corchetes: [música tensa], [corte a negro]...
      - Etiquetas de rol: "Voz en off:", "VOZ EN OFF:", "Narrador:", "NARRACIÓN:"...
      - Indicaciones de stage direction al inicio de línea
      - Markdown residual: **, __, ##, ---
    """
    # Eliminar acotaciones entre paréntesis (instrucciones de dirección)
    text = re.sub(r'\([^)]{0,80}\)', '', text)
    # Eliminar acotaciones entre corchetes
    text = re.sub(r'\[[^\]]{0,80}\]', '', text)
    # Eliminar etiquetas de rol al inicio del fragmento o de una frase
    text = re.sub(
        r'(?i)\b(voz\s+en\s+off|narrador[a]?|narración|off[-\s]?camera|voice[-\s]?over)\s*[:：\-–]?\s*',
        '', text
    )
    # Eliminar markdown residual
    text = re.sub(r'\*{1,3}|_{1,3}|#{1,6}\s*|---+', '', text)
    # Colapsar espacios y puntuación doble
    text = re.sub(r'\s{2,}', ' ', text)
    text = re.sub(r'([.,;:!?])\s*\1+', r'\1', text)
    text = re.sub(r'^\s*[,;:.]\s*', '', text)
    return text.strip()


def extract_narration(script: str) -> str:
    """
    Extrae solo el texto de narración (🎙️) del guión de storytelling.
    También elimina secciones no narrativas: visual, micro-hook, duración, ficha técnica.
    """
    parts = []
    in_narration = False

    # Secciones que señalan que NO es narración y deben ignorarse
    NON_NARRATION_MARKERS = (
        "🎬", "⏱️", "━━", "⚡", "🎵", "📌", "#️⃣", "💬", "🔁",
        "VISUAL:", "MICRO-HOOK", "DURACIÓN:", "MÚSICA:", "TÍTULO:",
        "HASHTAGS:", "CTA FINAL:", "PARTE 2",
    )

    # Líneas que son claramente instrucciones de dirección (inicio de línea)
    DIRECTION_PREFIXES = (
        "Plano", "Iluminación", "Fondo", "Ambiente", "Encuadre",
        "Corte a", "Transición", "Efecto", "Música:", "Sonido:",
        "VISUAL", "ESCENA", "Escena", "INT.", "EXT.",
    )

    for line in script.split("\n"):
        stripped = line.strip()

        # Activar captura de narración
        if "🎙️" in stripped or re.search(r'\bNARRACI[OÓ]N\b', stripped, re.IGNORECASE):
            in_narration = True
            # Capturar contenido después del marcador en la misma línea
            # Usar flags=re.IGNORECASE en llamada separada (Python 3.13 no permite (?i) inline en alternados)
            after = re.sub(r'🎙️\s*', '', stripped)
            after = re.sub(r'\bNARRACI[OÓ]N\s*[:：]?\s*', '', after, flags=re.IGNORECASE).strip()
            if after:
                parts.append(after)
            continue

        if in_narration:
            # Detener si encontramos un marcador de otra sección
            if any(marker in stripped for marker in NON_NARRATION_MARKERS):
                in_narration = False
                continue
            # Detener en encabezados de escena nuevos (ej: "ESCENA 2 — ...")
            if re.match(r'^ESCENA\s+\d', stripped, re.IGNORECASE):
                in_narration = False
                continue
            if stripped:
                # Filtrar líneas que son instrucciones de dirección
                if not any(stripped.startswith(p) for p in DIRECTION_PREFIXES):
                    parts.append(stripped)

    narration = " ".join(parts).strip()

    # Limpiar acotaciones, etiquetas de rol y markdown
    narration = _clean_narration_text(narration)
    # Colapsar espacios extra
    narration = re.sub(r'\s+', ' ', narration)
    narration = re.sub(r'\.{3,}', '...', narration)

    if narration:
        print(f"  📝 Narración extraída: {len(narration.split())} palabras", flush=True)
        return narration

    # Fallback: usar todo el texto del issue, quitando líneas de instrucción
    print("  ⚠️  No se detectó sección 🎙️ — usando texto completo como narración", flush=True)
    lines = [l.strip() for l in script.split("\n") if l.strip()
             and not any(m in l for m in NON_NARRATION_MARKERS)
             and not l.strip().startswith("#")]
    fallback = " ".join(lines)[:3000]
    return _clean_narration_text(fallback)


def get_best_voice(api_key: str) -> str:
    """Busca la mejor voz disponible para español dramático."""
    preferred = ["mateo", "antonio", "pablo", "miguel", "carlos",
                 "adam", "josh", "arnold", "Antoni"]
    try:
        req = urllib.request.Request(
            f"{ELEVENLABS_API}/voices",
            headers={"xi-api-key": api_key, "Accept": "application/json"},
            method="GET"
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            voices = json.loads(r.read().decode("utf-8")).get("voices", [])
        name_map = {v["name"].lower(): v["voice_id"] for v in voices}
        for name in preferred:
            if name.lower() in name_map:
                vid = name_map[name.lower()]
                print(f"  🎤 Voz seleccionada: {name} ({vid})", flush=True)
                return vid
    except Exception as e:
        print(f"  ⚠️  No se pudo listar voces: {e}", flush=True)
    print(f"  🎤 Usando voz por defecto: Antoni", flush=True)
    return DEFAULT_VOICE


def generate_audio(text: str, voice_id: str, api_key: str, output_path: str) -> bool:
    """Llama a ElevenLabs TTS y guarda el MP3 en output_path."""
    payload = json.dumps({
        "text": text,
        "model_id": MODEL_ID,
        "voice_settings": {
            "stability": 0.35,        # más bajo = más expresivo y dramático
            "similarity_boost": 0.80,  # fidelidad a la voz base
            "style": 0.55,             # más estilo = más emoción en pausas y énfasis
            "use_speaker_boost": True
        }
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{ELEVENLABS_API}/text-to-speech/{voice_id}",
        data=payload,
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            audio_data = r.read()
        with open(output_path, "wb") as f:
            f.write(audio_data)
        print(f"  ✅ Audio guardado: {output_path} ({len(audio_data)/1024:.1f} KB)", flush=True)
        return True
    except urllib.error.HTTPError as e:
        body = ""
        try: body = e.read().decode("utf-8", errors="replace")
        except Exception: pass
        print(f"  ❌ ElevenLabs HTTP {e.code}: {body[:300]}", flush=True)
        return False
    except Exception as e:
        print(f"  ❌ Error TTS: {e}", flush=True)
        return False


def upload_file(file_path: str) -> str:
    """
    Sube archivo probando varios servicios hasta que uno funcione.
    Orden de preferencia — URLs directas primero (reproducibles en <audio>/<video>):
      1. Litterbox catbox.moe — URL directa litter.catbox.moe/*.mp3  ← PREFERIDO
      2. tmpfiles.org/dl/     — URL directa
      3. uguu.se              — URL directa
      4. Pixeldrain           — URL directa (falla en Railway)
      5. transfer.sh          — URL directa (falla en Railway)
      6. GoFile               — URL de página — último recurso
    """
    import mimetypes
    filename  = os.path.basename(file_path)
    mime      = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
    boundary  = "----PaperclipBoundary7MA4YWxkTrZu0gW"

    with open(file_path, "rb") as f:
        file_data = f.read()

    size_kb = len(file_data) / 1024
    print(f"  📤 Subiendo {filename} ({size_kb:.0f} KB)...", flush=True)

    # ── 1. Litterbox catbox.moe (72h, URL directa) ───────────────────────────
    try:
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="reqtype"\r\n\r\nfileupload\r\n'
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="time"\r\n\r\n72h\r\n'
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="fileToUpload"; filename="{filename}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(
            "https://litterbox.catbox.moe/resources/internals/api.php",
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "paperclip-agent/1.0",
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            url = resp.read().decode("utf-8").strip()
        if url.startswith("http"):
            print(f"  ✅ catbox.moe: {url}", flush=True)
            return url
    except Exception as e:
        print(f"  ⚠️  catbox.moe falló: {e}", flush=True)

    # ── 2. tmpfiles.org (URL directa /dl/) ───────────────────────────────────
    try:
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(
            "https://tmpfiles.org/api/v1/upload",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            tj = json.loads(resp.read().decode("utf-8"))
        url = tj.get("data", {}).get("url", "").replace("tmpfiles.org/", "tmpfiles.org/dl/")
        if url.startswith("http"):
            print(f"  ✅ tmpfiles.org: {url}", flush=True)
            return url
    except Exception as e:
        print(f"  ⚠️  tmpfiles.org falló: {e}", flush=True)

    # ── 3. uguu.se (URL directa) ──────────────────────────────────────────────
    try:
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="files[]"; filename="{filename}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(
            "https://uguu.se/upload",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            uj = json.loads(resp.read().decode("utf-8"))
        url = uj.get("files", [{}])[0].get("url", "")
        if url.startswith("http"):
            print(f"  ✅ uguu.se: {url}", flush=True)
            return url
    except Exception as e:
        print(f"  ⚠️  uguu.se falló: {e}", flush=True)

    # ── 4. Pixeldrain (URL directa — falla en Railway) ────────────────────────
    try:
        req = urllib.request.Request(
            f"https://pixeldrain.com/api/file/{filename}",
            data=file_data,
            headers={"Content-Type": mime, "User-Agent": "paperclip-agent/1.0"},
            method="PUT"
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            pd = json.loads(resp.read().decode("utf-8"))
        file_id = pd.get("id", "")
        if file_id:
            url = f"https://pixeldrain.com/api/file/{file_id}"
            print(f"  ✅ Pixeldrain: {url}", flush=True)
            return url
    except Exception as e:
        print(f"  ⚠️  Pixeldrain falló: {e}", flush=True)

    # ── 5. transfer.sh (URL directa — falla en Railway) ──────────────────────
    try:
        req = urllib.request.Request(
            f"https://transfer.sh/{filename}",
            data=file_data,
            headers={"Content-Type": mime, "User-Agent": "paperclip-agent/1.0", "Max-Days": "7"},
            method="PUT"
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            url = resp.read().decode("utf-8").strip()
        if url.startswith("http"):
            print(f"  ✅ transfer.sh: {url}", flush=True)
            return url
    except Exception as e:
        print(f"  ⚠️  transfer.sh falló: {e}", flush=True)

    # ── 6. GoFile (último recurso — URL de página) ────────────────────────────
    try:
        with urllib.request.urlopen("https://api.gofile.io/servers", timeout=10) as r:
            servers_data = json.loads(r.read().decode("utf-8"))
        server = servers_data["data"]["servers"][0]["name"]
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(
            f"https://{server}.gofile.io/contents/uploadFile",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            gf = json.loads(resp.read().decode("utf-8"))
        url = gf.get("data", {}).get("downloadPage", "")
        if url.startswith("http"):
            print(f"  ✅ GoFile (página): {url}", flush=True)
            return url
    except Exception as e:
        print(f"  ⚠️  GoFile falló: {e}", flush=True)

    raise Exception("Todos los servicios de upload fallaron")


def main():
    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        print("ERROR: ELEVENLABS_API_KEY no configurada", file=sys.stderr)
        sys.exit(1)

    if len(sys.argv) > 1:
        script = " ".join(sys.argv[1:])
    else:
        script = sys.stdin.read().strip()

    issue_title, issue_body = resolve_issue_context()
    if issue_title:
        script = issue_body if issue_body else script
        post_issue_comment(
            f"🎙️ Generando voz en off para: **{issue_title}**\n\n"
            f"Extraigo la narración de cada escena y la convierto en audio con ElevenLabs."
        )

    if not script:
        print("ERROR: No hay guión para convertir", file=sys.stderr)
        sys.exit(1)

    narration = extract_narration(script)
    print(f"📝 Narración extraída ({len(narration)} chars):", flush=True)
    print(f"   {narration[:200]}...", flush=True)

    voice_id    = get_best_voice(api_key)
    timestamp   = int(time.time())
    output_path = f"/tmp/narration_{timestamp}.mp3"

    print("🎙️ Generando audio con ElevenLabs...", flush=True)
    ok = generate_audio(narration, voice_id, api_key, output_path)

    if not ok:
        print("⚠️  Reintentando con voz Antoni...", flush=True)
        ok = generate_audio(narration, DEFAULT_VOICE, api_key, output_path)

    if not ok or not os.path.exists(output_path):
        print("ERROR: Fallo al generar audio", file=sys.stderr)
        sys.exit(1)

    file_size = os.path.getsize(output_path)
    duration_estimate = len(narration.split()) / 2.5  # ~2.5 palabras/seg

    print("📤 Subiendo audio...", flush=True)
    try:
        audio_url = upload_file(output_path)
        print(f"  ✅ URL: {audio_url}", flush=True)
    except Exception as e:
        print(f"  ⚠️  Upload falló: {e} — solo ruta local disponible", flush=True)
        audio_url = ""

    result = json.dumps({
        "audio_url":         audio_url,
        "audio_path":        output_path,
        "narration_text":    narration,
        "duration_estimate": f"{duration_estimate:.0f}s",
        "file_size_kb":      round(file_size / 1024, 1),
    }, ensure_ascii=False, indent=2)

    print(result)
    post_issue_result(
        f"🎙️ **Audio generado**\n\n"
        + (f"📥 [Descargar MP3]({audio_url})\n" if audio_url else "")
        + f"⏱️ Duración estimada: {duration_estimate:.0f}s\n"
        f"📦 Tamaño: {file_size/1024:.1f} KB\n\n"
        f"**Narración:**\n> {narration[:300]}..."
    )


if __name__ == "__main__":
    main()
