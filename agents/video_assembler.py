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


def download_image(url: str, path: str) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            with open(path, "wb") as f:
                f.write(r.read())
        return True
    except Exception as e:
        print(f"  ⚠️  Error descargando {url[:60]}: {e}", flush=True)
        return False


def extract_image_urls(text: str) -> list:
    urls = re.findall(r"https?://[^\s\"')]+\.(?:png|jpg|jpeg|webp)", text)
    return list(dict.fromkeys(urls))


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


def assemble_video(image_paths: list, audio_path: str,
                   output_path: str, scene_duration: float) -> bool:
    """
    Crea el video con ffmpeg:
    - Slideshow de imágenes con duración proporcional al audio
    - Escala a 720x1280 (9:16 TikTok)
    - Overlay de audio (narración)
    - Fade in/out entre escenas
    """
    filelist = output_path.replace(".mp4", "_list.txt")
    with open(filelist, "w") as f:
        for img in image_paths:
            f.write(f"file '{img}'\n")
            f.write(f"duration {scene_duration:.2f}\n")
        # Duplicar última imagen para evitar corte brusco al final
        f.write(f"file '{image_paths[-1]}'\n")

    scale_filter = (
        "scale=720:1280:force_original_aspect_ratio=decrease,"
        "pad=720:1280:(ow-iw)/2:(oh-ih)/2:black,"
        "fps=24"
    )

    has_audio = audio_path and os.path.exists(audio_path)

    if has_audio:
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", filelist,
            "-i", audio_path,
            "-vf", scale_filter,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-shortest",
            output_path
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", filelist,
            "-vf", scale_filter,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            output_path
        ]

    print(f"  🎬 Ejecutando ffmpeg...", flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        print(f"  ❌ ffmpeg error:\n{r.stderr[-800:]}", flush=True)
        return False
    print(f"  ✅ Video ensamblado: {output_path}", flush=True)
    return True


def upload_file(file_path: str) -> str:
    """Sube archivo probando varios servicios hasta que uno funcione."""
    import mimetypes
    mime     = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
    filename = os.path.basename(file_path)
    boundary = "----PaperclipBoundary"

    with open(file_path, "rb") as f:
        file_data = f.read()

    def _multipart_post(url: str, field: str, timeout: int = 120) -> str:
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8").strip()

    services = [
        ("https://0x0.st",       "file"),
        ("https://file.io",      "file"),
        ("https://litterbox.catbox.moe/resources/internals/api.php", "fileToUpload"),
    ]
    for url, field in services:
        try:
            result = _multipart_post(url, field)
            if url == "https://file.io":
                result = json.loads(result).get("link", result)
            if result.startswith("http"):
                print(f"  ✅ Subido a {url.split('/')[2]}: {result}", flush=True)
                return result
        except Exception as e:
            print(f"  ⚠️  {url.split('/')[2]} falló: {e}", flush=True)
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
        "🎬 Ensamblando video final...\n\n"
        "Combino las imágenes con la voz en off en un MP4 9:16 listo para TikTok/Reels."
    )

    # Parsear JSON del input (puede venir como dict con image_urls + audio_path)
    data = {}
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        try:
            data = json.loads(m.group(0))
        except Exception:
            pass

    image_urls = data.get("image_urls") or extract_image_urls(raw)
    audio_path = data.get("audio_path", "")

    # Si no llegó audio_path, buscar el MP3 más reciente en /tmp
    if not audio_path or not os.path.exists(audio_path):
        mp3s = sorted(glob.glob("/tmp/narration_*.mp3"), key=os.path.getmtime, reverse=True)
        audio_path = mp3s[0] if mp3s else ""

    print(f"🖼️  {len(image_urls)} imágenes", flush=True)
    print(f"🎙️  Audio: {audio_path or 'no encontrado'}", flush=True)

    if not image_urls:
        print("ERROR: sin imágenes para ensamblar", file=sys.stderr)
        sys.exit(1)

    timestamp = int(time.time())
    tmp_dir   = f"/tmp/video_{timestamp}"
    os.makedirs(tmp_dir, exist_ok=True)

    # Descargar imágenes
    image_paths = []
    for i, url in enumerate(image_urls):
        ext  = url.rsplit(".", 1)[-1].split("?")[0] or "png"
        path = f"{tmp_dir}/scene_{i+1:02d}.{ext}"
        print(f"  📥 Imagen {i+1}/{len(image_urls)}: {url[-50:]}", flush=True)
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
