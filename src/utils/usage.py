import os
import sys
from typing import Any

USAGE_ENV_FLAG = "PDFSCOUT_LOG_USAGE"
CACHE_TTL_ENV = "PDFSCOUT_CACHE_TTL"


def cache_control() -> dict[str, str]:
    """Prompt-cache marker for the PDF document block.

    Default 5-minute TTL is optimal for single extractions (1.25x write cost).
    Multi-run workloads over the same document (golden regeneration, N-run
    variance measurement) should set PDFSCOUT_CACHE_TTL=1h: the 2x write is
    paid once and every later run reads the ~12k-token PDF prefix at 0.1x,
    where the 5m TTL often expires between runs on long documents."""
    if os.environ.get(CACHE_TTL_ENV, "").lower() in ("1h", "1hr", "hour"):
        return {"type": "ephemeral", "ttl": "1h"}
    return {"type": "ephemeral"}


def usage_entry(context: str, response: Any) -> dict[str, Any]:
    """Build a usage-log entry from an Anthropic API response.

    Also prints a per-call [USAGE] line to stderr when PDFSCOUT_LOG_USAGE is
    set to a truthy value ('1', 'true', 'yes')."""
    u = response.usage
    entry = {
        "context": context,
        "input_tokens": u.input_tokens,
        "output_tokens": u.output_tokens,
        "cache_read_input_tokens": u.cache_read_input_tokens,
        "cache_creation_input_tokens": u.cache_creation_input_tokens,
        "stop_reason": response.stop_reason,
    }
    if os.environ.get(USAGE_ENV_FLAG, "").lower() in ("1", "true", "yes"):
        print(
            f"[USAGE] {context}: "
            f"cache_write={entry['cache_creation_input_tokens']} "
            f"cache_read={entry['cache_read_input_tokens']} "
            f"input={entry['input_tokens']} "
            f"output={entry['output_tokens']} "
            f"stop={entry['stop_reason']}",
            file=sys.stderr,
            flush=True,
        )
    return entry


def summarize_usage(usage_log: list[dict[str, Any]]) -> dict[str, int]:
    """Aggregate a run's usage entries into totals (for the end-of-run summary
    and Langfuse trace metadata)."""
    totals = {
        "api_calls": len(usage_log),
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }
    for e in usage_log:
        for k in (
            "input_tokens",
            "output_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
        ):
            totals[k] += e.get(k) or 0
    return totals
