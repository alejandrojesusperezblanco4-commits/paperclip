"""
Agente: Product Hunter — DiscontrolDrops
Busca productos ganadores para dropshipping usando:
- YouTube Data API  → videos de reviews/unboxing del nicho (señal de demanda real)
- Perplexity LLM    → búsqueda web en tiempo real de trending products
- Google Trends RSS → validación de tendencia por región
- Amazon.es         → bestsellers como referencia de mercado

Variables de entorno:
  OPENROUTER_API_KEY          (LLM + Perplexity)
  YOUTUBE_API_KEY_DEEP_SEARCH (YouTube Data API v3)

Input (desde issue o CEO):
  "tactical gadgets"
  "home office accessories"
  {"niche": "pet accessories", "region": "ES", "limit": 15}

Output: lista de productos con score, margen estimado y señales de demanda.
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
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":          "text/html,application/xhtml+xml,application/xml,*/*",
    "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
}

YOUTUBE_API_URL = "https://www.googleapis.com/youtube/v3"


# ── YouTube Data API ──────────────────────────────────────────────────────────

def fetch_youtube_products(niche: str, yt_key: str, max_results: int = 20) -> list:
    """
    Busca videos de reviews/unboxing del nicho en YouTube.
    Extrae señales de producto de los títulos más vistos.
    Quota: ~100 units por llamada (search) + 1 unit por video (statistics).
    """
    if not yt_key:
        print("  ⚠️  YOUTUBE_API_KEY_DEEP_SEARCH no configurada", flush=True)
        return []

    results = []
    queries = [
        f"{niche} product review",
        f"{niche} unboxing 2024",
        f"best {niche} dropshipping",
        f"{niche} aliexpress find",
    ]

    seen_titles = set()
    for query in queries[:2]:  # 2 queries = ~200 units de quota
        try:
            params = urllib.parse.urlencode({
                "part":       "snippet",
                "q":          query,
                "type":       "video",
                "order":      "viewCount",
                "maxResults": max_results // 2,
                "relevanceLanguage": "es",
                "key":        yt_key,
            })
            url = f"{YOUTUBE_API_URL}/search?{params}"
            req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read().decode("utf-8"))

            video_ids = [i["id"]["videoId"] for i in data.get("items", []) if i.get("id", {}).get("videoId")]

            # Obtener estadísticas de los videos
            stats = {}
            if video_ids:
                stats_params = urllib.parse.urlencode({
                    "part": "statistics",
                    "id":   ",".join(video_ids),
                    "key":  yt_key,
                })
                stats_url = f"{YOUTUBE_API_URL}/videos?{stats_params}"
                stats_req = urllib.request.Request(stats_url, headers={"Accept": "application/json"}, method="GET")
                with urllib.request.urlopen(stats_req, timeout=15) as r:
                    stats_data = json.loads(r.read().decode("utf-8"))
                for v in stats_data.get("items", []):
                    stats[v["id"]] = int(v.get("statistics", {}).get("viewCount", 0))

            for item in data.get("items", []):
                vid_id  = item.get("id", {}).get("videoId", "")
                snippet = item.get("snippet", {})
                title   = snippet.get("title", "").strip()
                channel = snippet.get("channelTitle", "")
                views   = stats.get(vid_id, 0)

                if title in seen_titles or not title:
                    continue
                seen_titles.add(title)

                # Extraer nombre de producto del título (limpiar "review", "unboxing", etc.)
                product_name = re.sub(
                    r'\b(review|unboxing|haul|test|vs|2024|2025|amazon|aliexpress|'
                    r'dropshipping|best|top|cheap|cheap|compra|análisis|opinión)\b',
                    '', title, flags=re.IGNORECASE
                ).strip(" -|·:")
                product_name = re.sub(r'\s+', ' ', product_name).strip()

                if len(product_name) < 5:
                    product_name = title

                results.append({
                    "name":        product_name,
                    "yt_title":    title,
                    "yt_views":    views,
                    "yt_channel":  channel,
                    "source":      "youtube",
                    "demand_signal": "high" if views > 100_000 else "medium" if views > 10_000 else "low",
                })

        except Exception as e:
            print(f"  ⚠️  YouTube API error ({query}): {e}", flush=True)

    # Ordenar por views
    results.sort(key=lambda x: x.get("yt_views", 0), reverse=True)
    print(f"  → {len(results)} señales de YouTube", flush=True)
    return results[:15]


# ── Perplexity research ───────────────────────────────────────────────────────

def fetch_perplexity_products(niche: str, region: str, api_key: str) -> list:
    """
    Usa Perplexity via OpenRouter para buscar trending products en tiempo real.
    Devuelve lista de productos con contexto de mercado actual.
    """
    if not api_key:
        return []

    prompt = f"""Busca los productos más vendidos y con mayor tendencia para dropshipping en el nicho: "{niche}"
