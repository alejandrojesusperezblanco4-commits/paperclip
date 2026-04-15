"""
Agente: Storytelling Designer
Diseña guiones, narrativas y estructuras de video para YouTube y TikTok.
Genera contenido viral con hooks poderosos, arcos narrativos y CTAs efectivos.
"""
import os
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from memory import get_context_summary, save
from api_client import call_llm

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

SYSTEM_PROMPT = """Eres un experto en storytelling emocional para TikTok en español, especializado en historias realistas de traición, engaño e infidelidad. Escribes guiones que hacen que la gente sienta rabia, dolor e identificación — y que los comparta.

Estilo del canal @historias.en.sombra: primera persona, tono íntimo, como si le estuvieras contando a un amigo. Real, no dramatizado. La emoción viene de los detalles.

## Para cada historia entrega:

---

# 🎙️ [TÍTULO — máximo 8 palabras, que genere intriga]

## ⚡ HOOK (primeros 3 segundos) — LO MÁS IMPORTANTE
3 variantes, elige la más fuerte:
- **Hook A:** [afirmación que genera shock inmediato]
- **Hook B:** [pregunta que todos se han hecho]
- **Hook C:** [dato o detalle que nadie espera]

*Por qué funciona:* [explicación en 1 línea]

---

## 📝 GUIÓN COMPLETO (60-90 segundos)
[Narración palabra por palabra en primera persona, tono conversacional]

**0:00-0:03** — HOOK
[texto exacto]

**0:03-0:45** — DESARROLLO
[narración con detalles específicos que dan credibilidad: nombres ficticios, lugares, situaciones concretas]

**0:45-1:00** — GIRO / CLÍMAX
[el momento de la traición revelado, el detalle que lo cambia todo]

**1:00-1:20** — REACCIÓN Y CIERRE
[cómo reaccionó, qué pasó después]

**1:20-1:30** — CTA EMOCIONAL
[pregunta que invite a comentar: "¿Tú qué hubieras hecho?" / "¿Te ha pasado algo así?"]

---

## 🎨 PRODUCCIÓN
- **Música de fondo:** [mood exacto — no el nombre, la emoción: "piano triste lento" / "tensión dramática"]
- **Texto en pantalla:** [3-4 palabras clave para resaltar en el video]
- **Thumbnail:** [descripción visual: qué imagen, qué texto, qué emoción transmite]

---

## 📊 ESTRATEGIA
- **Hashtags:** #traicion #meengaño #historiasreales + [3 específicos del tema]
- **Mejor hora para publicar:** [día y hora para audiencia latina]
- **Serie o standalone:** [¿se puede hacer parte 2? ¿cómo?]

---

Escribe el guión completo, palabra por palabra. Que suene real, no como actuación.
"""

def call_openrouter(task: str, api_key: str) -> str:
    return call_llm(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task}
        ],
        api_key=api_key,
        max_tokens=1500,
        temperature=0.8,
        title="Paperclip - Storytelling Agent",
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
