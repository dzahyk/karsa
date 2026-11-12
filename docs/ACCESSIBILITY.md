# Accessibility

Target: WCAG 2.2 AA for the critical flows (spec §4.14).

## Automated (run in CI via Playwright)
- axe-core (`wcag2a/aa`, `wcag21aa`, `wcag22aa`) on the sign-in page and 11 signed-in pages: no serious/critical issues.
- Keyboard-only approver flow (AC-10): skip link, open package, read diff, open Reject, focus moves into the dialog,
  Escape returns focus to the opener, type the note, submit — no pointer used.
- Mobile: touch targets ≥ 44 px on the approval action bar; no horizontal scrolling at 390 px.

## Manual checklist (not yet performed — needs a person with a screen reader)
| Task | VoiceOver (macOS/iOS) | NVDA (Windows) |
|---|---|---|
| Sign in with a demo account | ☐ | ☐ |
| Find the missing lead definition and hear its status ("Missing") | ☐ | ☐ |
| Hear the evidence quote and its verification label | ☐ | ☐ |
| Trace the pricing formula (calculation trace) | ☐ | ☐ |
| Notice a changed approval snapshot (409 message) | ☐ | ☐ |
| Approve with a note; hear the confirmation toast once | ☐ | ☐ |
| Follow a queued run and hear "Run … finished" once (no progress spam) | ☐ | ☐ |
| Zoom to 200 %: all actions still reachable | ☐ | ☐ |
| `prefers-reduced-motion`: no non-essential animation | ☐ | ☐ |

Record findings with page, assistive technology, steps and severity.
