---
name: diskontrol-ecosystem
description: >
  Ecosistema completo de Diskontrol — 4 empresas en Paperclip sobre Railway.
  Úsala cuando trabajes con DiscontrolsBags (trading), DiscontrolDrops (dropshipping),
  DiscontrolGrowth (captación de clientes), o la infraestructura compartida.
  Cubre: arquitectura, IDs de agentes, APIs, patrones de código, estado actual y pendientes.
---

# Diskontrol Ecosystem — Guía completa

## Infraestructura

```
Railway (servidor único — spirited-charm-production.up.railway.app)
├── Paperclip server (Node.js + PostgreSQL)
├── Python agents (todos los pipelines)
├── Studio UI (frontend/index.html — SPA)
└── Express endpoints internos (/api/internal/*)

Supabase (content pipeline DB)
  → videos, trends, channels tables
  → URL: https://nuaajypknpjbsyhssclm.supabase.co
  → Usar SUPABASE_KEY (secret, no publishable)

GitHub: alejandrojesusperezblanco4-commits/paperclip
  → push a master → Railway autodeploy (~2-3 min)
```

---

## Las 4 empresas en Paperclip

| Empresa | Slug URL | CompanyID | Estado |
|---|---|---|---|
| Discontrol Historys (Studio) | AUTA | 4d39bc9c-a76c-4558-a3b0-2a3267124dc0 | ✅ Producción |
| DiscontrolsBags (Trading) | DIS | 866b74e7-79a7-4166-9f9f-025faa751aa1 | 🔧 DRY_RUN |
| DiscontrolDrops (Dropshipping) | DISA | 0b4751e7-24e7-4e8b-98e0-5b5ed73b6d7c | ✅ Funcional |
| DiscontrolGrowth (Ventas) | DISAA | 14a23847-5215-44fc-8b2d-c45e25d3f291 | 🔧 Parcial |

---

## DiscontrolDrops — Pipeline completo

### Agentes y sus IDs

```python
CEO_AGENT_ID             = "60dd4b7a-4ec3-4555-8e52-807ffcf15a7b"
PRODUCT_HUNTER_AGENT_ID  = "01a671f6-a303-4f74-90e2-914c63a2e34d"
AD_SPY_AGENT_ID          = "9d3649ad-b902-495a-8330-8048d94ac20d"
LEAD_QUALIFIER_AGENT_ID  = "fbf55d11-03cb-4d88-9132-7a04a9091d8c"
WEB_DESIGNER_AGENT_ID    = "e39f154b-0415-42f2-bd60-b79f66ecaca7"
MARKETING_CREATOR_AGENT_ID = "f6fb0f5a-ea32-4a29-aac1-95e7c3db6335"
DROPS_COMPANY            = "0b4751e7-24e7-4e8b-98e0-5b5ed73b6d7c"
DROPS_PROJECT_ONBOARDING = "7bd04480-4dec-4a12-973f-5a6dd0784bee"
```

### Flujo CEO (agents/drops/ceo.py)

```
Issue al CEO: "nicho del producto"
    ↓
1. Product Hunter → Amazon BS + Google Trends + LLM → 10 productos
   (combined_json slim ~200 chars/producto para caber en 4000 chars)
    ↓
2. Ad Spy → Google Trends + YouTube + Google Shopping → evidence_score
    ↓
3. Lead Qualifier → score 0-100 LAUNCH/TEST/SKIP (max_tokens=4000, timeout=90s)
    ↓
4. Web Designer → estructura copy + HTML preview en Railway + preview URL
    ↓
5. Marketing Creator → 3 ads + 2 TikTok scripts + emails
```

### Problemas críticos resueltos

1. **HTTP 500 en create_sub_issue** → causa: `run_id` ficticio violaba FK en `activity_log.run_id → heartbeat_runs`. Fix: usar `PAPERCLIP_RUN_ID` de env vars.

2. **Sub-issues en backlog sin despertar** → causa: `queueIssueAssignmentWakeup` hace return si `status==="backlog"`. Fix: crear sub-issues con `status: "todo"`.

3. **Lead Qualifier "No se encontraron productos"** → causa: combined_json >4000 chars truncaba el JSON. Fix: slim products a campos esenciales + description limit 8000.

4. **JSONDecodeError en Lead Qualifier** → causa: max_tokens=2000 cortaba el JSON a mitad. Fix: max_tokens=4000.

