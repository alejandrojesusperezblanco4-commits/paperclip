"""
Agente: Storytelling Designer
Diseña guiones, narrativas y estructuras de video para YouTube y TikTok.
Genera contenido viral con hooks poderosos, arcos narrativos y CTAs efectivos.
"""
import os
import sys
import json
import urllib.request
import urllib.error
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from memory import get_context_summary, save

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

SYSTEM_PROMPT = """Eres un maestro del storytelling para video corto y largo, especializado en crear contenido viral para YouTube y TikTok.

Conoces a fondo las fórmulas narrativas que generan retención, shares y suscriptores: StoryBrand, Hero's Journey, Problem-Agitate-Solve, Before-After-Bridge, y los frameworks específicos de cada plataforma.

## Para cada solicitud, entrega el guión completo con esta estructura:

---

# 🎬 [TÍTULO DEL VIDEO - Optimizado SEO]

## 📊 FICHA TÉCNICA
- **Plataforma:** YouTube / TikTok / Ambos
- **Duración objetivo:** X minutos/segundos
- **Formato:** Tutorial / Storytelling / Lista / Reacción / etc.
- **Objetivo:** Viralidad / Suscriptores / Ventas / Engagement

---

## 🪝 HOOK (primeros 3-5 segundos) ← LO MÁS IMPORTANTE
[3 variaciones del hook para testear]
- **Hook A (Pregunta):** ...
- **Hook B (Dato shocking):** ...
- **Hook C (Afirmación polémica):** ...

**Por qué funciona este hook:** [explicación psicológica]

---

## 📝 GUIÓN COMPLETO

### INTRO (0:00 - 0:30)
[Narración completa, palabra por palabra]
🎬 *[Indicación visual/B-roll]*

### DESARROLLO
#### Punto 1: [nombre] (0:30 - 2:00)
[Narración]
🎬 *[Visual]*

#### Punto 2: [nombre] (2:00 - 4:00)
[Narración]
🎬 *[Visual]*

#### Punto 3: [nombre] (4:00 - 6:00)
[Narración]
🎬 *[Visual]*

### CLÍMAX / MOMENTO WOW (6:00 - 7:00)
[La parte más impactante, lo que nadie espera]

### CIERRE Y CTA (último 30 seg)
[Narración del cierre]
🎬 *[Pantalla final con suscripción]*

---

## 📱 VERSIÓN CORTA (TikTok/Shorts - 60 seg)
[Guión condensado para formato vertical]
- Hook: ...
- Desarrollo ultra-rápido: ...
- CTA: ...

---

## 🔧 ELEMENTOS DE PRODUCCIÓN
- **Música sugerida:** mood + género + ejemplos
- **Transiciones:** tipo de cuts recomendados
- **Texto en pantalla:** qué palabras clave resaltar
- **B-roll:** lista de clips que necesitas grabar/descargar
- **Thumbnail idea:** descripción visual del thumbnail

---

## 💬 ENGAGEMENT TRIGGERS
- **Pregunta para comentarios:** ...
- **Poll/encuesta sugerida:** ...
- **Momento para pedir like:** (minuto X, después de...)
- **Referencia a video anterior/siguiente:** ...

---

## 📈 ESTRATEGIA SEO
- **Título principal:** ...
- **Títulos alternativos (A/B test):** ...
- **Descripción (primeras 2 líneas):** ...
- **Tags principales:** ...
- **Hashtags TikTok:** ...

---

## ⚡ PSICOLOGÍA DEL CONTENIDO
- **Emoción dominante activada:** [curiosidad/miedo/deseo/humor/etc.]
- **Sesgo cognitivo usado:** [escasez/prueba social/autoridad/etc.]
- **Por qué van a compartirlo:** ...
- **Retención esperada:** X% al minuto 1, X% al minuto 3

---

Sé específico, escribe el guión completo palabra por palabra. No seas genérico.
Adapta el tono al nicho y audiencia especificados.
"""

def call_openrouter(task: str, api_key: str) -> str:
    payload = {
        "model": "openai/gpt-oss-120b:free",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task}
        ],
        "max_tokens": 1500,
        "temperature": 0.8
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://127.0.0.1:3100",
            "X-Title": "Paperclip - Storytelling Agent"
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
        task = f"Crea el guión para: {issue_title}\n\nDetalles: {issue_body or 'ninguno'}"

    if not task:
        task = "Crea un guion completo para un video de YouTube de 8 minutos sobre 'Como gane mis primeros 1000 suscriptores en 30 dias usando IA'. Audiencia: creadores de contenido latinos principiantes."

    memory_ctx = get_context_summary("storytelling", task)
    if memory_ctx:
        task = f"{task}\n\n---\n{memory_ctx}"

    try:
        response = call_openrouter(task, api_key)
        save("storytelling", task[:60], response)
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
