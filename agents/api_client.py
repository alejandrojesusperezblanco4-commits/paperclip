"""
Módulo compartido: cliente de OpenRouter con retry y fallback de modelos.
"""
import json
import time
import urllib.request
import urllib.error

# Modelos paid — baratos y rápidos. Fallback cascada.
# Costos aproximados (input/output por 1M tokens):
#   gemini-2.0-flash-001 ........ $0.10 / $0.40   (el más barato y rápido)
#   gpt-4o-mini ................. $0.15 / $0.60
#   claude-haiku-4-5 ............ $1.00 / $5.00   (mejor calidad, síntesis)
FREE_MODELS = [
    "google/gemini-2.0-flash-001",
    "openai/gpt-4o-mini",
    "anthropic/claude-3-5-haiku",
]

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def call_llm(
    messages: list,
    api_key: str,
    max_tokens: int = 1500,
    temperature: float = 0.7,
    title: str = "Paperclip Agent",
    timeout: int = 60,
    retries: int = 1,
    model: str = None,
) -> str:
    """
    Llama a OpenRouter con retry automático y fallback de modelos.
    Si se pasa `model`, lo usa como primera opción antes de la cascada.
    Devuelve el texto generado o lanza Exception con el error detallado.
    """
    last_error = None
    models_to_try = [model] + FREE_MODELS if model else FREE_MODELS

    for attempt, model_name in enumerate(models_to_try):
        if attempt >= retries + 1:
            break
        model = model_name  # compat con el resto de la función
        try:
            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                OPENROUTER_URL,
                data=data,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "http://127.0.0.1:7777",
                    "X-Title": title,
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw = response.read().decode("utf-8")

            try:
                result = json.loads(raw)
            except json.JSONDecodeError as e:
                raise Exception(f"Respuesta no es JSON ({e}): {raw[:300]}")

            # Verificar errores dentro del JSON
            if "error" in result:
                err = result["error"]
                code = err.get("code", "") if isinstance(err, dict) else str(err)
                msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                # Rate limit → esperar y reintentar
                if code in (429, "429") or "rate" in str(msg).lower():
                    print(f"⚠️  Rate limit en {model}, esperando 10s...", flush=True)
                    time.sleep(10)
                    last_error = Exception(f"Rate limit: {msg}")
                    continue
                raise Exception(f"Error API ({code}): {msg}")

            choices = result.get("choices", [])
            if not choices:
                raise Exception(f"Sin choices en respuesta: {raw[:300]}")

            return choices[0]["message"]["content"]

        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")[:300]
            except Exception:
                pass
            last_error = Exception(f"HTTP {e.code} en {model}: {body}")
            if e.code == 429:
                print(f"⚠️  Rate limit HTTP en {model}, esperando 10s...", flush=True)
                time.sleep(10)
                continue
            # Para otros errores HTTP, prueba siguiente modelo
            print(f"⚠️  HTTP {e.code} con {model}, probando siguiente modelo...", flush=True)
            continue

        except Exception as e:
            last_error = e
            print(f"⚠️  Error con {model}: {e} — probando siguiente modelo...", flush=True)
            time.sleep(3)
            continue

    raise last_error or Exception("Todos los modelos fallaron")
