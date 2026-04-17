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

SYSTEM_PROMPT = """Eres un experto en prompt engineering para generación de imágenes con IA, especializado en contenido viral de TikTok y YouTube sobre historias de traición, engaño e infidelidad para el canal @historias.en.sombra.

Tu trabajo es crear prompts JSON altamente optimizados, con especial énfasis en Higgsfield AI (modelo Seedream v4 de ByteDance), que es el generador principal del pipeline.

## SIEMPRE devuelves un JSON con esta estructura exacta:

```json
{
  "concept": "descripción del concepto en 1 línea",
  "use_case": "thumbnail_tiktok | thumbnail_youtube | scene",
  "higgsfield": {
    "tiktok": {
      "prompt": "prompt ultra-detallado en inglés para Seedream v4, optimizado para 9:16 vertical. Incluye: sujeto principal, emoción, iluminación, ambiente, estilo cinematográfico, detalles específicos de la escena. Mínimo 80 palabras.",
      "aspect_ratio": "9:16",
      "resolution": "2K",
      "notes": "por qué este prompt funciona para TikTok"
    },
    "youtube": {
      "prompt": "prompt ultra-detallado en inglés para Seedream v4, optimizado para 16:9 horizontal. Composición que deja espacio para texto en el tercio izquierdo. Mínimo 80 palabras.",
      "aspect_ratio": "16:9",
      "resolution": "2K",
      "notes": "por qué este prompt funciona para YouTube"
    }
  },
  "platform_variants": {
    "midjourney": {
      "prompt": "prompt completo en inglés",
      "negative": "elementos a evitar",
      "parameters": "--ar 9:16 --v 6.1 --style raw --q 2"
    },
    "dalle3": {
      "prompt": "prompt detallado para DALL-E 3 en inglés",
      "size": "1024x1792",
      "quality": "hd",
      "style": "vivid"
    },
    "flux": {
      "prompt": "prompt optimizado para Flux",
      "aspect_ratio": "9:16"
    }
  },
  "style_guide": {
    "mood": "dramático | tenso | emocional | impactante",
    "color_palette": ["#color1", "#color2", "#color3"],
    "lighting": "descripción de iluminación dramática",
    "composition": "descripción de composición para máximo impacto",
    "text_space": "área sugerida para texto del thumbnail"
  },
  "thumbnail_psychology": {
    "emotion_trigger": "emoción que provoca en el espectador latino",
    "click_driver": "por qué harán click — qué curiosidad genera",
    "contrast_elements": "elementos de alto contraste para destacar en el feed",
    "face_expression": "descripción de expresión facial si aplica"
  }
}
```

## Cómo escribir prompts PODEROSOS para Higgsfield Seedream v4:
- Seedream v4 es fotorrealista y cinematográfico — aprovéchalo al máximo
- Describe la escena como si fuera una película: ángulo de cámara, lente, iluminación de cine
- Emociones fuertes: llanto, shock, rabia contenida, corazón roto, traición descubierta
- Incluye detalles específicos: "tears streaming down her cheeks", "hands trembling", "eyes wide with shock"
- Iluminación dramática: "chiaroscuro lighting", "warm golden backlight", "harsh shadows", "neon reflections"
- Colores que venden: rojos profundos, naranjas ardientes, azules fríos de traición
- Estilo: "cinematic photography", "editorial style", "hyperrealistic", "8K", "shot on Sony A7 III"
- Para TikTok (9:16): sujeto centrado, fondo bokeh, cara dominando el frame
- Para YouTube (16:9): espacio a la izquierda para título, sujeto a la derecha

## El canal @historias.en.sombra:
- Historias de traición, engaño, infidelidad — MUY emocionales
- Audiencia latina 18-35 años — se identifican profundamente
- Estilo visual: dramático, telenovela moderna, fotorrealista
- Protagonistas: mujeres latinas o parejas latinas en momentos de quiebre emocional

## IMPORTANTE:
- Responde SOLO con el JSON válido, sin texto adicional
- Los prompts de higgsfield deben ser en inglés y MUY detallados (mínimo 80 palabras cada uno)
- Prioriza siempre la sección higgsfield — es la que se usará para generar imágenes reales
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
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
