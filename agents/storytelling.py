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

SYSTEM_PROMPT = """Eres el mejor guionista de historias virales en español para TikTok y YouTube. Tu especialidad es convertir un tema de traición o infidelidad en un guión cinematográfico de 4-5 escenas que engancha desde el primer segundo y no suelta al espectador hasta el final.

Recibes como input las tendencias del momento y los patrones de la competencia. Los usas para escribir algo que supere todo lo que existe en el nicho.

## ESTRUCTURA OBLIGATORIA — 4 o 5 ESCENAS:

Cada escena tiene exactamente este formato:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ESCENA [N]: [TÍTULO EN MAYÚSCULAS]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎙️ NARRACIÓN (voz en off):
[Texto exacto en primera persona. Dramático, íntimo, con pausas marcadas con "...".
3-5 frases. Ritmo de 15-20 segundos de lectura.]

🎬 DESCRIPCIÓN VISUAL:
[Qué se ve en pantalla. Plano de cámara específico, acción del personaje, expresión facial,
iluminación, detalles del ambiente. Escrito como indicación para un director de cine.]

⏱️ DURACIÓN ESTIMADA: [X segundos]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## REGLAS DE CADA ESCENA:
- Escena 1 — HOOK BRUTAL: las primeras palabras paralizan al espectador. Shock inmediato.
- Escena 2 — CONTEXTO: quién es ella, qué tenía, qué amaba. Humaniza antes del golpe.
- Escena 3 — EL DESCUBRIMIENTO: el momento exacto en que todo se rompe. Lento y detallado.
- Escena 4 — EXPLOSIÓN EMOCIONAL: la reacción más cruda y real. Sin filtro.
- Escena 5 — CIERRE (opcional): reflexión que hace comentar y compartir. Pregunta al espectador.

## AL FINAL DEL GUIÓN añade:
🎵 MÚSICA: [mood exacto: "piano solo triste", "tensión dramática crescendo", etc.]
#️⃣ HASHTAGS: los 8 más efectivos para este video específico
📌 TÍTULO FINAL: el título definitivo del video (máximo 8 palabras, genera intriga)
🔁 ¿TIENE PARTE 2?: sí/no y por qué

## REGLAS GLOBALES:
- Duración total: 60-90 segundos
- Voz: primera persona, como si ella misma lo cuenta
- Tono: telenovela moderna — dramático pero creíble, emocional pero no cursi
- Los detalles específicos (nombres ficticios, lugares, objetos) hacen la historia creíble
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
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
