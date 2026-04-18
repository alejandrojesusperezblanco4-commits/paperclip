"""
Agente: Video Assembler
Combina imágenes generadas + audio de narración en un video MP4.
Usa ffmpeg: slideshow de imágenes sincronizado con la voz en off.

Output: MP4 720p 9:16 (formato TikTok/Reels/Shorts)
"""
import os
import sys
import re
import json
import glob
import subprocess
import time
import urllib.request
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from api_client import post_issue_result, post_issue_comment, resolve_issue_context

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


def _is_html(data: bytes) -> bool:
    """Detecta respuestas HTML (errores 403/404 disfrazados como 200)."""
    start = data[:100].lower()
    return start.startswith(b"<!doctype") or start.startswith(b"<html") or b"<html" in start[:60]


def download_image(url: str, path: str) -> bool:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",
        "Referer": "https://higgsfield.ai/",
        "Cache-Control": "no-cache",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=60) as r:
            content_type = r.headers.get("Content-Type", "")
            data = r.read()
        print(f"  📦 Descargado: {len(data)//1024}KB, Content-Type: {content_type[:40]}", flush=True)
        # Rechazar solo respuestas HTML (errores disfrazados)
        if _is_html(data):
            print(f"  ⚠️  Respuesta es HTML (error del servidor): {url[:70]}", flush=True)
            return False
        if len(data) < 500:
            print(f"  ⚠️  Respuesta demasiado pequeña ({len(data)}B): {url[:70]}", flush=True)
            return False
        with open(path, "wb") as f:
            f.write(data)
        print(f"  ✅ Imagen guardada: {path}", flush=True)
        return True
    except Exception as e:
        print(f"  ⚠️  Error descargando {url[:70]}: {e}", flush=True)
        return False


def convert_to_jpg(src: str, dst: str) -> bool:
    """Convierte cualquier formato de imagen a JPG con ffmpeg."""
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", src,
             "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
             "-q:v", "2", dst],
            capture_output=True, text=True, timeout=30
        )
        return r.returncode == 0 and os.path.exists(dst)
    except Exception:
        return False


def extract_image_urls(text: str) -> list:
    urls = re.findall(r"https?://[^\s\"')]+\.(?:png|jpg|jpeg|webp)", text)
    return list(dict.fromkeys(urls))


def extract_audio_url(text: str) -> str:
    """Extrae URL de audio MP3 del texto (para modo standalone)."""
    m = re.search(r"https?://[^\s\"')]+\.mp3", text)
    return m.group(0) if m else ""


def download_audio(url: str, output_path: str) -> bool:
    """Descarga un MP3 desde URL a output_path."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            with open(output_path, "wb") as f:
                f.write(r.read())
        print(f"  ✅ Audio descargado: {output_path}", flush=True)
        return True
    except Exception as e:
        print(f"  ⚠️  Error descargando audio: {e}", flush=True)
        return False


def get_audio_duration(path: str) -> float:
    """Devuelve la duración del audio en segundos."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=10
        )
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def normalize_images(image_paths: list, work_dir: str) -> list:
    """
    Convierte todas las imágenes a JPG estándar para máxima compatibilidad con ffmpeg.
    WebP y otros formatos raros pueden fallar en el concat demuxer.
    """
    normalized = []
    for i, src in enumerate(image_paths):
        dst = os.path.join(work_dir, f"norm_{i+1:02d}.jpg")
        if convert_to_jpg(src, dst):
            normalized.append(dst)
            print(f"  🔄 Normalizada: {os.path.basename(src)} → {os.path.basename(dst)}", flush=True)
        else:
            # Si la conversión falla, intentar usar la original
            print(f"  ⚠️  No se pudo normalizar {os.path.basename(src)}, usando original", flush=True)
            normalized.append(src)
    return normalized


