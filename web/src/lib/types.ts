/**
 * Wire types for the compliance API.
 *
 * These mirror `labelguard-inspection/1.1` as produced by
 * `backend/app/services/pipeline.py`. Fields the backend can legitimately
 * leave unset are optional or nullable here rather than being defaulted away,
 * because "not assessed" and "assessed as zero" mean very different things in
 * a compliance report.
 */

export type Decision = "COMPLIANT" | "NON_COMPLIANT" | "MANUAL_REVIEW"

/** Per-rule outcome. These are the engine's own labels (rule_engine.py). */
export type RuleStatus =
  | "PASS"
  | "FAIL"
  | "MANUAL_REVIEW"
  | "NOT_APPLICABLE"
  | "UNVERIFIED"

export type Severity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | string

export interface Citation {
  document?: string | null
  rule?: string | null
  title?: string | null
  page?: number | null
  effective_date?: string | null
  quote?: string | null
  status?: string | null
  verified?: boolean | null
  url?: string | null
  chunk_id?: string | null
}

/** Where a rule came from - the clause, its page and its verbatim wording. */
export interface RuleSource {
  document?: string | null
  rule?: string | null
  page?: number | null
  evidence_text?: string | null
  status?: string | null
  category?: string | null
  url?: string | null
}

export interface RuleResult {
  rule_id: string | null
  status: RuleStatus
  severity: Severity
  requirement: string
  reason: string
  fields?: string[]
  verified?: boolean
  evidence?: Record<string, unknown>
  source?: RuleSource | null
}

export interface ExtractedField {
  field_name: string
  value: string | null
  ocr_text?: string | null
  ocr_confidence?: number | null
  extraction_confidence?: number | null
  confidence_level?: string | null
  bbox?: number[][] | null
  reason?: string | null
  line_index?: number | null
}

/** One quality-gate check, e.g. blur or glare, with the threshold it was held to. */
export interface QualityCheck {
  value: number
  pass: boolean
  threshold?: number
  min?: number
  max?: number
}

export interface SurfaceQuality {
  usable?: boolean
  score?: number | null
  checks?: Record<string, QualityCheck>
  reasons?: string[]
  [key: string]: unknown
}

export interface InspectionImage {
  index: number
  name: string
  usable: boolean
  gate_usable: boolean
  usability_basis: string
  quality: SurfaceQuality | null
  ocr_avg_confidence: number | null
  num_lines: number
  ocr_error: string | null
}

export interface AnnotatedImage {
  name: string
  path: string
  boxes: unknown[]
}

export interface Disclaimer {
  system_role: string
  text: string
  short: string
}

/** Fused confidence, with the components that produced it. */
export interface ConfidenceBreakdown {
  overall: number
  components: Record<string, number>
  per_field: Record<string, number>
  decision: Decision
  decision_reasons: string[]
  downgraded_from: string | null
}

/** Severity-weighted score out of 100, excluding rules that could not be assessed. */
export interface ComplianceScoreCategory {
  bucket: string
  label: string
  score: number | null
  rules_scored: number
  pass: number
  fail: number
  manual_review: number
  not_assessable: number
}

export interface ComplianceScore {
  score: number | null
  max_score: number
  grade: string
  grade_meaning: string
  scored_rules: number
  not_assessable: number
  counts: {
    pass: number
    fail: number
    manual_review: number
    not_applicable: number
    unverified: number
  }
  categories: ComplianceScoreCategory[]
  basis: string
  system_role?: string
  disclaimer?: string
}

export interface ComplianceDecision {
  decision: Decision
  reasons: string[]
  failed_rules: unknown[]
  review_rules: unknown[]
}

export interface ProductCategory {
  category: string
  label: string
  confidence: number
  confident: boolean
  evidence: string[]
  scores: Record<string, number>
  basis: string
}

