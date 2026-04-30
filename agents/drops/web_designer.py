"""
Agente: Web Designer — DiscontrolDrops
Genera estructura completa de landing Shopify para el producto ganador.
"""
import os, sys, json, re
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from api_client import post_issue_result, post_issue_comment, resolve_issue_context, call_llm
sys.stdout.reconfigure(encoding="utf-8")

SYSTEM = """Eres experto en CRO para Shopify en el mercado español.
Generas landing pages de alto rendimiento para dropshipping.
Todo en español, orientado al consumidor español: directo, garantías claras, sin exageraciones."""

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
        post_issue_result("❌ Web Designer: OPENROUTER_API_KEY no configurada.")
        sys.exit(1)
    issue_title, issue_body = resolve_issue_context()
    raw = issue_body if issue_body else (issue_title or "")
    product = extract_top_product(raw)
    name    = product.get("name", "el producto")
    post_issue_comment(f"🎨 Web Designer generando landing Shopify para: **{name}**")
    prompt = f"""Genera la estructura completa de una landing page Shopify para:

Producto: {name}
Score: {product.get('score','?')}/100
Precio sugerido: €{product.get('suggested_price_eur','?')}
Margen: {product.get('est_margin_pct','?')}%
Fortaleza: {product.get('key_strength','')}
Hook: {product.get('suggested_hook','')}

Genera estas secciones con copy real en español:
1. HERO — headline, subheadline, CTA, badges de confianza
2. PROBLEMA/SOLUCIÓN — copy empático
3. BENEFICIOS — 6 puntos (beneficio, no característica técnica)
4. SOCIAL PROOF — estructura de reseñas con nombres españoles
5. GARANTÍA/FAQ — 4 preguntas con respuestas
6. CTA FINAL — urgencia + precio con descuento
7. APPS SHOPIFY — top 3 para este producto
8. SEO — meta title, meta description, URL slug
9. CHECKLIST — 10 puntos antes de publicar"""

    try:
        response = call_llm(
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
            api_key=api_key, max_tokens=2500, temperature=0.6,
            title="DiscontrolDrops - Web Designer",
            model="anthropic/claude-sonnet-4-5", timeout=40, retries=1,
        )
        post_issue_result(f"# 🎨 LANDING SHOPIFY — {name}\n\n{response}")
    except Exception as e:
        post_issue_result(f"❌ Web Designer error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
