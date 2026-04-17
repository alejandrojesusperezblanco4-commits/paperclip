"""
Agente: JSON Prompt Generator
Crea prompts estructurados en JSON para generación de imágenes con IA.
Compatible con Midjourney, DALL-E 3, Stable Diffusion, Flux y Leonardo.AI

Flujo interno:
  1. Búsqueda web de referencias visuales reales del tema (Perplexity sonar)
  2. Generación del JSON de prompts usando esas referencias
"""
import os
import sys
import json
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from memory import get_context_summary, save
from api_client import call_llm, post_issue_result, post_issue_comment, resolve_issue_context

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# ── Paso 1: búsqueda de referencias visuales ────────────────────────────────

VISUAL_SEARCH_PROMPT = """Eres un experto en referencias visuales para generación de imágenes con IA.
Tu tarea: dado un tema, extraer las referencias visuales EXACTAS y verificadas que necesita un prompt engineer para crear imágenes precisas.

Busca y devuelve SOLO esto, en formato estructurado:

## PERSONAJE / ELEMENTO PRINCIPAL
- Descripción física exacta (rasgos, complexión, edad aparente, color de piel/cabello/ojos)
- Ropa / atuendo / accesorios icónicos con colores exactos
- Elementos visuales distintivos (cicatrices, tatuajes, armas, objetos)

## PALETA DE COLORES
- Colores dominantes (hex o nombre exacto)
- Colores de acento
- Tono general: oscuro/brillante/saturado/desaturado

## ESTILO VISUAL
- Referencia de película, videojuego, serie o artista visual más cercana
- Tipo de iluminación dominante en este universo visual
- Textura y acabado visual (hiperrealista, dibujado, cinematográfico, etc.)

## ESCENARIOS ICÓNICOS
- 3-5 locaciones/fondos típicos de este universo con descripción visual detallada

Sé específico con datos reales. No inventes — solo lo que realmente existe para este tema.
"""

def search_visual_references(topic: str, api_key: str) -> str:
    """Busca referencias visuales reales usando Perplexity sonar vía OpenRouter."""
    try:
        query = f"Visual references for AI image generation: {topic} — character appearance, color palette, iconic visual style, art direction"
        result = call_llm(
            messages=[
                {"role": "system", "content": VISUAL_SEARCH_PROMPT},
                {"role": "user", "content": f"Busca referencias visuales reales para: {topic}\n\nQuery de búsqueda: {query}"}
            ],
            api_key=api_key,
            max_tokens=800,
            temperature=0.3,
            title="Paperclip - Visual Reference Search",
            model="perplexity/sonar",  # acceso a internet en tiempo real
        )
        print(f"  🔎 Referencias visuales obtenidas ({len(result)} chars)", flush=True)
        return result
    except Exception as e:
        print(f"  ⚠️  Búsqueda de referencias falló: {e} — continuando sin referencias web", flush=True)
        return ""


# ── Paso 2: generación de prompts ───────────────────────────────────────────

SYSTEM_PROMPT = """Eres el mejor prompt engineer del mundo para Higgsfield Soul (text-to-image). Tu trabajo es leer el guión completo con sus escenas y crear UN prompt por escena — entre 4 y 6 prompts en total — que al generarse formen una secuencia visual coherente y cinematográfica.

Recibes:
1. El guión completo con sus escenas (narración + descripción visual)
2. Referencias visuales REALES del tema (personaje, paleta, estilo) — ÚSALAS para ser preciso

## REGLAS DE ORO para prompts de Higgsfield Soul:
- Mínimo 80 palabras por prompt, en inglés
- COHERENCIA VISUAL: el personaje o elemento principal debe ser CONSISTENTE en todos los prompts
  (mismos rasgos físicos, ropa si aplica, paleta de colores) — usa las referencias reales
- Cada prompt describe exactamente lo que ocurre en esa escena del guión
- Describe la escena como si fuera una producción de Hollywood o una campaña visual premium
- Adapta el estilo visual al nicho del contenido:
  • Drama/historias: chiaroscuro, colores cálidos dramáticos, primer plano emocional
  • Gaming/acción: épico, épicas, colores saturados, partículas de fuego/luz, escenarios masivos
  • Fitness/salud: iluminación vibrante, acción dinámica, fondos de gym o naturaleza
  • Finanzas/negocios: estilo editorial limpio, oficinas modernas, gráficos visuales
  • Tech/IA: luces de neón, interfaces futuristas, fondos oscuros con highlights cyan/purple
  • Lifestyle: golden hour, paleta pastel, ambientes aspiracionales

## ESTRUCTURA DE CADA PROMPT:
[Descripción física EXACTA del personaje usando las referencias reales] + [acción específica de la escena] +
[emoción o estado con detalles físicos concretos] +
[plano de cámara: close-up / medium shot / wide shot / overhead] +
[iluminación cinematográfica adaptada al nicho] +
[ambiente y fondo detallado con colores exactos de la paleta real] +
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
    }
  ]
}

SIN markdown, SIN texto antes o después. Solo el JSON válido.
"""

def call_openrouter(task: str, visual_refs: str, api_key: str) -> str:
    # Inyectar referencias visuales en el mensaje del usuario
    if visual_refs:
        user_content = f"""## REFERENCIAS VISUALES REALES (úsalas para ser preciso):
{visual_refs}

---

## GUIÓN Y TAREA:
{task}"""
    else:
        user_content = task

    content = call_llm(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content}
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

    issue_title, issue_body = resolve_issue_context()
    if issue_title:
        context = issue_body if issue_body and len(issue_body) > len(issue_title) else issue_title
        task = f"Genera prompts para: {context}\n\nContexto adicional: {issue_body or 'ninguno'}"
        post_issue_comment(
            f"🎨 Entendido. Voy a crear los prompts de imagen para: **{issue_title}**\n\n"
            f"Primero busco referencias visuales reales del tema, luego genero los prompts "
            f"con descripción precisa del personaje, paleta de colores y estilo visual exacto."
        )

    if not task:
        task = "Genera prompts JSON para un thumbnail de YouTube sobre '5 herramientas de IA que cambiaran tu vida en 2025'. Canal tech moderno, audiencia hispana 18-35 anos."

    memory_ctx = get_context_summary("prompts", task)
    if memory_ctx:
        task = f"{task}\n\n---\n{memory_ctx}"

    # ── Paso 1: buscar referencias visuales reales ──
    print("🔎 Buscando referencias visuales reales del tema...", flush=True)
    visual_refs = search_visual_references(task[:300], api_key)

    # ── Paso 2: generar prompts con las referencias ──
    print("🎨 Generando prompts con referencias visuales...", flush=True)
    try:
        response = call_openrouter(task, visual_refs, api_key)
        save("prompts", task[:60], response)
        print(response)
        post_issue_result(response)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
