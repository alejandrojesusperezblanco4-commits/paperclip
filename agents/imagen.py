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
from api_client import post_issue_result, post_issue_comment

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


def generate_image(prompt: str, aspect_ratio: str, label: str, api_key: str) -> dict:
    print(f"\n🎨 Generando {label} ({aspect_ratio}) con Higgsfield Soul...", flush=True)
    try:
        request_id = submit_image(prompt, aspect_ratio, api_key)
        url = poll_result(request_id, api_key)
        print(f"  ✅ {label} lista → {url}", flush=True)
        return {"label": label, "aspect_ratio": aspect_ratio, "prompt": prompt, "url": url, "status": "ok"}
    except Exception as e:
        print(f"  ❌ Error generando {label}: {e}", flush=True)
        return {"label": label, "aspect_ratio": aspect_ratio, "prompt": prompt, "url": None, "status": f"error: {e}"}


def extract_prompts(input_text: str) -> list:
    """Extrae scene_prompts[] del JSON del prompt_generator, o usa fallback."""
    json_str = None
    if "```json" in input_text:
        json_str = input_text.split("```json")[1].split("```")[0].strip()
    elif "```" in input_text:
        json_str = input_text.split("```")[1].split("```")[0].strip()
    elif input_text.strip().startswith("{"):
        json_str = input_text.strip()

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

    print("  ℹ️  Usando prompt de fallback", flush=True)
    lines = [l.strip() for l in input_text.split("\n") if l.strip()]
    concept = " ".join(lines[:5])[:250]
    return [{
        "prompt": (
            "Cinematic vertical TikTok thumbnail, dramatic Latin telenovela style. "
            "A Latin woman with tears streaming down her face, eyes wide with shock and betrayal, "
            "close-up portrait. Chiaroscuro lighting, deep red and orange tones, bokeh background, "
            f"hyperrealistic, 8K quality. Scene: {concept}"
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

    issue_title = os.environ.get("PAPERCLIP_ISSUE_TITLE", "")
    issue_body  = os.environ.get("PAPERCLIP_ISSUE_BODY", "")
    if issue_title:
        script_input = f"{issue_title}\n\n{issue_body or ''}"
        post_issue_comment(
            f"🖼️ Recibido. Voy a generar las imágenes para: **{issue_title}**\n\n"
            f"Mando las escenas a Higgsfield Soul ahora mismo — las proceso en paralelo "
            f"para que no tengas que esperar. Puede tardar 2-3 minutos dependiendo de "
            f"cuántas escenas tenga el guión."
        )

    if not script_input:
        script_input = "Historia de traición: ella descubre que su pareja la engañó con su mejor amiga"

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

    with ThreadPoolExecutor(max_workers=4) as executor:
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
