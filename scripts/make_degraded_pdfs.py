"""Create synthetic 'scanned' versions of the degraded subset (golden_set.csv: degraded=True).

All CUAD PDFs are digital-born, so OCR vs multimodal parsers can't be compared fairly on them.
We render each page to an image, apply scanner-like damage, and save an image-only PDF
(no text layer). Ground truth stays valid because the underlying words are unchanged.

Output: data/degraded/{light,heavy}/<file>.pdf
Run: uv run python scripts/make_degraded_pdfs.py
"""

import csv
import io
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
CUAD = ROOT / "data" / "raw" / "CUAD_v1"
GOLDEN = ROOT / "evalsets" / "golden_set.csv"
OUT = ROOT / "data" / "degraded"
SEED = 7

# Each knob mimics a real scanning artefact.
LEVELS = {
    "light": {"dpi": 200, "blur": 0.6, "noise_sigma": 8, "max_rotate": 0.6, "jpeg_q": 70,
              "speckle": 0.0005},
    # v1 heavy (110dpi, blur 1.2, noise 22) was illegible even to a human -> useless test.
    # Target: "bad photocopy" - hard for machines, still readable by a person.
    "heavy": {"dpi": 150, "blur": 0.9, "noise_sigma": 16, "max_rotate": 1.5, "jpeg_q": 45,
              "speckle": 0.002},
}  # fmt: skip


def degrade(img: Image.Image, p: dict, rng: np.random.Generator) -> Image.Image:
    img = img.convert("L")  # scanners usually output grayscale
    # Skew: paper never sits perfectly straight on the glass.
    angle = rng.uniform(-p["max_rotate"], p["max_rotate"])
    img = img.rotate(angle, resample=Image.BICUBIC, expand=False, fillcolor=255)
    # Blur: optics / focus.
    img = img.filter(ImageFilter.GaussianBlur(p["blur"]))
    # Sensor noise (gaussian) + dust/toner specks (salt & pepper).
    arr = np.asarray(img, dtype=np.float32)
    arr += rng.normal(0, p["noise_sigma"], arr.shape)
    specks = rng.random(arr.shape)
    arr[specks < p["speckle"] / 2] = 0
    arr[specks > 1 - p["speckle"] / 2] = 255
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    # JPEG compression artefacts: re-encode through an in-memory JPEG.
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=p["jpeg_q"])
    return Image.open(io.BytesIO(buf.getvalue()))


def find_pdf(stem: str) -> Path:
    matches = [p for p in (CUAD / "full_contract_pdf").rglob("*") if p.stem == stem]
    if len(matches) != 1:
        raise FileNotFoundError(f"{stem}: {len(matches)} matches")
    return matches[0]


def main() -> None:
    with open(GOLDEN) as f:
        files = [r["file"] for r in csv.DictReader(f) if r["degraded"] == "True"]
    rng = np.random.default_rng(SEED)
    for level, p in LEVELS.items():
        (OUT / level).mkdir(parents=True, exist_ok=True)
        for stem in files:
            pdf = pdfium.PdfDocument(find_pdf(stem))
            # pypdfium2 renders at 72 dpi * scale
            pages = [degrade(pg.render(scale=p["dpi"] / 72).to_pil(), p, rng) for pg in pdf]
            out = OUT / level / f"{stem}.pdf"
            pages[0].save(out, save_all=True, append_images=pages[1:], resolution=p["dpi"])
            print(f"{level:5s} {len(pages):3d}p  {out.stat().st_size / 1e6:5.1f} MB  {stem[:60]}")


if __name__ == "__main__":
    main()
