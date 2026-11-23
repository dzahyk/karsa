# Portfolio screenshots

Screenshots of every screen, used in the main README and on the case study page
(https://dzahyk.github.io/case-karsa.html). All data shown is synthetic.

- `screenshots/`: the original PNG captures.
- `webp/`: the same images as WebP for the website (16 desktop at 1600×1000, 2 phone at 780×1688).

Held-out evaluation results are in [docs/eval/EVAL_V2_RESULTS.md](../eval/EVAL_V2_RESULTS.md).

## Regenerate

The capture runs against a freshly seeded, separate database (`backend/screens.db`); the demo database is not touched.

```bash
cd frontend && pnpm playwright test -c playwright.screens.config.ts
cd .. && uv run --with pillow python scripts/screens_to_webp.py
```
