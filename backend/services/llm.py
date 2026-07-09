"""Generic LLM abstraction so the provider/model can be swapped in one place.

To add a new provider: implement BaseLLMClient, add one branch to get_llm_client().
Nothing else in the codebase needs to change.
"""
import os
from abc import ABC, abstractmethod

from dotenv import load_dotenv

load_dotenv()


class BaseLLMClient(ABC):
    @abstractmethod
    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        json_mode: bool = False,
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> str:
        """Return the raw text content of the model's response."""
        raise NotImplementedError


class GroqLLMClient(BaseLLMClient):
    def __init__(self, model: str, api_keys: list[str]):
        from groq import Groq

        if not api_keys:
            raise ValueError("at least one Groq API key is required")
        self._clients = [Groq(api_key=key) for key in api_keys]
        self._key_index = 0
        self._model = model

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        json_mode: bool = False,
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> str:
        from groq import BadRequestError

        kwargs = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        # Reasoning models (gpt-oss, qwen) spend part of max_completion_tokens
        # on hidden reasoning even with include_reasoning=False. If the budget
        # runs out before any visible output, json_mode fails server-side with
        # json_validate_failed and an empty failed_generation. Retry with a
        # bigger budget instead of surfacing a 500.
        attempts = 3
        current_max_tokens = max_tokens
        for attempt in range(attempts):
            try:
                response = self._create_with_rate_limit_retry(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=temperature,
                    max_completion_tokens=current_max_tokens,
                    **kwargs,
                )
            except BadRequestError as e:
                if "json_validate_failed" in str(e) and attempt < attempts - 1:
                    current_max_tokens = int(current_max_tokens * 1.5)
                    continue
                raise

            content = (response.choices[0].message.content or "").strip()
            if content:
                return content
            # Same root cause without json_mode: budget exhausted by reasoning.
            if attempt < attempts - 1:
                current_max_tokens = int(current_max_tokens * 1.5)

        raise RuntimeError(
            f"LLM returned empty content after {attempts} attempts (last max_tokens={current_max_tokens})"
        )

    def _create_with_rate_limit_retry(self, **create_kwargs):
        """The pipeline fires 8-12 sequential calls per /generate-tests request,
        so free-tier 429s are routine, not exceptional. Strategy:
        - On a 429, immediately rotate to the next API key (limits are
          per-organization, so another key has its own fresh TPM/TPD budget).
          This is the only remedy for daily (TPD) exhaustion - no amount of
          waiting inside the same key helps within a demo timeframe.
        - Only sleep when EVERY key has been tried and all are limited, using
          the wait Groq suggests ("Please try again in 975ms") when parseable.
        """
        import re
        import time

        from groq import RateLimitError

        num_keys = len(self._clients)
        max_rate_limit_retries = max(6, num_keys * 3)
        consecutive_rate_limits = 0
        for retry in range(max_rate_limit_retries + 1):
            client = self._clients[self._key_index]
            try:
                return client.chat.completions.create(
                    model=self._model,
                    # gpt-oss/qwen reasoning models leak <think> chains into content
                    # unless reasoning is explicitly excluded. Never use reasoning_format.
                    include_reasoning=False,
                    **create_kwargs,
                )
            except RateLimitError as e:
                if retry >= max_rate_limit_retries:
                    raise
                consecutive_rate_limits += 1
                previous_index = self._key_index
                self._key_index = (self._key_index + 1) % num_keys
                limit_kind = "TPD (daily)" if "(TPD)" in str(e) else "TPM (per-minute)"
                print(
                    f"[llm] Groq key #{previous_index + 1}/{num_keys} hit its {limit_kind} rate limit - "
                    f"switching to key #{self._key_index + 1}",
                    flush=True,
                )
                if consecutive_rate_limits < num_keys:
                    continue  # next key gets its own budget - no need to wait
                # Full cycle of 429s: every key is limited right now, so waiting
                # is the only option left. Honor Groq's suggested wait if short;
                # a suggestion in minutes means TPD exhaustion on this key, but
                # another key may recover its per-minute budget sooner - cap the
                # sleep and keep cycling.
                match = re.search(r"try again in ([\d.]+)(ms|s)", str(e))
                if match:
                    wait = float(match.group(1)) / (1000 if match.group(2) == "ms" else 1)
                else:
                    wait = 2.0 * consecutive_rate_limits
                wait = min(wait + 1.0, 30.0)
                print(
                    f"[llm] all {num_keys} Groq keys are rate-limited right now - waiting {wait:.1f}s before retrying",
                    flush=True,
                )
                time.sleep(wait)


def get_llm_client() -> BaseLLMClient:
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    model = os.getenv("LLM_MODEL", "qwen/qwen3-32b")

    if provider == "groq":
        # GROQ_API_KEYS: comma-separated list, rotated automatically on 429s.
        # Falls back to the single GROQ_API_KEY if the list isn't set.
        raw_keys = os.getenv("GROQ_API_KEYS") or os.getenv("GROQ_API_KEY") or ""
        api_keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
        if not api_keys:
            raise RuntimeError("GROQ_API_KEYS (or GROQ_API_KEY) is not set")
        return GroqLLMClient(model=model, api_keys=api_keys)

    raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")