5. **Web Designer sin datos de producto** → causa: CEO pasaba markdown completo pero `extract_top_product` solo buscaba ` ```json ` blocks. Fix: manejo de JSON crudo + extracción por regex del markdown.

6. **Preview URL con localhost** → causa: `PAPERCLIP_API_URL` apunta a interno. Fix: hardcode Railway URL en web_designer.py.

### CEO lee comentarios correctamente

```python
# Toma el comentario más reciente con >200 chars (evita el progress comment corto)
result_comments = [c for c in items if len(c.get("body", "") or "") > 200]
best = result_comments[0] if result_comments else max(items, key=lambda c: len(...))
```

### Preview endpoint en servidor

```
POST /preview  → acepta HTML crudo, almacena en memoria, devuelve {id, url}
GET  /preview/:id → sirve el HTML
Auto-cleanup: 24h
URL siempre: https://spirited-charm-production.up.railway.app/preview/{id}
```

### Ad Spy — 3 fuentes (Amazon bloqueado con 503)

```python
# Fuentes activas:
check_google_trends(keyword, geo="ES")    # RSS público
check_youtube(keyword)                     # scraping búsqueda YT
check_google_shopping(keyword)             # scraping Google Shopping ES

# Scoring:
# YouTube: 35-50pts | Google Trends: 25pts | Shopping: 20-25pts
# Validado: score >= 40
```

---

## DiscontrolsBags — Trading Polymarket

### Agentes y sus IDs

```python
CEO_AGENT_ID             = "41df12d7-71c4-494e-a503-d02ef88fb1d8"
MARKET_SCANNER_AGENT_ID  = "6f75364c-0ab2-48ac-9144-f40578435d67"
PROBABILITY_ESTIMATOR_ID = "ff3e3f5f-118f-451d-b042-91ec19d0cf11"
RISK_MANAGER_AGENT_ID    = "149be654-dccb-4da3-a6c6-091c5b5fe1e6"
EXECUTOR_AGENT_ID        = "61ced466-af5b-43be-a049-e94cf895274a"
REPORTER_AGENT_ID        = "74bc12a4-6928-4450-b472-2962c3516627"
TRADING_COMPANY          = "866b74e7-79a7-4166-9f9f-025faa751aa1"
```

### Variables de entorno necesarias (Railway)

```
TRADING_DRY_RUN=true          # NUNCA cambiar a false sin validar 2 semanas
TRADING_BANKROLL_USDC=200
TELEGRAM_BOT_TOKEN=...        # pendiente configurar
TELEGRAM_CHAT_ID=...          # pendiente configurar
POLYGON_PRIVATE_KEY=...       # para trading real (futuro)
POLYMARKET_API_KEY=...        # para trading real (futuro)
```

### Estado actual

- ✅ Agentes creados en Paperclip
- ✅ Market Scanner funcional (filtra solo crypto, min $5k volumen)
- ⚠️ CEO tiene bug run_id (mismo fix que Drops — pendiente aplicar)
- ⚠️ Telegram no configurado
- ⚠️ TikTok Research API — 401 (app en revisión de TikTok)

### Fix pendiente en CEO de Bags

El CEO debe usar `PAPERCLIP_RUN_ID` del env var, igual que el CEO de Drops. Sin esto el create_sub_issue dará HTTP 500 por FK violation en activity_log.

---

## DiscontrolGrowth — Captación de clientes

### Agentes y sus IDs

```python
CEO_GROWTH_AGENT_ID          = "8a58fe92-6799-42e0-81e0-d3f234dbf5cc"
LEAD_SCOUT_AGENT_ID          = "90288f23-a593-4876-82a6-56f9b4448ac7"
LEAD_QUALIFIER_AGENT_ID      = "6403595f-6850-43c5-9f35-bba0a3e6a4e6"
OUTREACH_WRITER_AGENT_ID     = "77839380-ef3a-4f02-aa7f-6ef5e0e42b09"
SENDER_AGENT_ID              = "bc1948d9-53d9-4fc2-aafb-bfadc009332a"
TRACKER_AGENT_ID             = "6fcc7a88-4b5a-4a0e-bcc3-3489e7c8a90b"
GROWTH_COMPANY               = "14a23847-5215-44fc-8b2d-c45e25d3f291"
```

### Variables de entorno necesarias

```
GOOGLE_MAPS_API_KEY=AIzaSyAa_fXcTAiTBhCwE2lCjb32Fgwbd60waqo
```

### Estado actual

- ✅ Lead Scout funcional (Google Maps Places API, busca por ciudad+tipo)
- ✅ Lead Qualifier funcional (scoring LLM)
- ✅ Outreach Writer funcional (email/WhatsApp/Instagram DM)
- ❌ Sender — esqueleto, pendiente implementar
- ❌ Tracker — esqueleto, pendiente implementar
- ⚠️ CEO tiene mismo bug run_id (pendiente fix)

---

## Endpoints internos del servidor (app.ts)

```
GET /api/internal/seed-drops-agents?secret=<16chars>
GET /api/internal/seed-trading-agents?secret=<16chars>
GET /api/internal/seed-growth-agents?secret=<16chars>
GET /api/internal/seed-agents?secret=<16chars>          ← Discontrol Historys
GET /api/internal/list-companies?secret=<16chars>
GET /api/internal/list-projects?secret=<16chars>&companyId=...
GET /api/internal/list-recent-issues?secret=<16chars>&companyId=...
GET /api/internal/read-issue-comments?secret=<16chars>&issueId=...
GET /api/internal/test-issue-tx?secret=<16chars>&companyId=...
GET /api/internal/fix-agent-timeout?id=<agentId>&timeoutSec=1800

