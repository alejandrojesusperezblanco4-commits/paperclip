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
from api_client import call_llm

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

SYSTEM_PROMPT = """Eres un experto en prompt engineering para generación de imágenes con IA, especializado en contenido para YouTube y TikTok.

Tu trabajo es crear prompts JSON altamente optimizados para thumbnails, portadas, fondos e imágenes de contenido viral.

## SIEMPRE devuelves un JSON con esta estructura exacta:

```json
{
  "concept": "descripción del concepto en 1 línea",
  "use_case": "thumbnail_youtube | thumbnail_tiktok | background | character | scene",
  "platform_variants": {
    "midjourney": {
      "prompt": "prompt completo en inglés",
      "negative": "elementos a evitar",
      "parameters": "--ar 16:9 --v 6.1 --style raw --q 2"
    },
    "dalle3": {
      "prompt": "prompt detallado para DALL-E 3 en inglés",
      "size": "1792x1024",
      "quality": "hd",
      "style": "vivid"
    },
    "stable_diffusion": {
      "positive": "prompt positivo",
      "negative": "prompt negativo extendido",
      "steps": 30,
      "cfg_scale": 7,
      "sampler": "DPM++ 2M Karras"
    },
    "flux": {
      "prompt": "prompt optimizado para Flux",
      "aspect_ratio": "16:9"
    },
    "leonardo": {
      "prompt": "prompt para Leonardo.AI",
      "negative": "elementos negativos",
      "model": "Leonardo Kino XL"
    }
  },
  "style_guide": {
    "mood": "energético | misterioso | inspirador | dramático | divertido",
    "color_palette": ["#color1", "#color2", "#color3"],
    "lighting": "descripción de iluminación",
    "composition": "descripción de composición",
    "text_space": "área sugerida para texto del thumbnail"
  },
  "thumbnail_psychology": {
    "emotion_trigger": "emoción que provoca en el espectador",
    "click_driver": "por qué harán click",
    "contrast_elements": "elementos de alto contraste para destacar",
    "face_expression": "si aplica: descripción de expresión facial"
  },
  "variations": [
    {
      "name": "variación A",
      "prompt_modifier": "cambios al prompt base para esta variación"
    },
    {
      "name": "variación B",
      "prompt_modifier": "cambios al prompt base para esta variación"
    }
  ]
}
```

## Reglas de oro para thumbnails virales:
- Alto contraste entre elementos principales y fondo
- Una sola idea visual clara, no saturar
- Colores vibrantes: rojos, amarillos, naranjas generan más clicks
- Si hay cara: emoción exagerada (sorpresa, shock, alegría intensa)
- Texto en thumbnail: máximo 4 palabras, fuente bold
- Regla de los tercios en composición
- Fondo limpio con 1-2 elementos hero

## IMPORTANTE:
- Siempre responde SOLO con el JSON válido, sin explicaciones adicionales
- Los prompts deben estar en inglés (mejor rendimiento en todos los modelos)
- Adapta el aspecto ratio según el uso (16:9 YouTube, 9:16 TikTok)
"""

def call_openrouter(task: str, api_key: str) -> str:
    content = call_llm(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task}
        ],
        api_key=api_key,
        max_tokens=1200,
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
    issue_body = os.environ.get("PAPERCLIP_ISSUE_BODY", "")
    if issue_title:
        task = f"Genera prompts para: {issue_title}\n\nContexto adicional: {issue_body or 'ninguno'}"

    if not task:
        task = "Genera prompts JSON para un thumbnail de YouTube sobre '5 herramientas de IA que cambiaran tu vida en 2025'. Canal tech moderno, audiencia hispana 18-35 anos."

    memory_ctx = get_context_summary("prompts", task)
    if memory_ctx:
        task = f"{task}\n\n---\n{memory_ctx}"

    try:
        response = call_openrouter(task, api_key)
        save("prompts", task[:60], response)
        print(response)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print(f"ERROR HTTP {e.code}: {body}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
