"""
Agente: Web Designer — DiscontrolDrops
Genera landing page completa + HTML preview visual en Railway.
El preview se puede ver, editar y luego publicar en Shopify.
"""
import os, sys, json, re, urllib.request, urllib.parse
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from api_client import post_issue_result, post_issue_comment, resolve_issue_context, call_llm
sys.stdout.reconfigure(encoding="utf-8")

STRUCTURE_SYSTEM = """Eres experto en CRO para Shopify en el mercado español.
Generas landing pages de alto rendimiento para dropshipping.
Todo en español, orientado al consumidor español: directo, garantías claras, sin exageraciones."""

HTML_SYSTEM = """Eres un desarrollador frontend experto en landing pages de Shopify para el mercado español.
Generas HTML/CSS completo, limpio y visual de una landing page de dropshipping.
El resultado debe verse profesional y listo para convertir.

REGLAS:
- HTML completo con <style> embebido (no CDN externos salvo Google Fonts)
- Diseño dark/moderno o claro según el producto
- Mobile-first, responsive
- Botones CTA en color llamativo (naranja o verde)
- Incluir sección hero, beneficios, reseñas, garantía y CTA final
- Usar los textos exactos que se te proporcionen
- Todo en español"""


def extract_top_product(raw: str) -> dict:
    try:
        for block in reversed(raw.split("```json")[1:]):
            try:
                data = json.loads(block.split("```")[0].strip())
                if data.get("top_pick"): return data["top_pick"]
                if data.get("qualified"): return data["qualified"][0]
            except Exception: continue
    except Exception: pass
    return {"name": raw[:100]}


