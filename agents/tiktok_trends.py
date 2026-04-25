"""
Módulo: TikTok Creative Center Trends
Extrae tendencias reales del TikTok Creative Center sin API key.
Usa las APIs internas públicas de ads.tiktok.com/business/creativecenter

Endpoints:
  Hashtags: /creative_radar_api/v1/popular_trend/hashtag/list
  Sonidos:  /creative_radar_api/v1/popular_trend/music/list
  Keywords: /creative_radar_api/v1/popular_trend/keyword/list

Sin autenticación — datos públicos del Creative Center.
"""
import json
import urllib.request
import urllib.parse
import urllib.error

CC_BASE = "https://ads.tiktok.com/creative_radar_api/v1/popular_trend"

CC_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
    "Referer":         "https://ads.tiktok.com/business/creativecenter/",
    "Origin":          "https://ads.tiktok.com",
}

# Códigos de país disponibles
COUNTRIES = {
    "mx": "México",
    "es": "España",
    "co": "Colombia",
    "ar": "Argentina",
    "us": "US (Hispanic)",
}


def _cc_get(endpoint: str, params: dict) -> dict:
    """Llama a una API del Creative Center."""
    url = f"{CC_BASE}/{endpoint}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=CC_HEADERS, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"  ⚠️  Creative Center HTTP {e.code} ({endpoint})", flush=True)
        return {}
    except Exception as e:
        print(f"  ⚠️  Creative Center error ({endpoint}): {e}", flush=True)
        return {}


def get_trending_hashtags(country: str = "mx", period: int = 7,
                           limit: int = 20) -> list:
    """
    Retorna hashtags trending en TikTok.
    period: 7 (semana) | 30 (mes)
    country: mx, es, co, ar, us
    """
    data = _cc_get("hashtag/list", {
        "period":       period,
        "page":         1,
        "limit":        limit,
        "country_code": country.upper(),
        "order_by":     "popular",
    })
    items = (data.get("data") or {}).get("list", [])
    result = []
    for item in items:
        hashtag = item.get("hashtag_name", "") or item.get("name", "")
        views   = item.get("video_views", 0) or item.get("view_sum", 0)
        posts   = item.get("publish_cnt", 0) or item.get("post_count", 0)
        trend   = item.get("trend", "")
        if hashtag:
            result.append({
                "hashtag": f"#{hashtag}" if not hashtag.startswith("#") else hashtag,
                "views":   int(views),
                "posts":   int(posts),
                "trend":   trend,
            })
    return result


def get_trending_sounds(country: str = "mx", period: int = 7,
                         limit: int = 10) -> list:
    """Retorna sonidos/música trending en TikTok."""
    data = _cc_get("music/list", {
        "period":       period,
        "page":         1,
        "limit":        limit,
        "country_code": country.upper(),
        "order_by":     "popular",
    })
    items = (data.get("data") or {}).get("list", [])
    result = []
    for item in items:
        title  = item.get("music_title", "") or item.get("title", "")
        artist = item.get("author", "") or item.get("artist", "")
        usage  = item.get("use_cnt", 0) or item.get("usage_count", 0)
        if title:
            result.append({
                "title":  title,
                "artist": artist,
                "usage":  int(usage),
            })
    return result


def get_trending_keywords(country: str = "mx", period: int = 7,
                           limit: int = 15) -> list:
    """Retorna keywords trending de búsqueda en TikTok."""
    data = _cc_get("keyword/list", {
        "period":       period,
        "page":         1,
        "limit":        limit,
        "country_code": country.upper(),
        "order_by":     "popular",
    })
    items = (data.get("data") or {}).get("list", [])
    result = []
    for item in items:
        keyword = item.get("keyword", "") or item.get("name", "")
        score   = item.get("trend_score", 0) or item.get("score", 0)
        if keyword:
            result.append({
                "keyword": keyword,
                "score":   score,
            })
    return result


def format_number(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n/1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def build_tiktok_trends_context(countries: list = None) -> str:
    """
    Construye un bloque de contexto con todas las tendencias de TikTok.
    Se usa para inyectar en los prompts de Deep Search y Channel Analyzer.
    """
    if countries is None:
        countries = ["mx", "es", "co"]

    lines = ["## 📱 TENDENCIAS REALES DE TIKTOK (Creative Center)\n"]

    all_hashtags = {}
    all_sounds   = []

    for country in countries:
        country_name = COUNTRIES.get(country, country.upper())
        print(f"  📡 TikTok trends para {country_name}...", flush=True)

        hashtags = get_trending_hashtags(country, period=7, limit=15)
        sounds   = get_trending_sounds(country, period=7, limit=5)
        keywords = get_trending_keywords(country, period=7, limit=10)

        if hashtags:
            lines.append(f"### 🏷️ Hashtags trending — {country_name}")
            for h in hashtags[:10]:
                views_str = format_number(h["views"]) if h["views"] else "?"
                posts_str = format_number(h["posts"]) if h["posts"] else "?"
                trend_arrow = "📈" if "up" in str(h.get("trend", "")).lower() else "➡️"
                lines.append(f"  {trend_arrow} `{h['hashtag']}` — {views_str} views · {posts_str} videos")
                # Acumular para cross-country
                tag = h["hashtag"]
                all_hashtags[tag] = all_hashtags.get(tag, 0) + 1
            lines.append("")

        if sounds:
            lines.append(f"### 🎵 Sonidos trending — {country_name}")
            for s in sounds[:5]:
                usage_str = format_number(s["usage"]) if s["usage"] else "?"
                artist_str = f" ({s['artist']})" if s.get("artist") else ""
                lines.append(f"  🎵 \"{s['title']}\"{artist_str} — {usage_str} usos")
                all_sounds.append(s["title"])
            lines.append("")

        if keywords:
            lines.append(f"### 🔍 Keywords trending — {country_name}")
            kw_list = [f"`{k['keyword']}`" for k in keywords[:8]]
            lines.append("  " + " · ".join(kw_list))
            lines.append("")

    # Hashtags que trendan en múltiples países (más relevantes)
    cross_country = [tag for tag, count in all_hashtags.items() if count >= 2]
    if cross_country:
        lines.append("### 🌎 Hashtags en múltiples países LATAM (máxima relevancia)")
        lines.append("  " + " · ".join(cross_country[:8]))
        lines.append("")

    if len(lines) <= 2:
        return ""  # No se obtuvo ningún dato

    return "\n".join(lines)


if __name__ == "__main__":
    # Test rápido
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print(build_tiktok_trends_context(["mx", "es"]))
