// VITE_API_URL="/" means "same origin as the dashboard" (single-container
// hosting); the trailing slash is dropped so paths join cleanly.
const API_BASE = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/+$/, '')
const API_KEY = import.meta.env.VITE_API_KEY ?? 'dev-local-key-change-me'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': API_KEY,
      ...init?.headers,
    },
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`${init?.method ?? 'GET'} ${path} -> ${res.status}: ${body}`)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export interface Scenario {
  id: string
}

export interface LoadScenarioResult {
  scenario_id: string
  counts: Record<string, number>
}

export interface Run {
  id: string
  scenario_id: string
  strategy: 'greedy' | 'cpsat'
  status: string
}

export interface StartRunResult {
  run_id: string
  disruption_events: number
  disrupted_bookings: number
  plan_batches_queued: number
}

export interface RunCounters {
  run_id: string
  status: string
  strategy: string
  disruption_events: number
  bookings_by_status: Record<string, number>
  sagas_by_state: Record<string, number>
  queue_depth: number | null
  workers_active: number | null
}

export interface DisruptionEvent {
  id: string
  type: string
  cause: 'WEATHER' | 'AOG' | 'CREW' | 'CASCADE' | 'ATC'
  target_flight_id: string | null
  target_airport_id: string | null
  delay_minutes: number | null
  occurred_at: string
}

export interface InvariantCheck {
  passed: boolean
  violations: Record<string, unknown>[]
}

export interface InvariantReport {
  passed: boolean
  total_violations: number
  checks: Record<string, InvariantCheck>
  checked_at: string
}

export interface SagaEvent {
  seq: number
  type: string
  payload: Record<string, unknown>
  created_at: string
}

export interface SagaDetail {
  saga_id: string
  booking_id: string
  state: string
  current_step: string | null
  priority: number
  events: SagaEvent[]
}

export interface SagaSearchResult {
  saga_id: string
  booking_id: string
  pnr: string
  passenger_name: string
  state: string
  current_step: string | null
}

export interface RunSummary {
  id: string
  scenario_id: string
  strategy: string
  status: string
  preset: string | null
  seed: number
  created_at: string | null
}

export interface RunMetrics {
  run_id: string
  strategy: string
  status: string
  sagas_by_state: Record<string, number>
  total_sagas: number
  terminal_sagas: number
  recovered: number
  recovered_pct: number
  weighted_recovered_pct: number
  unrecovered: number
  total_delay_minutes: number
  avg_delay_minutes: number
  planning_seconds: number
  planner_cpu_seconds: number
  seat_conflicts: number
  recovery_seconds: number | null
  invariants_passed: boolean | null
}

export interface TenantRow {
  airline: string
  sagas: number
  recovered: number
  recovered_pct: number
  in_flight: number
  queue_share_pct: number
  avg_delay_minutes: number
  avg_recovery_seconds: number
}

export interface FinopsReport {
  run_id: string
  profile: string
  profile_label: string
  currency: string
  cost_run: number
  cost_per_1000_recovered: number | null
  components: Record<string, number>
  assumptions: string[]
}

export const api = {
  createScenario: (body: {
    preset: string
    seed: number
    hub?: string | null
    severity: number
    cascade_chains?: number
  }) => request<Scenario>('/scenarios', { method: 'POST', body: JSON.stringify(body) }),

  loadScenario: (scenarioId: string) =>
    request<LoadScenarioResult>(`/scenarios/${scenarioId}/load`, { method: 'POST' }),

  createRun: (body: { scenario_id: string; strategy: string }, idempotencyKey: string) =>
    request<Run>('/runs', {
      method: 'POST',
      headers: { 'Idempotency-Key': idempotencyKey },
      body: JSON.stringify(body),
    }),

  startRun: (runId: string) => request<StartRunResult>(`/runs/${runId}/start`, { method: 'POST' }),

  getRun: (runId: string) => request<RunCounters>(`/runs/${runId}`),

  getDisruptions: (runId: string) => request<DisruptionEvent[]>(`/runs/${runId}/disruptions`),

  getSagaSummary: (runId: string) => request<Record<string, number>>(`/runs/${runId}/sagas/summary`),

  listRuns: (limit = 25) => request<RunSummary[]>(`/runs?limit=${limit}`),

  getRunMetrics: (runId: string) => request<RunMetrics>(`/runs/${runId}/metrics`),

  compareRuns: (a: string, b: string) =>
    request<{ a: RunMetrics; b: RunMetrics }>(`/runs/compare?a=${a}&b=${b}`),

  getTenants: (runId: string) => request<TenantRow[]>(`/runs/${runId}/tenants`),

  getFinops: (runId: string) => request<FinopsReport>(`/runs/${runId}/finops`),

  getFairness: () =>
    request<{ caps: Record<string, number>; in_flight: Record<string, number> }>('/fairness'),

  setFairness: (body: { default_cap?: number; caps?: Record<string, number> }) =>
    request<{ caps: Record<string, number>; in_flight: Record<string, number> }>('/fairness', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  checkInvariants: (runId: string) =>
    request<InvariantReport>(`/runs/${runId}/invariants/check`, { method: 'POST' }),

  getInvariants: (runId: string) => request<InvariantReport>(`/runs/${runId}/invariants`),

  setChaos: (body: { crash_probability: number; partner_failure_rate: number }) =>
    request<typeof body>('/chaos', { method: 'POST', body: JSON.stringify(body) }),

  getChaos: () => request<{ crash_probability: number; partner_failure_rate: number }>('/chaos'),

  getSagaEvents: (sagaId: string) => request<SagaDetail>(`/sagas/${sagaId}/events`),

  searchSagas: (q: string) => request<SagaSearchResult[]>(`/sagas/search?q=${encodeURIComponent(q)}`),

  streamUrl: (runId: string) => `${API_BASE}/runs/${runId}/stream?api_key=${API_KEY}`,
}
