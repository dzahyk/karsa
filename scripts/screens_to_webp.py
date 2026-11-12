"""Convert portfolio screenshots (PNG) to WebP with the file names the portfolio page uses.
Run: uv run --with pillow python scripts/screens_to_webp.py"""
import sys
from pathlib import Path
from PIL import Image
ROOT = Path(__file__).resolve().parents[1] / "docs" / "portfolio"
src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "screenshots"
dst = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "webp"
dst.mkdir(parents=True, exist_ok=True)
names = {"06-approval-review": "decisionflow", "02-cases": "decisionflow-cases", "03b-evidence-highlight": "decisionflow-evidence",
         "04-feasibility": "decisionflow-pricing", "05-capacity-scenarios": "decisionflow-capacity", "07-dual-approval": "decisionflow-dual-approval",
         "08-execution-unknown-outcome": "decisionflow-execution", "09-exception-queue": "decisionflow-exceptions",
         "10-evaluation-gate": "decisionflow-evaluation", "12-impact": "decisionflow-impact", "14-manage-integrations": "decisionflow-manage",
         "15-audit-log": "decisionflow-audit", "16-mobile-approval": "decisionflow-mobile", "01-sign-in": "decisionflow-sign-in",
         "03-requirements-evidence": "decisionflow-requirements", "11-evaluation-dev": "decisionflow-evaluation-dev",
         "13-manage-rate-cards": "decisionflow-rate-cards", "17-mobile-cases": "decisionflow-mobile-cases"}
for png in sorted(src.glob("*.png")):
    im = Image.open(png).convert("RGB")
    out = dst / f"{names.get(png.stem, png.stem)}.webp"
    im.save(out, "WEBP", quality=86, method=6)
    print(f"{out.name:38s} {im.size[0]}x{im.size[1]} {out.stat().st_size // 1024} KB")
