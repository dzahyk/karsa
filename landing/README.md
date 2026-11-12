# Karsa — landing page

A static marketing page for Karsa (formerly DecisionFlow AI). It follows the landing mockup's layout
(the original headline "Make clarity your next move." was replaced by "What gets approved is what runs."; glass and green panels, a copper beam, and the
Understand → Evaluate → Approve → Execute row) and explains the product step by step as you scroll.

No build step and no framework: `index.html`, `styles.css`, `main.js`, and `assets/`.

## Run locally

```bash
cd landing
python3 -m http.server 8768 --bind 127.0.0.1
```

Then open http://127.0.0.1:8768/.

## Sections

| Section | What moves |
|---|---|
| Hero | Light threads draw in and converge on the panels, the copper beam extends, and a pulse travels along it. The panels drift slightly with the pointer (fine pointers only). |
| From uncertainty to action | Four steps fade in one after another. |
| 01 · The problem | A synthetic brief highlights its issues one at a time: confirmed, missing, missing, conflicting. |
| 02 · How it works | Sticky product frame. For each step the screenshot zooms to the part that matters, dims the rest, outlines it in copper and shows a callout: "This is X — for Y". On phones the callout sits under the frame. A copper progress line fills as you go. |
| 03 · Principles | Green band with five rules. |
| 04 · What is proven | Test counts, plus a "Not yet" box that lists what has not been done. |
| 05 · Closing | Mobile approval screen inside a phone frame. |

## Honesty

All screenshots come from the real prototype running on synthetic data. The numbers match the
project docs: 51 backend tests, 16 browser journeys, 12 pages scanned, 60/60 prices, and a held-out
score of 1/36. The page says it is a portfolio prototype. It claims no clients or business results.

## Quality checks done

- axe-core (WCAG 2.0/2.1/2.2 A and AA, plus best-practice): 0 violations at 1440×900 and 390×844.
- No horizontal scroll at 390px.
- `prefers-reduced-motion`: animations are switched off, and all content and highlights show at once.
- Without JavaScript, content stays visible. Hidden-until-revealed states only apply under the `js` class.
- Not done: manual screen-reader testing and testing on real devices.

## Not published

This folder has not been deployed or pushed anywhere.
