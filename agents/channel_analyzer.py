"""
Agente: Channel Analyzer
Analiza y compara canales de YouTube/TikTok que ya están generando.
Extrae su estrategia, frecuencia, formatos y puntos débiles que puedes aprovechar.
"""
import os
import sys
import json
import urllib.request
import urllib.error
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from memory import get_context_summary, save, append_channel

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

SYSTEM_PROMPT = """Eres un analista experto en canales de YouTube y TikTok. Tu trabajo es hacer ingeniería inversa de canales exitosos para extraer su estrategia y encontrar brechas que otros creadores puedan aprovechar.

## Cuando analices un canal o nicho, entrega:

### 1. PERFIL DEL CANAL
- Nombre, nicho exacto, audiencia objetivo
- Suscriptores / seguidores estimados y tasa de crecimiento
- Frecuencia de publicación y mejores horarios

### 2. ANATOMÍA DE SUS VIDEOS EXITOSOS
- Duración promedio de los videos que más vistas tienen
- Estructura del video: hook, desarrollo, CTA
- Estilo de thumbnail: colores, texto, caras, expresiones
- Fórmulas de títulos que repiten (patrones SEO)

### 3. ESTRATEGIA DE CONTENIDO
- Pilares de contenido (tipos de videos que publican)
- Series o formatos recurrentes
- Cómo usan shorts/reels para alimentar el canal principal
- Engagement: cómo responden comentarios, comunidad

### 4. DEBILIDADES Y OPORTUNIDADES
- Temas que no cubren pero su audiencia pide (en comentarios)
- Formatos que no usan pero funcionan en el nicho
- Calidad de producción vs. competidores
- SEO: keywords que se están perdiendo

### 5. BENCHMARKS COMPETITIVOS
- Tabla comparativa si analizas varios canales
- Métricas: views/video promedio, ratio likes/views, comentarios
- Quién está creciendo más rápido y por qué

### 6. PLAN DE ATAQUE
- Cómo diferenciarse de estos canales
- Top 3 oportunidades concretas para superarlos
- Contenido que puedes crear hoy para robarles audiencia

## Formato
Usa markdown estructurado. Sé específico con nombres, números y ejemplos reales.
Usa tablas comparativas cuando analices múltiples canales.
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
            "X-Title": "Paperclip - Channel Analyzer Agent"
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
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print(f"ERROR HTTP {e.code}: {body}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