def assemble_video(image_paths: list, audio_path: str,
                   output_path: str, scene_duration: float) -> bool:
    """
    Crea el video con ffmpeg usando el enfoque POR CLIP (no concat demuxer).
    El concat demuxer con imágenes estáticas cuelga en ciertos ffmpeg — en
    cambio, '-loop 1 -t DURATION' es fiable y no requiere seek.

    Pasos:
      1. Normalizar imágenes a JPG
      2. Generar un clip MP4 silencioso por imagen con -loop 1
      3. Concatenar clips con stream copy
      4. Muxear audio en el video final
    """
    work_dir = os.path.dirname(output_path)

    scale_filter = (
        "scale=720:1280:force_original_aspect_ratio=decrease,"
        "pad=720:1280:(ow-iw)/2:(oh-ih)/2:black"
    )

    # Paso 1: normalizar imágenes a JPG
    print(f"  🔄 Normalizando {len(image_paths)} imágenes a JPG...", flush=True)
    norm_paths = normalize_images(image_paths, work_dir)
    if not norm_paths:
        print("  ❌ Sin imágenes normalizadas", flush=True)
        return False

    # Paso 2: generar clip silencioso por imagen (-loop 1, ultrafast, sin seek)
    clip_paths = []
    per_clip_timeout = max(60, int(scene_duration * 3))  # headroom generoso
    for i, img in enumerate(norm_paths):
        clip = os.path.join(work_dir, f"clip_{i:02d}.mp4")
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",          # loop la imagen como stream de video
            "-framerate", "1",     # entrada a 1fps (reduce trabajo interno)
            "-i", img,
            "-vf", f"{scale_filter},fps=24",   # escalar + convertir a 24fps
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
            "-pix_fmt", "yuv420p",
            "-t", f"{scene_duration:.3f}",     # duración exacta
            "-an",                 # sin audio en el clip
            clip
        ]
        print(f"  🎞️  Clip {i+1}/{len(norm_paths)}: {scene_duration:.1f}s desde {os.path.basename(img)}", flush=True)
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=per_clip_timeout)
        if r.returncode != 0:
            print(f"  ❌ Clip {i+1} falló (código {r.returncode}):", flush=True)
            print(f"     stderr: {r.stderr[-800:]}", flush=True)
            return False
        if not os.path.exists(clip) or os.path.getsize(clip) < 1000:
            print(f"  ❌ Clip {i+1} vacío o no existe (tamaño: {os.path.getsize(clip) if os.path.exists(clip) else 0}B)", flush=True)
            print(f"     stderr: {r.stderr[-400:]}", flush=True)
            return False
        sz = os.path.getsize(clip) // 1024
        print(f"  ✅ Clip {i+1} listo: {sz}KB", flush=True)
        clip_paths.append(clip)

    # Paso 3: concatenar clips (stream copy → rápido)
    if len(clip_paths) == 1:
        silent_video = clip_paths[0]
        print(f"  ⏩ Clip único — sin necesidad de concatenar", flush=True)
    else:
        filelist = os.path.join(work_dir, "clips_list.txt")
        with open(filelist, "w", encoding="utf-8") as f:
            for c in clip_paths:
                f.write(f"file '{c}'\n")
        silent_video = os.path.join(work_dir, "silent.mp4")
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", filelist,
            "-c", "copy", silent_video
        ]
        print(f"  🔗 Concatenando {len(clip_paths)} clips...", flush=True)
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            print(f"  ❌ Concat falló:\n{r.stderr[-600:]}", flush=True)
            return False
        print(f"  ✅ Clips concatenados", flush=True)

    # Paso 4: muxear audio
    if audio_path:
        exists = os.path.exists(audio_path)
        sz = os.path.getsize(audio_path) // 1024 if exists else 0
        print(f"  🎙️  Audio: '{audio_path}' — exists={exists}, {sz}KB", flush=True)
    else:
        print(f"  🔇 Sin audio_path — video mudo", flush=True)
    has_audio = bool(audio_path and os.path.exists(audio_path))
    if has_audio:
        cmd = [
            "ffmpeg", "-y",
            "-i", silent_video,
            "-i", audio_path,
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            "-shortest",
            output_path
        ]
        print(f"  🎙️  Muxeando audio...", flush=True)
    else:
        cmd = [
            "ffmpeg", "-y",
            "-i", silent_video,
            "-c", "copy",
            "-movflags", "+faststart",
            output_path
        ]
        print(f"  🔇 Video sin audio (mux directo)...", flush=True)

    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.stderr:
        print(f"  📋 mux stderr:\n{r.stderr[-800:]}", flush=True)
    if r.returncode != 0:
        print(f"  ❌ Mux falló (código {r.returncode})", flush=True)
        return False

    final_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
    print(f"  ✅ Video ensamblado: {output_path} ({final_size//1024}KB)", flush=True)
    return True


