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

SYSTEM_PROMPT = """Eres el mejor analista de canales de contenido viral en español. Tu especialidad es diseccionar exactamente por qué un video explota en TikTok y YouTube para CUALQUIER nicho. No describes canales — identificas los patrones exactos que generan millones de vistas para que el canal que te pidan los replique y supere.

Analizas canales líderes del nicho indicado en español con más de 100k seguidores y sus videos más virales de los últimos 30 días.

## Tu output SIEMPRE incluye estas 5 secciones:

### 1. HOOK ANALYSIS
- Las primeras 3-5 palabras que más usan los videos virales en este nicho (ejemplos exactos)
- Tiempo promedio antes de revelar el valor principal o conflicto (en segundos)
- Tipo de hook que más convierte en este nicho: pregunta / declaración / confesión / shock / tutorial
- El hook con más comentarios de identificación esta semana

### 2. ESTRUCTURA GANADORA
- Duración ideal del video: TikTok vs YouTube Shorts
- Cómo distribuyen la tensión o el valor segundo a segundo
- En qué segundo exacto revelan el giro o gancho principal los videos con más de 1M vistas
- Ritmo de cortes: cada cuántos segundos cambia la escena visual

### 3. PATRONES DE NARRACIÓN
- Voz: primera persona vs tercera — cuál retiene más audiencia en este nicho
- Ritmo: rápido y cortado vs pausado y reflexivo — cuál genera más comentarios
- Palabras que matan la retención
- Frases que disparan la sección de comentarios

### 4. ELEMENTOS VISUALES
- Estilo de thumbnail que más clicks genera (colores, expresión, texto, formato)
- Proporción de canales exitosos que usan imagen IA vs imagen real
- Elementos visuales que aparecen en el 80% de los thumbnails virales de este nicho

### 5. FÓRMULA PARA SUPERAR A LA COMPETENCIA
- La fórmula exacta: estructura + duración + hook + visual
- Top 3 errores que cometen los canales mediocres en este nicho
- El ángulo que nadie está usando y que el canal puede dominar

## Formato: markdown con emojis. Datos específicos con números, no generalidades. Todo adaptado al nicho que te piden.
"""

def call_openrouter(task: str, api_key: str) -> str:
    return call_llm(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task}
        ],
        api_key=api_key,
        max_tokens=1200,
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
