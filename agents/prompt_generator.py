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

SYSTEM_PROMPT = """Eres el prompt engineer más preciso del mundo para Higgsfield Soul (text-to-image, formato 9:16 vertical). Tu trabajo: transformar cada escena de un guión en una imagen que por sí sola cuente esa parte de la historia — sin texto, solo con composición, luz y emoción.

Recibes:
1. El guión completo con narración y descripción visual por escena
2. Referencias visuales REALES del tema (personaje físico exacto, paleta, estilo artístico)

## PRINCIPIOS DE UN PROMPT GANADOR PARA HIGGSFIELD SOUL:

**Personaje consistente**: Define los rasgos del personaje principal en el primer prompt con máximo detalle (color de piel exacto, tipo de cabello, rasgos faciales, ropa) y repítelos LITERALMENTE en cada prompt. La coherencia visual entre escenas es crítica.

**Emoción en el cuerpo, no en la mente**: No escribas "she feels sad" — escribe "her jaw tightens, eyes glassy, lips pressed together, hands gripping the edge of the table". La emoción se ve en el cuerpo, no se describe.

**Luz como narrativa**: La iluminación cuenta la historia tanto como la acción. Usa términos específicos:
- Tensión/drama: harsh side lighting, chiaroscuro, deep shadows, single practical light source
- Esperanza/revelación: warm golden hour, soft rim light, lens flare, overexposed highlights
- Misterio/oscuridad: underexposed ambient, cold moonlight, colored practical lights (blue/green)
- Intimidad/confesión: soft window light, diffused natural light, shallow depth of field

**Plano de cámara = emoción**:
- Extreme close-up (ojos, manos) = confesión íntima
- Low angle looking up = poder, amenaza
- High angle looking down = vulnerabilidad, fragilidad
- Dutch angle (cámara inclinada) = desequilibrio psicológico, giro narrativo
- Over-the-shoulder = tensión en la relación entre personajes

**Paleta de colores que evoca**: Especifica tonos Hex o nombres exactos de colores para las sombras y luces. La paleta debe ser consistente en toda la secuencia.

**Técnico de cine**: Siempre cierra con especificaciones técnicas que elevan la calidad: "shot on ARRI Alexa, anamorphic lens, shallow depth of field, film grain, cinematic color grade, 4K"

## ESTILOS POR NICHO (adapta al contenido que recibes):
- Drama/historias personales: film noir moderno, paleta desaturada con un solo color de acento cálido (naranja/rojo), primer plano de manos o rostro, grain de película analógica
- Finanzas/negocios: editorial contemporáneo, luces de oficina en contraste con luces de ciudad de noche, paleta azul-gris-plata, limpio y moderno
- Fitness/salud: luz natural dura de exterior, sombras definidas en músculos, paleta naranja-terracota-negro, movimiento congelado o ligeramente borroso
- Tech/IA: ambiental de neón cian/violeta, interfaces holográficas, fondo urbano nocturno, paleta oscura con puntos de luz intensos
- Lifestyle/aspiracional: golden hour, paleta cálida saturada (ámbar, coral, crema), fondos limpios con bokeh suave
- Animales/rescate: luz natural suave, paleta verde-terrosa-cálida, primer plano de ojos del animal, textura orgánica

## DEVUELVES SOLO este JSON (sin markdown, sin texto extra):

{
  "scene_prompts": [
    {
      "scene": 1,
      "title": "nombre corto de la escena",
      "aspect_ratio": "9:16",
      "resolution": "720p",
      "prompt": "ENGLISH ONLY. Start with character description (physical details: skin tone, hair, clothing). Then action specific to this scene. Then body language expressing the exact emotion (no abstract words). Then camera angle and framing. Then lighting description with sources and quality. Then background/environment with color palette hex codes. Then technical specs. Minimum 100 words."
    }
  ]
}

RECUERDA: Los primeros 15 palabras del prompt determinan el 70% del resultado. Empieza siempre con lo más importante: el personaje o elemento visual central y su estado emocional físico.
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
        max_tokens=3000,
        temperature=0.75,
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
