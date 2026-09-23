// Mirrors backend/app/schemas. Field names match the API exactly so payloads round-trip as-is.

export type ApplicationStatus = 'draft' | 'submitted' | 'underwriting' | 'completed'
export type RunStatus = 'queued' | 'running' | 'completed' | 'failed'

export interface BusinessPayload {
  legal_name: string | null
  entity_type: string | null
  state: string | null
  industry: string | null
  years_in_business: number | null
  annual_revenue: number | null
  has_physical_location: boolean | null
  is_us_based: boolean | null
  trucks_operated: number | null
}

export interface LoanPayload {
  amount: number | null
  term_months: number | null
  transaction_type: string | null
  down_payment_pct: number | null
  soft_cost_pct: number | null
  corp_only: boolean
  notes: string | null
}

export interface BusinessCreditPayload {
  paynet_score: number | null
  trade_lines_count: number | null
  trade_history_years: number | null
  largest_comparable_credit: number | null
  comparable_contracts_count: number | null
  clean_payment_history_months: number | null
}

export interface GuarantorPayload {
  full_name: string | null
  ownership_pct: number | null
  fico_score: number | null
  is_homeowner: boolean | null
  years_at_residence: number | null
  is_us_citizen: boolean | null
  industry_experience_years: number | null
  has_cdl: boolean | null
  cdl_class: string | null
  cdl_years: number | null
  is_licensed_medical_professional: boolean | null
  years_licensed: number | null
  revolving_credit_limit: number | null
  revolving_balance: number | null
  unsecured_debt: number | null
  has_bankruptcy: boolean
  bankruptcy_discharge_date: string | null
  has_judgments: boolean
  has_foreclosures: boolean
  has_repossessions: boolean
  has_tax_liens: boolean
  has_recent_collections: boolean
}

export interface EquipmentPayload {
  category: string | null
  description: string | null
  model_year: number | null
  condition: string | null
  mileage: number | null
  hours: number | null
  is_titled: boolean | null
}

export interface ApplicationPayload {
  business: BusinessPayload
  loan: LoanPayload
  business_credit: BusinessCreditPayload
  guarantors: GuarantorPayload[]
  equipment: EquipmentPayload[]
}

export interface FieldIssue {
  path: string
  label: string
}

export interface RunSummary {
  id: string
  status: RunStatus
  mode: string
  error: string | null
  created_at: string
  completed_at: string | null
  eligible_count: number
  lender_count: number
  best_lender: string | null
  best_program: string | null
  best_score: number | null
}

export interface Application extends ApplicationPayload {
  id: string
  status: ApplicationStatus
  created_at: string
  updated_at: string
  missing_fields: FieldIssue[]
  latest_run: RunSummary | null
}

export interface ApplicationListItem {
  id: string
  status: ApplicationStatus
  legal_name: string | null
  industry: string | null
  state: string | null
  amount: number | null
  notes: string | null
  created_at: string
  updated_at: string
  latest_run: RunSummary | null
}

export interface SampleApplication {
  key: string
  title: string
  payload: ApplicationPayload
}

export type FieldType = 'number' | 'boolean' | 'enum'
export type Unit = '' | 'money' | 'percent' | 'years' | 'months' | 'miles' | 'score' | 'count'

export interface CatalogField {
  key: string
  label: string
  type: FieldType
  category: string
  unit: Unit
  options: string[]
  derived: boolean
  description: string
  operators: string[]
}

export interface CatalogOperator {
  key: string
  label: string
  value_shape: 'none' | 'scalar' | 'range' | 'list'
}

export interface Catalog {
  categories: string[]
  fields: CatalogField[]
  operators: CatalogOperator[]
}

export type FeatureValue = string | number | boolean | null
export type FeatureSet = Record<string, FeatureValue>

export interface MatchResultSummary {
  id: string
  rank: number
  lender_id: string
  lender_name: string
  policy_version_id: string
  policy_version_number: number
  status: 'evaluated' | 'error'
  error: string | null
  eligible: boolean
  decision: 'eligible' | 'manual_review' | 'needs_information' | 'ineligible' | 'error'
  matched_program_name: string | null
  fit_score: number
  score_breakdown: { tier?: number; headroom?: number; soft?: number; total?: number; notes?: string[] }
  near_miss_ratio: number
  rejection_reasons: string[]
  program_details: Record<string, unknown>
  program_summaries: ProgramSummary[]
}

