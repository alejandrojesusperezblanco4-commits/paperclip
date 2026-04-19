"""
Agente: Imagen Generator
Genera imágenes con Higgsfield Soul (text-to-image).

Docs: https://docs.higgsfield.ai
Auth: Authorization: Key {KEY_ID}:{KEY_SECRET}
Submit: POST https://platform.higgsfield.ai/higgsfield-ai/soul/standard
Poll:   GET  https://platform.higgsfield.ai/requests/{id}/status
Result: incluido en el status cuando status == "completed"
"""
import os
import sys
import json
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from api_client import post_issue_result, post_issue_comment, resolve_issue_context

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

BASE_URL   = "https://platform.higgsfield.ai"
MODEL_ID   = "higgsfield-ai/soul/standard"

# Statuses según docs oficiales
DONE_STATUSES    = {"completed", "failed", "nsfw"}
SUCCESS_STATUSES = {"completed"}

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://cloud.higgsfield.ai",
    "Referer": "https://cloud.higgsfield.ai/",
}


def auth_header(api_key: str) -> str:
    # api_key debe ser "KEY_ID:KEY_SECRET"
    return f"Key {api_key}"


def http_post(url: str, payload: dict, api_key: str) -> dict:
    data = json.dumps(payload).encode("utf-8")
    headers = {**BROWSER_HEADERS, "Authorization": auth_header(api_key), "Content-Type": "application/json"}
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


def submit_image(prompt: str, aspect_ratio: str, api_key: str) -> str:
    """Envía solicitud a Higgsfield Soul y devuelve request_id."""
    url = f"{BASE_URL}/{MODEL_ID}"
    payload = {
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,  # "9:16", "16:9", "1:1"
        "resolution": "720p",
    }
    print(f"  📡 POST {url}", flush=True)
    result = http_post(url, payload, api_key)
    request_id = result.get("request_id")
    if not request_id:
        raise Exception(f"Sin request_id en respuesta: {result}")
    print(f"  📤 En cola → ID: {request_id}", flush=True)
    return request_id


def poll_result(request_id: str, api_key: str, max_wait: int = 180) -> str:
    """Hace polling hasta obtener la URL de la imagen. Timeout 3 min."""
    deadline = time.time() + max_wait
    interval = 5
    status_url = f"{BASE_URL}/requests/{request_id}/status"

    while time.time() < deadline:
        data = http_get(status_url, api_key)
        status = (data.get("status") or "unknown").lower()
        print(f"  ⏳ Estado: {status}", flush=True)

        if status in SUCCESS_STATUSES:
            # La imagen viene embebida en el mismo status response
            images = data.get("images") or []
            if images and images[0].get("url"):
                return images[0]["url"]
            raise Exception(f"completed pero sin images[].url: {data}")

        if status == "nsfw":
            raise Exception("Imagen rechazada por moderación (NSFW). Intenta con otro prompt.")

        if status == "failed":
            raise Exception(f"Generación fallida: {data}")

        time.sleep(interval)

    raise Exception(f"Timeout ({max_wait}s) esperando resultado de {request_id}")


def generate_image(prompt: str, aspect_ratio: str, label: str, api_key: str,
                   max_retries: int = 2) -> dict:
    """Genera imagen con reintentos automáticos ante fallos de API o timeout."""
    print(f"\n🎨 Generando {label} ({aspect_ratio}) con Higgsfield Soul...", flush=True)
    last_error = None
    for attempt in range(1, max_retries + 2):  # intentos: 1, 2, 3
        if attempt > 1:
            wait = 15 * (attempt - 1)  # 15s, 30s entre reintentos
            print(f"  🔄 Reintento {attempt}/{max_retries + 1} en {wait}s...", flush=True)
            time.sleep(wait)
        try:
            request_id = submit_image(prompt, aspect_ratio, api_key)
            url = poll_result(request_id, api_key)
            print(f"  ✅ {label} lista → {url}", flush=True)
            return {"label": label, "aspect_ratio": aspect_ratio, "prompt": prompt,
                    "url": url, "status": "ok"}
        except Exception as e:
            last_error = e
            print(f"  ⚠️  Intento {attempt} fallido: {e}", flush=True)

    print(f"  ❌ {label} falló tras {max_retries + 1} intentos", flush=True)
    return {"label": label, "aspect_ratio": aspect_ratio, "prompt": prompt,
            "url": None, "status": f"error: {last_error}"}


