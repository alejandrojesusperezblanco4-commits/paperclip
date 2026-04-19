"""
Agente: Imagen Video (Higgsfield DOP — Image-to-Video)
Anima imágenes estáticas generadas por Soul en clips de video de 4-6 segundos.

Docs: https://docs.higgsfield.ai
Auth: Authorization: Key {KEY_ID}:{KEY_SECRET}
Submit:  POST https://platform.higgsfield.ai/higgsfield-ai/dop/turbo
Poll:    GET  https://platform.higgsfield.ai/requests/{id}/status
Result:  videos[0].url cuando status == "completed"

Input (JSON del video_prompt_generator):
{
  "video_prompts": [
    { "scene": 1, "image_url": "...", "motion_prompt": "slow push-in..." },
    ...
  ]
}

Output: texto con URLs de los clips MP4 generados.
"""
import os
import sys
import json
import time
import urllib.request
import urllib.error
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from api_client import post_issue_result, post_issue_comment, resolve_issue_context

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

BASE_URL  = "https://platform.higgsfield.ai"
# Endpoints DOP disponibles (en orden de preferencia según la API Reference de Higgsfield):
DOP_MODEL_V1   = "v1/image2video/dop"       # endpoint nuevo recomendado
DOP_MODEL_LITE = "higgsfield-ai/dop/lite"   # mismo patrón que Soul (legacy)
DOP_MODEL      = DOP_MODEL_LITE             # usar lite (lo que tiene el usuario)

DONE_STATUSES    = {"completed", "failed", "nsfw"}
SUCCESS_STATUSES = {"completed"}

BROWSER_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":          "application/json, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin":          "https://cloud.higgsfield.ai",
    "Referer":         "https://cloud.higgsfield.ai/",
}


def auth_header(api_key: str) -> str:
    return f"Key {api_key}"


