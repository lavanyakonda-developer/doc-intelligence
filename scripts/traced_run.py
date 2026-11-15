"""Run the golden set once with tracing on, as a fresh replicate (real LLM calls -> real
LLM spans). Saves doc -> root span id so eval results can be attached as annotations.

  make phoenix                                   # in another terminal
  uv run --group observability python scripts/traced_run.py
  uv run --group observability python scripts/annotate_traces.py
"""

import json

from docintel.config import PROJECT_ROOT
from docintel.corpus import find_pdf, golden_set
from docintel.pipeline import process_pdf
from docintel.tracing import flush, setup_tracing

REPLICATE = 3  # r0-r2 are the Phase 4 replicates; r3 = the traced run
OUT = PROJECT_ROOT / "data" / "results" / "traced_run.json"


def main() -> None:
    setup_tracing()
    spans, cost = {}, 0.0
    for g in golden_set():
        r = process_pdf(find_pdf(g["file"]), doc_id=g["file"], condition="clean",
                        replicate=REPLICATE, include_text=False)  # fmt: skip
        spans[g["file"]] = {"trace_id": r.trace_id, "span_id": r.span_id, "run_id": r.run_id,
                            "status": r.status}  # fmt: skip
        cost += r.cost.extract_usd + r.cost.retry_usd
        print(f"{r.status:5s} ${r.cost_usd:.4f} {r.seconds:5.1f}s {g['file'][:60]}")
    flush()
    OUT.write_text(json.dumps(spans, indent=1))
    print(f"{len(spans)} traced docs, extraction cost ${cost:.4f} -> {OUT.name}")


if __name__ == "__main__":
    main()
