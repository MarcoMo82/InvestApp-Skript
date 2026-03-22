"""
Claude API Wrapper mit Retry-Logik und Token-Logging.
"""

from __future__ import annotations

import time
from typing import Optional

import anthropic

from .logger import get_logger

logger = get_logger(__name__)


class ClaudeClient:
    """
    Wrapper für die Anthropic Claude API.
    Bietet einheitliche Fehlerbehandlung, Retry-Logik und Token-Tracking.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-opus-4-6",
        max_tokens: int = 2048,
        retry_attempts: int = 3,
        retry_delay: float = 2.0,
    ) -> None:
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay

        # Kumulierte Token-Nutzung
        self._total_input_tokens: int = 0
        self._total_output_tokens: int = 0
        self._total_calls: int = 0

        logger.info(f"ClaudeClient initialisiert | Modell: {model}")

    def analyze(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.3,
    ) -> str:
        """
        Sendet eine Anfrage an Claude und gibt die Antwort als String zurück.

        Args:
            prompt: User-Prompt
            system_prompt: System-Instruktion für den Agenten
            temperature: Sampling-Temperatur (0.0–1.0)

        Returns:
            Antworttext des Modells

        Raises:
            RuntimeError: Wenn alle Retry-Versuche fehlschlagen
        """
        last_error: Optional[Exception] = None

        for attempt in range(1, self.retry_attempts + 1):
            try:
                messages = [{"role": "user", "content": prompt}]

                kwargs: dict = {
                    "model": self.model,
                    "max_tokens": self.max_tokens,
                    "messages": messages,
                }
                if system_prompt:
                    kwargs["system"] = system_prompt

                response = self.client.messages.create(**kwargs)

                # Token-Tracking
                usage = response.usage
                self._total_input_tokens += usage.input_tokens
                self._total_output_tokens += usage.output_tokens
                self._total_calls += 1

                logger.debug(
                    f"Claude-Aufruf #{self._total_calls} | "
                    f"Input: {usage.input_tokens} | Output: {usage.output_tokens} | "
                    f"Gesamt Input: {self._total_input_tokens} | Gesamt Output: {self._total_output_tokens}"
                )

                return response.content[0].text

            except anthropic.RateLimitError as e:
                wait = self.retry_delay * attempt * 2  # Exponentielles Backoff
                logger.warning(f"Rate-Limit erreicht. Warte {wait}s... (Versuch {attempt}/{self.retry_attempts})")
                last_error = e
                time.sleep(wait)

            except anthropic.APIStatusError as e:
                logger.error(f"API-Fehler: {e.status_code} – {e.message} (Versuch {attempt}/{self.retry_attempts})")
                last_error = e
                if e.status_code >= 500:
                    time.sleep(self.retry_delay * attempt)
                else:
                    raise  # 4xx-Fehler nicht wiederholen

            except Exception as e:
                logger.error(f"Unerwarteter Fehler: {e} (Versuch {attempt}/{self.retry_attempts})")
                last_error = e
                time.sleep(self.retry_delay)

        raise RuntimeError(
            f"Claude-Aufruf nach {self.retry_attempts} Versuchen fehlgeschlagen: {last_error}"
        )

    def token_stats(self) -> dict:
        """Gibt die bisherige Token-Nutzung zurück."""
        return {
            "total_calls": self._total_calls,
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "total_tokens": self._total_input_tokens + self._total_output_tokens,
        }
