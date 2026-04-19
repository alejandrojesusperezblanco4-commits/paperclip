---
name: content-pipeline
description: >
  Pipeline de generación de contenido viral de Paperclip (historias.en.sombra).
  Úsala cuando trabajes con los agentes Python, el frontend Studio, el Director,
  o cualquier integración con Higgsfield / ElevenLabs / OpenRouter.
  Cubre: arquitectura del pipeline, archivos clave, APIs, patrones de código,
  despliegue en Railway, y el Studio frontend.
---

# Content Pipeline — Paperclip (historias.en.sombra)

Proyecto de generación automática de videos virales para TikTok/YouTube.
El Director orquesta agentes especializados que producen guión, imágenes, clips y video final.

---

## 1. Arquitectura del pipeline

```
Usuario (Studio) → Director → Deep Search
                            → Channel Analyzer
                            → Storytelling
                            → [LLM elige soul_style + dop_motion basado en tendencias]
                            → TTS (ElevenLabs)           ← solo si ELEVENLABS_API_KEY
                            → Prompt Generator
                            → Popcorn Auto (Higgsfield)  ← 5 imágenes coherentes
                            → Imagen Video (DoP Turbo)   ← N-1 clips first-last-frame
                            → Video Assembler (FFmpeg)   ← MP4 final 9:16
```

**Agentes individuales** (desde Studio, sin Director):
- `imagen.py` → genera imágenes con Soul API (soul_style text field)
- `imagen_video.py` → genera clips con DoP Turbo First-Last Frame
- `popcorn.py` → genera set de imágenes coherentes con Popcorn Auto
- `tts.py` → narración con ElevenLabs
- `video_assembler.py` → ensambla MP4 con FFmpeg

---

## 2. Archivos clave

```
agents/
  director.py          # Orquestador principal — LEE SIEMPRE antes de modificar
  imagen.py            # Soul API (texto → imagen) — campo: soul_style (texto, no UUID)
  imagen_video.py      # DoP Turbo First-Last Frame — campo: dop_motion (texto)
  popcorn.py           # Popcorn Auto — 1 prompt → N imágenes coherentes
  video_assembler.py   # FFmpeg — ensambla clips + audio
  tts.py               # ElevenLabs TTS
  api_client.py        # Helpers: post_issue_result, post_issue_comment, post_parent_update

frontend/
  index.html           # Studio UI — SPA completa en un solo archivo HTML+JS+CSS
```

---

## 3. Variables de entorno requeridas

| Variable | Uso |
|---|---|
| `OPENROUTER_API_KEY` | LLM calls (Claude Haiku/Sonnet via OpenRouter) |
| `HIGGSFIELD_API_KEY` | Formato `<key_id>:<key_secret>` para Soul v1; o solo `<key>` para Popcorn/DoP |
| `ELEVENLABS_API_KEY` | TTS narración |
| `PAPERCLIP_API_KEY` | Auth Paperclip API |
| `PAPERCLIP_API_URL` | URL de la API (ej: `https://...railway.app`) |
| `PAPERCLIP_COMPANY_ID` | ID de la empresa en Paperclip |

---

## 4. APIs de Higgsfield

### Soul (texto → imagen)
- **Endpoint v1**: `POST https://platform.higgsfield.ai/v1/text2image/soul`
- **Auth**: headers `hf-api-key: <uuid>` + `hf-secret: <secret>`
- **Campo estilo**: `soul_style` (nombre texto, ej: "Cinematic") — NO usar UUID
- **Campo tamaño**: `width_and_height` (ej: "1152x2048" para 9:16)
- **Dentro de**: `{ "params": { ... } }`
- **Fallback legacy**: `POST /soul` con `Authorization: Key <key>`

### Popcorn Auto (prompt → N imágenes coherentes)
- **Endpoint**: `POST https://platform.higgsfield.ai/higgsfield-ai/popcorn/auto`
- **Auth**: `Authorization: Key <api_key>`
- **Payload**: `{ prompt, aspect_ratio, num_images (1-8), resolution, image_urls, seed }`
- **Poll**: `GET /requests/{id}/status` → `status == "completed"` → `images[].url`

### DoP Turbo First-Last Frame (2 imágenes → clip)
- **Endpoint**: `POST https://platform.higgsfield.ai/higgsfield-ai/dop/turbo/first-last-frame`
- **Auth**: `Authorization: Key <api_key>`
- **Payload**: `{ image_url, end_image_url, prompt, motions: ["Dolly In"], enhance_prompt, seed }`
- **Poll**: `GET /requests/{id}/status` → `status == "completed"` → `video.url`
- **Patrón**: N imágenes → N-1 clips (pares consecutivos)

### Motions DoP (121 disponibles, todos compatibles con first-last-frame)
Categorías principales:
- **Cámara**: Dolly In/Out, Arc Left/Right, Crane Up/Down, Crash Zoom In/Out, Whip Pan, FPV Drone, Snorricam, Super Dolly In/Out, Tilt Up/Down, Zoom In/Out, YoYo Zoom, Overhead, Hyperlapse
- **Efectos**: Focus Change, Glitch, VHS, Datamosh, Lens Flare, Glowshift, Paparazzi, Fisheye, Static
- **Personaje**: Catwalk, Levitation, Agent Reveal, Soul Jump, Moonwalk, Boxing, Flying
- **Transformación**: Freezing, Melting, Head Explosion, Disintegration, Morphskin, Thunder God
- **Explosiones**: Fire Breathe, Sand Storm, Powder Explosion, Bullet Time, Car Explosion
- **Criaturas**: Timelapse Landscape, Jelly Drift, Floating Fish

