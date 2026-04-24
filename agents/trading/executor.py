"""
Agente: Executor (Polymarket)
Coloca órdenes en Polymarket usando py-clob-client.
En modo DRY_RUN (default) solo simula la orden sin ejecutarla.

Variables de entorno:
  POLYGON_PRIVATE_KEY       → clave privada Ethereum (0x...)
  POLYMARKET_API_KEY        → API key de Polymarket
  POLYMARKET_API_SECRET     → API secret
  POLYMARKET_API_PASSPHRASE → passphrase
  TRADING_DRY_RUN=true      → simular sin ejecutar (default: true)

Input (JSON del Risk Manager):
{
  "approved":      true,
  "question":      "...",
  "direction":     "BUY_YES",
  "price_yes":     0.54,
  "position_usdc": 12.50,
  "condition_id":  "0x..."
}
"""
import os
import sys
import json
import re
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from api_client import post_issue_result, post_issue_comment, resolve_issue_context

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

DRY_RUN = os.environ.get("TRADING_DRY_RUN", "true").lower() != "false"


def extract_params(raw: str) -> dict:
    json_str = None
    if "```json" in raw:
        json_str = raw.split("```json")[1].split("```")[0].strip()
    elif raw.strip().startswith("{"):
        json_str = raw.strip()
    else:
        m = re.search(r'\{[\s\S]*?"approved"[\s\S]*?\}', raw)
        if m:
            json_str = m.group(0)
    if json_str:
        try:
            return json.loads(json_str)
        except Exception:
            pass
    return {}


def execute_order_dry(params: dict) -> dict:
    """Simula la orden sin conectar a Polymarket."""
    direction    = params.get("direction", "BUY_YES")
    price_yes    = params.get("price_yes", 0.5)
    position     = params.get("position_usdc", 0)
    condition_id = params.get("condition_id", "N/A")

    entry_price = price_yes if direction == "BUY_YES" else (1 - price_yes)
    shares      = round(position / entry_price, 4) if entry_price > 0 else 0

    return {
        "status":       "simulated",
        "dry_run":      True,
        "direction":    direction,
        "entry_price":  entry_price,
        "shares":       shares,
        "usdc_spent":   position,
        "condition_id": condition_id,
        "order_id":     f"DRY_{int(__import__('time').time())}",
    }


def execute_order_live(params: dict) -> dict:
    """Coloca la orden real en Polymarket via py-clob-client."""
    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import ApiCreds, OrderArgs, OrderType

        private_key = os.environ.get("POLYGON_PRIVATE_KEY", "").strip()
        api_key     = os.environ.get("POLYMARKET_API_KEY", "").strip()
        api_secret  = os.environ.get("POLYMARKET_API_SECRET", "").strip()
        passphrase  = os.environ.get("POLYMARKET_API_PASSPHRASE", "").strip()

        if not all([private_key, api_key, api_secret, passphrase]):
            raise Exception("Faltan credenciales de Polymarket (POLYGON_PRIVATE_KEY, POLYMARKET_API_KEY, etc.)")

        client = ClobClient(
            host      = "https://clob.polymarket.com",
            key       = private_key,
            chain_id  = 137,
            creds     = ApiCreds(
                api_key        = api_key,
                api_secret     = api_secret,
                api_passphrase = passphrase,
            )
        )

        direction    = params.get("direction", "BUY_YES")
        price_yes    = params.get("price_yes", 0.5)
        position     = params.get("position_usdc", 0)
        condition_id = params.get("condition_id", "")

        # Determinar token_id (YES=0, NO=1 en el condition)
        side        = "BUY"
        token_index = 0 if direction == "BUY_YES" else 1
        entry_price = price_yes if direction == "BUY_YES" else (1 - price_yes)
        size        = round(position / entry_price, 2) if entry_price > 0 else 0

        # Obtener token_id del mercado
        market = client.get_market(condition_id=condition_id)
        tokens = market.get("tokens", [])
        token_id = tokens[token_index].get("token_id", "") if len(tokens) > token_index else ""

        if not token_id:
            raise Exception(f"No se pudo obtener token_id para condition_id={condition_id}")

        order_args = OrderArgs(
            price    = entry_price,
            size     = size,
            side     = side,
            token_id = token_id,
        )
        signed_order = client.create_order(order_args)
        response     = client.post_order(signed_order, OrderType.GTC)

        return {
            "status":       "placed",
            "dry_run":      False,
            "direction":    direction,
            "entry_price":  entry_price,
            "size":         size,
            "usdc_spent":   position,
            "token_id":     token_id,
            "order_id":     response.get("orderID", ""),
            "order_hash":   response.get("orderHash", ""),
        }

    except ImportError:
        raise Exception("py-clob-client no instalado. Ejecuta: pip install py-clob-client")


def main():
    issue_title, issue_body = resolve_issue_context()
    raw = issue_body if issue_body else (issue_title or "")
    if len(sys.argv) > 1:
        raw = " ".join(sys.argv[1:])

    params = extract_params(raw)

    if not params.get("approved", False):
        post_issue_result("⚡ Executor: Trade no aprobado por Risk Manager. Sin acción.")
        return

    mode = "🧪 DRY RUN (simulación)" if DRY_RUN else "🔴 LIVE — ORDEN REAL"
    post_issue_comment(f"⚡ Executor procesando orden... Modo: {mode}")

    question  = params.get("question", "")
    direction = params.get("direction", "BUY_YES")
    position  = params.get("position_usdc", 0)

    print(f"📋 Mercado: {question[:60]}...", flush=True)
    print(f"📊 Dirección: {direction} | Posición: ${position:.2f} USDC", flush=True)
    print(f"⚙️  Modo: {'DRY RUN' if DRY_RUN else 'LIVE'}", flush=True)

    try:
        if DRY_RUN:
            result = execute_order_dry(params)
        else:
            result = execute_order_live(params)

        status_emoji = "🧪" if DRY_RUN else "✅"
        lines = [f"# ⚡ EXECUTOR — {mode}\n"]
        lines.append(f"**{question}**\n")
        lines.append(f"| Campo | Valor |")
        lines.append(f"|---|---|")
        lines.append(f"| Estado | {status_emoji} {result['status']} |")
        lines.append(f"| Dirección | **{result['direction']}** |")
        lines.append(f"| Precio entrada | {result['entry_price']:.0%} |")
        lines.append(f"| USDC gastado | ${result['usdc_spent']:.2f} |")
        lines.append(f"| Order ID | `{result.get('order_id', 'N/A')}` |")
        lines.append("")

        if DRY_RUN:
            lines.append("> ⚠️ **Modo DRY RUN** — Ninguna orden real fue enviada.")
            lines.append("> Para activar trading real: `TRADING_DRY_RUN=false` en Railway.")

        output_json = {**result, "question": question, "params": params}
        lines.append("\n```json")
        lines.append(json.dumps(output_json, indent=2, ensure_ascii=False))
        lines.append("```")

        post_issue_result("\n".join(lines))

    except Exception as e:
        error_msg = f"❌ Executor error: {e}"
        print(error_msg, file=sys.stderr)
        post_issue_result(error_msg)
        sys.exit(1)


if __name__ == "__main__":
    main()