def upload_preview(html: str, api_url: str, secret: str) -> str:
    """Sube el HTML al servidor Railway y devuelve la URL de preview."""
    url = f"{api_url.rstrip('/')}/preview"
    data = html.encode("utf-8")
    req  = urllib.request.Request(
        url, data=data,
        headers={
            "Content-Type":  "text/html; charset=utf-8",
            "Authorization": f"Bearer {secret}",
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            result = json.loads(r.read().decode("utf-8"))
            return result.get("url", "")
    except Exception as e:
        print(f"  ⚠️  Preview upload error: {e}", flush=True)
        return ""


def main():
    api_key    = os.environ.get("OPENROUTER_API_KEY", "").strip()
    # Usar PUBLIC_URL para el preview (no localhost)
    api_url    = (os.environ.get("PUBLIC_URL") or
                  os.environ.get("PAPERCLIP_API_URL", "http://localhost:3100")).rstrip("/")
    # Si sigue siendo localhost, usar la URL pública conocida
    if "localhost" in api_url or "127.0.0.1" in api_url:
        api_url = "https://spirited-charm-production.up.railway.app"
    jwt_secret = (os.environ.get("PAPERCLIP_AGENT_JWT_SECRET") or
                  os.environ.get("BETTER_AUTH_SECRET", "")).strip()

    if not api_key:
        post_issue_result("❌ Web Designer: OPENROUTER_API_KEY no configurada.")
        sys.exit(1)

    issue_title, issue_body = resolve_issue_context()
    raw     = issue_body if issue_body else (issue_title or "")
    product = extract_top_product(raw)
    name    = product.get("name", "el producto")
    score   = product.get("score", "?")
    price   = product.get("suggested_price_eur", "?")
    margin  = product.get("est_margin_pct", "?")
    hook    = product.get("suggested_hook", "")
    strength = product.get("key_strength", "")
    risk    = product.get("main_risk", "")
    audience = product.get("target_audience", "adultos 25-45")

    post_issue_comment(
        f"🎨 Web Designer generando landing para: **{name}**\n\n"
        f"Primero estructura → luego HTML preview visual..."
    )

    # ── PASO 1: Generar estructura de copy ────────────────────────────────────
    structure_prompt = f"""Genera la estructura completa de copy para una landing page Shopify:

Producto: {name}
Score: {score}/100 | Precio: €{price} | Margen: {margin}%
Audiencia: {audience}
Fortaleza: {strength}
Riesgo a superar: {risk}
Hook: {hook}

Genera estas secciones con copy real en español:
1. HERO — headline (máx 8 palabras), subheadline, CTA text, 3 badges de confianza
2. PROBLEMA — 2 párrafos empáticos
3. BENEFICIOS — 6 puntos con emoji + título + descripción
4. RESEÑAS — 3 reseñas con nombre español, ciudad, profesión, 5 estrellas
5. GARANTÍA — texto de garantía 30 días
6. FAQ — 4 preguntas frecuentes con respuestas
7. CTA FINAL — urgencia + precio tachado + precio actual"""

    try:
        structure = call_llm(
            messages=[
                {"role": "system", "content": STRUCTURE_SYSTEM},
                {"role": "user", "content": structure_prompt}
            ],
            api_key=api_key, max_tokens=2500, temperature=0.6,
            title="DiscontrolDrops - Web Designer (structure)",
            model="anthropic/claude-sonnet-4-5", timeout=40, retries=1,
        )
    except Exception as e:
        post_issue_result(f"❌ Web Designer error generando estructura: {e}")
        sys.exit(1)

    # ── PASO 2: Generar HTML visual ───────────────────────────────────────────
    html_prompt = f"""Crea una landing page HTML completa y visual para este producto:

PRODUCTO: {name}
PRECIO: €{price}
HOOK: {hook}

COPY GENERADO:
{structure[:3000]}

Genera HTML completo con:
- <head> con meta tags y Google Fonts
- <style> con CSS moderno (colores: fondo oscuro #0f0f0f o blanco limpio, CTA naranja #f97316)
- Secciones: hero, beneficios, reseñas, garantía, FAQ, CTA final
- Botón CTA grande y llamativo
- Footer con badges de pago seguro
- Totalmente en español
- Responsive mobile-first

Devuelve SOLO el HTML completo, sin explicaciones."""

    try:
        html_content = call_llm(
            messages=[
                {"role": "system", "content": HTML_SYSTEM},
                {"role": "user", "content": html_prompt}
            ],
            api_key=api_key, max_tokens=4000, temperature=0.5,
            title="DiscontrolDrops - Web Designer (HTML)",
            model="anthropic/claude-sonnet-4-5", timeout=60, retries=1,
        )
        # Limpiar markdown si el LLM añadió ```html
        if "```html" in html_content:
            html_content = html_content.split("```html")[1].split("```")[0].strip()
        elif "```" in html_content:
            html_content = html_content.split("```")[1].split("```")[0].strip()

    except Exception as e:
        html_content = ""
        print(f"  ⚠️  HTML generation error: {e}", flush=True)

    # ── PASO 3: Subir preview a Railway ──────────────────────────────────────
    preview_url = ""
    if html_content and jwt_secret:
        secret16 = jwt_secret[:16]
        preview_url = upload_preview(html_content, api_url, secret16)
        if preview_url:
            print(f"  ✅ Preview disponible: {preview_url}", flush=True)

    # ── Output final ──────────────────────────────────────────────────────────
    preview_section = ""
    if preview_url:
        preview_section = (
            f"\n\n## 🌐 PREVIEW VISUAL\n"
            f"**[Ver landing page en vivo → {preview_url}]({preview_url})**\n\n"
            f"> Abre el link, revisa el diseño, edita lo que necesites.\n"
            f"> Cuando estés listo, publica en Shopify.\n"
        )
    else:
        preview_section = "\n\n> ⚠️ Preview no disponible — revisa PAPERCLIP_API_URL y BETTER_AUTH_SECRET\n"

    output = f"# 🎨 LANDING SHOPIFY — {name}\n{preview_section}\n## 📝 Estructura de copy\n\n{structure}"
    print(output[:500], flush=True)
    post_issue_result(output)


if __name__ == "__main__":
    main()
