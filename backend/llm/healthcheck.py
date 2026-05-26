from __future__ import annotations

import json
import logging
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from backend.core.config import get_settings
from backend.llm.providers import create_llm_provider

logger = logging.getLogger(__name__)


def _safe_models_probe(base_url: str, timeout_seconds: float = 2.5) -> tuple[bool, list[str], str | None]:
	models_url = f"{base_url.rstrip('/')}/models"
	try:
		with urlopen(models_url, timeout=timeout_seconds) as response:  # nosec B310 - startup health probe for configured local endpoint
			payload = json.loads(response.read().decode("utf-8"))
			models = [item.get("id", "") for item in payload.get("data", []) if isinstance(item, dict)]
			return True, [m for m in models if m], None
	except URLError as exc:
		return False, [], str(exc)
	except Exception as exc:  # pragma: no cover - defensive fallback
		return False, [], str(exc)


def run_startup_llm_healthcheck() -> dict[str, Any]:
	settings = get_settings()
	provider_name = (settings.llm_provider or "qwen").lower()
	result: dict[str, Any] = {
		"provider": provider_name,
		"model": settings.llm_model,
		"base_url": settings.llm_base_url,
		"ready": False,
		"warnings": [],
	}

	try:
		create_llm_provider(provider_name)
	except Exception as exc:
		warning = f"Cannot initialize LLM provider '{provider_name}': {exc}"
		result["warnings"].append(warning)
		logger.warning("LLM startup health-check failed: %s", warning)
		return result

	if provider_name in {"qwen", "openai"}:
		if settings.llm_base_url:
			ok, discovered_models, error = _safe_models_probe(settings.llm_base_url)
			result["endpoint_reachable"] = ok
			result["discovered_models"] = discovered_models
			if not ok:
				result["warnings"].append(f"LLM endpoint unreachable at {settings.llm_base_url}: {error}")
			elif discovered_models and settings.llm_model not in discovered_models:
				result["warnings"].append(
					f"Configured model '{settings.llm_model}' was not listed by endpoint. "
					f"Available models: {discovered_models}"
				)
			result["ready"] = ok and not result["warnings"]
		else:
			if provider_name == "qwen":
				result["warnings"].append("LLM_BASE_URL is not set for qwen provider.")
			if not settings.openai_api_key:
				result["warnings"].append("OPENAI_API_KEY is not set.")
			result["ready"] = not result["warnings"]
	elif provider_name == "anthropic":
		if not settings.anthropic_api_key:
			result["warnings"].append("ANTHROPIC_API_KEY is not set.")
		result["ready"] = not result["warnings"]
	else:
		result["warnings"].append(f"Unsupported provider '{provider_name}'.")
		result["ready"] = False

	if result["ready"]:
		logger.info(
			"LLM startup health-check OK (provider=%s, model=%s, base_url=%s)",
			provider_name,
			settings.llm_model,
			settings.llm_base_url,
		)
	else:
		logger.warning(
			"LLM startup health-check has warnings (provider=%s, model=%s, warnings=%s)",
			provider_name,
			settings.llm_model,
			result["warnings"],
		)

	return result
