"""Tracing: OpenTelemetry spans for every pipeline stage, viewable in Arize Phoenix.

Off by default. The pipeline only uses the OpenTelemetry *API*, which is a no-op until an
application installs a tracer provider, so tests, CI and the CLI pay nothing. Turn it on:

    make phoenix                       # local Phoenix UI on http://localhost:6006
    DOCINTEL_TRACING=1 make serve      # or call setup_tracing() in a script

Span tree for one document (OpenInference span kinds in brackets):
    process_pdf [CHAIN]
    ├── parse [TOOL]
    ├── extract [CHAIN] ── ChatCompletion/Responses [LLM]   (auto-instrumented OpenAI call)
    ├── validate [GUARDRAIL]
    └── retry [CHAIN] ── [LLM]                              (only if a field failed)
Cached stages still get a span (docintel.cache_hit=true) carrying the original cost/tokens,
but no LLM child span: no call was made.

Privacy: the OpenAI instrumentation records full prompts, i.e. the whole contract. Fine for a
local Phoenix; for a hosted backend set OPENINFERENCE_HIDE_INPUTS / _OUTPUTS (see D14).
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode

PHOENIX_ENDPOINT = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006")
PROJECT = "docintel"

# A proxy: spans go to whichever provider is installed later (or nowhere if none is).
tracer = trace.get_tracer("docintel")

# OpenInference span kinds (the attribute Phoenix uses to pick icons and views).
KIND = "openinference.span.kind"


@contextmanager
def stage(name: str, kind: str, **attributes: Any) -> Iterator[Span]:
    """A pipeline-stage span. Exceptions are recorded and re-raised."""
    with tracer.start_as_current_span(name) as span:
        span.set_attribute(KIND, kind)
        set_attrs(span, **attributes)
        yield span


def set_attrs(span: Span, **attributes: Any) -> None:
    """Set `docintel.*` attributes, skipping None (OTel rejects it) and stringifying the
    types OTel can't store (OTel accepts str/bool/int/float and lists of those)."""
    for k, v in attributes.items():
        if v is None:
            continue
        if isinstance(v, list | tuple):
            v = [x if isinstance(x, str | bool | int | float) else str(x) for x in v]
        elif not isinstance(v, str | bool | int | float):
            v = str(v)
        span.set_attribute(f"docintel.{k}", v)


def mark_error(span: Span, message: str) -> None:
    span.set_status(Status(StatusCode.ERROR, message))


def ids(span: Span) -> tuple[str | None, str | None]:
    """(trace_id, span_id) as hex, or (None, None) when tracing is off."""
    ctx = span.get_span_context()
    if not ctx.is_valid:
        return None, None
    return format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")


_provider = None


def setup_tracing(endpoint: str = PHOENIX_ENDPOINT, project: str = PROJECT):
    """Install a tracer provider that exports to Phoenix + instrument the OpenAI SDK.
    Needs the optional group: `uv sync --group observability`. Idempotent."""
    global _provider
    if _provider is not None:
        return _provider
    from openinference.instrumentation.openai import OpenAIInstrumentor
    from phoenix.otel import register

    _provider = register(
        endpoint=f"{endpoint.rstrip('/')}/v1/traces",
        project_name=project,
        batch=True,  # export in the background, never on the request path
        verbose=False,
    )
    OpenAIInstrumentor().instrument(tracer_provider=_provider)
    return _provider


def maybe_setup_tracing() -> None:
    if os.environ.get("DOCINTEL_TRACING") == "1":
        setup_tracing()


def flush() -> None:
    if _provider is not None:
        _provider.force_flush()
