"""Thin OpenAI-compatible client: chat, vision, and code extraction.

Everything about the endpoint comes from the environment, as the challenge
requires (`OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL`). No key is ever
read from a file in the image.

`openai` is imported lazily so the deterministic half of the pipeline (build,
measure, render, compare) runs on a machine without the SDK installed -- which is
exactly how the pipeline is developed.
"""

from __future__ import annotations

import base64
import io
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

CODE_BLOCK_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)

# Downscale before sending. A 1024 px render is far more pixel budget than the
# model needs to read a silhouette, and image tokens are the dominant cost when
# eight views go out with every attempt.
DEFAULT_IMAGE_MAX_SIDE = 768


@dataclass
class LlmConfig:
    base_url: str
    api_key: str
    model: str
    temperature: float = 0.2
    max_tokens: int = 8000
    timeout_s: float = 240.0
    attempts: int = 3
    image_max_side: int = DEFAULT_IMAGE_MAX_SIDE

    @classmethod
    def from_env(cls) -> "LlmConfig | None":
        base_url = os.environ.get("OPENAI_BASE_URL", "").strip()
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        model = os.environ.get("OPENAI_MODEL", "").strip()
        if not base_url or not model:
            return None
        return cls(
            base_url=base_url,
            api_key=api_key,
            model=model,
            temperature=float(os.environ.get("OPENAI_TEMPERATURE", "0.2") or 0.2),
            max_tokens=int(os.environ.get("OPENAI_MAX_TOKENS", "8000") or 8000),
            timeout_s=float(os.environ.get("OPENAI_TIMEOUT_S", "240") or 240),
            attempts=int(os.environ.get("OPENAI_RETRIES", "3") or 3),
            image_max_side=int(os.environ.get("OPENAI_IMAGE_MAX_SIDE", str(DEFAULT_IMAGE_MAX_SIDE))),
        )


def _encode_image(path: Path, max_side: int) -> str:
    """PNG as a data URL, downscaled when larger than `max_side`."""
    from PIL import Image

    with Image.open(path) as image:
        image = image.convert("RGB")
        if max_side and max(image.size) > max_side:
            ratio = max_side / max(image.size)
            image = image.resize(
                (max(1, int(image.width * ratio)), max(1, int(image.height * ratio))),
                Image.LANCZOS,
            )
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
    payload = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{payload}"


class LlmClient:
    """Minimal chat client. Fails loudly rather than silently degrading."""

    def __init__(self, config: LlmConfig):
        self.config = config
        self._client = None

    def _sdk(self):
        if self._client is None:
            from openai import OpenAI  # imported lazily on purpose

            self._client = OpenAI(
                base_url=self.config.base_url,
                api_key=self.config.api_key or "not-needed",
                timeout=self.config.timeout_s,
            )
        return self._client

    def chat(self, *, system: str, user: str, images: list[Path] | None = None) -> str:
        """One completion. Retries transient failures, then raises."""
        content: list[dict[str, object]] = [{"type": "text", "text": user}]
        for path in images or []:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": _encode_image(path, self.config.image_max_side)},
                }
            )

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": content if images else user},
        ]

        last_error: Exception | None = None
        for attempt in range(1, max(1, self.config.attempts) + 1):
            try:
                response = self._sdk().chat.completions.create(
                    model=self.config.model,
                    messages=messages,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                )
                return (response.choices[0].message.content or "").strip()
            except Exception as error:  # noqa: BLE001 - provider errors vary widely
                last_error = error
                if attempt >= self.config.attempts:
                    break
                time.sleep(min(2 ** attempt, 8))
        raise RuntimeError(f"LLM call failed after {self.config.attempts} attempts: {last_error}")


def extract_code(text: str) -> str | None:
    """Pull the first fenced Python block out of a reply.

    Models occasionally wrap the module in two blocks or add prose; taking the
    longest block is the robust choice, since a real module is always the largest
    thing in the reply.
    """
    blocks = CODE_BLOCK_RE.findall(text)
    if not blocks:
        # Some providers return raw code without fences.
        stripped = text.strip()
        return stripped if "def build" in stripped else None
    return max(blocks, key=len).strip()


def extract_prose(text: str) -> str:
    """Everything that is not a code block, for notes and diagnoses."""
    without = CODE_BLOCK_RE.sub("", text)
    return without.strip()
