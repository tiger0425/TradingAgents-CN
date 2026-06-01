"""Shared helpers for invoking an agent with structured output and a graceful fallback.

The Portfolio Manager, Trader, and Research Manager all follow the same
canonical pattern:

1. At agent creation, wrap the LLM with ``with_structured_output(Schema)``
   so the model returns a typed Pydantic instance. If the provider does
   not support structured output (rare; mostly older Ollama models), the
   wrap is skipped and the agent uses free-text generation instead.
2. At invocation, run the structured call and render the result back to
   markdown. If the structured call itself fails for any reason
   (malformed JSON from a weak model, transient provider issue), fall
   back to a plain ``llm.invoke`` so the pipeline never blocks.

Centralising the pattern here keeps the agent factories small and ensures
all three agents log the same warnings when fallback fires.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional, TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _is_deepseek(llm: Any) -> bool:
    """Check whether *llm* is a DeepSeek model that needs thinking disabled."""
    return (
        hasattr(llm, 'model_name')
        and isinstance(llm.model_name, str)
        and 'deepseek-v4' in llm.model_name
    )


def bind_structured(llm: Any, schema: type[T], agent_name: str) -> Optional[Any]:
    """Return ``llm.with_structured_output(schema)`` or ``None`` if unsupported.

    Logs a warning when the binding fails so the user understands the agent
    will use free-text generation for every call instead of one-shot fallback.
    """
    try:
        base = llm.with_structured_output(schema)
    except (NotImplementedError, AttributeError) as exc:
        logger.warning(
            "%s: provider does not support with_structured_output (%s); "
            "falling back to free-text generation",
            agent_name, exc,
        )
        return None

    # DeepSeek V4 thinking mode rejects tool_choice.  We must disable
    # thinking during the *invoke*, not during setup, because
    # with_structured_output returns a Runnable that defers the API
    # call.  Wrapping invoke with a temporary extra_body override
    # ensures the flag is active when the HTTP request is made.
    if _is_deepseek(llm):
        from langchain_core.runnables import RunnableLambda

        def _invoke_disabled_thinking(input, config=None, **kw):
            was_extra = llm.model_kwargs.get('extra_body')
            llm.model_kwargs['extra_body'] = {"thinking": {"type": "disabled"}}
            try:
                return base.invoke(input, config, **kw)
            finally:
                if was_extra is not None:
                    llm.model_kwargs['extra_body'] = was_extra
                else:
                    llm.model_kwargs.pop('extra_body', None)

        return RunnableLambda(_invoke_disabled_thinking)

    return base


def invoke_structured_or_freetext(
    structured_llm: Optional[Any],
    plain_llm: Any,
    prompt: Any,
    render: Callable[[T], str],
    agent_name: str,
) -> str:
    """Run the structured call and render to markdown; fall back to free-text on any failure.

    ``prompt`` is whatever the underlying LLM accepts (a string for chat
    invocations, a list of message dicts for chat models that take that
    shape). The same value is forwarded to the free-text path so the
    fallback sees the same input the structured call did.
    """
    if structured_llm is not None:
        try:
            result = structured_llm.invoke(prompt)
            return render(result)
        except Exception as exc:
            logger.warning(
                "%s: structured-output invocation failed (%s); retrying once as free text",
                agent_name, exc,
            )

    response = plain_llm.invoke(prompt)
    return response.content
