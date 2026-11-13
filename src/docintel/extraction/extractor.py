"""Run one extraction: contract text -> LLMExtraction -> ContractRecord.

Every result is cached under a config hash (model, effort, prompt hash, schema version,
parser, condition). Same config = same cache = never billed twice; any change to the
prompt file automatically produces a new run id. That IS our prompt versioning.
"""

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from functools import cached_property

from openai import OpenAI

from docintel.config import PROJECT_ROOT, get_settings
from docintel.extraction.llm_schema import SCHEMA_VERSION, LLMExtraction
from docintel.extraction.to_record import to_record
from docintel.llm.pricing import cost_usd

PROMPTS = PROJECT_ROOT / "prompts"
RUNS = PROJECT_ROOT / "data" / "runs"


@dataclass(frozen=True)
class RunConfig:
    model: str
    effort: str = "low"
    prompt: str = "extract_v1"
    parser: str = "pypdf"
    condition: str = "clean"
    replicate: int = 0  # >0 = repeat of the same config, to measure run-to-run variance

    @property
    def prompt_text(self) -> str:
        return (PROMPTS / f"{self.prompt}.md").read_text()

    @property
    def prompt_hash(self) -> str:
        return hashlib.sha256(self.prompt_text.encode()).hexdigest()[:10]

    @property
    def run_id(self) -> str:
        key = json.dumps(
            {**asdict(self), "prompt_hash": self.prompt_hash, "schema": SCHEMA_VERSION},
            sort_keys=True,
        )
        short = self.model.replace("gpt-", "")
        digest = hashlib.sha256(key.encode()).hexdigest()[:8]
        parts = [short, self.effort, self.prompt, self.parser, self.condition]
        return "-".join([*parts, f"r{self.replicate}", digest])


@dataclass
class ExtractionResult:
    doc_id: str
    run_id: str
    status: str  # ok | refused | incomplete | error
    raw: dict | None  # LLMExtraction as JSON
    record: dict | None  # ContractRecord as JSON
    conversion_errors: list[str] = field(default_factory=list)
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd: float = 0.0
    seconds: float = 0.0
    detail: str | None = None


class Extractor:
    def __init__(self, cfg: RunConfig):
        self.cfg = cfg
        self.dir = RUNS / cfg.run_id

    @cached_property
    def client(self) -> OpenAI:
        key = get_settings().openai_api_key
        if key is None:
            raise RuntimeError("OPENAI_API_KEY not set")
        return OpenAI(api_key=key.get_secret_value(), max_retries=4, timeout=300)

    def _write_config(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        meta = {
            **asdict(self.cfg),
            "run_id": self.cfg.run_id,
            "prompt_hash": self.cfg.prompt_hash,
            "schema_version": SCHEMA_VERSION,
        }
        (self.dir / "config.json").write_text(json.dumps(meta, indent=2))

    def extract(self, doc_id: str, text: str, *, refresh: bool = False) -> ExtractionResult:
        path = self.dir / f"{doc_id}.json"
        if path.exists() and not refresh:
            return ExtractionResult(**json.loads(path.read_text()))
        self._write_config()
        res = self._call(doc_id, text)
        path.write_text(json.dumps(asdict(res), ensure_ascii=False))
        return res

    def _call(self, doc_id: str, text: str) -> ExtractionResult:
        t0 = time.perf_counter()
        base = {"doc_id": doc_id, "run_id": self.cfg.run_id, "raw": None, "record": None}
        try:
            r = self.client.responses.parse(
                model=self.cfg.model,
                instructions=self.cfg.prompt_text,  # stable prefix -> eligible for prompt caching
                input=f"<contract>\n{text}\n</contract>",
                text_format=LLMExtraction,
                reasoning={"effort": self.cfg.effort},
                max_output_tokens=16000,
            )
        except Exception as e:  # after SDK retries
            return ExtractionResult(**base, status="error", detail=f"{type(e).__name__}: {e}")

        u = r.usage
        cached = getattr(u.input_tokens_details, "cached_tokens", 0) or 0
        reasoning = getattr(u.output_tokens_details, "reasoning_tokens", 0) or 0
        usage = {
            "input_tokens": u.input_tokens,
            "cached_tokens": cached,
            "output_tokens": u.output_tokens,
            "reasoning_tokens": reasoning,
            "cost_usd": round(cost_usd(self.cfg.model, u.input_tokens, u.output_tokens, cached), 6),
            "seconds": round(time.perf_counter() - t0, 2),
        }
        if r.status != "completed":
            return ExtractionResult(
                **base, **usage, status="incomplete", detail=str(r.incomplete_details)
            )
        refusal = next(
            (c.refusal for o in r.output if o.type == "message" for c in o.content
             if c.type == "refusal"),
            None,
        )  # fmt: skip
        if refusal:
            return ExtractionResult(**base, **usage, status="refused", detail=refusal)

        parsed: LLMExtraction = r.output_parsed
        record, errors = to_record(doc_id, parsed)
        return ExtractionResult(
            doc_id=doc_id,
            run_id=self.cfg.run_id,
            status="ok",
            raw=parsed.model_dump(mode="json"),
            record=record.model_dump(mode="json"),
            conversion_errors=errors,
            **usage,
        )
