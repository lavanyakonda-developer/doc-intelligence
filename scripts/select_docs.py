"""Select the golden set: 30 CUAD contracts, stratified by length + type, split dev/test.

Output (committed, small): evalsets/golden_set.csv
Run after scripts/explore_cuad.py:  uv run python scripts/select_docs.py
"""

import csv
import random
import re
import unicodedata
from collections import Counter
from pathlib import Path

import duckdb
import tiktoken

ROOT = Path(__file__).resolve().parents[1]
CUAD = ROOT / "data" / "raw" / "CUAD_v1"
DOCS_CSV = ROOT / "data" / "explore" / "docs.csv"
OUT = ROOT / "evalsets" / "golden_set.csv"

BOOL_FIELDS = [
    "Non-Compete",
    "Exclusivity",
    "Uncapped Liability",
    "Termination For Convenience",
    "Change Of Control",
]
BUCKETS = {"short": (1, 7), "medium": (8, 25), "long": (26, 60)}  # pages, inclusive
PER_BUCKET = 10
MAX_PER_TYPE = 2
MIN_POSITIVES = 5
N_DEV_PER_BUCKET = {"short": 3, "medium": 3, "long": 2}  # 8 dev / 22 test
N_DEGRADED = 6
BASE_SEED = 42


def match_key(name: str) -> str:
    """Normalize filenames so label rows match PDFs ('MACY'S' vs 'MACY_S', É NFC vs NFD)."""
    name = unicodedata.normalize("NFC", name.removesuffix(".pdf").removesuffix(".PDF"))
    return re.sub(r"[^0-9a-z]+", "_", name.lower()).strip("_")


def normalize_type(folder: str) -> str:
    """'Endorsement Agreement' / 'Endorsement' -> 'endorsement'; 'Joint Venture _ Filing' -> ..."""
    t = folder.lower().replace("_", " ")
    t = re.sub(r"\b(agreements?|filing)\b", "", t)
    return re.sub(r"\s+", " ", t).strip()


def bucket_of(pages: int) -> str | None:
    for name, (lo, hi) in BUCKETS.items():
        if lo <= pages <= hi:
            return name
    return None  # > 60 pages: excluded (cost; documented limitation)


def load_pool() -> list[dict]:
    with open(DOCS_CSV) as f:
        docs = {match_key(r["file"]): r for r in csv.DictReader(f)}
    cols = ", ".join(f'"{c}-Answer" AS "{c}"' for c in BOOL_FIELDS)
    labels = duckdb.sql(
        f"SELECT Filename, {cols} FROM read_csv_auto('{CUAD / 'master_clauses.csv'}')"
    ).fetchall()

    pool, unmatched = [], 0
    for filename, *bools in labels:
        doc = docs.get(match_key(filename))
        if doc is None:
            unmatched += 1
            continue
        pages = int(doc["pages"])
        b = bucket_of(pages)
        if b is None:
            continue
        pool.append(
            {
                "file": doc["file"],
                "label_filename": filename,  # exact key into master_clauses.csv
                "part": doc["part"],
                "contract_type": normalize_type(doc["contract_type"]),
                "pages": pages,
                "bucket": b,
                **{
                    f: str(v).strip().lower() == "true"
                    for f, v in zip(BOOL_FIELDS, bools, strict=True)
                },
            }
        )
    print(f"pool: {len(pool)} docs (dropped {unmatched} unmatched label rows, and >60-page docs)")
    return pool


def sample_once(pool: list[dict], rng: random.Random) -> list[dict]:
    picked, per_type = [], Counter()
    for b in BUCKETS:
        cands = [d for d in pool if d["bucket"] == b]
        rng.shuffle(cands)
        n = 0
        for d in cands:
            if n == PER_BUCKET:
                break
            if per_type[d["contract_type"]] < MAX_PER_TYPE:
                picked.append(d)
                per_type[d["contract_type"]] += 1
                n += 1
    return picked


def main() -> None:
    pool = load_pool()
    # Rejection sampling: try seeds until every boolean field has enough positives.
    # The seed that worked is recorded, so the selection is fully reproducible.
    for attempt in range(1000):
        seed = BASE_SEED + attempt
        rng = random.Random(seed)
        picked = sample_once(pool, rng)
        pos = {f: sum(d[f] for d in picked) for f in BOOL_FIELDS}
        if min(pos.values()) >= MIN_POSITIVES:
            break
    else:
        raise SystemExit("no seed met MIN_POSITIVES; relax constraints")
    print(f"seed {seed} (attempt {attempt + 1}) positives per boolean: {pos}")

    # Dev/test split within each bucket, so both splits contain short/medium/long docs.
    for b, n_dev in N_DEV_PER_BUCKET.items():
        docs = [d for d in picked if d["bucket"] == b]
        rng.shuffle(docs)
        for i, d in enumerate(docs):
            d["split"] = "dev" if i < n_dev else "test"

    # Degraded-scan subset: from TEST only, shortest first (multimodal cost scales per page).
    # Half short, half medium: enough layout variety while keeping ~60 pages per level.
    degraded = set()
    for b in ("short", "medium"):
        cands = sorted(d["file"] for d in picked if d["split"] == "test" and d["bucket"] == b)
        degraded |= set(rng.sample(cands, N_DEGRADED // 2))
    for d in picked:
        d["degraded"] = d["file"] in degraded

    # Token counts on the CUAD text (o200k_base = tokenizer for GPT-4o-and-later models).
    enc = tiktoken.get_encoding("o200k_base")
    for d in picked:
        text = (CUAD / "full_contract_txt" / f"{d['file']}.txt").read_text(errors="ignore")
        d["tokens"] = len(enc.encode(text, disallowed_special=()))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fields = ["file", "label_filename", "split", "bucket", "pages", "tokens", "contract_type",
              "part", "degraded", *BOOL_FIELDS]  # fmt: skip
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(picked, key=lambda d: (d["split"], d["bucket"], d["file"])))

    # Summary
    print(f"\nwrote {OUT.relative_to(ROOT)}: {len(picked)} docs")
    print("split:", dict(Counter(d["split"] for d in picked)))
    print("bucket x split:", dict(Counter((d["bucket"], d["split"]) for d in picked)))
    print("types:", len({d["contract_type"] for d in picked}), "distinct")
    for s in ("dev", "test"):
        print(f"positives in {s}:", {f: sum(d[f] for d in picked if d["split"] == s)
                                     for f in BOOL_FIELDS})  # fmt: skip
    tok = [d["tokens"] for d in picked]
    print(f"tokens: total {sum(tok):,}  max {max(tok):,}  mean {sum(tok) // len(tok):,}")
    deg = [d for d in picked if d["degraded"]]
    print(f"degraded subset: {len(deg)} docs, {sum(d['pages'] for d in deg)} pages")


if __name__ == "__main__":
    main()
