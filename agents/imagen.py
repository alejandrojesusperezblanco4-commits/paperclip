"""
Agente: Imagen Generator
Toma el guión generado por Storytelling y genera imágenes reales con Higgsfield AI.
Devuelve URLs de las imágenes generadas (thumbnail TikTok 9:16 + portada 16:9).

Requiere: HIGGSFIELD_API_KEY en env
"""
import os
import sys
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

HIGGSFIELD_API_URL = "https://cloud.higgsfield.ai/api"
MODEL = "bytedance/seedream/v4/text-to-image"


def build_auth_header(api_key: str) -> str:
    """
    Higgsfield usa formato KEY_ID:KEY_SECRET como Bearer token.
    Acepta tanto el string combinado como solo el KEY_ID.
    """
    return f"Bearer {api_key}"


def submit_image(prompt: str, aspect_ratio: str, resolution: str, api_key: str) -> str:
    """Envía una solicitud de generación a Higgsfield y devuelve el request_id."""
    payload = {
        "model": MODEL,
        "arguments": {
            "prompt": prompt,
            "resolution": resolution,
            "aspect_ratio": aspect_ratio,
            "camera_fixed": True,
        }
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{HIGGSFIELD_API_URL}/requests",
        data=data,
        headers={
            "Authorization": build_auth_header(api_key),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    request_id = result.get("id") or result.get("request_id")
    if not request_id:
        raise Exception(f"No se obtuvo request_id: {result}")
    print(f"  📤 Solicitud enviada → ID: {request_id}", flush=True)
    return request_id


def poll_result(request_id: str, api_key: str, max_wait: int = 120) -> str:
    """Hace polling hasta obtener la URL de la imagen generada."""
    deadline = time.time() + max_wait
    interval = 5

    while time.time() < deadline:
        req = urllib.request.Request(
            f"{HIGGSFIELD_API_URL}/requests/{request_id}",
            headers={"Authorization": build_auth_header(api_key)},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        status = result.get("status", "unknown")
        print(f"  ⏳ Estado: {status}", flush=True)

        if status == "completed":
            # Buscar URL en distintos formatos posibles de respuesta
            url = (
                result.get("result", {}).get("url")
                or result.get("output", [None])[0]
                or result.get("url")
            )
            if url:
                return url
            raise Exception(f"Completado pero sin URL: {result}")

        if status in ("failed", "error", "cancelled"):
            raise Exception(f"Generación fallida: {result.get('error', result)}")

        time.sleep(interval)

    raise Exception(f"Timeout esperando resultado de {request_id}")


def generate_image(prompt: str, aspect_ratio: str, label: str, api_key: str) -> dict:
    """Genera una imagen y devuelve un dict con label, prompt, url."""
    resolution = "2K"
    print(f"\n🎨 Generando {label} ({aspect_ratio})...", flush=True)
    try:
        request_id = submit_image(prompt, aspect_ratio, resolution, api_key)
        url = poll_result(request_id, api_key)
        print(f"  ✅ {label} lista → {url}", flush=True)
        return {"label": label, "aspect_ratio": aspect_ratio, "prompt": prompt, "url": url, "status": "ok"}
    except Exception as e:
        print(f"  ❌ Error generando {label}: {e}", flush=True)
        return {"label": label, "aspect_ratio": aspect_ratio, "prompt": prompt, "url": None, "status": f"error: {e}"}


def build_prompts_from_script(script_text: str) -> list:
    """
    Extrae el concepto visual del guión y genera 2 prompts:
    - Thumbnail TikTok (9:16)
    - Portada/Cover YouTube (16:9)
    """
    # Tomar las primeras líneas del guión para contexto
    lines = [l.strip() for l in script_text.split("\n") if l.strip()]
    concept = " ".join(lines[:5])[:400]

    tiktok_prompt = (
        f"Cinematic vertical thumbnail for TikTok, dramatic Latin telenovela style. "
        f"Betrayal and infidelity emotional scene. Close-up of a woman with tear-filled eyes, "
        f"shocked expression, discovering betrayal. Dark dramatic lighting with warm tones. "
        f"High contrast. Photorealistic. Context: {concept[:200]}"
    )

    youtube_prompt = (
        f"Cinematic horizontal YouTube thumbnail. Dramatic betrayal scene inspired by: {concept[:200]}. "
        f"Bold colors, red and orange tones, high contrast. One clear emotional face showing shock or rage. "
        f"Space for text overlay on left third. Photorealistic. 16:9 composition."
    )

    return [
        {"prompt": tiktok_prompt, "aspect_ratio": "9:16", "label": "Thumbnail TikTok"},
        {"prompt": youtube_prompt, "aspect_ratio": "16:9", "label": "Portada YouTube"},
    ]


def main():
    higgsfield_key = os.environ.get("HIGGSFIELD_API_KEY", "")
    if not higgsfield_key:
        print("ERROR: HIGGSFIELD_API_KEY no configurada", file=sys.stderr)
        sys.exit(1)

    # Leer guión desde stdin o args
    if len(sys.argv) > 1:
        script_input = " ".join(sys.argv[1:])
    else:
        script_input = sys.stdin.read().strip()

    issue_title = os.environ.get("PAPERCLIP_ISSUE_TITLE", "")
    issue_body = os.environ.get("PAPERCLIP_ISSUE_BODY", "")
    if issue_title:
        script_input = f"{issue_title}\n\n{issue_body or ''}"

    if not script_input:
        script_input = "Historia de traición: ella descubre que su pareja la engañó con su mejor amiga"

    print(f"🖼️  IMAGEN GENERATOR INICIANDO", flush=True)
    print(f"📌 Concepto: {script_input[:100]}...", flush=True)

    prompts = build_prompts_from_script(script_input)
    results = []

    for item in prompts:
        result = generate_image(
            prompt=item["prompt"],
            aspect_ratio=item["aspect_ratio"],
            label=item["label"],
            api_key=higgsfield_key,
        )
        results.append(result)

    # Output estructurado
    output_lines = ["# 🖼️ IMÁGENES GENERADAS\n"]
    for r in results:
        status_icon = "✅" if r["status"] == "ok" else "❌"
        output_lines.append(f"## {status_icon} {r['label']} ({r['aspect_ratio']})")
        if r["url"]:
            output_lines.append(f"**URL:** {r['url']}")
            output_lines.append(f"![{r['label']}]({r['url']})")
        else:
            output_lines.append(f"**Error:** {r['status']}")
        output_lines.append(f"**Prompt usado:** {r['prompt'][:150]}...")
        output_lines.append("")

    # JSON para que el Director pueda parsearlo
    output_lines.append("```json")
    output_lines.append(json.dumps(results, indent=2, ensure_ascii=False))
    output_lines.append("```")

    output = "\n".join(output_lines)
    print(output, flush=True)


if __name__ == "__main__":
    main()
