"""
Agente: Ad Spy — DiscontrolDrops
Analiza anuncios activos en Facebook Ads Library (completamente público, sin auth).
Si hay anuncios corriendo durante semanas = el producto está vendiendo.

Input (JSON del Product Hunter o texto libre):
{
  "products": [...],
  "niche": "tactical gadgets"
}

Output: datos de anuncios activos por producto + insights de copy y creative.
"""
import os
import sys
import json
import re
import urllib.request
import urllib.parse
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from api_client import post_issue_result, post_issue_comment, resolve_issue_context, call_llm

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

FB_ADS_LIBRARY_URL = "https://www.facebook.com/ads/library/api/"


def search_fb_ads(query: str, country: str = "ES") -> dict:
    """
    Consulta la Facebook Ads Library API (pública, sin auth para datos básicos).
    Devuelve número de anuncios activos y metadata.
    """
    params = {
        "ad_type":        "ALL",
        "countries[]":    country,
        "q":              query,
        "search_type":    "KEYWORD_UNORDERED",
        "active_status":  "ACTIVE",
        "limit":          "20",
        "fields":         "id,ad_creative_bodies,ad_creative_link_captions,ad_delivery_start_time,page_name,spend",
    }
    url = f"{FB_ADS_LIBRARY_URL}?{urllib.parse.urlencode(params, doseq=True)}"
    headers = {
        "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept":          "application/json",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Referer":         "https://www.facebook.com/ads/library/",
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"  ⚠️  FB Ads API error ({query}): {e}", flush=True)
        return {}


