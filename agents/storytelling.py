"""
Agente: Storytelling Designer
Diseña guiones, narrativas y estructuras de video para YouTube y TikTok.
Genera contenido viral con hooks poderosos, arcos narrativos y CTAs efectivos.
"""
import os
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from memory import get_context_summary, save
from api_client import call_llm, post_issue_result, post_issue_comment

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

SYSTEM_PROMPT = """Eres el mejor guionista de contenido viral en español para TikTok y YouTube. Tu especialidad es convertir CUALQUIER tema — drama personal, finanzas, fitness, tech, humor, lifestyle o lo que te pidan — en un guión de 4-5 escenas que engancha desde el primer segundo y no suelta al espectador hasta el final.

Recibes el tema, las tendencias del momento y los patrones de la competencia. Los usas para escribir algo que supere todo lo que existe en el nicho.

ADAPTA el tono, la voz narrativa y la estructura al tipo de contenido que te pidan:
- Drama/historias personales: primera persona, íntimo, emocional, telenovela moderna
- Finanzas/negocios: directo, datos concretos, revelación de "secreto que no te cuentan"
- Fitness/salud: motivacional, transformación personal, antes/después
- Tech/IA: asombro, futuro, "esto cambia todo", demostración práctica
- Humor: setup-punchline, giro inesperado, situaciones cotidianas exageradas
- Tutorial/educativo: promesa de valor, pasos claros, resultado concreto al final

## ESTRUCTURA — 4 o 5 ESCENAS:

Cada escena tiene exactamente este formato:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ESCENA [N]: [TÍTULO EN MAYÚSCULAS]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎙️ NARRACIÓN (voz en off):
[Texto exacto. Tono y voz adaptados al nicho. Con pausas marcadas con "...".
3-5 frases. Ritmo de 15-20 segundos de lectura.]

🎬 DESCRIPCIÓN VISUAL:
[Qué se ve en pantalla. Plano de cámara específico, acción, expresión facial o visual clave,
iluminación, detalles del ambiente. Escrito como indicación para un director.]

⏱️ DURACIÓN ESTIMADA: [X segundos]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## ESTRUCTURA NARRATIVA (adaptar al nicho):
- Escena 1 — HOOK: las primeras palabras paralizan al espectador. Shock, curiosidad o promesa brutal.
- Escena 2 — CONTEXTO: quién, qué situación, qué estaba en juego. Humaniza o establece el problema.
- Escena 3 — DESARROLLO: el momento clave, el dato revelador, el giro, la técnica secreta.
- Escena 4 — CLÍMAX/RESULTADO: la reacción más cruda, el antes vs después, la demostración.
- Escena 5 — CIERRE (opcional): reflexión, llamada a la acción, pregunta que hace comentar.

## AL FINAL DEL GUIÓN añade:
🎵 MÚSICA: [mood exacto adaptado al nicho]
#️⃣ HASHTAGS: los 8 más efectivos para este video específico
📌 TÍTULO FINAL: el título definitivo del video (máximo 8 palabras, genera intriga o curiosidad)
🔁 ¿TIENE PARTE 2?: sí/no y por qué

## REGLAS GLOBALES:
- Duración total: 60-90 segundos
- Los detalles específicos (números reales, nombres ficticios, lugares, objetos) hacen el contenido creíble
- Siempre termina con una pregunta o CTA que invite a comentar
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
    issue_body  = os.environ.get("PAPERCLIP_ISSUE_BODY", "")
    if issue_title:
        context = issue_body if issue_body and len(issue_body) > len(issue_title) else issue_title
        task = f"Crea el guión para: {context}\n\nDetalles: {issue_body or 'ninguno'}"
        post_issue_comment(
            f"✍️ Perfecto, voy a escribir el guión para: **{issue_title}**\n\n"
            f"Diseño 4-5 escenas con hook brutal, tensión creciente y un cierre que haga "
            f"comentar. Primera persona, voz íntima, como si ella misma lo cuenta. "
            f"Dame un momento — el guión está en camino."
        )

    if not task:
        task = "Crea un guion completo para un video de YouTube de 8 minutos sobre 'Como gane mis primeros 1000 suscriptores en 30 dias usando IA'. Audiencia: creadores de contenido latinos principiantes."

    memory_ctx = get_context_summary("storytelling", task)
    if memory_ctx:
        task = f"{task}\n\n---\n{memory_ctx}"

    try:
        response = call_openrouter(task, api_key)
        save("storytelling", task[:60], response)
        print(response)
        post_issue_result(response)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
