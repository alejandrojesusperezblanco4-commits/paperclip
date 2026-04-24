"""
Agente: Wallet Analyzer (Polymarket)
Opción C: encuentra los wallets más rentables en crypto (leaderboard)
y analiza sus posiciones actuales para extraer señales de trading.

Fase 1 → Top 50 traders crypto por P&L all-time (leaderboard)
Fase 2 → Posiciones abiertas de cada whale
Fase 3 → Score: P&L, volumen, posiciones crypto activas
Fase 4 → Output: top whales + sus apuestas actuales = señales

APIs usadas (sin auth):
  Leaderboard: https://data-api.polymarket.com/v1/leaderboard
  Positions:   https://data-api.polymarket.com/positions
"""
import os
import sys
import json
import time
import urllib.request
import urllib.error
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from api_client import post_issue_result, post_issue_comment, resolve_issue_context

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

DATA_API = "https://data-api.polymarket.com"

BROWSER_HEADERS = {
    "Accept":          "application/json",
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin":          "https://polymarket.com",
    "Referer":         "https://polymarket.com/",
}

# Palabras clave para detectar posiciones crypto
CRYPTO_KEYWORDS = [
    "bitcoin", "btc", "ethereum", "eth", "solana", "sol", "crypto",
    "xrp", "ripple", "bnb", "doge", "dogecoin", "coinbase", "binance",
    "altcoin", "defi", "token", "blockchain", "price", "ath", "halving",
    "stablecoin", "usdc", "tether", "nft", "web3", "layer", "l2",
]

TOP_WHALES     = int(os.environ.get("WALLET_ANALYZER_TOP_WHALES", "20"))
TOP_POSITIONS  = int(os.environ.get("WALLET_ANALYZER_TOP_POSITIONS", "5"))
MIN_PNL_USD    = float(os.environ.get("WALLET_ANALYZER_MIN_PNL", "1000"))


def http_get(url: str) -> dict | list:
    req = urllib.request.Request(url, headers=BROWSER_HEADERS, method="GET")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def get_leaderboard(limit: int = 50) -> list:
    """Top traders crypto por P&L all-time."""
    url = (
        f"{DATA_API}/v1/leaderboard"
        f"?category=CRYPTO&timePeriod=ALL&orderBy=PNL&limit={limit}"
    )
    print(f"  📡 Leaderboard crypto: {url}", flush=True)
    data = http_get(url)
    return data if isinstance(data, list) else []


def get_positions(wallet: str, limit: int = 50) -> list:
    """Posiciones abiertas de un wallet."""
    url = (
        f"{DATA_API}/positions"
        f"?user={wallet}&limit={limit}&sortBy=CASHPNL&sortDirection=DESC"
    )
    try:
        data = http_get(url)
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"    ⚠️  Error obteniendo posiciones de {wallet[:10]}…: {e}", flush=True)
        return []


def is_crypto_position(pos: dict) -> bool:
    """Detecta si una posición es de mercado crypto."""
    title = (pos.get("title") or pos.get("question") or "").lower()
    return any(k in title for k in CRYPTO_KEYWORDS)


def score_whale(trader: dict, positions: list) -> dict:
    """Puntúa un whale por rentabilidad y actividad crypto."""
    pnl    = float(trader.get("pnl", 0) or 0)
    vol    = float(trader.get("vol", 0) or 0)
    crypto_pos = [p for p in positions if is_crypto_position(p)]

    # Score compuesto: PnL (70%) + Volumen relativo (20%) + Posiciones activas (10%)
    pnl_score  = min(100, pnl / 1000)       # 1 punto por cada $1k de PnL
    vol_score  = min(20, vol / 10000)       # hasta 20 puntos por volumen
    pos_score  = min(10, len(crypto_pos))   # hasta 10 posiciones activas

    return {
        "wallet":       trader.get("proxyWallet", ""),
        "username":     trader.get("userName") or trader.get("xUsername") or "anon",
        "pnl_usd":      round(pnl, 2),
        "volume_usd":   round(vol, 2),
        "score":        round(pnl_score + vol_score + pos_score, 2),
        "crypto_positions": [
            {
                "title":      p.get("title", p.get("question", ""))[:100],
                "side":       "YES" if float(p.get("currentValue", 0) or 0) > 0 else "NO",
                "size_usdc":  round(float(p.get("currentValue", 0) or 0), 2),
                "avg_price":  round(float(p.get("avgPrice", 0) or 0), 4),
                "pnl_usdc":   round(float(p.get("cashPnl", 0) or 0), 2),
            }
            for p in crypto_pos[:5]
        ],
    }


