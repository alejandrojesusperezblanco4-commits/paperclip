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


def extract_narration(script: str) -> str:
    """Extrae solo el texto de narración (🎙️) del guión de storytelling."""
    parts = []
    in_narration = False

    for line in script.split("\n"):
        stripped = line.strip()
        if "🎙️" in stripped or "NARRACIÓN" in stripped.upper():
            in_narration = True
            continue
        if in_narration:
            if stripped.startswith("🎬") or stripped.startswith("⏱️") or "━━" in stripped:
                in_narration = False
                continue
            if stripped:
                clean = re.sub(r"\*+|_+", "", stripped)
                parts.append(clean)

    narration = " ".join(parts).strip()
    return narration if narration else script[:3000]


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
            "stability": 0.45,
            "similarity_boost": 0.75,
            "style": 0.30,
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
    """Sube archivo a 0x0.st y devuelve URL pública."""
    import mimetypes
    mime     = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
    filename = os.path.basename(file_path)
    boundary = "----PaperclipBoundary"

    with open(file_path, "rb") as f:
        file_data = f.read()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        "https://0x0.st",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8").strip()


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
