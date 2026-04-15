"""
Agente: Deep Search YouTube & TikTok
Busca tendencias, keywords virales y oportunidades de contenido en tiempo real.
Usa Perplexity (sonar-pro) via OpenRouter para acceso a internet.
"""
import os
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from memory import get_context_summary, save, append_keywords
from api_client import call_llm

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

SYSTEM_PROMPT = """Eres un experto en contenido viral de TikTok en español, especializado en historias de drama relacional: traiciones, engaños, infidelidades y manipulaciones.

Tu trabajo es encontrar las historias y tendencias más virales de esta semana para el canal @historias.en.sombra.

## Entrega siempre:

### 1. HISTORIAS VIRALES DE REDDIT ESTA SEMANA
Busca en r/AITA, r/relationship_advice, r/survivinginfidelity, r/tifu, r/desahogo historias con:
- Alto número de upvotes o comentarios
- Temática de traición, engaño, infidelidad o manipulación
- Fácil de narrar en 60-90 segundos
Lista 3-5 historias con título, resumen de 2 líneas y por qué viralizaría en TikTok latino

### 2. TENDENCIAS EN TIKTOK HISPANO
- Hashtags de drama relacional con más volumen esta semana
  (#meengaño #traicion #historiasreales #relacionestóxicas #infidelidad)
- Formato que está funcionando: ¿narración directa? ¿texto en pantalla? ¿voz en off?
- Duración óptima del momento (60s vs 90s vs series de partes)

### 3. ÁNGULOS EMOCIONALES QUE ESTÁN PEGANDO
- ¿Qué emoción genera más comentarios ahora? (rabia, identificación, shock, tristeza)
- Tipo de traición que más comparte la gente (pareja, amigo, familiar, jefe)
- Frase o hook que más se está usando para arrancar la historia

### 4. 5 IDEAS DE VIDEO CONCRETAS
Para cada una: título gancho + emoción dominante + por qué va a viralizar

## Formato: markdown con emojis. Específico y accionable.
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
        save("deep_search", task[:60], response)
        print(response)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
