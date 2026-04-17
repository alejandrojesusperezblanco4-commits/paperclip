"""
Agente: JSON Prompt Generator
Crea prompts estructurados en JSON para generación de imágenes con IA.
Compatible con Midjourney, DALL-E 3, Stable Diffusion, Flux y Leonardo.AI
"""
import os
import sys
import json
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from memory import get_context_summary, save
from api_client import call_llm, post_issue_result, post_issue_comment

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

SYSTEM_PROMPT = """Eres el mejor prompt engineer del mundo para Higgsfield Soul (text-to-image). Tu trabajo es leer el guión completo con sus escenas y crear UN prompt por escena — entre 5 y 6 prompts en total — que al generarse formen una secuencia visual coherente y cinematográfica para el canal @historias.en.sombra.

Recibes el guión completo con sus escenas (narración + descripción visual de cada una).

## REGLAS DE ORO para prompts de Higgsfield Soul:
- Mínimo 80 palabras por prompt, en inglés
- COHERENCIA VISUAL: la protagonista debe ser IDÉNTICA en todos los prompts
  (mismo color de cabello, rasgos latinos específicos, edad, ropa si aplica)
- Cada prompt describe exactamente lo que ocurre en esa escena del guión
- Describe la escena como si fuera una película de Hollywood

## ESTRUCTURA DE CADA PROMPT:
[Descripción física consistente de la protagonista] + [acción específica de la escena] +
[emoción con detalles físicos: tears streaming, hands trembling, eyes wide with shock] +
[plano de cámara: close-up / medium shot / wide shot] +
[iluminación cinematográfica: chiaroscuro / warm golden backlight / cold blue neon] +
[ambiente y fondo detallado] +
[técnico: shot on Sony A7 III, 35mm lens, f/1.8, 8K, hyperrealistic, cinematic photography]

## DEVUELVES SOLO este JSON, sin texto adicional:

{
  "scene_prompts": [
    {
      "scene": 1,
      "title": "título de la escena",
      "aspect_ratio": "9:16",
      "resolution": "720p",
      "prompt": "prompt ultra-detallado en inglés, mínimo 80 palabras..."
    },
    {
      "scene": 2,
      "title": "título de la escena",
      "aspect_ratio": "9:16",
      "resolution": "720p",
      "prompt": "prompt ultra-detallado en inglés, mínimo 80 palabras..."
    }
  ]
}

SIN markdown, SIN texto antes o después. Solo el JSON válido.
"""

def call_openrouter(task: str, api_key: str) -> str:
    content = call_llm(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task}
        ],
        api_key=api_key,
        max_tokens=2500,
        temperature=0.7,
        title="Paperclip - Prompt Generator Agent",
    )

    # Limpiar markdown code blocks si el modelo los incluye
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()

    # Validar que sea JSON válido
    try:
        parsed = json.loads(content)
        return json.dumps(parsed, indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        return content


def main():
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY no configurada", file=sys.stderr)
        sys.exit(1)

    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
    else:
        task = sys.stdin.read().strip()

    issue_title = os.environ.get("PAPERCLIP_ISSUE_TITLE", "")
    issue_body  = os.environ.get("PAPERCLIP_ISSUE_BODY", "")
    if issue_title:
        context = issue_body if issue_body and len(issue_body) > len(issue_title) else issue_title
        task = f"Genera prompts para: {context}\n\nContexto adicional: {issue_body or 'ninguno'}"
        post_issue_comment(
            f"🎨 Entendido. Voy a crear los prompts de imagen para: **{issue_title}**\n\n"
            f"Genero uno por escena — protagonista consistente en todas las imágenes, "
            f"descripción cinematográfica, iluminación dramática. "
            f"El JSON estará listo en segundos."
        )

    if not task:
        task = "Genera prompts JSON para un thumbnail de YouTube sobre '5 herramientas de IA que cambiaran tu vida en 2025'. Canal tech moderno, audiencia hispana 18-35 anos."

    memory_ctx = get_context_summary("prompts", task)
    if memory_ctx:
        task = f"{task}\n\n---\n{memory_ctx}"

    try:
        response = call_openrouter(task, api_key)
        save("prompts", task[:60], response)
        print(response)
        post_issue_result(response)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
