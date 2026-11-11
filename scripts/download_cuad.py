"""Download CUAD v1 (PDFs + labels) from Zenodo into data/raw/. Idempotent.

Source: https://zenodo.org/records/4595826 (Atticus Project, CC BY 4.0).
The GitHub repo only ships the QA-format JSON; the Zenodo release also has
the 510 original contract PDFs and master_clauses.csv.
"""

import hashlib
import shutil
import urllib.request
import zipfile
from pathlib import Path

URL = "https://zenodo.org/records/4595826/files/CUAD_v1.zip?download=1"
RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
ZIP = RAW / "CUAD_v1.zip"
OUT = RAW / "CUAD_v1"


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        print(f"already extracted: {OUT}")
        return
    if not ZIP.exists():
        print(f"downloading {URL} (~106 MB)...")
        tmp = ZIP.with_suffix(".part")  # write to temp then rename: no half-files on Ctrl-C
        with urllib.request.urlopen(URL) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        tmp.rename(ZIP)
    print("sha256:", hashlib.sha256(ZIP.read_bytes()).hexdigest())  # record for reproducibility
    with zipfile.ZipFile(ZIP) as z:
        z.extractall(RAW)
    print(f"extracted to {RAW}")


if __name__ == "__main__":
    main()
