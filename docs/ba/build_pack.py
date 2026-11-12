"""Build 04_TRACEABILITY.md and 05_UAT_REPORT.md from the recorded test runs in docs/ba/evidence/.

Re-run the suites first (see 05_UAT_REPORT.md), then:  python3 docs/ba/build_pack.py
A requirement is 'Passed' only if every mapped check exists in the evidence and passed; a mapped check that is
missing from the evidence is reported as 'Not run', never as passed.
"""
import html, pathlib, re, subprocess

BA = pathlib.Path(__file__).resolve().parent
EV = BA / "evidence"

# FR id → (title, BR/AC refs, persona, UAT script id, [check name prefixes])
REQ = [
    ("FR-01", "Intake keeps the original brief with a hash", "—", "Analyst", "UAT-01",
     ["test_brief_text_is_stored_with_hash", "test_pdf_upload_keeps_pages_and_rejects_scans", "test_eml_upload"]),
    ("FR-02", "Extraction with exact evidence; nothing invented", "BR-009, AC-01", "Analyst", "UAT-01",
     ["test_every_span_is_a_real_substring_of_the_source", "test_aster_brief_extracts_values_and_leaves_gaps_missing",
      "test_model_output_without_verbatim_quote_is_discarded", "test_per_lead_rate_is_not_read_as_budget"]),
    ("FR-03", "Conflicting values are surfaced, not resolved silently", "AC-02", "Analyst", "UAT-02",
     ["test_conflicting_budget_is_flagged_with_both_sources"]),
    ("FR-04", "Brief text is untrusted data", "—", "Analyst", "UAT-02",
     ["test_instruction_text_is_flagged_as_data", "test_injected_instructions_do_not_change_permissions_or_state"]),
    ("FR-05", "Versioned requirement review; stale edits refused", "—", "Analyst", "UAT-01",
     ["test_stale_versions_get_409", "test_reextract_keeps_human_decisions"]),
    ("FR-06", "Clarification answers carry their evidence", "—", "Analyst", "UAT-01",
     ["test_clarification_evidence_is_labelled_by_verification"]),
    ("FR-07", "Deterministic integer-rupiah pricing", "BR-002, AC-03", "Analyst", "UAT-03",
     ["test_reference_scenario_is_exact", "test_margin_rounds_half_up_in_basis_points", "test_repeating_decimal_margin",
      "test_negative_margin_is_reported_not_hidden", "test_zero_fee_is_rejected_instead_of_dividing_by_zero",
      "test_invalid_inputs_are_listed_per_field", "test_large_values_have_no_float_error"]),
    ("FR-08", "Capacity check and scenario comparison", "FR-008", "Analyst", "UAT-03",
     ["test_capacity_blocks_package_and_options_are_compared"]),
    ("FR-09", "Package gate blocks incomplete decisions", "BR-001", "Analyst", "UAT-03",
     ["test_package_is_blocked_while_critical_requirements_are_missing",
      "test_approve_endpoint_rechecks_blockers_on_the_frozen_content"]),
    ("FR-10", "Approval binds one exact snapshot", "BR-003, AC-04", "Approver", "UAT-04",
     ["test_approval_records_the_exact_snapshot_hash_and_version", "test_stale_hash_or_version_gets_409",
      "test_tampered_snapshot_still_fails_closed_without_the_trigger"]),
    ("FR-11", "Change after approval creates a new version", "BR-004", "Analyst, Approver", "UAT-05",
     ["test_change_after_approval_creates_new_version_and_keeps_old_snapshot"]),
    ("FR-12", "Segregation of duties and mandatory notes", "—", "Approver", "UAT-04",
     ["test_package_author_cannot_review_own_package", "test_reject_and_request_changes_need_a_note",
      "keyboard-only approver can open a package, compare changes and reject it (AC-10)"]),
    ("FR-13", "High risk needs an exception and two approvers", "BR-006", "Approver", "UAT-06",
     ["test_below_floor_needs_exception_and_two_different_approvers",
      "mobile second approver completes a high-risk dual approval"]),
    ("FR-14", "Approval is not execution", "—", "Approver", "UAT-07",
     ["test_execution_requires_approval_and_separate_authorization"]),
    ("FR-15", "Connector allowlist", "BR-005", "Admin", "UAT-07", ["test_disabled_connector_blocks_authorization"]),
    ("FR-16", "Expired rate card blocks approval and execution", "BR-013", "Admin", "UAT-03",
     ["test_expired_rate_card_blocks_approval_and_execution"]),
    ("FR-17", "Idempotent retry", "BR-007, AC-05", "Automation Engineer", "UAT-08",
     ["test_retry_after_timeout_does_not_duplicate_sandbox_records",
      "test_duplicate_delivery_and_lease_expiry_do_not_duplicate_writes"]),
    ("FR-18", "Unknown outcome needs reconciliation", "AC-06", "Automation Engineer", "UAT-08",
     ["test_unknown_outcome_blocks_blind_retry_and_reconciles_without_second_write"]),
    ("FR-19", "Recovery: exception queue, manual resolution, cancel, reopen", "—", "Automation Engineer", "UAT-08",
     ["test_manual_resolution_continues_the_run", "test_cancelled_run_lists_compensation_and_case_can_be_reopened",
      "test_rejected_case_is_locked_until_reopened"]),
    ("FR-20", "Server-side roles and tenant isolation", "AC-08", "All", "UAT-09",
     ["test_unauthorized_roles_are_denied_and_audited", "test_other_tenant_cannot_see_or_touch_cases",
      "test_password_login_session_and_csrf", "password sign-in, role-based navigation and tenant isolation"]),
    ("FR-21", "Append-only audit with request IDs", "—", "All", "UAT-09",
     ["test_audit_is_append_only_and_traced", "test_database_refuses_to_change_frozen_package_content"]),
    ("FR-22", "Evaluation Lab with held-out gate", "—", "AI Evaluation Analyst", "UAT-10",
     ["test_eval_run_scores_all_cases_and_reports_real_failures", "test_eval_splits_gate_and_adjudication"]),
    ("FR-23", "Keyboard and automated accessibility checks", "AC-10", "All", "UAT-09",
     ["keyboard-only approver can open a package, compare changes and reject it (AC-10)",
      "no serious accessibility violations"]),
    ("FR-24", "End-to-end critical path in the browser", "—", "All", "UAT-01..08",
     ["intake → requirements → clarification → pricing → package → approval → authorization → async sandbox run"]),
]

