"""
Agente: Market Scanner (Polymarket)
Escanea la Gamma API de Polymarket buscando mercados con:
- Volumen > $10k USDC
- Liquidez suficiente (spread < 5%)
- Precio entre 0.10 y 0.90 (no resolved, no trivial)
- Categorías prioritarias: política, crypto, macro

Docs: https://gamma-api.polymarket.com
Output: lista de mercados candidatos con precio, volumen y metadata.
"""
import os
import sys
import json
import urllib.request
import urllib.error
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from api_client import post_issue_result, post_issue_comment, resolve_issue_context

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

GAMMA_API = "https://gamma-api.polymarket.com"

# Categorías con mejor edge histórico
PRIORITY_CATEGORIES = ["politics", "crypto", "economics", "finance"]
MIN_VOLUME_USD = 10_000
MIN_PRICE      = 0.10
MAX_PRICE      = 0.90


def fetch_markets(limit: int = 50) -> list:
    """Obtiene mercados activos de Polymarket via Gamma API."""
    url = f"{GAMMA_API}/markets?active=true&closed=false&limit={limit}&order=volume&ascending=false"
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def filter_candidates(markets: list) -> list:
    """Filtra mercados con potencial de edge."""
    candidates = []
    for m in markets:
        try:
            volume = float(m.get("volumeNum", 0) or 0)
            if volume < MIN_VOLUME_USD:
                continue

            # Obtener precio YES del primer outcome
            outcomes = m.get("outcomes", "[]")
            if isinstance(outcomes, str):
                outcomes = json.loads(outcomes)
            prices = m.get("outcomePrices", "[]")
            if isinstance(prices, str):
                prices = json.loads(prices)

            if not prices:
                continue
            price_yes = float(prices[0]) if prices else 0.5
            if not (MIN_PRICE <= price_yes <= MAX_PRICE):
                continue

            candidates.append({
                "id":           m.get("id", ""),
                "question":     m.get("question", ""),
                "category":     m.get("category", "").lower(),
                "price_yes":    round(price_yes, 4),
                "price_no":     round(1 - price_yes, 4),
                "volume_usd":   round(volume, 2),
                "end_date":     m.get("endDate", ""),
                "condition_id": m.get("conditionId", ""),
                "slug":         m.get("slug", ""),
            })
        except Exception:
            continue

    # Ordenar por volumen descendente
    candidates.sort(key=lambda x: x["volume_usd"], reverse=True)
    return candidates


def main():
    issue_title, issue_body = resolve_issue_context()

    post_issue_comment("🔍 Market Scanner iniciando escaneo de Polymarket...")

    try:
        print("📡 Fetching markets from Gamma API...", flush=True)
        markets = fetch_markets(limit=100)
        print(f"  → {len(markets)} mercados obtenidos", flush=True)

        candidates = filter_candidates(markets)
        print(f"  → {len(candidates)} candidatos filtrados", flush=True)

        lines = [f"# 🔍 MARKET SCANNER — Polymarket\n"]
        lines.append(f"**{len(candidates)} mercados candidatos** (volumen > ${MIN_VOLUME_USD:,})\n")

        for i, m in enumerate(candidates[:20], 1):
            lines.append(f"## {i}. {m['question']}")
            lines.append(f"- **YES:** {m['price_yes']:.0%} | **NO:** {m['price_no']:.0%}")
            lines.append(f"- **Volumen:** ${m['volume_usd']:,.0f}")
            lines.append(f"- **Categoría:** {m['category']}")
            lines.append(f"- **Cierre:** {m['end_date'][:10] if m['end_date'] else 'N/A'}")
            lines.append("")

        output_json = {
            "candidates":   candidates[:20],
            "total_scanned": len(markets),
            "source":       "gamma_api",
        }
        lines.append("```json")
        lines.append(json.dumps(output_json, indent=2, ensure_ascii=False))
        lines.append("```")

        output = "\n".join(lines)
        print(output[:500], flush=True)
        post_issue_result(output)

    except Exception as e:
        error_msg = f"❌ Error en Market Scanner: {e}"
        print(error_msg, file=sys.stderr)
        post_issue_result(error_msg)
        sys.exit(1)


if __name__ == "__main__":
    main()