Enfócate en el mercado {region} / Europa.

Criterios:
- Productos físicos, no digitales
- Precio de venta entre €15-€150
- Disponibles en AliExpress o CJ Dropshipping
- Alta demanda demostrable (reviews, búsquedas, viral en redes)
- Margen potencial >50%

Lista los 8 mejores productos con:
- Nombre específico del producto
- Por qué está en tendencia ahora
- Precio estimado proveedor y venta
- Nivel de competencia (bajo/medio/alto)

Sé específico con nombres de productos reales, no categorías generales."""

    try:
        response = call_llm(
            messages=[{"role": "user", "content": prompt}],
            api_key     = api_key,
            max_tokens  = 1500,
            temperature = 0.3,
            title       = "ProductHunter-Perplexity",
            model       = "perplexity/sonar",
            timeout     = 30,
            retries     = 1,
        )
        # Extraer nombres de productos del texto
        products = []
        lines = response.split("\n")
        for line in lines:
            line = line.strip()
            # Detectar líneas que parecen nombres de producto (numeradas o con bullet)
            m = re.match(r'^[\d\-\*•·]+\.?\s*\*{0,2}([^:*\n]{8,60})\*{0,2}', line)
            if m:
                name = m.group(1).strip()
                if name and not any(w in name.lower() for w in ["por qué", "precio", "margen", "competencia", "conclusión"]):
                    products.append({"name": name, "source": "perplexity", "raw_context": response[:500]})
        print(f"  → {len(products)} productos de Perplexity", flush=True)
        return products[:8]
    except Exception as e:
        print(f"  ⚠️  Perplexity error: {e}", flush=True)
        return []


# ── Google Trends RSS ─────────────────────────────────────────────────────────

def fetch_google_trends(geo: str = "ES") -> list:
    """Obtiene trending searches de Google para contexto de mercado."""
    try:
        rss_url = f"https://trends.google.com/trending/rss?geo={geo}"
        req     = urllib.request.Request(rss_url, headers=BROWSER_HEADERS, method="GET")
        with urllib.request.urlopen(req, timeout=10) as r:
            xml = r.read().decode("utf-8", errors="replace")
        root = ET.fromstring(xml)
        ch   = root.find("channel")
        results = []
        if ch:
            for item in list(ch.findall("item"))[:10]:
                title = item.findtext("title", "").strip()
                if title:
                    results.append({"term": title, "source": "google_trends_rss"})
        print(f"  → {len(results)} trending searches", flush=True)
        return results
    except Exception as e:
        print(f"  ⚠️  Google Trends error: {e}", flush=True)
        return []


# ── Amazon.es scraping ────────────────────────────────────────────────────────

def fetch_amazon_es(category: str = "electronics") -> list:
    """Scraping Amazon.es Best Sellers (más permisivo que .com para España)."""
    category_urls = {
        "electronics": "https://www.amazon.es/gp/bestsellers/electronics",
        "gadgets":     "https://www.amazon.es/gp/bestsellers/electronics/937757031",
        "home":        "https://www.amazon.es/gp/bestsellers/kitchen",
        "sports":      "https://www.amazon.es/gp/bestsellers/sports",
        "pets":        "https://www.amazon.es/gp/bestsellers/pet-supplies",
        "beauty":      "https://www.amazon.es/gp/bestsellers/beauty",
        "office":      "https://www.amazon.es/gp/bestsellers/office-products",
        "toys":        "https://www.amazon.es/gp/bestsellers/toys",
    }
    url = category_urls.get(category.lower(), category_urls["electronics"])
    try:
        req = urllib.request.Request(url, headers=BROWSER_HEADERS, method="GET")
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8", errors="replace")

        products = []
        seen     = set()
        patterns = [
            r'<span class="_cDEzb_p13n-sc-css-line-clamp[^>]*>([^<]{10,80})<',
            r'"title":"([^"]{10,80})"',
            r'<span class="a-size-base-plus[^"]*"[^>]*>([^<]{10,80})</span>',
            r'<span class="a-size-medium[^"]*"[^>]*>([^<]{10,80})</span>',
        ]
        for pat in patterns:
            for m in re.findall(pat, html):
                clean = m.strip()
                if clean and clean not in seen and len(clean) > 8:
                    seen.add(clean)
                    products.append({"name": clean, "source": "amazon_es", "category": category})
                if len(products) >= 12:
                    break
            if len(products) >= 12:
                break

        print(f"  → {len(products)} productos Amazon.es", flush=True)
        return products
    except Exception as e:
        print(f"  ⚠️  Amazon.es error: {e}", flush=True)
        return []


# ── LLM enrichment ───────────────────────────────────────────────────────────

def enrich_with_llm(raw_products: list, niche: str, yt_signals: list, api_key: str) -> list:
    """
    Analiza todos los productos y señales de YouTube para generar el ranking final.
    Devuelve los 8-10 mejores con métricas de dropshipping.
    """
    if not api_key:
        return raw_products

    # Preparar contexto de YouTube (los más vistos)
    yt_context = ""
    if yt_signals:
        top_yt = yt_signals[:5]
        yt_context = "\nSEÑALES DE YOUTUBE (productos con más visualizaciones):\n" + "\n".join(
            f"- {p['name']} ({p.get('yt_views', 0):,} views, demanda: {p.get('demand_signal', '?')})"
            for p in top_yt
        )

    products_text = "\n".join(
        f"- {p.get('name', p.get('term', '?'))} [{p.get('source', '')}]"
        for p in raw_products[:25]
    )

    # Extraer la parte principal del nicho (antes de cualquier explicación adicional)
    niche_core = niche.split("(")[0].split("—")[0].split("\n")[0].strip()

    # Filtrar productos digitales/servicios antes de pasar al LLM
    digital_keywords = ["curso", "online", "digital", "ebook", "software", "app",
                        "suscripción", "servicio", "consultoría", "oposición",
                        "formación", "academia", "clases", "taller", "webinar"]
    raw_products = [
        p for p in raw_products
        if not any(kw in p.get("name", "").lower() for kw in digital_keywords)
    ]

    prompt = f"""Eres un experto en dropshipping con Shopify, especialista en el mercado español y europeo.

