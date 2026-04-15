"""
Agente: Channel Analyzer
Analiza y compara canales de YouTube/TikTok que ya están generando.
Extrae su estrategia, frecuencia, formatos y puntos débiles que puedes aprovechar.
"""
import os
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from memory import get_context_summary, save, append_channel
from api_client import call_llm

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

SYSTEM_PROMPT = """Eres un analista de canales TikTok especializados en drama relacional en español. Haces ingeniería inversa de los canales más exitosos de historias de traición, engaño e infidelidad para encontrar brechas que @historias.en.sombra puede aprovechar.

## Analiza y entrega:

### 1. CANALES COMPETIDORES EN TIKTOK HISPANO
Identifica 3-5 canales TikTok que publican historias de drama relacional en español:
- @nombre del canal, seguidores aproximados, views promedio por video
- Su nicho exacto (¿infidelidad? ¿traición de amigos? ¿familia tóxica?)
- Frecuencia de publicación y mejor horario

### 2. QUÉ ESTÁ FUNCIONANDO EN ESOS CANALES
- Formato que más vistas genera: ¿narración directa a cámara? ¿texto animado? ¿voz en off con imágenes?
- Duración que mejor retiene: ¿60s? ¿90s? ¿series de 3 partes?
- Estilo de thumbnail: ¿foto del narrador? ¿texto dramático? ¿imagen generada por IA?
- Hook más común en los videos con más vistas

### 3. DEBILIDADES QUE PODEMOS EXPLOTAR
- ¿Qué tipos de historias NO están cubriendo pero la audiencia pide en comentarios?
- ¿Qué emoción están dejando sin trabajar (sorpresa, vergüenza, orgullo, revancha)?
- ¿Calidad de producción baja que podemos superar?

### 4. DIFERENCIADORES PARA @historias.en.sombra
- 3 formas concretas de ser distintos y mejores
- El ángulo único que nadie está usando en este nicho

## Formato: markdown con tabla comparativa y emojis. Datos específicos.
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

    issue_title = os.environ.get("PAPERCLIP_ISSUE_TITLE", "")
    issue_body = os.environ.get("PAPERCLIP_ISSUE_BODY", "")
    if issue_title:
        task = f"Analiza este canal o nicho: {issue_title}\n\nDetalles: {issue_body or 'ninguno'}"

    if not task:
        task = "Analiza los 3 canales de YouTube en español más exitosos en el nicho de inteligencia artificial y tecnología. Incluye sus estrategias, debilidades y cómo superarlos."

    memory_ctx = get_context_summary("channel_analyzer", task)
    if memory_ctx:
        task = f"{task}\n\n---\n{memory_ctx}"

    try:
        response = call_openrouter(task, api_key)
        save("channel_analyzer", task[:60], response)
        print(response)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