def main():
    issue_title, issue_body = resolve_issue_context()

    post_issue_comment(
        "🐋 **Wallet Analyzer** iniciando...\n\n"
        f"Fase 1: Top {TOP_WHALES} traders crypto por P&L all-time\n"
        "Fase 2: Posiciones abiertas de cada whale\n"
        "Fase 3: Scoring y extracción de señales"
    )

    # ── FASE 1: Leaderboard ──────────────────────────────────────────────────
    print("🏆 Fase 1: Obteniendo leaderboard crypto...", flush=True)
    leaderboard = get_leaderboard(limit=50)

    # Filtrar por PnL mínimo
    top_traders = [
        t for t in leaderboard
        if float(t.get("pnl", 0) or 0) >= MIN_PNL_USD
    ][:TOP_WHALES]

    print(f"  → {len(top_traders)} whales con PnL > ${MIN_PNL_USD:,.0f}", flush=True)

    if not top_traders:
        post_issue_result("❌ No se encontraron whales con el PnL mínimo requerido.")
        return

    # ── FASE 2: Posiciones de cada whale ────────────────────────────────────
    print("\n📊 Fase 2: Analizando posiciones...", flush=True)
    analyzed = []
    for i, trader in enumerate(top_traders):
        wallet = trader.get("proxyWallet", "")
        if not wallet:
            continue
        print(f"  [{i+1}/{len(top_traders)}] {wallet[:12]}… ({trader.get('userName', 'anon')})", flush=True)
        positions = get_positions(wallet)
        scored    = score_whale(trader, positions)
        analyzed.append(scored)
        time.sleep(0.3)  # Rate limit suave

    # ── FASE 3: Ranking final ────────────────────────────────────────────────
    analyzed.sort(key=lambda x: x["score"], reverse=True)
    top_whales = analyzed[:TOP_POSITIONS]

    print(f"\n✅ Top {len(top_whales)} whales identificados", flush=True)

    # ── Output ───────────────────────────────────────────────────────────────
    lines = ["# 🐋 WALLET ANALYZER — Top Crypto Whales de Polymarket\n"]
    lines.append(
        f"Analizados: **{len(top_traders)} traders** del leaderboard crypto (all-time PnL)\n"
    )

    for i, w in enumerate(top_whales, 1):
        lines.append(f"## #{i} — {w['username']} `{w['wallet'][:14]}…`")
        lines.append(f"| Métrica | Valor |")
        lines.append(f"|---|---|")
        lines.append(f"| P&L Total | **${w['pnl_usd']:,.0f}** |")
        lines.append(f"| Volumen | ${w['volume_usd']:,.0f} |")
        lines.append(f"| Score | {w['score']:.1f} |")
        lines.append(f"| Posiciones crypto activas | {len(w['crypto_positions'])} |")
        lines.append("")

        if w["crypto_positions"]:
            lines.append("**Posiciones abiertas:**")
            for p in w["crypto_positions"]:
                pnl_emoji = "🟢" if p["pnl_usdc"] >= 0 else "🔴"
                lines.append(
                    f"- {pnl_emoji} **{p['side']}** @ {p['avg_price']:.0%} — "
                    f"${p['size_usdc']:.0f} USDC — P&L: ${p['pnl_usdc']:+.0f}\n"
                    f"  _{p['title']}_"
                )
            lines.append("")

    # Señales consolidadas: mercados donde 2+ whales tienen posición
    all_positions = []
    for w in top_whales:
        for p in w["crypto_positions"]:
            all_positions.append({**p, "whale": w["username"]})

    # Agrupar por título
    from collections import defaultdict
    grouped: dict = defaultdict(list)
    for p in all_positions:
        grouped[p["title"]].append(p)

    consensus = {k: v for k, v in grouped.items() if len(v) >= 2}
    if consensus:
        lines.append("---\n## 🎯 SEÑALES CONSENSUS (2+ whales en mismo mercado)\n")
        for title, positions in sorted(consensus.items(), key=lambda x: -len(x[1])):
            whales_in  = [p["whale"] for p in positions]
            sides      = [p["side"] for p in positions]
            lines.append(f"**{title}**")
            lines.append(f"- Whales: {', '.join(whales_in)}")
            lines.append(f"- Direcciones: {', '.join(sides)}")
            lines.append("")

    # JSON estructurado para el CEO / Probability Estimator
    output_json = {
        "top_whales":       top_whales,
        "consensus_markets": [
            {"title": k, "whale_count": len(v), "sides": [p["side"] for p in v]}
            for k, v in consensus.items()
        ],
        "analyzed_count": len(analyzed),
        "source":         "polymarket_leaderboard",
    }
    lines.append("```json")
    lines.append(json.dumps(output_json, indent=2, ensure_ascii=False)[:8000])
    lines.append("```")

    output = "\n".join(lines)
    print(output[:300], flush=True)
    post_issue_result(output)


if __name__ == "__main__":
    main()