NICHO OBJETIVO EXACTO: "{niche_core}"

⚠️ REGLA CRÍTICA: TODOS los productos que devuelvas DEBEN ser del nicho "{niche_core}".
Si un producto no pertenece DIRECTAMENTE a este nicho, DESCÁRTALO sin excepción.
NO generes productos de otros nichos aunque los datos de fuentes no sean relevantes.
Si las fuentes no tienen datos útiles, inventa 8 productos específicos del nicho "{niche_core}".
{yt_context}

PRODUCTOS ENCONTRADOS EN FUENTES (filtra solo los del nicho):
{products_text}

TAREA:
1. Descarta cualquier producto que NO sea del nicho "{niche_core}"
2. De los relevantes, selecciona los 8 mejores para dropshipping en España
3. Si hay pocos relevantes, completa con productos del nicho que conozcas
4. Prioriza productos con señales de YouTube (alta demanda demostrada)

Responde SOLO con JSON válido (sin markdown):
{{
  "products": [
    {{
      "name": "nombre específico del producto (debe ser del nicho {niche_core})",
      "score": 85,
      "est_margin_pct": 65,
      "competition": "Low|Med|High",
      "suggested_price_eur": 39.99,
      "supplier_est_cost_eur": 8.50,
      "why": "razón concisa de por qué funciona en España/EU ahora (1 frase)",
      "target_audience": "descripción del comprador ideal",
      "yt_demand": "high|medium|low|unknown",
      "source": "youtube|amazon_es|perplexity|manual"
    }}
  ]
}}"""

    try:
        response = call_llm(
            messages    = [{"role": "user", "content": prompt}],
            api_key     = api_key,
            max_tokens  = 3000,
            temperature = 0.4,
            title       = "DiscontrolDrops-ProductHunter",
            model       = "anthropic/claude-3-5-haiku",
            timeout     = 45,
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


# ── Input parser ──────────────────────────────────────────────────────────────

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


def get_amazon_category(niche: str) -> str:
    niche_lower = niche.lower()
    category_map = {
        "gadget": "gadgets", "electronic": "electronics", "tech": "electronics",
        "tecnolog": "electronics",
        "home": "home", "kitchen": "home", "cocina": "home", "hogar": "home",
        "oficina": "office", "office": "office",
        "sport": "sports", "fitness": "sports", "deporte": "sports", "gym": "sports",
        "pet": "pets", "mascota": "pets", "perro": "pets", "gato": "pets",
        "beauty": "beauty", "cosmetic": "beauty", "belleza": "beauty",
        "piel": "beauty", "skincare": "beauty", "cabello": "beauty",
        "toy": "toys", "kid": "toys", "niño": "toys", "juguete": "toys",
    }
    return next((v for k, v in category_map.items() if k in niche_lower), "electronics")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    yt_key  = os.environ.get("YOUTUBE_API_KEY_DEEP_SEARCH", "").strip()

    issue_title, issue_body = resolve_issue_context()
    raw = issue_body if issue_body else (issue_title or "")
    if len(sys.argv) > 1:
        raw = " ".join(sys.argv[1:])
    if not raw:
        raw = "gadgets home office"

    params = parse_input(raw)
    niche  = params["niche"]
    region = params["region"]

    sources = []
    if yt_key:  sources.append("YouTube API")
    sources += ["Perplexity", "Google Trends", "Amazon.es"]

    post_issue_comment(
        f"🔍 **Product Hunter** buscando en nicho: **{niche}**\n\n"
        f"Fuentes: {' · '.join(sources)}"
    )
    print(f"🔍 Nicho: '{niche}' | Región: {region}", flush=True)

    # ── Recopilar señales de todas las fuentes ────────────────────────────────

    # 1. YouTube (mejor señal de demanda real)
    print("\n📺 YouTube Data API...", flush=True)
    yt_signals = fetch_youtube_products(niche, yt_key) if yt_key else []

    # 2. Perplexity (trending en tiempo real)
    print("\n🔎 Perplexity research...", flush=True)
    perplexity_products = fetch_perplexity_products(niche, region, api_key)

    # 3. Google Trends (contexto de búsquedas)
    print(f"\n📈 Google Trends ({region})...", flush=True)
    trends = fetch_google_trends(region)
    niche_words = set(niche.lower().split())
    relevant_trends = [
        t for t in trends
        if any(w in t.get("term", "").lower() for w in niche_words)
    ]

    # 4. Amazon.es
    print(f"\n🛒 Amazon.es ({get_amazon_category(niche)})...", flush=True)
    amazon_products = fetch_amazon_es(get_amazon_category(niche))

    # ── Combinar todas las fuentes ────────────────────────────────────────────
    all_products = []
    all_products.extend(yt_signals)
    all_products.extend(perplexity_products)
    all_products.extend(relevant_trends)
    all_products.extend(amazon_products)

    if not all_products:
        all_products = [{"name": niche, "source": "manual"}]

    print(f"\n🤖 Analizando {len(all_products)} señales con LLM...", flush=True)
    products = enrich_with_llm(all_products, niche, yt_signals, api_key) if api_key else all_products

    # Ordenar por score
    if products and isinstance(products[0], dict) and "score" in products[0]:
        products.sort(key=lambda p: p.get("score", 0), reverse=True)

    print(f"\n✅ {len(products)} productos analizados", flush=True)

    # ── Formatear output ──────────────────────────────────────────────────────
    lines = [f"# 🔍 PRODUCT HUNTER — {niche.title()}\n"]
    lines.append(f"**{len(products)} productos encontrados** | Fuentes: {', '.join(sources)}\n")

    for i, p in enumerate(products[:10], 1):
        name     = p.get("name", p.get("term", "?"))
        score    = p.get("score", "?")
        margin   = p.get("est_margin_pct", "?")
        comp     = p.get("competition", "?")
        price    = p.get("suggested_price_eur", "?")
        cost     = p.get("supplier_est_cost_eur", "?")
        why      = p.get("why", "")
        audience = p.get("target_audience", "")
        yt_dem   = p.get("yt_demand", "unknown")

        score_emoji = "🟢" if isinstance(score, (int, float)) and score >= 75 else "🟡" if isinstance(score, (int, float)) and score >= 50 else "🔴"
        comp_emoji  = {"Low": "🟢", "Med": "🟡", "High": "🔴"}.get(str(comp), "⚪")
        yt_emoji    = {"high": "🔥", "medium": "📈", "low": "📉"}.get(yt_dem, "")

        lines.append(f"## {i}. {name}")
        lines.append(f"- {score_emoji} Score: **{score}** | Margen: **{margin}%** | {comp_emoji} Competencia: {comp}")
        if yt_dem != "unknown":
            lines.append(f"- {yt_emoji} Demanda YouTube: **{yt_dem}**")
        if isinstance(price, (int, float)):
            lines.append(f"- 💶 Venta: €{price} | Coste: €{cost}")
        if why:
            lines.append(f"- 💡 {why}")
        if audience:
            lines.append(f"- 🎯 {audience}")
        lines.append("")

    # JSON slim para el siguiente agente (Ad Spy / Lead Qualifier)
    slim_products = [
        {
            "name":                p.get("name", ""),
            "score":               p.get("score", 0),
            "est_margin_pct":      p.get("est_margin_pct", 0),
            "competition":         p.get("competition", "Med"),
            "suggested_price_eur": p.get("suggested_price_eur", 0),
            "supplier_est_cost_eur": p.get("supplier_est_cost_eur", 0),
            "why":                 p.get("why", "")[:120],
            "yt_demand":           p.get("yt_demand", "unknown"),
        }
        for p in products[:10]
    ]

    output_json = {
        "products": slim_products,
        "niche":    niche,
        "region":   region,
        "total":    len(products),
        "sources":  sources,
    }
    lines.append("```json")
    lines.append(json.dumps(output_json, indent=2, ensure_ascii=False))
    lines.append("```")

    output = "\n".join(lines)
    print(output[:300], flush=True)
    post_issue_result(output)


if __name__ == "__main__":
    main()
