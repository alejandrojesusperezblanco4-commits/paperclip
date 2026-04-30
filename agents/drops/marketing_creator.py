"""
Agente: Marketing Creator — DiscontrolDrops
Genera todos los assets de marketing para lanzar el producto:
ad copy, video scripts, descripción Shopify y emails.
"""
import os, sys, json
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from api_client import post_issue_result, post_issue_comment, resolve_issue_context, call_llm
sys.stdout.reconfigure(encoding="utf-8")

SYSTEM = """Eres el mejor copywriter de dropshipping para el mercado español y latinoamericano.
Escribes copy que convierte: directo, emocional, con prueba social y urgencia real.
Conoces los formatos de Facebook Ads, TikTok y Shopify a la perfección.
Todo en español neutro (funciona en ES y LATAM)."""

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

def main():
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        post_issue_result("❌ Marketing Creator: OPENROUTER_API_KEY no configurada.")
        sys.exit(1)
    issue_title, issue_body = resolve_issue_context()
    raw     = issue_body if issue_body else (issue_title or "")
    product = extract_top_product(raw)
    name    = product.get("name", "el producto")
    hook    = product.get("suggested_hook", "")
    price   = product.get("suggested_price_eur", "?")
    audience = product.get("target_audience", "adultos 25-45")

    post_issue_comment(f"📣 Marketing Creator generando assets para: **{name}**")

    prompt = f"""Genera todos los assets de marketing para este producto de dropshipping:

Producto: {name}
Precio: €{price}
Audiencia: {audience}
Hook base: {hook}
Fortaleza: {product.get('key_strength','')}
Riesgo a superar: {product.get('main_risk','')}

Genera en español:

## 1. FACEBOOK / INSTAGRAM ADS (3 variantes)
Para cada variante: Headline + Primary Text (80-120 palabras) + CTA

## 2. TIKTOK / REELS SCRIPTS (2 scripts de 30 segundos)
Formato: [0-3s HOOK] [3-15s DEMO] [15-25s BENEFICIO] [25-30s CTA]

## 3. DESCRIPCIÓN SHOPIFY
Headline emocional + 5 bullets de beneficios + garantía + urgencia

## 4. EMAIL SECUENCIA (3 emails)
- Email 1 (día 0): Confirmación de pedido + expectativas
- Email 2 (día 3): Consejos de uso + upsell
- Email 3 (día 7): Solicitud de reseña + descuento próxima compra

## 5. HOOKS TIKTOK (8 hooks de 3 segundos)
Frases de apertura que paran el scroll

Todo en español. Copy real, listo para usar."""

    try:
        response = call_llm(
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
            api_key=api_key, max_tokens=3000, temperature=0.75,
            title="DiscontrolDrops - Marketing Creator",
            model="anthropic/claude-sonnet-4-5", timeout=50, retries=1,
        )
        post_issue_result(f"# 📣 MARKETING ASSETS — {name}\n\n{response}")
    except Exception as e:
        post_issue_result(f"❌ Marketing Creator error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
