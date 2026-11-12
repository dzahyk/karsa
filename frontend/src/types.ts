export type User = {
  id: string; name: string; role: string; role_label: string; title: string; initials: string; permissions: string[];
  modules: string[]; username: string; organization_id: string;
};
export type CaseSummary = {
  code: string; title: string; client_name: string; status: string; status_label: string; next_action: string;
  owner: User; due_at: string | null; created_at: string; updated_at: string; synthetic: boolean; flags: number;
};
export type Span = { document_id: number; start: number; end: number; quote: string };
export type Candidate = { value: string; span: { start: number; end: number; quote: string }; source_document_id: number };
export type Requirement = {
  key: string; label: string; value_type: "integer" | "idr" | "weeks" | "text" | "date"; critical: boolean; version: number;
  overridden: boolean; source_value: string | null;
  state: "DRAFT" | "CONFIRMED" | "MISSING" | "CONFLICTING" | "NOT_APPLICABLE"; value: string | null;
  origin: string; note: string | null; candidates: Candidate[]; source: Span | null; updated_at: string;
};
export type SourceDocument = {
  id: number; kind: string; title: string; content: string; sha256: string; created_at: string;
  verification: "client_text" | "analyst_recorded"; channel: string | null; reference: string | null; page_breaks: number[];
  artifact_id: number | null; artifact?: { id: number; filename: string; mime: string; pages: number; sha256: string };
};
export type Flag = { kind: "prompt_injection" | "unsupported_claim"; message: string; span: { start: number; end: number; quote: string } };
export type PackageSummary = {
  id: number; version: number; state: string; risk_level: string; content_hash: string; created_by: User;
  required_approvals: number; approvals_count?: number; approved_by_me?: boolean;
  created_at: string; superseded_reason: string | null; case: { code: string; title: string; client_name: string };
  fee_idr: number; margin_pct: string; duration_weeks: number;
};
export type RunSummary = {
  code: string; status: string; simulate: string; package_id: number; package_hash: string; started_by: User;
  cancelled_reason: string | null;
  started_at: string; finished_at: string | null; steps_done: number; steps_total: number;
};
export type CaseDetail = CaseSummary & {
  description: string; extractor: string; flags: Flag[]; action_hints: string[]; requirements: Requirement[];
  documents: SourceDocument[]; latest_package: PackageSummary | null; latest_run: RunSummary | null;
  lock_reason: string | null; can_reopen: boolean; reopen_count: number;
};
export type Clarification = {
  id: number; requirement_key: string | null; question: string; status: "OPEN" | "ANSWERED"; answer: string | null;
  answered_source: string | null; applied: boolean; channel: string | null; reference: string | null; source_document_id: number | null; asked_by: User;
  answered_by: User | null; created_at: string; answered_at: string | null;
};
export type Change = {
  id: number; action: string; from_state: string; to_state: string; from_value: string | null; to_value: string | null;
  reason: string | null; actor: User; at: string;
};
export type Issue = { field: string; code: string; message: string };
export type PricingResult = {
  valid: boolean; inputs: Record<string, number>; variable_cost_idr: number | null; total_cost_idr: number | null;
  gross_profit_idr: number | null; margin_bp: number | null; margin_pct: string | null; issues: Issue[];
  trace: string[]; formula_version: string;
};
export type Blocker = { code: string; field?: string; message: string };
export type Capacity = { required_per_week: number; capacity_per_week: number; utilization_pct: number };
export type ScenarioOption = {
  label: string; description: string; unit_cost_idr: number; total_cost_idr: number | null; margin_bp: number | null;
  margin_pct: string | null; below_floor: boolean;
};
export type Assessment = {
  result: PricingResult; blockers: Blocker[]; warnings: Blocker[]; capacity: Capacity | null;
  scenario_comparison: Record<string, ScenarioOption>;
};
export type RateCard = {
  code: string; name: string; synthetic: boolean; notes: string;
  unit_cost_idr: Record<"conservative" | "expected" | "aggressive", number>; fixed_cost_idr: number;
  margin_floor_bp: number; margin_floor_pct: string; valid_from: string; valid_to: string;
  capacity_leads_per_week: number; expired: boolean;
};
export type FeasibilityRun = {
  id: number; scenario: string; inputs: Record<string, number>; result: PricingResult; blockers: Blocker[];
  assumptions: string[]; rate_card: string; created_by: User; created_at: string;
};
export type Feasibility = {
  rate_card: RateCard; scenario: string; scenarios: Record<string, { label: string; description: string }>;
  inputs: Record<string, number | null>; defaults: Record<string, number | null>; assessment: Assessment;
  latest_run: FeasibilityRun | null; lock_reason: string | null;
};
export type PackageRequirement = {
  key: string; label: string; critical: boolean; state: string; value: string | null; value_type: string;
  origin: string; overridden?: boolean; source_value?: string | null;
  source: {
    document: string; document_sha256: string; start: number; end: number; quote: string;
    verification?: string; channel?: string | null; reference?: string | null;
  } | null;
};
export type ProposedAction = { action: string; label: string; target: string; description: string };
export type PackageContent = {
  schema: string; case: { code: string; title: string; client: string; owner: string }; version: number;
  recommendation: string; recommendation_basis: string; requirements: PackageRequirement[];
  pricing: {
    feasibility_run_id: number; scenario: string; rate_card: string; formula_version: string;
    inputs: Record<string, number>; variable_cost_idr: number; total_cost_idr: number; gross_profit_idr: number;
    margin_bp: number; margin_pct: string; margin_floor_bp: number; trace: string[]; calculated_at: string;
  };
  assumptions: string[]; risks: string[]; open_items: string[];
  evidence: { document: string; kind: string; sha256: string; citations: number }[];
  proposed_actions: ProposedAction[]; prepared_by: string; synthetic: boolean;
  options?: (ScenarioOption & { scenario: string; recommended: boolean })[]; capacity?: Capacity | null;
  fit_gap?: { requested: string; from: string; capability: string | null; fit: string }[];
  exception?: { reason: string; requested_by: string } | null;
};
export type DiffEntry = { field: string; label: string; kind: string; before: unknown; after: unknown };
export type Approval = {
  package_state?: string;
  id: number; decision: "APPROVE" | "REJECT" | "REQUEST_CHANGES"; note: string | null; package_hash: string;
  package_version: number; actor: User; created_at: string;
};
export type Authorization = { id: number; actions: string[]; note: string | null; package_hash: string; actor: User; created_at: string };
export type PackageDetail = PackageSummary & {
  content: PackageContent; is_current: boolean; previous: PackageSummary | null; diff: DiffEntry[];
  approvals: Approval[]; previous_reviews: Approval[]; authorization: Authorization | null; runs: RunSummary[]; approval_blockers: Blocker[];
  case_status: string;
  approvals_count: number; rate_card_expired: boolean; disabled_connectors: string[];
};
export type AuditEvent = {
  id: number; verb: string; summary: string; entity_type: string; entity_id: string; actor: User | null;
  actor_role: string | null; detail: Record<string, unknown>; at: string;
};
export type StepAttempt = { number: number; kind: string; outcome: string; detail: string; actor: User; at: string };
export type RunStep = {
  key: string; label: string; target: string; status: string; attempts: number; max_attempts: number;
  idempotency_key: string | null; external_ref: string | null; last_error: string | null; started_at: string | null;
  finished_at: string | null; can_retry: boolean; can_reconcile: boolean; can_resolve: boolean; attempt_log: StepAttempt[];
};
export type Incident = {
  id: number; status: "OPEN" | "RESOLVED"; title: string; detail: string; compensation: { step: string; external_ref: string }[];
  step_key: string | null; run_code: string | null; case_code: string | null; opened_by: User | null;
  resolved_by: User | null; resolution: string | null; created_at: string; resolved_at: string | null;
};
export type Notification = { id: number; kind: string; title: string; body: string; link: string; read: boolean; created_at: string };
export type RunDetail = RunSummary & {
  steps: RunStep[]; case: { code: string; title: string; client_name: string };
  package: { id: number; version: number; state: string; content_hash: string }; simulation_label: string;
  events: AuditEvent[]; incident: Incident | null;
};