### Soul Styles (106 disponibles, campo `soul_style` = nombre texto)
Categorías: Retratos/Makeup, Moda/Editorial, Y2K/Retro, Cámara/Efecto visual,
Escenarios/Localizaciones, Surreal/Fantasy/Arte, Lifestyle/Mood, General.
Ejemplos: "Spotlight", "90's Editorial", "Y2K", "Rainy Day", "Realistic", "Glitch", "Artwork", "General"

---

## 5. Patrones de código importantes

### Comunicación Director → Studio (async)
```python
# En api_client.py — notificar Studio con resultado de agente asíncrono
marker = f"AGENT_UPDATE_START:{agent_name}:\n{output[:9500]}"
# Se postea como comentario en el issue PADRE
```

### PARENT_ISSUE_ID (agentes asíncronos)
```python
# Director inyecta en la descripción del sub-issue:
_desc = f"PARENT_ISSUE_ID:{issue_id}\n{task}"

# El agente lo extrae así:
_parent_match = re.search(r'PARENT_ISSUE_ID:([^\n\s>]+)', raw)
os.environ['PAPERCLIP_PARENT_ISSUE_ID'] = _parent_match.group(1)
```

### ASSEMBLER_PARAMS (Director → Imagen Video → Video Assembler)
```python
# Director embeds in imagen_video task:
_iv_task = f"ASSEMBLER_PARAMS:{json.dumps(_asm_params)}\n\n{_iv_input}"

# imagen_video.py extrae y lanza video_assembler como proceso detachado:
proc = subprocess.Popen([sys.executable, script], stdin=PIPE, start_new_session=True, env=env)
```

### Inteligencia de estilo (Director, Fase 3b)
Después de Deep Search + Storytelling, el Director llama al LLM (Haiku) para elegir:
- `soul_style`: qué estilo visual encaja con el nicho
- `dop_motion`: qué movimiento de cámara encaja con el tono

El `dop_motion` elegido se inyecta en el JSON de imagen_video:
```json
{ "image_urls": [...], "source": "popcorn_auto", "dop_motion": "Crash Zoom In" }
```

### Input desde Studio (imagen.py)
Studio envía `{"soul_style": "X", "soul_style_strength": 1.0, "prompt": "tema"}`.
`extract_prompts()` maneja: `scene_prompts[]` (del Prompt Generator) > `prompt` (de Studio) > fallback texto.

---

## 6. Studio frontend (frontend/index.html)

SPA en un único archivo HTML. Agentes registrados en `AGENTS = { key: config }`.

### Selectores visuales
- **🎨 Estilo Soul** (`#soulStyleSection`): visible solo para agente `imagen`. Dropdown con 106 estilos en 8 optgroups. Valor enviado como `soul_style` en JSON.
- **🎬 Motion DoP** (`#dopMotionSection`): visible solo para agente `imagen_video`. Dropdown con 121 motions en 7 optgroups. Default: "Auto (arco narrativo)". Valor enviado como `dop_motion` en JSON.

### Polling de resultados async
```javascript
// Cada 8s, busca marcadores AGENT_UPDATE_START en comentarios del issue padre
regex: /AGENT_UPDATE_START:(\w+):\n?([\s\S]*)/
// Fetch: GET /api/issues/{id}/comments?limit=100
```

### IDs de agentes Paperclip
```javascript
director:      'director-agent-id'
imagen:        '2492962a-b9f0-4611-90e2-c7ccca5aa281'
imagen_video:  '62e14c73-905b-45ce-b4d9-4cd532ec3dca'
tts:           '0d43b313-77b5-481b-83cc-a41485823f8e'
video:         '28f0a4aa-a230-4d82-aedf-4c327ab4a506'
```

---

## 7. Despliegue

```bash
# Siempre en: C:\Users\Alejandro\paperclip
git add <archivos>
git commit -m "descripción"
git push  # Railway redeploy automático en ~2-3 min
```

URL producción: `https://spirited-charm-production.up.railway.app/studio`

**Agentes que NO necesitan commit** (corren como subprocess en Railway):
- `popcorn.py`, `imagen_video.py`, `video_assembler.py`, `tts.py`
  → Se llaman desde `director.py` que sí corre en Railway.

---

## 8. Problemas comunes y soluciones

| Problema | Causa | Solución |
|---|---|---|
| Studio no muestra clips/video | Marcador `AGENT_UPDATE_START` no llega | Verificar `post_parent_update` en api_client.py |
| Imagen Generator falla desde Studio | Input JSON sin `scene_prompts` | `extract_prompts` lee campo `prompt` directo |
| Video Assembler usa fotos fijas | Lanza antes de que imagen_video termine | imagen_video lanza assembler internamente con `start_new_session=True` |
| HTTP 409 en sub-issue | Dos procesos intentan cerrar el mismo issue | Usar `paperclip_timeout=0` (fire-and-forget) para agentes asíncronos |
| Soul API devuelve error | HIGGSFIELD_API_KEY no es `uuid:secret` | Verificar formato; imagen.py usa `parse_api_key()` para dividirlo |
| Popcorn falla auth | Key en formato incorrecto | Popcorn usa `Authorization: Key {api_key}` tal cual |

---

## 9. Últimas features implementadas

- **Popcorn Auto** reemplaza Soul en el Director (imágenes coherentes de una sola llamada)
- **DoP Turbo First-Last Frame**: N imágenes → N-1 clips cinematográficos en cadena
- **Arco narrativo automático**: motions se eligen según posición del clip (apertura→tensión→resolución)
- **Inteligencia del Director**: LLM elige `soul_style` y `dop_motion` basándose en tendencias de Deep Search
- **Studio selectores**: 106 Soul Styles + 121 DoP Motions en dropdowns con optgroups por categoría
- **Marcadores texto plano**: `AGENT_UPDATE_START:name:` (los HTML comments eran sanitizados por la API)