POST /preview       → almacena HTML, devuelve {id, url}
GET  /preview/:id   → sirve el HTML
GET  /terms         → ToS para TikTok app review
GET  /privacy       → Privacy Policy para TikTok app review
GET  /sounds/:file  → sirve success.m4a / error.m4a
```

### Secreto para endpoints internos

```python
secret = BETTER_AUTH_SECRET[:16]  # primeros 16 chars
```

---

## Patrón JWT para CEOs de nuevas empresas

```python
# CRÍTICO: usar PAPERCLIP_RUN_ID del env var (no inventar un run_id)
# activity_log.run_id tiene FK → heartbeat_runs.id
# Un run_id ficticio viola el constraint y da HTTP 500

def make_jwt(agent_id, company_id, run_id, secret):
    payload = {
        "sub": agent_id,
        "company_id": company_id,
        "adapter_type": "process",
        "run_id": run_id,  # ← debe ser PAPERCLIP_RUN_ID real
        ...
    }
```

---

## APIs externas activas

| Servicio | Variable | Uso | Estado |
|---|---|---|---|
| OpenRouter | OPENROUTER_API_KEY | LLM (Haiku/Sonnet/Perplexity) | ✅ |
| Higgsfield | HIGGSFIELD_API_KEY | Popcorn + DoP Lite | ✅ |
| ElevenLabs | ELEVENLABS_API_KEY | TTS narración | ✅ |
| YouTube Data API | YOUTUBE_API_KEY_DEEP_SEARCH | Trends + canal stats | ✅ (3 keys) |
| YouTube Data API | YOUTUBE_API_KEY_CHANNEL_ANALYZER | Canal analysis | ✅ |
| YouTube Data API | YOUTUBE_API_KEY_DIRECTOR | Viral titles | ✅ |
| Google Maps | GOOGLE_MAPS_API_KEY | Lead Scout | ✅ |
| TikTok Content | TIKTOK_CLIENT_KEY / SECRET | Auto-publisher | ⏳ App review |
| TikTok Research | TIKTOK_RESEARCH_CLIENT_KEY | Video data | ⏳ Pendiente |
| Supabase | SUPABASE_URL / KEY | Content DB | ✅ |

---

## Studio UI — DiscontrolCreator

- `frontend/index.html` — SPA completa
- Galería carga desde Supabase al abrir (últimos 30 videos)
- Sonidos custom: `/sounds/success.m4a` y `/sounds/error.m4a`
- Preview URL siempre pública Railway (no localhost)
- Fuentes: Barlow + Barlow Condensed + DM Mono
- Agentes en grid 2×5 con iconos grandes

---

## Equipo

```
Alejandro     → Director técnico + content pipeline + infraestructura
Amigo 1       → DiscontrolsBags (trading) — empieza con Market Scanner
Amigo 2       → DiscontrolGrowth (ventas) — empieza con Sender agent
```

PDF de onboarding: C:\Users\Alejandro\Downloads\Diskontrol_Team_Guide.pdf

---

## Pendientes prioritarios

```
🔴 Fix run_id en CEO de Bags y Growth (mismo fix que Drops)
🟡 Sender agent (Growth) — para completar pipeline de captación
🟡 Telegram (Bags) — para alertas de trading
🟡 Shopify integration (Drops) — publicar productos directamente
🟢 TikTok OAuth — activar auto-publisher de videos
🟢 Galería Studio conectada a Supabase (implementada, verificar)
```