def extract_prompts(input_text: str) -> list:
    """Extrae scene_prompts[] del JSON del prompt_generator, o usa fallback."""
    import re as _re
    json_str = None
    if "```json" in input_text:
        json_str = input_text.split("```json")[1].split("```")[0].strip()
    elif "```" in input_text:
        json_str = input_text.split("```")[1].split("```")[0].strip()
    elif input_text.strip().startswith("{"):
        json_str = input_text.strip()
    else:
        # Buscar JSON embebido en texto mixto (ej: título + cuerpo del issue)
        m = _re.search(r'\{[\s\S]*?"scene_prompts"[\s\S]*?\}(?:\s*$|\n)', input_text)
        if not m:
            # Intentar extraer cualquier bloque JSON que empiece con {
            m = _re.search(r'(\{[\s\S]*\})', input_text)
        if m:
            json_str = m.group(0).strip()

    if json_str:
        try:
            data = json.loads(json_str)
            scenes = data.get("scene_prompts", [])
            if scenes:
                prompts = []
                for s in scenes:
                    prompts.append({
                        "prompt": s["prompt"],
                        "aspect_ratio": s.get("aspect_ratio", "9:16"),
                        "label": f"Escena {s['scene']}: {s.get('title', '')}",
                    })
                print(f"  ✅ {len(prompts)} escenas extraídas del prompt_generator", flush=True)
                return prompts
        except (json.JSONDecodeError, KeyError) as e:
            print(f"  ⚠️  No se pudo parsear JSON: {e} — usando fallback", flush=True)

    print("  ℹ️  Usando prompt de fallback (sin JSON válido en el input)", flush=True)
    lines = [l.strip() for l in input_text.split("\n") if l.strip()]
    concept = " ".join(lines[:5])[:300]
    return [{
        "prompt": (
            f"Cinematic vertical TikTok thumbnail for: {concept}. "
            "Epic action scene, dramatic lighting, cinematic photography. "
            "Close-up portrait with intense expression, moody atmosphere, "
            "hyperrealistic, 8K quality, shot on Sony A7 III, 35mm lens, f/1.8."
        ),
        "aspect_ratio": "9:16",
        "label": "Escena 1: Thumbnail",
    }]


def main():
    api_key = os.environ.get("HIGGSFIELD_API_KEY", "").strip()
    if not api_key:
        print("ERROR: HIGGSFIELD_API_KEY no configurada", file=sys.stderr)
        sys.exit(1)

    if len(sys.argv) > 1:
        script_input = " ".join(sys.argv[1:])
    else:
        script_input = sys.stdin.read().strip()

    issue_title, issue_body = resolve_issue_context()
    if issue_title:
        # Usar issue_body como input principal si existe (contiene el JSON de prompts del prompt_generator)
        # NO anteponer el título porque extract_prompts busca JSON que empiece con "{"
        script_input = issue_body if issue_body else issue_title
        post_issue_comment(
            f"🖼️ Recibido. Voy a generar las imágenes para: **{issue_title}**\n\n"
            f"Mando las escenas a Higgsfield Soul ahora mismo — las proceso en paralelo "
            f"para que no tengas que esperar. Puede tardar 2-3 minutos dependiendo de "
            f"cuántas escenas tenga el guión."
        )

    if not script_input:
        script_input = "Genera imágenes cinematográficas para contenido viral en TikTok y YouTube"

    print("🖼️  IMAGEN GENERATOR INICIANDO", flush=True)
    print(f"📌 Input: {script_input[:100]}…", flush=True)

    prompts = extract_prompts(script_input)
    results = [None] * len(prompts)

    print(f"\n🚀 Generando {len(prompts)} imágenes en paralelo...", flush=True)

    def run(idx, item):
        return idx, generate_image(
            prompt=item["prompt"],
            aspect_ratio=item["aspect_ratio"],
            label=item["label"],
            api_key=api_key,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(run, i, item): i for i, item in enumerate(prompts)}
        for future in as_completed(futures):
            idx, result = future.result()
            results[idx] = result
            status = "✅" if result["status"] == "ok" else "❌"
            print(f"  {status} {result['label']} completada", flush=True)

    # Output estructurado
    lines = ["# 🖼️ IMÁGENES GENERADAS\n"]
    for r in results:
        icon = "✅" if r["status"] == "ok" else "❌"
        lines.append(f"## {icon} {r['label']} ({r['aspect_ratio']})")
        if r["url"]:
            lines.append(f"**URL:** {r['url']}")
            lines.append(f"![{r['label']}]({r['url']})")
        else:
            lines.append(f"**Error:** {r['status']}")
        lines.append(f"**Prompt:** {r['prompt'][:150]}…")
        lines.append("")

    lines.append("```json")
    lines.append(json.dumps(results, indent=2, ensure_ascii=False))
    lines.append("```")

    output = "\n".join(lines)
    print(output, flush=True)
    post_issue_result(output)


if __name__ == "__main__":
    main()
