# Business analysis pack — Karsa

A reviewable set of business-analysis deliverables for Karsa, the AI-assisted deal-desk portfolio build. Everything
describes a fictional agency and synthetic data; nothing here was signed off by a real business owner.

| # | Deliverable | What a reviewer can check |
|---|---|---|
| 1 | [Business requirements (BRD)](01_BRD.md) | Problem, objectives, scope, personas, the spec's business rules, risks — including the failed extractor gate |
| 2 | [Functional requirements + acceptance criteria (FRD)](02_FRD.md) | 24 requirements with Given/When/Then criteria on seeded cases |
| 3 | [Process models](03_PROCESS.md) | AS-IS (assumed) and TO-BE as BPMN 2.0 files that open in bpmn.io, with SVG renders |
| 4 | [Traceability matrix](04_TRACEABILITY.md) | Business rule → requirement → UAT script → automated checks → status (generated) |
| 5 | [UAT report](05_UAT_REPORT.md) | Scripted acceptance results, defects, sign-off status (generated) |
| 6 | [Change request CR-001](06_CHANGE_REQUEST_CR-001.md) | A worked change-impact analysis on a seeded case |

Generated files come from the recorded runs in `evidence/`:

```bash
python3 docs/ba/build_pack.py
```

```bash
python3 docs/ba/bpmn/build_bpmn.py
```

Authorship: requirements analysis by Daffa Zahy Khairy; implementation and much of the drafting with AI coding
agents under his direction. The extractor evaluation that the BRD cites is in [`../eval/`](../eval/).
