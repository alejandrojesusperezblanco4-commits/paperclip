"""
Agente: Reporter (Polymarket)
Reporta el resultado de un trade a Telegram y lo registra en SQLite.

Variables de entorno:
  TELEGRAM_BOT_TOKEN → token del bot de Telegram
  TELEGRAM_CHAT_ID   → ID del chat/canal destino
  TRADING_DB_PATH    → path al archivo SQLite (default: /app/data/trades.db)

Input (JSON del Executor):
{
  "status":      "simulated|placed",
  "dry_run":     true,
  "direction":   "BUY_YES",
  "entry_price": 0.54,
  "usdc_spent":  12.50,
  "order_id":    "...",
  "question":    "..."
}
"""
import os
import sys
import json
import re
import sqlite3
import urllib.request
import urllib.parse
from datetime import datetime, timezone
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from api_client import post_issue_result, post_issue_comment, resolve_issue_context

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT  = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
DB_PATH        = os.environ.get("TRADING_DB_PATH", "/app/data/trades.db")


def init_db():
    """Crea la tabla de trades si no existe."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT NOT NULL,
            question    TEXT,
            direction   TEXT,
            entry_price REAL,
            usdc_spent  REAL,
            order_id    TEXT,
            dry_run     INTEGER,
            status      TEXT,
            raw_json    TEXT
        )
    """)
    conn.commit()
    return conn


def log_trade(conn, trade: dict):
    """Registra un trade en SQLite."""
    conn.execute("""
        INSERT INTO trades (ts, question, direction, entry_price, usdc_spent, order_id, dry_run, status, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now(timezone.utc).isoformat(),
        trade.get("question", ""),
        trade.get("direction", ""),
        trade.get("entry_price", 0),
        trade.get("usdc_spent", 0),
        trade.get("order_id", ""),
        1 if trade.get("dry_run", True) else 0,
        trade.get("status", ""),
        json.dumps(trade),
    ))
    conn.commit()


def send_telegram(message: str) -> bool:
    """Envía mensaje a Telegram."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        print("  ⚠️  TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no configurados", flush=True)
        return False
    url     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id":    TELEGRAM_CHAT,
        "text":       message,
        "parse_mode": "HTML",
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status == 200
    except Exception as e:
        print(f"  ⚠️  Telegram error: {e}", flush=True)
        return False


def format_telegram_message(trade: dict) -> str:
    """Formatea el mensaje de Telegram."""
    dry_tag   = "🧪 <b>DRY RUN</b> | " if trade.get("dry_run") else "🔴 <b>LIVE</b> | "
    direction = trade.get("direction", "")
    emoji     = "🟢" if direction == "BUY_YES" else "🔴"
    price_pct = f"{trade.get('entry_price', 0):.0%}"
    usdc      = f"${trade.get('usdc_spent', 0):.2f}"
    question  = trade.get("question", "")[:100]
    order_id  = trade.get("order_id", "N/A")

    return (
        f"{dry_tag}{emoji} <b>Polymarket Trade</b>\n"
        f"📋 {question}\n"
        f"📊 {direction} @ {price_pct} — {usdc} USDC\n"
        f"🆔 Order: <code>{order_id}</code>\n"
        f"⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )


def extract_params(raw: str) -> dict:
    json_str = None
    if "```json" in raw:
        json_str = raw.split("```json")[1].split("```")[0].strip()
    elif raw.strip().startswith("{"):
        json_str = raw.strip()
    else:
        m = re.search(r'\{[\s\S]*?"status"[\s\S]*?\}', raw)
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

    post_issue_comment("📣 Reporter registrando trade...")

    trade = extract_params(raw)
    if not trade:
        post_issue_result("❌ Reporter: No se pudo leer el trade del Executor.")
        sys.exit(1)

    # 1. Log en SQLite
    try:
        conn = init_db()
        log_trade(conn, trade)
        conn.close()
        print("✅ Trade registrado en SQLite", flush=True)
    except Exception as e:
        print(f"⚠️  SQLite error: {e}", flush=True)

    # 2. Enviar a Telegram
    msg     = format_telegram_message(trade)
    tg_sent = send_telegram(msg)
    if tg_sent:
        print("✅ Telegram notificado", flush=True)

    # 3. Output a Paperclip
    dry_label = "🧪 Simulado" if trade.get("dry_run") else "✅ Ejecutado"
    lines = [f"# 📣 REPORTER — Trade {dry_label}\n"]
    lines.append(f"**{trade.get('question', '')}**\n")
    lines.append(f"| Campo | Valor |")
    lines.append(f"|---|---|")
    lines.append(f"| Estado | {dry_label} |")
    lines.append(f"| Dirección | {trade.get('direction', '')} |")
    lines.append(f"| Precio | {trade.get('entry_price', 0):.0%} |")
    lines.append(f"| USDC | ${trade.get('usdc_spent', 0):.2f} |")
    lines.append(f"| Order ID | `{trade.get('order_id', 'N/A')}` |")
    lines.append(f"| SQLite | ✅ |")
    lines.append(f"| Telegram | {'✅' if tg_sent else '⚠️ No configurado'} |")

    post_issue_result("\n".join(lines))


if __name__ == "__main__":
    main()
