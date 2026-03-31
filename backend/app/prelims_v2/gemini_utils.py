"""
gemini_utils.py — Helpers for creating specialised GeminiClient instances
inside the prelims_v2 pipeline.
"""
from __future__ import annotations

from app.gemini_core.gemini_client import GeminiClient

# Blueprint generation uses Flash — fast, cheap, deterministic structured output
FLASH_MODEL = "gemini-2.0-flash"


def make_flash_client(base_client: GeminiClient) -> GeminiClient:
    """
    Return a GeminiClient wired to Gemini Flash, reusing
    the same API key and timeout as the base client.

    If base_client is already Flash, return it directly.
    """
    if base_client.model_name == FLASH_MODEL:
        return base_client

    return GeminiClient(
        api_key=base_client.api_key,
        model_name=FLASH_MODEL,
        timeout=base_client.timeout,
    )
