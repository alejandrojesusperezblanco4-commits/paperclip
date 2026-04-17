"""
Agente: Deep Search YouTube & TikTok
Busca tendencias, keywords virales y oportunidades de contenido en tiempo real.
Usa Perplexity (sonar-pro) via OpenRouter para acceso a internet.
"""
import os
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from memory import get_context_summary, save, append_keywords
from api_client import call_llm, post_issue_result, post_issue_comment, resolve_issue_context

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

SYSTEM_PROMPT = """Eres el mejor investigador de tendencias virales para contenido de video en español. Tu especialidad es encontrar qué está explotando ahora mismo en internet para CUALQUIER nicho que te pidan — drama, fitness, finanzas, tech, humor, lifestyle, gaming o cualquier otro.

Buscas en TODAS las fuentes disponibles simultáneamente:
- TikTok: hashtags virales, sonidos trending, videos con millones de vistas
- YouTube: títulos con más engagement, thumbnails que generan clicks, comentarios más emotivos
- Reddit: subreddits relevantes al nicho, historias con más upvotes
- Twitter/X: tweets virales, tendencias del momento en LATAM
- Google Trends: qué frases busca la gente latina ahora mismo
- Noticias: casos reales que estén en boca de todos esta semana

## Tu output SIEMPRE incluye estas 5 secciones:

### 1. TOP 5 TENDENCIAS DEL MOMENTO
Para cada una: fuente, por qué está viral ahora, potencial para TikTok Y YouTube

### 2. TOP 10 TÍTULOS VIRALES REALES
Títulos exactos que más engagement generaron esta semana en cualquier plataforma para este nicho.
Indica la plataforma y el número aproximado de vistas o interacciones.

### 3. FRASES GANCHO DE LA AUDIENCIA
Las frases exactas que usa la gente en comentarios para identificarse con este tema.
Estas son oro para el hook del video.

### 4. ÁNGULO RECOMENDADO ESTA SEMANA
El enfoque exacto que más va a conectar con la audiencia latina ahora mismo para este tema.
Incluye: emoción dominante, ángulo específico, perspectiva narrativa más efectiva.

### 5. PLATAFORMA GANADORA
¿Este tema pega más en TikTok o YouTube esta semana? ¿Por qué?
Duración óptima recomendada para cada plataforma.

## Formato: markdown con emojis. Datos específicos, no generalidades. Adapta TODO al nicho que te dan.
"""

def call_openrouter(task: str, api_key: str) -> str:
    return call_llm(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task}
        ],
        api_key=api_key,
        max_tokens=1200,
        title="Paperclip - Deep Search Agent",
    )


def main():
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY no configurada", file=sys.stderr)
        sys.exit(1)

    # Leer tarea desde stdin o args
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
    else:
        task = sys.stdin.read().strip()

    # Variables de contexto de Paperclip
    issue_title, issue_body = resolve_issue_context()
    if issue_title:
        context = issue_body if issue_body and len(issue_body) > len(issue_title) else issue_title
        task = f"Búsqueda solicitada: {context}\n\nDetalles adicionales: {issue_body or 'ninguno'}"
        post_issue_comment(
            f"🔍 Entendido. Voy a buscar en TikTok, YouTube, Reddit, Twitter y Google Trends "
            f"sobre: **{issue_title}**\n\nDame un par de minutos — te traigo las tendencias más "
            f"calientes del momento con datos reales."
        )

    if not task:
        task = "Dame las tendencias más importantes en YouTube Shorts y TikTok esta semana para canales de contenido en español. Incluye nichos de oportunidad con baja competencia."

    # Inyectar contexto de memoria Obsidian
    memory_ctx = get_context_summary("deep_search", task)
    if memory_ctx:
        task = f"{task}\n\n---\n{memory_ctx}"

    try:
        response = call_openrouter(task, api_key)
        save("deep_search", task[:60], response)
        print(response)
        post_issue_result(response)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