def scrape_fb_ads_page(query: str, country: str = "ES") -> dict:
    """
    Alternativa: scrape básico de la página web de Ads Library.
    Extrae número de resultados y anunciantes activos.
    """
    url = f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country={country}&q={urllib.parse.quote(query)}&search_type=keyword_unordered"
    headers = {
        "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept":          "text/html,application/xhtml+xml,*/*",
        "Accept-Language": "es-ES,es;q=0.9",
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8", errors="replace")

        # Extraer número de resultados
        count_match = re.search(r'"total_count":(\d+)', html)
        count = int(count_match.group(1)) if count_match else 0

        # Extraer nombres de páginas anunciantes
        page_names = re.findall(r'"page_name":"([^"]{2,50})"', html)[:10]

        # Extraer fragmentos de copy
        bodies = re.findall(r'"ad_creative_bodies":\["([^"]{10,200})"', html)[:5]

        # Extraer fechas de inicio
        dates = re.findall(r'"ad_delivery_start_time":"([^"]+)"', html)[:5]

        return {
            "total_ads": count,
            "advertisers": list(set(page_names))[:8],
            "copy_samples": bodies[:3],
            "oldest_ad_date": min(dates) if dates else "",
        }
    except Exception as e:
        print(f"  ⚠️  FB scraping error ({query}): {e}", flush=True)
        return {"total_ads": 0, "advertisers": [], "copy_samples": [], "oldest_ad_date": ""}


def analyze_ad_signals(product_name: str, ad_data: dict, api_key: str) -> dict:
    """Usa LLM para interpretar los datos de anuncios y extraer insights."""
    if not api_key or not ad_data.get("total_ads", 0):
        return {}

    prompt = f"""Analiza estos datos de Facebook Ads Library para el producto: "{product_name}"

Datos:
- Anuncios activos: {ad_data.get('total_ads', 0)}
- Anunciantes: {', '.join(ad_data.get('advertisers', [])[:5]) or 'N/A'}
- Muestras de copy: {' | '.join(ad_data.get('copy_samples', [])[:2]) or 'N/A'}
- Anuncio más antiguo activo: {ad_data.get('oldest_ad_date', 'N/A')}

Evalúa:
1. ¿Está validado este producto? (muchos anuncios activos = alguien está ganando dinero)
2. ¿Qué ángulo de copy están usando?
3. ¿Hay oportunidad de diferenciarse?

Responde SOLO con JSON:
{{
  "validated": true,
  "competition_level": "Low|Med|High",
  "dominant_angle": "el ángulo de copy más común en 1 frase",
  "differentiation_opportunity": "cómo diferenciarse en 1 frase",
  "ad_signal": "Strong|Medium|Weak"
}}"""

    try:
        response = call_llm(
            messages=[{"role": "user", "content": prompt}],
            api_key=api_key, max_tokens=300, temperature=0.3,
            title="DiscontrolDrops - Ad Spy Analysis",
            model="anthropic/claude-3-5-haiku", timeout=15, retries=0,
        )
        clean = response.strip()
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```")[1].split("```")[0].strip()
        return json.loads(clean)
    except Exception:
        return {}


def extract_input(raw: str) -> tuple:
    """Extrae productos y nicho del input."""
    json_str = None
    if "```json" in raw:
        json_str = raw.split("```json")[1].split("```")[0].strip()
    elif raw.strip().startswith("{"):
        json_str = raw.strip()
    else:
        m = re.search(r'\{[\s\S]*?"products"[\s\S]*?\}', raw)
        if m:
            json_str = m.group(0)

    if json_str:
        try:
            data     = json.loads(json_str)
            products = data.get("products", [])
            niche    = data.get("niche", "products")
            return products, niche
        except Exception:
            pass
    # Fallback: tratar el texto como query directa
    return [{"name": raw.strip()[:100]}], raw.strip()


def main():
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()

    issue_title, issue_body = resolve_issue_context()
    raw = issue_body if issue_body else (issue_title or "")
    if len(sys.argv) > 1:
        raw = " ".join(sys.argv[1:])
    if not raw:
        raw = "tactical gadgets dropshipping"

    products, niche = extract_input(raw)
    products = products[:8]  # máximo 8 para no tardar demasiado

    post_issue_comment(
        f"🕵️ Ad Spy analizando **{len(products)} productos** en Facebook Ads Library...\n\n"
        f"Buscando anuncios activos para validar demanda real."
    )
    print(f"🕵️ Analizando {len(products)} productos en FB Ads Library", flush=True)

    results = []
    for i, product in enumerate(products):
        name = product.get("name", product.get("term", f"Product {i+1}"))
        print(f"\n  [{i+1}/{len(products)}] {name[:50]}...", flush=True)

        ad_data = scrape_fb_ads_page(name, "ES")
        insights = analyze_ad_signals(name, ad_data, api_key) if ad_data.get("total_ads", 0) > 0 else {}

        result = {
            "product":      name,
            "total_ads":    ad_data.get("total_ads", 0),
            "advertisers":  ad_data.get("advertisers", []),
            "copy_samples": ad_data.get("copy_samples", []),
            "oldest_ad":    ad_data.get("oldest_ad_date", ""),
            "insights":     insights,
            "validated":    ad_data.get("total_ads", 0) > 5,
        }
        results.append(result)
        print(f"    → {ad_data.get('total_ads', 0)} anuncios activos | validated: {result['validated']}", flush=True)

    # Ordenar: más validados primero
    results.sort(key=lambda r: r["total_ads"], reverse=True)

    lines = [f"# 🕵️ AD SPY — Facebook Ads Library\n"]
    lines.append(f"**{len(results)} productos analizados** · País: España\n")

    for r in results:
        ads = r["total_ads"]
        signal = r["insights"].get("ad_signal", "Unknown")
        validated = r["validated"]

        signal_emoji = "🟢" if signal == "Strong" or ads > 20 else "🟡" if signal == "Medium" or ads > 5 else "🔴"
        valid_badge  = "✅ VALIDADO" if validated else "⚠️ POCO TRÁFICO"

        lines.append(f"---\n## {signal_emoji} {r['product']}")
        lines.append(f"**{ads} anuncios activos** · {valid_badge}")

        if r["advertisers"]:
            lines.append(f"**Anunciantes:** {', '.join(r['advertisers'][:4])}")

        if r["copy_samples"]:
            lines.append(f"**Copy samples:**")
            for cs in r["copy_samples"][:2]:
                lines.append(f"> {cs[:120]}")

        if r["insights"]:
            ins = r["insights"]
            if ins.get("dominant_angle"):
                lines.append(f"**Ángulo dominante:** {ins['dominant_angle']}")
            if ins.get("differentiation_opportunity"):
                lines.append(f"**Oportunidad:** {ins['differentiation_opportunity']}")

        lines.append("")

    output_json = {"results": results, "niche": niche, "total_analyzed": len(results)}
    lines.append("```json")
    lines.append(json.dumps(output_json, indent=2, ensure_ascii=False))
    lines.append("```")

    post_issue_result("\n".join(lines))


if __name__ == "__main__":
    main()
