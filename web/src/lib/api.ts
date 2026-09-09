/**
 * Thin fetch wrapper around the compliance API.
 *
 * Everything goes through `/api`, which Vite proxies to the FastAPI backend in
 * development and which a reverse proxy is expected to route in production.
 * That keeps the browser on one origin, so no CORS config and no cross-origin
 * token handling.
 *
 * The bearer token lives in `sessionStorage`, not `localStorage`: it is a
 * signed short-lived token for a supervisory tool, and it should not outlive
 * the browser tab.
 */

import type {
  ChatTurn,
  CorpusStats,
  HealthResponse,
  Inspection,
  InspectionSummary,
  RagAnswer,
  RagStatus,
  RegulationSearchResponse,
  ReviewQueueEntry,
  Stats,
  ViolationRow,
} from "@/lib/types"

const BASE = "/api"
const TOKEN_KEY = "labelsure.token"

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

export const token = {
  get(): string | null {
    try {
      return sessionStorage.getItem(TOKEN_KEY)
    } catch {
      return null
    }
  },
  set(value: string | null) {
    try {
      if (value) sessionStorage.setItem(TOKEN_KEY, value)
      else sessionStorage.removeItem(TOKEN_KEY)
    } catch {
      /* private mode - the app still works, it just cannot stay signed in */
    }
  },
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  const bearer = token.get()
  if (bearer) headers.set("Authorization", `Bearer ${bearer}`)
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json")
  }

  const response = await fetch(`${BASE}${path}`, { ...init, headers })
  if (!response.ok) {
    throw new ApiError(response.status, await readError(response))
  }
  if (response.status === 204) return undefined as T
  const type = response.headers.get("content-type") ?? ""
  return (type.includes("application/json")
    ? await response.json()
    : await response.text()) as T
}

/** FastAPI returns `detail` as a string or as a list of validation errors. */
async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json()
    const detail = body?.detail
    if (typeof detail === "string") return detail
    if (Array.isArray(detail)) {
      return detail.map((d) => d?.msg ?? JSON.stringify(d)).join("; ")
    }
    return JSON.stringify(body)
  } catch {
    return `${response.status} ${response.statusText}`
  }
}

export const api = {
  health: () => request<HealthResponse>("/health"),

  // --- inspection ---------------------------------------------------------
  inspect(files: File[], productName?: string) {
    const form = new FormData()
    files.forEach((file) => form.append("files", file))
    if (productName?.trim()) form.append("product_name", productName.trim())
    return request<Inspection>("/inspect", { method: "POST", body: form })
  },
  getInspection: (id: string) => request<Inspection>(`/inspections/${id}`),
  listInspections: (limit = 50) =>
    request<{ count: number; inspections: InspectionSummary[] }>(
      `/inspections?limit=${limit}`,
    ),
  searchInspections(params: { product?: string; decision?: string; limit?: number }) {
    const query = new URLSearchParams()
    if (params.product) query.set("product", params.product)
    if (params.decision) query.set("decision", params.decision)
    query.set("limit", String(params.limit ?? 50))
    return request<{ count: number; inspections: InspectionSummary[] }>(
      `/inspections/search?${query}`,
    )
  },
  reportUrl: (id: string) => `${BASE}/inspections/${id}/report`,
  pdfUrl: (id: string) => `${BASE}/inspections/${id}/report.pdf`,
  annotatedUrl: (id: string, index: number) =>
    `${BASE}/inspections/${id}/annotated/${index}`,

  // --- human sign-off -----------------------------------------------------
  recordDecision(
    id: string,
    body: {
      action: "ACCEPT" | "OVERRIDE"
      reason: string
      /** Required for OVERRIDE: the decision the inspector puts in its place. */
      final_decision?: string
      /** Ignored by the server when auth is enabled - the token wins. */
      inspector_id?: string
      inspector_name?: string
    },
  ) {
    return request<Record<string, unknown>>(`/inspections/${id}/decision`, {
      method: "POST",
      body: JSON.stringify(body),
    })
  },
  reviewQueue: (limit = 50) =>
    request<{ count: number; queue: ReviewQueueEntry[] }>(
      `/review-queue?limit=${limit}`,
    ),

  // --- regulations --------------------------------------------------------
  corpusStats: () => request<CorpusStats>("/regulations"),
  searchRegulations: (query: string, topK = 5) =>
    request<RegulationSearchResponse>(
      `/regulations/search?q=${encodeURIComponent(query)}&top_k=${topK}`,
    ),

  // --- RAG ----------------------------------------------------------------
  ragStatus: () => request<RagStatus>("/rag"),
  ask: (body: {
    query: string
    k?: number
    use_reranker?: boolean
    history?: ChatTurn[]
  }) => request<RagAnswer>("/rag/ask", { method: "POST", body: JSON.stringify(body) }),

  // --- dashboard ----------------------------------------------------------
  stats: () => request<Stats>("/stats"),
  violations: (limit = 20) =>
    request<{ violations: ViolationRow[]; total_inspections: number }>(
      `/stats/violations?limit=${limit}`,
    ),

  // --- auth ---------------------------------------------------------------
  login: (username: string, password: string) =>
    request<{ access_token: string; token_type: string; role: string }>(
      "/auth/login",
      { method: "POST", body: JSON.stringify({ username, password }) },
    ),
  authStatus: () => request<{ enabled: boolean }>("/auth/status"),
  me: () => request<Record<string, unknown>>("/auth/me"),
}
