"""
Agente: Risk Manager (Polymarket)
Calcula el tamaño óptimo de posición usando Kelly Criterion (fracción 1/4)
y aplica límites de riesgo para proteger el capital.

Input (JSON del Probability Estimator):
{
  "question":       "...",
  "price_yes":      0.54,
  "p_yes_llm":      0.71,
  "edge":           0.17,
  "recommendation": "BUY_YES",
  "tradeable":      true
}

Output: tamaño de posición en USDC + stop-loss + take-profit.
"""
import os
import sys
import json
import re
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from api_client import post_issue_result, post_issue_comment, resolve_issue_context

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# Parámetros de riesgo
KELLY_FRACTION    = 0.25   # Kelly conservador (1/4)
MAX_POSITION_PCT  = 0.05   # Máximo 5% del bankroll por trade
MAX_POSITION_USDC = 50.0   # Límite absoluto en USDC (ajustar según capital)
MIN_POSITION_USDC = 2.0    # Mínimo para que valga la pena (fees)
MIN_EDGE          = 0.05   # Edge mínimo para aprobar (5 puntos)
BANKROLL_USDC     = float(os.environ.get("TRADING_BANKROLL_USDC", "200"))


def kelly_position(p_estimated: float, price_yes: float, bankroll: float,
                   direction: str) -> dict:
    """
    Calcula posición óptima según Kelly Criterion fraccionado.

    direction: "BUY_YES" o "BUY_NO"
    Si BUY_NO: p = 1 - p_estimated, precio = 1 - price_yes
    """
    if direction == "BUY_NO":
        p     = 1 - p_estimated
        price = 1 - price_yes
    else:
        p     = p_estimated
        price = price_yes

    q = 1 - p
    # Odds: si ganas, cobras (1-price)/price por cada USDC arriesgado
    b = (1 - price) / price if price > 0 else 0

    kelly_raw = (b * p - q) / b if b > 0 else 0
    kelly_raw = max(0, kelly_raw)  # No apostar si Kelly < 0

    kelly_conservative = kelly_raw * KELLY_FRACTION
    position_kelly     = kelly_conservative * bankroll
    position_capped    = min(position_kelly, bankroll * MAX_POSITION_PCT, MAX_POSITION_USDC)

    return {
        "kelly_raw":         round(kelly_raw, 4),
        "kelly_conservative": round(kelly_conservative, 4),
        "position_usdc":     round(position_capped, 2),
        "expected_profit":   round(position_capped * b * p - position_capped * q, 2),
        "max_loss_usdc":     round(position_capped, 2),
        "roi_if_win":        round(b, 4),
    }


def extract_params(raw: str) -> dict:
    """Extrae parámetros del Probability Estimator."""
    json_str = None
    if "```json" in raw:
        json_str = raw.split("```json")[1].split("```")[0].strip()
    elif raw.strip().startswith("{"):
        json_str = raw.strip()
    else:
        m = re.search(r'\{[\s\S]*?"question"[\s\S]*?\}', raw)
        if m:
            json_str = m.group(0)

    if json_str:
        try:
            return json.loads(json_str)
        except Exception:
            pass
    return {}


def main():
    issue_title, issue_body = resolve_issue_context()
    raw = issue_body if issue_body else (issue_title or "")
    if len(sys.argv) > 1:
        raw = " ".join(sys.argv[1:])

    post_issue_comment(f"⚖️ Risk Manager calculando posición (bankroll: ${BANKROLL_USDC:.0f} USDC)...")

    params = extract_params(raw)

    if not params:
        post_issue_result("❌ Risk Manager: No se pudo leer los parámetros del Probability Estimator.")
        sys.exit(1)

    tradeable  = params.get("tradeable", False)
    edge       = params.get("edge", 0)
    rec        = params.get("recommendation", "PASS")
    price_yes  = params.get("price_yes", 0.5)
    p_yes_llm  = params.get("p_yes_llm", 0.5)
    question   = params.get("question", "")

    print(f"📊 Edge: {edge:.1%} | Rec: {rec} | Tradeable: {tradeable}", flush=True)

    # Verificar si el trade pasa los filtros
    reasons_reject = []
    if not tradeable:
        reasons_reject.append("Edge insuficiente según Probability Estimator")
    if edge < MIN_EDGE:
        reasons_reject.append(f"Edge {edge:.1%} < mínimo {MIN_EDGE:.1%}")
    if rec == "PASS":
        reasons_reject.append("Probability Estimator recomienda PASS")

    if reasons_reject:
        lines = ["# ⚖️ RISK MANAGER — Decisión: ❌ NO TRADE\n"]
        lines.append("## Razones de rechazo")
        for r in reasons_reject:
            lines.append(f"- {r}")

        output_json = {
            "approved": False,
            "reasons":  reasons_reject,
            "question": question,
        }
        lines.append("\n```json")
        lines.append(json.dumps(output_json, indent=2))
        lines.append("```")
        post_issue_result("\n".join(lines))
        return

    # Calcular posición
    sizing = kelly_position(p_yes_llm, price_yes, BANKROLL_USDC, rec)
    position_usdc = sizing["position_usdc"]

    if position_usdc < MIN_POSITION_USDC:
        post_issue_result(
            f"❌ Risk Manager: Posición calculada ${position_usdc:.2f} < mínimo ${MIN_POSITION_USDC}. PASS."
        )
        return

    print(f"✅ Posición aprobada: ${position_usdc:.2f} USDC", flush=True)

    lines = ["# ⚖️ RISK MANAGER — Decisión: ✅ TRADE APROBADO\n"]
    lines.append(f"**{question}**\n")
    lines.append(f"| Parámetro | Valor |")
    lines.append(f"|---|---|")
    lines.append(f"| Dirección | **{rec}** |")
    lines.append(f"| Precio entrada | {price_yes:.0%} (YES) |")
    lines.append(f"| P(YES) estimada | {p_yes_llm:.0%} |")
    lines.append(f"| Edge | {edge:.1%} |")
    lines.append(f"| Bankroll | ${BANKROLL_USDC:.0f} USDC |")
    lines.append(f"| Kelly raw | {sizing['kelly_raw']:.1%} |")
    lines.append(f"| Kelly 1/4 | {sizing['kelly_conservative']:.1%} |")
    lines.append(f"| **Posición** | **${position_usdc:.2f} USDC** |")
    lines.append(f"| Ganancia esperada | ${sizing['expected_profit']:.2f} |")
    lines.append(f"| Max pérdida | ${sizing['max_loss_usdc']:.2f} |")
    lines.append("")

    output_json = {
        "approved":     True,
        "question":     question,
        "direction":    rec,
        "price_yes":    price_yes,
        "p_yes_llm":    p_yes_llm,
        "edge":         edge,
        "position_usdc": position_usdc,
        "condition_id": params.get("condition_id", ""),
        "sizing":       sizing,
        "bankroll":     BANKROLL_USDC,
    }
    lines.append("```json")
    lines.append(json.dumps(output_json, indent=2, ensure_ascii=False))
    lines.append("```")

    post_issue_result("\n".join(lines))


if __name__ == "__main__":
    main()
