"""ResilientLLM — LLM wrapper with automatic retry and fallback.

Wraps a primary LLM client; when the primary fails (timeout, 5xx, quota
exhaustion), it retries up to max_retries times with a configurable delay,
then automatically degrades to a fallback LLM if one is configured.

DeepSeek's NotImplementedError (raised for unsupported features like
structured output) is treated specially — no retry, immediate fallback.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

_DEGRADED_DISCLAIMER = (
    "\n\n⚠️ 深度分析模型不可用，本决策使用备用模型"
)


class ResilientLLM:
    """LLM wrapper with automatic retry and fallback.

    Usage::

        resilient = ResilientLLM(
            primary=deep_llm,
            fallback=quick_llm,
            max_retries=2,
            retry_delay=3.0,
        )
        result = resilient.invoke(prompt)

    The ``is_degraded`` property can be queried by downstream agents to
    annotate output with a reliability disclaimer.
    """

    def __init__(
        self,
        primary: Any,
        fallback: Optional[Any] = None,
        max_retries: int = 2,
        retry_delay: float = 3.0,
    ):
        self.primary = primary
        self.fallback = fallback
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._degraded = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_degraded(self) -> bool:
        """Whether the current instance is operating in degraded (fallback) mode."""
        return self._degraded

    def invoke(self, prompt: Any, **kwargs: Any) -> Any:
        """Invoke the LLM with retry + fallback logic.

        *Primary path*: retry ``max_retries`` times with ``retry_delay``
        seconds between attempts.

        *NotImplementedError* (DeepSeek): skip retries, fall back immediately.

        *Fallback path*: if all primary attempts fail and a fallback is
        configured, the fallback LLM is invoked once.  The response content
        is annotated with a degradation disclaimer.

        *Failure path*: if both primary and fallback fail (or no fallback
        exists), a ``RuntimeError`` is raised.
        """
        errors: list[str] = []

        # --- Primary path (with retries) -----------------------------------
        for attempt in range(self.max_retries):
            try:
                result = self.primary.invoke(prompt, **kwargs)
                self._degraded = False
                return result
            except NotImplementedError:
                # DeepSeek-style: feature simply not available — no point retrying
                logger.warning(
                    "primary LLM does not support the requested operation. "
                    "Falling back immediately."
                )
                break
            except Exception as exc:
                errors.append(str(exc))
                if attempt < self.max_retries - 1:
                    logger.warning(
                        "primary LLM attempt %d/%d failed: %s. "
                        "Retrying in %.1fs...",
                        attempt + 1, self.max_retries, exc, self.retry_delay,
                    )
                    time.sleep(self.retry_delay)
                else:
                    logger.warning(
                        "primary LLM exhausted after %d attempt(s). Errors: %s",
                        self.max_retries, errors,
                    )

        # --- Fallback path --------------------------------------------------
        if self.fallback is not None:
            logger.warning(
                "primary LLM exhausted (%d attempts). "
                "Falling back to secondary LLM. Errors: %s",
                self.max_retries, errors,
            )
            try:
                result = self.fallback.invoke(prompt, **kwargs)
                self._degraded = True
                # Annotate response content with degradation disclaimer
                self._annotate_degraded(result)
                return result
            except Exception as exc:
                logger.error("fallback LLM also failed: %s", exc)
                raise RuntimeError(
                    f"Both primary and fallback LLMs failed. "
                    f"Primary errors: {errors}; Fallback error: {exc}"
                ) from exc

        # --- No fallback configured ----------------------------------------
        raise RuntimeError(
            f"Primary LLM failed after {self.max_retries} attempt(s) "
            f"and no fallback configured. Errors: {errors}"
        )

    def with_structured_output(
        self, schema: Any, **kwargs: Any
    ) -> Any | None:
        """Return a structured-output runnable with fallback awareness.

        If the *primary* LLM raises ``NotImplementedError`` (e.g. DeepSeek
        reasoner), the fallback LLM's structured output is returned instead.
        """
        # Try the primary's structured output binding
        try:
            return self.primary.with_structured_output(schema, **kwargs)
        except NotImplementedError:
            if self.fallback is not None:
                logger.warning(
                    "primary with_structured_output not supported. "
                    "Using fallback for structured output."
                )
                self._degraded = True
                return self.fallback.with_structured_output(schema, **kwargs)
            raise
        except Exception:
            if self.fallback is not None:
                logger.warning(
                    "primary with_structured_output failed. "
                    "Using fallback for structured output."
                )
                self._degraded = True
                return self.fallback.with_structured_output(schema, **kwargs)
            raise

    def bind_tools(self, tools: list, **kwargs: Any) -> Any:
        return self.primary.bind_tools(tools, **kwargs)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _annotate_degraded(response: Any) -> None:
        """Append the degradation disclaimer to the response content if possible."""
        if hasattr(response, "content") and isinstance(response.content, str):
            response.content += _DEGRADED_DISCLAIMER
