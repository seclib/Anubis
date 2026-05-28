
from typing import Optional

import requests

from config import OLLAMA_BASE_URL, OLLAMA_MODEL

OLLAMA_URL = f"{OLLAMA_BASE_URL.rstrip('/')}/api/generate"
DEFAULT_MODEL = OLLAMA_MODEL
FALLBACK_MODEL = "llama3"
MAX_RETRIES = 2
TIMEOUT = 15

def call_llm(prompt: str, model: str = DEFAULT_MODEL) -> str:
	payload = {"model": model, "prompt": prompt, "stream": False}
	last_err: Optional[Exception] = None

	for attempt in range(MAX_RETRIES + 1):
		try:
			resp = requests.post(OLLAMA_URL, json=payload, timeout=TIMEOUT)
			resp.raise_for_status()
			data = resp.json()
			# Try common response keys
			for key in ("response", "text", "output", "result", "generated_text"):
				if key in data:
					val = data[key]
					return val if isinstance(val, str) else str(val)
			# Try choices
			choices = data.get("choices")
			if isinstance(choices, list) and choices:
				first = choices[0]
				if isinstance(first, dict):
					for k in ("text", "message", "content"):
						if k in first:
							v = first[k]
							return v if isinstance(v, str) else str(v)
					return str(first)
			return str(data)
		except Exception as e:
			last_err = e
			if attempt == 0:
				continue  # retry once
			elif attempt == 1 and model != FALLBACK_MODEL:
				# Try fallback model
				payload["model"] = FALLBACK_MODEL
				continue
			else:
				break
	return f"[LLM ERROR] {last_err}"
