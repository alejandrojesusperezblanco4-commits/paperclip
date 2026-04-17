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
import base64
import urllib.request
import urllib.error
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

HIGGSFIELD_API_URL = "https://platform.higgsfield.ai"
MODEL_PATH = "bytedance/seedream/v4/text-to-image"
DONE_STATUSES = {"Completed", "completed", "Failed", "failed", "Cancelled", "cancelled", "NSFW"}
SUCCESS_STATUSES = {"Completed", "completed"}


def build_auth_header(api_key: str) -> str:
    """
    Higgsfield usa scheme de auth custom 'Key' (ni Bearer ni Basic).
    El api_key viene en formato 'KEY_ID:KEY_SECRET'.
    """
    return f"Key {api_key}"


def submit_image(prompt: str, aspect_ratio: str, resolution: str, api_key: str) -> str:
    """Envía una solicitud de generación a Higgsfield y devuelve el request_id."""
    payload = {
        "arguments": {
            "prompt": prompt,
            "resolution": resolution,
            "aspect_ratio": aspect_ratio,
            "camera_fixed": True,
        }
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{HIGGSFIELD_API_URL}/{MODEL_PATH}",
        data=data,
        headers={
            "Authorization": build_auth_header(api_key),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
        result = json.loads(body)

    request_id = result.get("request_id") or result.get("id")
    if not request_id:
        raise Exception(f"No se obtuvo request_id: {result}")
    print(f"  📤 Solicitud enviada → ID: {request_id}", flush=True)
    return request_id


def poll_result(request_id: str, api_key: str, max_wait: int = 120) -> str:
    """Hace polling hasta obtener la URL de la imagen generada."""
    deadline = time.time() + max_wait
    interval = 4
    headers = {"Authorization": build_auth_header(api_key)}

    while time.time() < deadline:
        # 1. Consultar status
        req = urllib.request.Request(
            f"{HIGGSFIELD_API_URL}/requests/{request_id}/status",
            headers=headers,
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            status_data = json.loads(resp.read().decode("utf-8"))

        status = status_data.get("status", "unknown")
        print(f"  ⏳ Estado: {status}", flush=True)

        if status in SUCCESS_STATUSES:
            # 2. Obtener el resultado
            req_result = urllib.request.Request(
                f"{HIGGSFIELD_API_URL}/requests/{request_id}/result",
                headers=headers,
                method="GET",
            )
            try:
                with urllib.request.urlopen(req_result, timeout=15) as r:
                    result = json.loads(r.read().decode("utf-8"))
            except Exception:
                # Fallback: el status a veces trae el resultado embebido
                result = status_data

            # Buscar URL en formatos posibles
            images = result.get("images") or status_data.get("images") or []
            if images and isinstance(images, list) and images[0].get("url"):
                return images[0]["url"]

            url = (
                result.get("url")
                or (result.get("result") or {}).get("url")
                or (result.get("output") or [None])[0]
            )
            if url:
                return url
            raise Exception(f"Completado sin URL reconocible: {result}")

        if status in DONE_STATUSES:
            raise Exception(f"Generación fallida con status '{status}': {status_data}")

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


def extract_higgsfield_prompts(input_text: str) -> list:
    """
    Intenta parsear el JSON del prompt_generator y extraer los prompts de Higgsfield.
    Si no hay JSON válido o no tiene sección higgsfield, cae al fallback.
    """
    # Intentar extraer JSON del input
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
            hf = data.get("higgsfield", {})
            prompts = []
            # Formato diario: solo 1 imagen (TikTok 9:16). YouTube ya no aplica.
            if hf.get("tiktok", {}).get("prompt"):
                prompts.append({
                    "prompt": hf["tiktok"]["prompt"],
                    "aspect_ratio": hf["tiktok"].get("aspect_ratio", "9:16"),
                    "resolution": hf["tiktok"].get("resolution", "2K"),
                    "label": "Thumbnail TikTok",
                })
            if prompts:
                print(f"  ✅ Prompts extraídos del prompt_generator ({len(prompts)} imágenes)", flush=True)
                return prompts
        except (json.JSONDecodeError, KeyError) as e:
            print(f"  ⚠️  No se pudo parsear JSON del prompt_generator: {e} — usando fallback", flush=True)

    # Fallback: construir prompts básicos desde el texto del guión
    print("  ℹ️  Usando prompts de fallback", flush=True)
    lines = [l.strip() for l in input_text.split("\n") if l.strip()]
    concept = " ".join(lines[:5])[:300]

    return [
        {
            "prompt": (
                f"Cinematic vertical TikTok thumbnail, dramatic Latin telenovela style, 9:16. "
                f"A Latin woman with tears streaming down her face, eyes wide with shock and betrayal, "
                f"trembling hands, close-up portrait. Chiaroscuro lighting, deep red and orange tones, "
                f"bokeh background, hyperrealistic, shot on Sony A7 III, 8K quality. Scene: {concept[:150]}"
            ),
            "aspect_ratio": "9:16",
            "resolution": "2K",
            "label": "Thumbnail TikTok",
        },
    ]


def main():
    higgsfield_key = os.environ.get("HIGGSFIELD_API_KEY", "").strip()
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
    print(f"📌 Input: {script_input[:100]}...", flush=True)

    prompts = extract_higgsfield_prompts(script_input)
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