export interface Inspection {
  inspection_id: string
  response_schema: string
  timestamp: string
  product_name: string | null
  ruleset: Record<string, unknown>
  images: InspectionImage[]
  coverage: { surfaces_total: number; surfaces_usable: number }
  extracted_fields: Record<string, ExtractedField>
  rule_results: RuleResult[]
  compliance_decision: ComplianceDecision | null
  confidence: ConfidenceBreakdown | null
  decision: Decision | null
  decision_reasons: string[] | null
  decision_downgraded_from: string | null
  decision_emoji: string | null
  compliance_score: ComplianceScore | null
  product_category: ProductCategory | null
  regulation_citations: Citation[]
  annotated_images: AnnotatedImage[]
  disclaimer: Disclaimer
  processing_time_sec: number | null
}

export interface InspectionSummary {
  inspection_id: string
  product_name?: string | null
  decision?: Decision | null
  confidence?: number | null
  timestamp?: string
  priority?: string | null
  compliance_score?: number | null
  [key: string]: unknown
}

/** One retrieved regulation clause from `/regulations/search`. */
export interface RegulationHit {
  score: number
  keyword_score: number
  vector_score: number
  chunk_id: string
  rule_reference: string
  title: string
  category: string
  text: string
  citation: Citation
}

export interface RegulationSearchResponse {
  query: string
  count: number
  results: RegulationHit[]
  note: string | null
}

export interface CorpusStats {
  chunks: number
  documents: string[]
  source_types: string[]
  with_page_numbers: number
  vector_dim: number
  vectorizer: string
  load_errors: string[]
}

/** A source behind a RAG answer. */
export interface RagSource {
  chunk_id: string
  content: string
  score: number
  chunk_type: string
  metadata: {
    rule?: string | null
    title?: string | null
    category?: string | null
    document?: string | null
    page?: number | null
    quote?: string | null
    status?: string | null
    verified?: boolean | null
    url?: string | null
  }
  scores: {
    keyword?: number | null
    vector?: number | null
    hybrid?: number | null
    rrf?: number | null
  }
}

/** How the assistant read the message. Only a "regulation" reply is held to
 *  the grounding gate and shown with citations. */
export type RagIntent = "regulation" | "conversation" | "out_of_scope"

/** One prior turn, sent back so a follow-up question can resolve. */
export interface ChatTurn {
  role: "user" | "assistant"
  content: string
}

export interface RagAnswer {
  query: string
  answer: string
  sources: RagSource[]
  confidence: number
  used_web_search: boolean
  grounded: boolean
  intent: RagIntent
  generator: "groq" | "extractive" | "none"
  reranked: boolean
  disclaimer: string
}

export interface RagStatus {
  corpus: CorpusStats
  generator: "groq" | "extractive"
  generation_model: string | null
  reranker_model: string | null
  web_search: boolean
  min_grounding_score: number
  disclaimer: string
}

/** One day of the dashboard trend. The API names the total `total`, and
 *  breaks it down by decision. */
export interface DailyTrendPoint {
  date: string
  total: number
  COMPLIANT: number
  NON_COMPLIANT: number
  MANUAL_REVIEW: number
}

export interface Stats {
  total_inspections: number
  compliant: number
  non_compliant: number
  manual_review: number
  compliance_rate: number | null
  average_confidence: number | null
  average_compliance_score: number | null
  by_decision: Record<string, number>
  by_category: Record<string, number>
  common_violations: { rule_id: string; count: number }[]
  manufacturer_trends: unknown[]
  daily_trend: DailyTrendPoint[]
  human_reviewed: number
  overrides: number
  override_rate: number | null
  disclaimer: string
}

export interface ViolationRow {
  rule_id: string
  count: number
  rule?: string | null
  title?: string | null
  page?: number | null
  document?: string | null
}

export interface ReviewQueueEntry {
  inspection_id: string
  product_name?: string | null
  decision?: Decision | null
  confidence: number | null
  timestamp?: string
  [key: string]: unknown
}

export interface HealthResponse {
  status: string
  service: string
  version: string
  system_role: string
  auth: { enabled: boolean; secret_configured?: boolean; [key: string]: unknown }
}
