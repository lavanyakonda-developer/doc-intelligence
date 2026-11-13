"""Run extraction for a config over a split, then score it.

  uv run python scripts/run_extraction.py --model gpt-6-luna --split dev
  uv run python scripts/run_extraction.py --model gpt-6.1-terra --split test
  uv run python scripts/run_extraction.py --model gpt-6-luna --parser vision-gpt-6-luna \
      --condition heavy --split degraded

Results are cached per (config, doc): re-running only pays for docs not done yet.
"""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

from docintel.corpus import golden_set, ground_truth
from docintel.eval.score import format_table, score
from docintel.extraction.extractor import Extractor, RunConfig
from docintel.parsing.base import CACHE_DIR, ParseResult


def load_parse(parser: str, condition: str, doc_id: str) -> str:
    path = CACHE_DIR / parser / condition / f"{doc_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"{path}: run scripts/run_parsers.py first")
    return ParseResult(**json.loads(path.read_text())).text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--effort", default="low")
    ap.add_argument("--prompt", default="extract_v1")
    ap.add_argument("--parser", default="pypdf")
    ap.add_argument("--condition", default="clean")
    ap.add_argument("--split", choices=["dev", "test", "all", "degraded"], default="dev")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--replicate", type=int, default=0)
    args = ap.parse_args()

    cfg = RunConfig(
        args.model, args.effort, args.prompt, args.parser, args.condition, args.replicate
    )
    golden = golden_set()
    if args.split == "degraded":
        docs = [d["file"] for d in golden if d["degraded"] == "True"]
    else:
        docs = [d["file"] for d in golden if args.split in ("all", d["split"])]

    ex = Extractor(cfg)
    texts = {d: load_parse(cfg.parser, cfg.condition, d) for d in docs}
    with ThreadPoolExecutor(args.workers) as pool:
        results = list(pool.map(lambda d: ex.extract(d, texts[d]), docs))

    print(f"run {cfg.run_id}  ({len(docs)} docs, split={args.split})")
    by_status = {}
    for r in results:
        by_status[r.status] = by_status.get(r.status, 0) + 1
        if r.status != "ok" or r.conversion_errors:
            print(f"  {r.status:10s} {r.doc_id[:45]:45s} {r.detail or ''} {r.conversion_errors}")
    cost = sum(r.cost_usd for r in results)
    secs = [r.seconds for r in results]
    print(
        f"status {by_status} | ${cost:.4f} total | in {sum(r.input_tokens for r in results):,}"
        f" (cached {sum(r.cached_tokens for r in results):,}) out "
        f"{sum(r.output_tokens for r in results):,} (reasoning "
        f"{sum(r.reasoning_tokens for r in results):,}) | latency mean {sum(secs) / len(secs):.1f}s"
        f" max {max(secs):.1f}s\n"
    )
    gt = {d: g for d, g in ground_truth().items() if d in docs}
    print(format_table(score({r.doc_id: asdict(r) for r in results}, gt)))


if __name__ == "__main__":
    main()