export interface ProgramSummary {
  name: string
  rank: number
  decision_mode?: 'automatic' | 'manual_review'
  decision?: 'eligible' | 'manual_review' | 'needs_information' | 'ineligible'
  applicable: boolean
  applicability_note: string | null
  eligible: boolean
  hard_failures: number
}

export interface Criterion {
  id: string
  rule_id: string | null
  program_name: string | null
  program_rank: number | null
  label: string
  category: string
  severity: 'hard' | 'soft'
  outcome: 'passed' | 'failed' | 'skipped' | 'missing'
  field_key: string | null
  operator: string | null
  expected: unknown
  actual: unknown
  message: string
}

export interface MatchResultDetail extends MatchResultSummary {
  criteria: Criterion[]
}

export interface Run {
  id: string
  application_id: string
  status: RunStatus
  mode: string
  error: string | null
  feature_snapshot: FeatureSet | null
  created_at: string
  started_at: string | null
  completed_at: string | null
  results: MatchResultSummary[]
}

// --- lender policies -------------------------------------------------------------------------

export type PolicyStatus = 'draft' | 'published' | 'archived'
export type Severity = 'hard' | 'soft'
export type RuleKind = 'simple' | 'any_of'

export interface Condition {
  field: string
  operator: string
  value?: unknown
  label?: string | null
}

export interface Rule {
  id: string
  program_id: string | null
  kind: RuleKind
  label: string
  category: string
  severity: Severity
  field: string | null
  operator: string | null
  value: unknown
  alternatives: Condition[]
  applies_when: Condition[]
  message_template: string | null
  source_document?: string | null
  source_quote?: string | null
  source_page?: number | null
  sort_order: number
  summary: string
}

export interface Program {
  id: string
  name: string
  rank: number
  decision_mode: 'automatic' | 'manual_review'
  description: string | null
  applies_when: Condition[]
  applies_when_summary: string[]
  details: Record<string, unknown>
  rules: Rule[]
}

export interface PolicyVersionSummary {
  id: string
  version_number: number
  status: PolicyStatus
  source_document: string | null
  notes: string | null
  published_at: string | null
  created_at: string
  updated_at: string
}

export interface Uncertainty {
  item: string
  reason: string
  suggestion: string | null
}

export interface ExtractionReview {
  job_id: string
  filename: string
  extractor: string | null
  uncertainties: Uncertainty[]
  completed_at: string | null
}

export interface PolicyVersion extends PolicyVersionSummary {
  lender_id: string
  lender_name: string
  rules: Rule[]
  programs: Program[]
  validation_errors: string[]
  extraction: ExtractionReview | null
}

export type IngestionStatus = 'uploaded' | 'extracting' | 'draft_ready' | 'failed'

export interface IngestionJob {
  id: string
  lender_id: string | null
  lender_name: string | null
  new_lender_name: string | null
  filename: string
  status: IngestionStatus
  mode: string
  error: string | null
  extractor: string | null
  uncertainties: Uncertainty[]
  policy_version_id: string | null
  created_at: string
  completed_at: string | null
}

export interface Lender {
  id: string
  name: string
  slug: string
  contact_name: string | null
  contact_email: string | null
  contact_phone: string | null
  is_active: boolean
  published_version: PolicyVersionSummary | null
  draft_version: PolicyVersionSummary | null
  program_count: number
  rule_count: number
  updated_at: string
}

export interface ProgramIn {
  name: string
  rank: number
  decision_mode?: 'automatic' | 'manual_review'
  description?: string | null
  applies_when?: Condition[]
  details?: Record<string, unknown>
}

/** Request body for creating or replacing a rule. */
export interface RuleInput {
  program_id?: string | null
  kind: RuleKind
  label: string
  category: string
  severity: Severity
  field: string | null
  operator: string | null
  value: unknown
  alternatives: Condition[]
  applies_when: Condition[]
  message_template: string | null
  source_document?: string | null
  source_quote?: string | null
  source_page?: number | null
}