def upload_file(file_path: str) -> str:
    """
    Sube archivo probando varios servicios hasta que uno funcione.
    Servicios en orden de preferencia (2026):
      1. transfer.sh  — PUT directo, URL permanente
      2. GoFile       — requiere obtener servidor primero, luego upload
      3. tmpfiles.org — multipart POST, JSON response
      4. uguu.se      — multipart POST, texto plano
      5. catbox.moe   — litterbox (72h)
    """
    import mimetypes
    filename  = os.path.basename(file_path)
    mime      = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
    boundary  = "----PaperclipBoundary7MA4YWxkTrZu0gW"

    with open(file_path, "rb") as f:
        file_data = f.read()

    size_mb = len(file_data) / 1024 / 1024
    print(f"  📤 Subiendo {filename} ({size_mb:.1f} MB)...", flush=True)

    # ── 1. transfer.sh (PUT) ─────────────────────────────────────────────────
    try:
        req = urllib.request.Request(
            f"https://transfer.sh/{filename}",
            data=file_data,
            headers={
                "Content-Type": mime,
                "User-Agent": "paperclip-agent/1.0",
                "Max-Days": "7",
            },
            method="PUT"
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            url = resp.read().decode("utf-8").strip()
        if url.startswith("http"):
            print(f"  ✅ transfer.sh: {url}", flush=True)
            return url
    except Exception as e:
        print(f"  ⚠️  transfer.sh falló: {e}", flush=True)

    # ── 2. GoFile (GET server + POST upload) ─────────────────────────────────
    try:
        # Obtener servidor disponible
        with urllib.request.urlopen("https://api.gofile.io/servers", timeout=10) as r:
            servers_data = json.loads(r.read().decode("utf-8"))
        server = servers_data["data"]["servers"][0]["name"]
        # Subir al servidor obtenido
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(
            f"https://{server}.gofile.io/contents/uploadFile",
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "paperclip-agent/1.0",
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            gf = json.loads(resp.read().decode("utf-8"))
        url = gf.get("data", {}).get("downloadPage", "")
        if url.startswith("http"):
            print(f"  ✅ GoFile: {url}", flush=True)
            return url
    except Exception as e:
        print(f"  ⚠️  GoFile falló: {e}", flush=True)

    # ── 3. tmpfiles.org ───────────────────────────────────────────────────────
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
        with urllib.request.urlopen(req, timeout=180) as resp:
            tj = json.loads(resp.read().decode("utf-8"))
        url = tj.get("data", {}).get("url", "")
        if url.startswith("http"):
            # tmpfiles devuelve la página de descarga; convertir a descarga directa
            url = url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
            print(f"  ✅ tmpfiles.org: {url}", flush=True)
            return url
    except Exception as e:
        print(f"  ⚠️  tmpfiles.org falló: {e}", flush=True)

    # ── 4. uguu.se ────────────────────────────────────────────────────────────
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
        with urllib.request.urlopen(req, timeout=180) as resp:
            uj = json.loads(resp.read().decode("utf-8"))
        url = uj.get("files", [{}])[0].get("url", "")
        if url.startswith("http"):
            print(f"  ✅ uguu.se: {url}", flush=True)
            return url
    except Exception as e:
        print(f"  ⚠️  uguu.se falló: {e}", flush=True)

    # ── 5. Litterbox catbox.moe (72h) ─────────────────────────────────────────
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
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            url = resp.read().decode("utf-8").strip()
        if url.startswith("http"):
            print(f"  ✅ catbox.moe: {url}", flush=True)
            return url
    except Exception as e:
        print(f"  ⚠️  catbox.moe falló: {e}", flush=True)

    raise Exception("Todos los servicios de upload fallaron")


def main():
    if len(sys.argv) > 1:
        raw = " ".join(sys.argv[1:])
    else:
        raw = sys.stdin.read().strip()

    issue_title, issue_body = resolve_issue_context()
    if issue_body:
        raw = issue_body

    post_issue_comment(
        "🎬 Ensamblando video...\n\n"
        "Descargo imágenes, busco audio y genero el MP4 9:16 listo para TikTok/Reels.\n\n"
        "**Formato aceptado en la descripción:**\n"
        "- URLs de imágenes (.png/.jpg)\n"
        "- URL de audio (.mp3) — opcional\n"
        "- O JSON: `{\"image_urls\": [...], \"audio_url\": \"...\"}`"
    )

    # Parsear input — acepta JSON o texto libre con URLs
    data = {}
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        try:
            data = json.loads(m.group(0))
        except Exception:
            pass

    image_urls = data.get("image_urls") or extract_image_urls(raw)
    audio_path = data.get("audio_path", "")
    audio_url  = data.get("audio_url", "") or extract_audio_url(raw)

    print(f"📋 image_urls recibidas ({len(image_urls)}):", flush=True)
    for u in image_urls:
        print(f"   • {u[:100]}", flush=True)
    print(f"🎙️  audio_path recibido: '{audio_path}'", flush=True)
    print(f"🔗 audio_url recibido: '{audio_url[:80] if audio_url else ''}'", flush=True)

    timestamp = int(time.time())
    tmp_dir   = f"/tmp/video_{timestamp}"
    os.makedirs(tmp_dir, exist_ok=True)

    # Resolver audio: prioridad → ruta local → URL → glob /tmp
    if audio_path and os.path.exists(audio_path):
        print(f"🎙️  Audio local: {audio_path}", flush=True)
    elif audio_url:
        # Modo standalone: descargar audio desde URL
        print(f"🎙️  Descargando audio desde URL: {audio_url[:60]}", flush=True)
        downloaded = f"{tmp_dir}/narration.mp3"
        if download_audio(audio_url, downloaded):
            audio_path = downloaded
        else:
            audio_path = ""
    else:
        # Fallback: buscar MP3 más reciente en /tmp (cuando corre tras TTS en el Director)
        mp3s = sorted(glob.glob("/tmp/narration_*.mp3"), key=os.path.getmtime, reverse=True)
        audio_path = mp3s[0] if mp3s else ""
        if audio_path:
            print(f"🎙️  Audio encontrado en /tmp: {audio_path}", flush=True)
        else:
            print("🎙️  Sin audio — se generará video mudo", flush=True)

    print(f"🖼️  {len(image_urls)} imágenes", flush=True)
    print(f"🎙️  Audio final: {audio_path or 'ninguno (video mudo)'}", flush=True)

    if not image_urls:
        print("ERROR: sin imágenes para ensamblar", file=sys.stderr)
        sys.exit(1)

    timestamp = int(time.time())
    tmp_dir   = f"/tmp/video_{timestamp}"
    os.makedirs(tmp_dir, exist_ok=True)

    # Descargar imágenes
    image_paths = []
    for i, url in enumerate(image_urls):
        # Extraer extensión solo del path de la URL (ignorar dominio y query params)
        from urllib.parse import urlparse as _urlparse
        _url_path = _urlparse(url).path          # e.g. "/outputs/abc.webp"
        _basename = _url_path.rsplit("/", 1)[-1] # e.g. "abc.webp"
        if "." in _basename:
            ext = _basename.rsplit(".", 1)[-1][:8]  # máx 8 chars para evitar basura
        else:
            ext = "jpg"  # default seguro — ffmpeg detecta el formato real
        # Validar que sea extensión de imagen conocida
        if ext.lower() not in {"jpg", "jpeg", "png", "webp", "avif", "gif", "bmp"}:
            ext = "jpg"
        path = f"{tmp_dir}/scene_{i+1:02d}.{ext}"
        print(f"  📥 Imagen {i+1}/{len(image_urls)} [{ext}]: {url[:80]}", flush=True)
        if download_image(url, path):
            image_paths.append(path)

    if not image_paths:
        print("ERROR: no se pudieron descargar las imágenes", file=sys.stderr)
        sys.exit(1)

    # Calcular duración por escena
    audio_dur     = get_audio_duration(audio_path) if audio_path else 0.0
    scene_duration = max(4.0, audio_dur / len(image_paths)) if audio_dur else 5.0
    total_dur      = scene_duration * len(image_paths)
    print(f"  ⏱️  {len(image_paths)} escenas × {scene_duration:.1f}s = {total_dur:.0f}s total", flush=True)

    output_path = f"{tmp_dir}/video.mp4"
    ok = assemble_video(image_paths, audio_path, output_path, scene_duration)

    if not ok:
        print("ERROR: ffmpeg falló", file=sys.stderr)
        sys.exit(1)

    file_size = os.path.getsize(output_path)
    print(f"📦 Tamaño del video: {file_size/1024/1024:.1f} MB", flush=True)

    print("📤 Subiendo video...", flush=True)
    try:
        video_url = upload_file(output_path)
        print(f"  ✅ Video: {video_url}", flush=True)
    except Exception as e:
        print(f"  ⚠️  Upload falló: {e}", flush=True)
        video_url = ""

    result = json.dumps({
        "video_url":    video_url,
        "scenes":       len(image_paths),
        "duration_s":   round(total_dur),
        "file_size_mb": round(file_size / 1024 / 1024, 1),
        "has_audio":    bool(audio_path),
    }, ensure_ascii=False, indent=2)

    print(result)
    post_issue_result(
        "🎬 **Video listo**\n\n"
        + (f"📥 [Descargar MP4]({video_url})\n" if video_url else "")
        + f"🖼️ {len(image_paths)} escenas — {total_dur:.0f}s\n"
        f"📦 {file_size/1024/1024:.1f} MB\n"
        f"{'🎙️ Con voz en off' if audio_path else '⚠️ Sin audio (TTS no disponible)'}\n\n"
        "Listo para subir a TikTok, Instagram Reels o YouTube Shorts. 🚀"
    )


if __name__ == "__main__":
    main()
