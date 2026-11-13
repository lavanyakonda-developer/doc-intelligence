"""Multimodal: render each page to an image and have a vision LLM transcribe it.

Pages are sent concurrently (independent requests), with retries on transient errors.
A page that still fails is recorded in `errors` and left as a marker in the text, never
silently dropped, so downstream metrics see the hole.
"""

import base64
import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pypdfium2 as pdfium
from openai import OpenAI

from docintel.config import get_settings
from docintel.llm.pricing import cost_usd
from docintel.parsing.base import ParseResult

PROMPT = (
    "Transcribe all text on this contract page exactly as written, in reading order. "
    "Plain text only: no commentary, no Markdown formatting, no summarizing, no corrections. "
    "Keep original line breaks between paragraphs. Write [illegible] for text you cannot read."
)

# 150 dpi letter page = 1275x1650 px -> 40x52 = 2,080 patches (x1.2 multiplier = ~2.5k tokens),
# under the 2,500-patch "high" budget, so the image isn't downscaled further by the API.
RENDER_DPI = 150


class VisionParser:
    def __init__(self, model: str = "gpt-6-luna", workers: int = 8):
        self.model = model
        self.name = f"vision-{model}"
        self.workers = workers
        key = get_settings().openai_api_key
        if key is None:
            raise RuntimeError("OPENAI_API_KEY not set (see .env.example)")
        # max_retries: SDK retries 429/5xx with exponential backoff.
        self.client = OpenAI(api_key=key.get_secret_value(), max_retries=4, timeout=120)

    def _page(self, png: bytes) -> tuple[str, int, int, str | None]:
        b64 = base64.b64encode(png).decode()
        r = self.client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": PROMPT},
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{b64}",
                            "detail": "high",
                        },
                    ],
                }
            ],
            # Reasoning tokens are billed as output and count against max_output_tokens;
            # transcription needs none (verified: effort=none -> 0 reasoning tokens, same text).
            reasoning={"effort": "none"},
            max_output_tokens=4000,
        )
        err = None
        if r.status != "completed":  # e.g. truncated at max_output_tokens: fail loudly
            err = f"status={r.status} details={r.incomplete_details}"
        return r.output_text, r.usage.input_tokens, r.usage.output_tokens, err

    def parse(self, pdf: Path) -> ParseResult:
        doc = pdfium.PdfDocument(pdf)
        pngs = []
        for page in doc:
            buf = io.BytesIO()
            page.render(scale=RENDER_DPI / 72).to_pil().convert("L").save(buf, format="PNG")
            pngs.append(buf.getvalue())

        def safe(i_png):
            i, png = i_png
            try:
                return self._page(png)
            except Exception as e:  # after SDK retries: record and continue with other pages
                return f"[page {i + 1} failed]", 0, 0, f"page {i + 1}: {type(e).__name__}: {e}"

        with ThreadPoolExecutor(self.workers) as pool:
            results = list(pool.map(safe, enumerate(pngs)))  # map preserves page order

        in_tok = sum(r[1] for r in results)
        out_tok = sum(r[2] for r in results)
        return ParseResult(
            parser=self.name,
            text="\n\n".join(r[0] for r in results),
            pages=len(pngs),
            seconds=0,
            cost_usd=round(cost_usd(self.model, in_tok, out_tok), 5),
            input_tokens=in_tok,
            output_tokens=out_tok,
            errors=[r[3] for r in results if r[3]],
        )