def http_post(url: str, payload: dict, api_key: str) -> dict:
    data = json.dumps(payload).encode("utf-8")
    headers = {
        **BROWSER_HEADERS,
        "Authorization": auth_header(api_key),
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = ""
        try: body = e.read().decode("utf-8", errors="replace")
        except Exception: pass
        raise Exception(f"HTTP {e.code} — {body[:500]}")


def http_get(url: str, api_key: str) -> dict:
    headers = {**BROWSER_HEADERS, "Authorization": auth_header(api_key)}
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = ""
        try: body = e.read().decode("utf-8", errors="replace")
        except Exception: pass
        raise Exception(f"HTTP {e.code} — {body[:500]}")


def submit_video(image_url: str, motion_prompt: str, api_key: str) -> str:
    """
    Envía imagen + motion prompt a Higgsfield DOP. Devuelve request_id.
    Prueba combinaciones de endpoint + payload hasta que funcione.
    """
    print(f"  🎬 Motion: {motion_prompt[:80]}", flush=True)

    # Distintas combinaciones endpoint / formato de payload
    attempts = [
        # dop/lite con payload plano (formato confirmado)
        (DOP_MODEL_LITE, {"prompt": motion_prompt, "image_url": image_url, "seed": 42}),
        # v1 con wrapper params (formato correcto para v1)
        (DOP_MODEL_V1,   {"params": {"prompt": motion_prompt, "image_url": image_url, "seed": 42}}),
    ]

    for attempt_num, (endpoint, payload) in enumerate(attempts):
        url = f"{BASE_URL}/{endpoint}"
        print(f"  📡 POST {url}  payload_keys={list(payload.keys())}", flush=True)
        try:
            result = http_post(url, payload, api_key)
            request_id = result.get("request_id")
            if request_id:
                print(f"  📤 En cola → ID: {request_id}  endpoint={endpoint}", flush=True)
                return request_id
            # Loguear la respuesta completa para diagnóstico
            print(f"  ⚠️  Sin request_id. Respuesta: {json.dumps(result)[:300]}", flush=True)
        except Exception as e:
            err_str = str(e)
            # Rate limit: esperar antes del siguiente intento
            if "concurrent" in err_str.lower() or "HTTP 400" in err_str:
                wait = 20 if attempt_num == 0 else 30
                print(f"  ⏳ Rate limit detectado — esperando {wait}s antes de reintentar...", flush=True)
                time.sleep(wait)
            print(f"  ⚠️  {endpoint} falló: {e}", flush=True)

    raise Exception("Todos los intentos DOP fallaron — revisa los logs arriba para el error exacto")


def poll_video(request_id: str, api_key: str, max_wait: int = 150) -> str:
    """Polling hasta obtener la URL del video MP4. Timeout 2.5 min por clip."""
    deadline   = time.time() + max_wait
    interval   = 4          # poll cada 4s para ser más ágil
    status_url = f"{BASE_URL}/requests/{request_id}/status"

    while time.time() < deadline:
        data   = http_get(status_url, api_key)
        status = (data.get("status") or "unknown").lower()
        print(f"  ⏳ {request_id[:12]}… → {status}", flush=True)

        if status in SUCCESS_STATUSES:
            # Intentar extraer video URL de distintos formatos de respuesta
            # Higgsfield DOP devuelve "video": {"url": "..."} (singular)
            video_url = (
                (data.get("video") or {}).get("url")           # ← formato real DOP
                or (data.get("videos") or [{}])[0].get("url")  # plural (legacy)
                or data.get("video_url")
                or (data.get("output") or {}).get("video_url")
            )
            if video_url:
                return video_url
            raise Exception(f"completed pero sin video URL: {json.dumps(data)[:300]}")

        if status == "nsfw":
            raise Exception("Clip rechazado por moderación (NSFW).")
        if status == "failed":
            raise Exception(f"Animación fallida: {data.get('error','')}")

        time.sleep(interval)

    raise Exception(f"Timeout ({max_wait}s) esperando clip de {request_id}")


def animate_scene(scene: int, image_url: str, motion_prompt: str, api_key: str,
                  max_retries: int = 1) -> dict:
    """Anima una imagen con reintentos automáticos ante timeout o error."""
    label = f"Escena {scene}"
    print(f"\n🎞️  Animando {label}...", flush=True)
    print(f"   🖼️  Imagen: {image_url[:80]}", flush=True)
    last_error = None
    for attempt in range(1, max_retries + 2):
        if attempt > 1:
            print(f"  🔄 Reintento {attempt}/{max_retries + 1} para {label}...", flush=True)
            time.sleep(10)
        try:
            request_id = submit_video(image_url, motion_prompt, api_key)
            video_url  = poll_video(request_id, api_key)
            print(f"  ✅ {label} animada → {video_url}", flush=True)
            return {
                "scene":         scene,
                "image_url":     image_url,
                "motion_prompt": motion_prompt,
                "video_url":     video_url,
                "status":        "ok",
            }
        except Exception as e:
            last_error = e
            print(f"  ⚠️  Intento {attempt} fallido para {label}: {e}", flush=True)

    print(f"  ❌ {label} falló tras {max_retries + 1} intentos", flush=True)
    return {
        "scene":         scene,
        "image_url":     image_url,
        "motion_prompt": motion_prompt,
        "video_url":     None,
        "status":        f"error: {last_error}",
    }


def extract_video_prompts(raw: str) -> list:
    """
    Extrae video_prompts[] del JSON del video_prompt_generator.
    Si no hay JSON válido, intenta extraer pares imagen/prompt del texto libre.
    """
    # Buscar JSON explícito
    json_str = None
    if "```json" in raw:
        json_str = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        json_str = raw.split("```")[1].split("```")[0].strip()
    elif raw.strip().startswith("{"):
        json_str = raw.strip()
    else:
        m = re.search(r'\{[\s\S]*?"video_prompts"[\s\S]*?\}', raw)
        if m:
            json_str = m.group(0)

    if json_str:
        try:
            data = json.loads(json_str)
            prompts = data.get("video_prompts", [])
            if prompts:
                print(f"  ✅ {len(prompts)} video_prompts extraídos del JSON", flush=True)
                return prompts
        except Exception as e:
            print(f"  ⚠️  JSON parse error: {e}", flush=True)

    # Fallback: extraer URLs de imágenes y usar prompt genérico
    print("  ℹ️  Fallback: usando motion prompt genérico para todas las imágenes", flush=True)
    ext_urls  = re.findall(r"https?://[^\s\"')]+\.(?:png|jpg|jpeg|webp)", raw)
    bold_urls = re.findall(r"\*\*URL:\*\*\s*(https?://\S+)", raw)
    md_urls   = re.findall(r"\]\((https?://[^\s)]+)\)", raw)
    urls = list(dict.fromkeys(ext_urls + bold_urls + md_urls))
    return [
        {
            "scene": i + 1,
            "image_url": url,
            "motion_prompt": (
                "slow cinematic push-in, subtle light shift, "
                "hair and clothes gently moving, ambient particles floating"
            ),
        }
        for i, url in enumerate(urls)
    ]


def main():
    api_key = os.environ.get("HIGGSFIELD_API_KEY", "").strip()
    if not api_key:
        print("ERROR: HIGGSFIELD_API_KEY no configurada", file=sys.stderr)
        sys.exit(1)

    if len(sys.argv) > 1:
        raw = " ".join(sys.argv[1:])
    else:
        raw = sys.stdin.read().strip()

    issue_title, issue_body = resolve_issue_context()
    if issue_title:
        raw = issue_body if issue_body else raw
        post_issue_comment(
            f"🎞️ Animando imágenes con Higgsfield DOP para: **{issue_title}**\n\n"
            f"Convierto cada imagen estática en un clip de video de 4-6 segundos "
            f"con movimiento de cámara cinematográfico. Puede tardar 3-5 min."
        )

    if not raw:
        print("ERROR: Sin input", file=sys.stderr)
        sys.exit(1)

    print("🎞️  IMAGEN VIDEO — HIGGSFIELD DOP", flush=True)
    video_prompts = extract_video_prompts(raw)

    if not video_prompts:
        print("ERROR: No hay imágenes para animar", file=sys.stderr)
        sys.exit(1)

    # Limitar a 3 imágenes máximo para no exceder el timeout del Director (300s).
    # Las 3 primeras escenas son las más importantes para el hook narrativo.
    MAX_CLIPS = 3
    if len(video_prompts) > MAX_CLIPS:
        print(f"  ℹ️  Limitando a {MAX_CLIPS} clips (de {len(video_prompts)}) para respetar el timeout", flush=True)
        video_prompts = video_prompts[:MAX_CLIPS]

    print(f"\n🚀 Animando {len(video_prompts)} imágenes (paralelo, máx 3 a la vez)...", flush=True)

    results = [None] * len(video_prompts)

    def run(idx, item):
        return idx, animate_scene(
            scene         = item.get("scene", idx + 1),
            image_url     = item["image_url"],
            motion_prompt = item.get("motion_prompt", "slow cinematic push-in"),
            api_key       = api_key,
        )

    # Secuencial (max_workers=1) para evitar el límite de 4 concurrent requests de Higgsfield
    with ThreadPoolExecutor(max_workers=1) as executor:
        futures = {executor.submit(run, i, item): i for i, item in enumerate(video_prompts)}
        for future in as_completed(futures):
            idx, result = future.result()
            results[idx] = result
            icon = "✅" if result["status"] == "ok" else "❌"
            print(f"  {icon} Escena {result['scene']} completada", flush=True)

    # Construir output
    lines = ["# 🎞️ CLIPS DE VIDEO GENERADOS (Higgsfield DOP)\n"]
    ok_count = sum(1 for r in results if r and r["status"] == "ok")
    lines.append(f"**{ok_count}/{len(results)} clips animados correctamente**\n")

    video_clip_urls = []
    for r in results:
        if not r:
            continue
        icon = "✅" if r["status"] == "ok" else "❌"
        lines.append(f"## {icon} Escena {r['scene']}")
        if r["video_url"]:
            lines.append(f"**VIDEO_CLIP:** {r['video_url']}")
            lines.append(f"![Clip escena {r['scene']}]({r['video_url']})")
            video_clip_urls.append(r["video_url"])
        else:
            lines.append(f"**Error:** {r['status']}")
            # Incluir imagen original como fallback
            if r["image_url"]:
                lines.append(f"**FALLBACK_IMAGE:** {r['image_url']}")
        lines.append(f"**Motion:** {r['motion_prompt'][:100]}")
        lines.append("")

    # JSON estructurado al final
    lines.append("```json")
    lines.append(json.dumps({
        "video_clips": [r["video_url"] for r in results if r and r["video_url"]],
        "fallback_images": [r["image_url"] for r in results if r and not r["video_url"]],
        "results": results,
    }, indent=2, ensure_ascii=False))
    lines.append("```")

    output = "\n".join(lines)
    print(output, flush=True)
    post_issue_result(output)


if __name__ == "__main__":
    main()