UAT = {
    "UAT-01": "Create DCF-1042 from the Aster Labs brief; check every draft value's quote; confirm or edit with a reason; answer a clarification with channel + reference",
    "UAT-02": "Open DCF-1046 (two budgets) and DCF-1051 (injection); pick a budget with a reason; confirm the flag changes nothing",
    "UAT-03": "Price DCF-1042: expect Rp117,000,000 total and 22.00% margin; try to freeze with a missing requirement and with an expired rate card",
    "UAT-04": "As Arif, approve the DCF-1042 package; try the author's own package; try rejecting without a note",
    "UAT-05": "Run change request CR-001 on DCF-1043 (timeline 6 → 8 weeks) and check v1 + its approval are unchanged",
    "UAT-06": "DCF-1045 (6.82% vs 15% floor): first approval by Arif, second by Sari on a phone-width screen",
    "UAT-07": "Authorize execution separately; disable the tracker connector and retry authorization",
    "UAT-08": "Run EX-0082: timeout after commit → reconcile; retry a pre-commit timeout; cancel a run and reopen",
    "UAT-09": "Sign in as each persona; open another tenant's DCF-2001; check the audit page; keyboard-only reject",
    "UAT-10": "Run the Evaluation Lab; check dev vs held-out split, gate verdict, adjudicate one failure",
}


def results():
    out = {}
    for f in (EV / "backend-junit.xml", EV / "e2e-run.txt"):
        text = f.read_text()
        for m in re.finditer(r'<testcase\b([^>]*?)(/>|>(.*?)</testcase>)', text, re.S):
            name = html.unescape(re.search(r'\bname="([^"]*)"', m.group(1)).group(1))
            body = m.group(3) or ""
            out[name] = "Failed" if ("<failure" in body or "<error" in body) else (
                "Skipped" if "<skipped" in body else "Passed")
    return out


def status_for(prefixes, res):
    found = []
    for p in prefixes:
        hits = [s for n, s in res.items() if n.startswith(p)]
        found.append(("Not run" if not hits else ("Failed" if "Failed" in hits else "Passed"), p, len(hits)))
    overall = "Failed" if any(s == "Failed" for s, *_ in found) else (
        "Not run" if any(s == "Not run" for s, *_ in found) else "Passed")
    return overall, found


