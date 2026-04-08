"""
Agente: Deep Search YouTube & TikTok
Busca tendencias, keywords virales y oportunidades de contenido en tiempo real.
Usa Perplexity (sonar-pro) via OpenRouter para acceso a internet.
"""
import os
import sys
import json
import urllib.request
import urllib.error
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from memory import get_context_summary, save, append_keywords

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

SYSTEM_PROMPT = """Eres un experto en crecimiento de canales de YouTube y TikTok con acceso a internet en tiempo real.

Tu especialidad es el DEEP SEARCH: encontrar tendencias, keywords virales, nichos sin explotar y oportunidades de contenido.

## Cuando hagas búsquedas, siempre entrega:

### 1. TENDENCIAS ACTUALES
- Top 5 temas virales en YouTube/TikTok ahora mismo relacionados con la consulta
- Hashtags con mayor crecimiento esta semana
- Formatos de video que están explotando (duración, estilo, estructura)

### 2. KEYWORDS DE OPORTUNIDAD
- Keywords con alto volumen pero baja competencia
- Long-tail keywords que los creadores grandes ignoran
- Variaciones en español e inglés cuando aplica

### 3. NICHOS Y ÁNGULOS
- Sub-nichos específicos dentro del tema
- Ángulos únicos que nadie está cubriendo
- Preguntas frecuentes de la audiencia sin responder

### 4. DATOS Y MÉTRICAS
- Estimado de búsquedas mensuales cuando disponible
- Ejemplos de videos que están funcionando (títulos reales)
- Patron de publicación de los canales exitosos

### 5. PLAN DE ACCIÓN
- 5 ideas de videos concretas con títulos optimizados para SEO
- Mejor momento para publicar
- Thumbnails: qué elementos visuales están funcionando

## Formato de respuesta
Usa markdown con emojis para facilitar la lectura. Sé específico y accionable. No seas genérico.
"""

def call_openrouter(task: str, api_key: str) -> str:
    payload = {
        "model": "openai/gpt-oss-120b:free",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task}
        ],
        "max_tokens": 1200
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://127.0.0.1:3100",
            "X-Title": "Paperclip - Deep Search Agent"
        },
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=90) as response:
        result = json.loads(response.read().decode("utf-8"))
        return result["choices"][0]["message"]["content"]


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
    issue_title = os.environ.get("PAPERCLIP_ISSUE_TITLE", "")
    issue_body = os.environ.get("PAPERCLIP_ISSUE_BODY", "")
    if issue_title:
        task = f"Búsqueda solicitada: {issue_title}\n\nDetalles adicionales: {issue_body or 'ninguno'}"

    if not task:
        task = "Dame las tendencias más importantes en YouTube Shorts y TikTok esta semana para canales de contenido en español. Incluye nichos de oportunidad con baja competencia."

    # Inyectar contexto de memoria Obsidian
    memory_ctx = get_context_summary("deep_search", task)
    if memory_ctx:
        task = f"{task}\n\n---\n{memory_ctx}"

    try:
        response = call_openrouter(task, api_key)

        # Guardar en memoria Obsidian
        save("deep_search", task[:60], response)

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
