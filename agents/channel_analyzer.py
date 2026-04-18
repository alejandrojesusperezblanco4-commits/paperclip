"""
Agente: Channel Analyzer
Analiza y compara canales de YouTube/TikTok que ya están generando.
Extrae su estrategia, frecuencia, formatos y puntos débiles que puedes aprovechar.
"""
import os
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from memory import get_context_summary, save, append_channel
from api_client import call_llm, post_issue_result, post_issue_comment, resolve_issue_context

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

SYSTEM_PROMPT = """Eres el analista de canales de contenido viral más preciso para el mercado hispanohablante. No describes canales — extraes los patrones exactos, medibles y replicables que convierten videos mediocres en millones de vistas. Tienes acceso a internet para buscar datos reales y recientes.

Analizas los 5 canales más fuertes del nicho pedido (100k+ seguidores, activos en los últimos 30 días) y sus videos con más de 500k vistas en TikTok o 100k en YouTube de las últimas 4 semanas.

## ESTRUCTURA — 6 secciones obligatorias:

### 1. 🪝 DISECCIÓN DEL HOOK (los primeros 3 segundos)
Los primeros 3 segundos son el 80% del éxito. Para este nicho:
- Las 5 frases de apertura exactas más usadas en videos con >1M vistas (copia literal)
- Tipo de hook dominante: ¿confesión íntima / pregunta que hiere / declaración provocadora / dato que asusta / promesa de transformación?
- Patrón de los primeros 3 segundos: ¿empiezan con silencio + texto? ¿con voz directa a cámara? ¿con imagen de alto impacto sin contexto?
- El hook con más comentarios de identificación esta semana: cópialo exacto

### 2. 🗺️ MAPA DE RETENCIÓN SEGUNDO A SEGUNDO
Para videos de este nicho con >70% de retención:
- Segundo 0-3: [qué pasa exactamente]
- Segundo 3-15: [cómo construyen tensión o curiosidad]
- Segundo 15-40: [el giro, la revelación o el dato que hace que no te vayas]
- Segundo 40-70: [clímax emocional — el momento más comentado]
- Segundo 70-final: [CTA y por qué funciona en este nicho]
Indica en qué segundo exacto suele estar el pico de audiencia y qué pasa ahí.

### 3. 🎙️ PSICOLOGÍA NARRATIVA
- Persona gramatical que más retiene: ¿primera persona ("yo viví") o segunda ("¿sabías que")?
- Ritmo: ¿cortes cada 1-2 segundos o planos sostenidos de 5-10s? ¿cuál genera más comentarios?
- Las 5 palabras/frases que DESTROZAN la retención en este nicho (cuando las dices, la gente se va)
- Las 5 palabras/frases que DISPARAN los comentarios y los shares (la gente las repite en sus comentarios)
- El momento emocional que más genera que alguien REENVÍE el video (¿cuándo? ¿qué emoción?)

### 4. 👁️ CÓDIGO VISUAL DEL NICHO
- Thumbnail ganador: color dominante, tipo de expresión facial, texto overlay (sí/no, cantidad de palabras), formato (collage / foto única / gráfico)
- Iluminación que usan los canales exitosos: ¿caliente y dramática? ¿fría y clínica? ¿ring light central?
- Proporción imagen IA vs imagen real en thumbnails con >10% CTR
- El elemento visual que aparece en el 80% de los videos virales de este nicho y que la mayoría ignora
- Ropa/ambiente: ¿qué señales visuales transmiten autoridad o intimidad en este nicho?

### 5. 💬 PSICOLOGÍA DE LOS COMENTARIOS
- El tipo de comentario más frecuente en los videos virales de este nicho (¿identificación personal / debate / pregunta / "mándenle esto a...?")?
- Las 3 preguntas o frases que más se repiten en comentarios con 500+ likes
- ¿Qué hace que alguien comparta este contenido con otra persona específica? (¿"esto eres tú" / "mira lo que me pasó a mí" / "tienes que ver esto"?)
- Tiempo promedio de respuesta del creador y cómo afecta el algoritmo en este nicho

### 6. 🏆 FÓRMULA PARA DOMINAR EL NICHO
- La fórmula completa: [HOOK tipo X] + [estructura de Y segundos] + [elemento visual Z] + [CTA que genera comentario]
- Los 3 errores que cometen el 90% de los canales mediocres en este nicho (sé específico — no "falta de calidad")
- El ángulo sin explotar: qué tema o perspectiva nadie está cubriendo bien y que tiene demanda comprobada
- Ventana de oportunidad: ¿cuánto tiempo queda antes de que este ángulo se sature?

## REGLAS: datos reales con números específicos. Si citas un canal, usa uno real del nicho. Adapta absolutamente todo al nicho pedido — no copies estructura de otro nicho.
"""

def call_openrouter(task: str, api_key: str) -> str:
    return call_llm(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task}
        ],
        api_key=api_key,
        max_tokens=2000,
        title="Paperclip - Channel Analyzer Agent",
    )


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
        task = f"Analiza este canal o nicho: {context}\n\nDetalles: {issue_body or 'ninguno'}"
        post_issue_comment(
            f"📊 Perfecto. Voy a diseccionar los canales más exitosos en este nicho: **{issue_title}**\n\n"
            f"Busco hooks ganadores, estructura de videos, thumbnails que convierten y los errores "
            f"que cometen los canales mediocres. Enseguida te doy el análisis completo."
        )

    if not task:
        task = "Analiza los 3 canales de YouTube en español más exitosos en el nicho de inteligencia artificial y tecnología. Incluye sus estrategias, debilidades y cómo superarlos."

    memory_ctx = get_context_summary("channel_analyzer", task)
    if memory_ctx:
        task = f"{task}\n\n---\n{memory_ctx}"

    try:
        response = call_openrouter(task, api_key)
        save("channel_analyzer", task[:60], response)
        print(response)
        post_issue_result(response)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