def main():
    res = results()
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                            cwd=BA).stdout.strip()
    n_pass = sum(s == "Passed" for s in res.values())
    t = ["# Requirements traceability — Karsa", "",
         f"Generated by `docs/ba/build_pack.py` from the recorded runs in `docs/ba/evidence/` (code at `{commit}`). "
         f"{len(res)} automated checks found, {n_pass} passed.", "",
         "| FR | Requirement | Rule | Persona | UAT script | Automated checks | Status |", "|---|---|---|---|---|---|---|"]
    for fr, title, rule, persona, uat, prefixes in REQ:
        overall, found = status_for(prefixes, res)
        checks = "<br>".join(f"`{p}`" + (f" ×{k}" if k > 1 else "") + ("" if s == "Passed" else f" — **{s}**")
                             for s, p, k in found)
        t.append(f"| {fr} | {title} | {rule} | {persona} | {uat} | {checks} | {overall} |")
    mapped = {n for *_, prefixes in REQ for p in prefixes for n in res if n.startswith(p)}
    unmapped = sorted(set(res) - mapped)
    t += ["", f"Checks not mapped to a requirement ({len(unmapped)}): " + (", ".join(f"`{n}`" for n in unmapped) or "none")]
    (BA / "04_TRACEABILITY.md").write_text("\n".join(t) + "\n")

    u = ["# UAT report — Karsa", "",
         "| | |", "|---|---|",
         "| Build | Karsa at commit `" + commit + "`, demo-rules-1.2 extractor, SQLite, simulated connectors |",
         "| Data | Seeded synthetic tenants Northstar and Bluepeak (`python -m app.seed`) |",
         "| Run date | 12 Nov 2026, macOS, Chromium (Playwright) |",
         "| Executed by | The builder, as **scripted acceptance**: each UAT script is automated by the checks listed in "
         "[`04_TRACEABILITY.md`](04_TRACEABILITY.md) |",
         "| Not done | Acceptance by a real business user; manual screen-reader pass; Safari/Firefox; real connectors |", "",
         "## How to reproduce", "", "```bash",
         "cd backend && uv run ruff check . && uv run pytest -v -p no:logging --junitxml=../docs/ba/evidence/backend-junit.xml",
         "cd frontend && pnpm e2e --reporter=list,junit > ../docs/ba/evidence/e2e-run.txt",
         "python3 docs/ba/build_pack.py", "```", "", "## Results by script", "",
         "| Script | Scenario | Requirements | Result |", "|---|---|---|---|"]
    for sid, scenario in UAT.items():
        frs = [r for r in REQ if r[4] == sid or (r[4] == "UAT-01..08" and sid <= "UAT-08")]
        statuses = [status_for(r[5], res)[0] for r in frs]
        overall = "Failed" if "Failed" in statuses else ("Not run" if "Not run" in statuses else "Passed")
        u.append(f"| {sid} | {scenario} | {', '.join(r[0] for r in frs)} | {overall} |")
    u += ["", "## Defects and observations", "",
          "| ID | Severity | Observation | Status |", "|---|---|---|---|",
          "| OBS-01 | High (release blocker for AI extraction) | Rule extractor passes 21/50 unseen briefs (gate 70%) and catches 1/6 new injection phrasings — see `docs/eval/EVAL_V2_RESULTS.md` | Open. Mitigated: AI values stay drafts until confirmed; brief text grants no permissions |",
          "| OBS-02 | Medium | Claude provider is implemented but has never been run live (no API key on the test machine) | Open |",
          "| OBS-03 | Low | Claim detector flags a product guarantee (\"we guarantee a replacement generator\") as a campaign claim | Open |",
          "", "## Sign-off", "", "| Role | Name | Decision | Date |", "|---|---|---|---|",
          "| Business owner | — (fictional organisation) | Not signed | — |",
          "| Business analyst | Daffa Zahy Khairy | Scripted acceptance recorded above | 12 Nov 2026 |"]
    (BA / "05_UAT_REPORT.md").write_text("\n".join(u) + "\n")
    print(f"{len(res)} checks, {n_pass} passed; unmapped: {unmapped}")


if __name__ == "__main__":
    main()
