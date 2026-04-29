"""
Agente: Product Hunter — DiscontrolDrops
Busca productos ganadores para dropshipping usando fuentes públicas:
- Google Trends RSS (trending searches)
- Amazon Best Sellers (público, sin auth)
- AliExpress trending (público)

Input (desde issue):
  "tactical gadgets"
  "home office accessories"
  {"niche": "pet accessories", "region": "ES", "limit": 15}

Output: lista de productos con métricas de tendencia y potencial.
"""
import os
import sys
import json
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from api_client import post_issue_result, post_issue_comment, resolve_issue_context, call_llm

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml,*/*",
    "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
}


def fetch_google_trends(keywords: list, geo: str = "US") -> list:
    """Obtiene tendencias de Google Trends RSS para validar demanda."""
    results = []
    for kw in keywords[:3]:
        try:
            url = f"https://trends.google.com/trends/explore?q={urllib.parse.quote(kw)}&geo={geo}"
            # Usar el RSS de trending para contexto
            rss_url = f"https://trends.google.com/trending/rss?geo={geo}"
            req     = urllib.request.Request(rss_url, headers=BROWSER_HEADERS, method="GET")
            with urllib.request.urlopen(req, timeout=10) as r:
                xml = r.read().decode("utf-8", errors="replace")
            root = ET.fromstring(xml)
            ch   = root.find("channel")
            if ch:
                for item in list(ch.findall("item"))[:5]:
                    title = item.findtext("title", "").strip()
                    if title:
                        results.append({"term": title, "source": "google_trends", "geo": geo})
        except Exception as e:
            print(f"  ⚠️  Google Trends error ({kw}): {e}", flush=True)
    return results


def fetch_amazon_bestsellers(category: str = "electronics") -> list:
    """Scraping básico de Amazon Best Sellers (página pública)."""
    category_urls = {
        "electronics":    "https://www.amazon.com/Best-Sellers-Electronics/zgbs/electronics",
        "gadgets":        "https://www.amazon.com/Best-Sellers-Electronics-Gadgets/zgbs/electronics/9967794011",
        "home":           "https://www.amazon.com/Best-Sellers-Home-Kitchen/zgbs/kitchen",
        "sports":         "https://www.amazon.com/Best-Sellers-Sports-Outdoors/zgbs/sporting-goods",
        "pets":           "https://www.amazon.com/Best-Sellers-Pet-Supplies/zgbs/pet-supplies",
        "office":         "https://www.amazon.com/Best-Sellers-Office-Products/zgbs/office-products",
        "beauty":         "https://www.amazon.com/Best-Sellers-Beauty/zgbs/beauty",
        "toys":           "https://www.amazon.com/Best-Sellers-Toys-Games/zgbs/toys-and-games",
    }
    url = category_urls.get(category.lower(), category_urls["electronics"])
    headers = {**BROWSER_HEADERS, "Accept-Language": "en-US,en;q=0.9"}
    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8", errors="replace")

        # Extraer nombres de productos del HTML
        products = []
        # Amazon usa data-component-type="s-search-result" o similar
        patterns = [
            r'<span class="a-size-medium[^"]*"[^>]*>([^<]{10,80})</span>',
            r'<span class="a-size-base-plus[^"]*"[^>]*>([^<]{10,80})</span>',
            r'"title":"([^"]{10,80})"',
            r'<div class="_cDEzb_p13n-sc-css-line-clamp[^>]*>([^<]{10,80})<',
        ]
        seen = set()
        for pat in patterns:
            for m in re.findall(pat, html):
                clean = m.strip()
                if clean and clean not in seen and len(clean) > 10:
                    seen.add(clean)
                    products.append({"name": clean, "source": "amazon_bestsellers", "category": category})
                if len(products) >= 15:
                    break
            if len(products) >= 15:
                break

        return products[:15]
    except Exception as e:
        print(f"  ⚠️  Amazon scraping error: {e}", flush=True)
        return []


def enrich_with_llm(raw_products: list, niche: str, api_key: str) -> list:
    """
    Usa LLM para analizar los productos encontrados y estimar:
    - Potencial de dropshipping (1-10)
    - Margen estimado (%)
    - Competencia (Low/Med/High)
    - Precio de venta sugerido
    - Por qué podría funcionar
    """
    if not raw_products or not api_key:
        return raw_products

    products_text = "\n".join(
        f"- {p.get('name', p.get('term', '?'))} ({p.get('source', '')})"
        for p in raw_products[:20]
    )

    prompt = f"""Eres un experto en dropshipping con Shopify y conocimiento profundo del mercado español/europeo.

Analiza estos productos encontrados en tendencias y bestsellers para el nicho: "{niche}"

PRODUCTOS:
{products_text}

Para cada producto que tenga potencial real de dropshipping, devuelve un análisis.
Selecciona los 8-10 mejores. Ignora los que no apliquen para dropshipping.

Responde SOLO con JSON válido (sin markdown):
{{
  "products": [
    {{
      "name": "nombre del producto",
      "score": 85,
      "est_margin_pct": 65,
      "competition": "Low|Med|High",
      "suggested_price_eur": 39.99,
      "supplier_est_cost_eur": 8.50,
      "why": "razón concisa de por qué funciona (1 frase)",
      "target_audience": "descripción del comprador",
      "source": "amazon_bestsellers|google_trends|manual"
    }}
  ]
}}"""

    try:
        response = call_llm(
            messages=[{"role": "user", "content": prompt}],
            api_key     = api_key,
            max_tokens  = 1500,
            temperature = 0.4,
            title       = "DiscontrolDrops - Product Hunter",
            model       = "anthropic/claude-sonnet-4-5",
            timeout     = 30,
            retries     = 1,
        )
        clean = response.strip()
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```")[1].split("```")[0].strip()
        data = json.loads(clean)
        return data.get("products", raw_products)
    except Exception as e:
        print(f"  ⚠️  LLM enrichment error: {e}", flush=True)
        return raw_products


def parse_input(raw: str) -> dict:
    m = re.search(r'\{[\s\S]*?\}', raw)
    if m:
        try:
            data = json.loads(m.group(0))
            return {
                "niche":  data.get("niche", data.get("query", raw.strip())),
                "region": data.get("region", "ES"),
                "limit":  int(data.get("limit", 15)),
            }
        except Exception:
            pass
    return {"niche": raw.strip() or "trending products", "region": "ES", "limit": 15}


def main():
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()

    issue_title, issue_body = resolve_issue_context()
    raw = issue_body if issue_body else (issue_title or "")
    if len(sys.argv) > 1:
        raw = " ".join(sys.argv[1:])
    if not raw:
        raw = "gadgets home office"

    params = parse_input(raw)
    niche  = params["niche"]
    region = params["region"]

    post_issue_comment(
        f"🔍 Product Hunter buscando en nicho: **{niche}**\n\n"
        f"Consultando Amazon Best Sellers + Google Trends + análisis LLM..."
    )
    print(f"🔍 Nicho: '{niche}' | Región: {region}", flush=True)

    # Detectar categoría Amazon del nicho
    category_map = {
        "gadget": "gadgets", "electronic": "electronics", "tech": "electronics",
        "home": "home", "kitchen": "home", "sport": "sports", "fitness": "sports",
        "pet": "pets", "office": "office", "beauty": "beauty", "cosmetic": "beauty",
        "toy": "toys", "kid": "toys", "child": "toys",
    }
    niche_lower = niche.lower()
    amazon_cat  = next((v for k, v in category_map.items() if k in niche_lower), "electronics")

    # Recopilar productos de fuentes
    all_products = []

    print(f"  📦 Amazon Best Sellers ({amazon_cat})...", flush=True)
    amazon_products = fetch_amazon_bestsellers(amazon_cat)
    all_products.extend(amazon_products)
    print(f"  → {len(amazon_products)} productos", flush=True)

    print(f"  📈 Google Trends ({region})...", flush=True)
    keywords = niche.split()[:3]
    trends   = fetch_google_trends(keywords, region)
    all_products.extend(trends)
    print(f"  → {len(trends)} tendencias", flush=True)

    if not all_products:
        # Fallback: solo LLM sin datos externos
        all_products = [{"name": niche, "source": "manual"}]

    # Enriquecer con LLM
    print(f"  🤖 Analizando {len(all_products)} productos con LLM...", flush=True)
    products = enrich_with_llm(all_products, niche, api_key) if api_key else all_products

    # Ordenar por score
    if products and isinstance(products[0], dict) and "score" in products[0]:
        products.sort(key=lambda p: p.get("score", 0), reverse=True)

    print(f"\n✅ {len(products)} productos analizados", flush=True)

    # Formatear output
    lines = [f"# 🔍 PRODUCT HUNTER — {niche.title()}\n"]
    lines.append(f"**{len(products)} productos encontrados y analizados**\n")

    for i, p in enumerate(products[:15], 1):
        name      = p.get("name", p.get("term", "?"))
        score     = p.get("score", "?")
        margin    = p.get("est_margin_pct", "?")
        comp      = p.get("competition", "?")
        price     = p.get("suggested_price_eur", "?")
        cost      = p.get("supplier_est_cost_eur", "?")
        why       = p.get("why", "")
        audience  = p.get("target_audience", "")

        score_emoji = "🟢" if isinstance(score, (int,float)) and score >= 75 else "🟡" if isinstance(score, (int,float)) and score >= 50 else "🔴"
        comp_emoji  = {"Low": "🟢", "Med": "🟡", "High": "🔴"}.get(comp, "⚪")

        lines.append(f"## {i}. {name}")
        lines.append(f"- {score_emoji} AI Score: **{score}** | Margen estimado: **{margin}%**")
        lines.append(f"- {comp_emoji} Competencia: {comp}")
        if isinstance(price, (int, float)):
            lines.append(f"- 💶 Precio venta: €{price} | Coste supplier: €{cost}")
        if why:
            lines.append(f"- 💡 {why}")
        if audience:
            lines.append(f"- 🎯 {audience}")
        lines.append("")

    output_json = {
        "products": products[:15],
        "niche":    niche,
        "region":   region,
        "total":    len(products),
        "source":   "amazon_bestsellers+google_trends+llm",
    }
    lines.append("```json")
    lines.append(json.dumps(output_json, indent=2, ensure_ascii=False))
    lines.append("```")

    post_issue_result("\n".join(lines))


if __name__ == "__main__":
    main()
