// VITE_API_URL="/" means "same origin as the dashboard" (single-container
// hosting); the trailing slash is dropped so paths join cleanly.
const API_BASE = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/+$/, '')
// When the API serves this page it injects its own key at runtime
// (window.__FLIGHTFLOW_API_KEY__), which wins over the build-time value so
// the two can never drift apart. Empty values fall through to the next one.
const API_KEY =
  (window as { __FLIGHTFLOW_API_KEY__?: string }).__FLIGHTFLOW_API_KEY__ ||
  import.meta.env.VITE_API_KEY ||
  'dev-local-key-change-me'

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

// ---- analytics ---------------------------------------------------------
// Mirrors GET /analytics/summary. Every figure is aggregated in Postgres;
// nothing in here is computed in the browser.

export interface AnalyticsProvenance {
  source: string
  network_origin: 'generated' | 'empty'
  is_synthetic: boolean
  note: string
  scenarios: { seed: number; preset: string | null }[]
  runs_covered: number
  has_flight_data: boolean
  has_recovery_data: boolean
  schedule_window: { first_departure: string | null; last_departure: string | null }
}

export interface AnalyticsOverview {
  total_flights: number
  disrupted_flights: number
  disrupted_flights_pct: number
  on_time_flights: number
  on_time_pct: number
  cancelled_flights: number
  delayed_flights: number
  avg_delay_minutes: number
  total_bookings: number
  affected_bookings: number
  rebooked_bookings: number
  unrecovered_bookings: number
  sagas: number
  recovered_sagas: number
  recovery_rate_pct: number
  retry_rate_pct: number
  avg_recovery_seconds: number
  avg_rebooked_delay_minutes: number
  dead_letters: number
}

export interface HourBucket {
  hour: number
  flights: number
  cancelled: number
  delayed: number
  disrupted: number
  avg_delay_minutes: number
}

export interface RouteRow {
  route: string
  origin: string
  dest: string
  flights: number
  cancelled: number
  delayed: number
  avg_delay_minutes: number
}

export interface AirportRow {
  iata: string
  is_hub: boolean
  departures: number
  cancelled: number
  delayed: number
  avg_delay_minutes: number
}

export interface AnalyticsSchedule {
  flights: {
    total: number
    scheduled: number
    delayed: number
    cancelled: number
    on_time: number
    avg_delay_minutes: number
    max_delay_minutes: number
    first_departure: string | null
    last_departure: string | null
  }
  by_hour: HourBucket[]
  delay_histogram: { bucket: string; flights: number }[]
  routes: RouteRow[]
  airports: AirportRow[]
  bookings_by_status: Record<string, number>
}

export interface CauseRow {
  cause: string
  events: number
  cancellations: number
  delays: number
  avg_delay_minutes: number
}

export interface RecoveryByCauseRow {
  cause: string
  sagas: number
  completed: number
  compensated: number
  failed_no_capacity: number
  needs_manual: number
  recovered_pct: number
}

export interface AnalyticsRecovery {
  run_ids: string[]
  runs: {
    id: string
    strategy: string
    status: string
    created_at: string | null
    seed: number
    preset: string | null
  }[]
  sagas: {
    total: number
    completed: number
    compensated: number
    failed_no_capacity: number
    needs_manual: number
    retried: number
    total_attempts: number
    avg_recovery_seconds: number
    avg_rebooked_delay_minutes: number
  }
  sagas_by_state: Record<string, number>
  disruption_causes: CauseRow[]
  recovery_by_cause: RecoveryByCauseRow[]
  dead_letters: { step: string; dead_letters: number }[]
}

export interface AnalyticsInsight {
  key: string
  headline: string
  detail: string
  support: Record<string, string | number | boolean | null>
  limited_data: boolean
  tone: 'neutral' | 'success' | 'warning'
}

export interface AnalyticsResponse {
  generated_at: string
  filters: { run_id: string | null; window_days: number | null; top_n: number }
  provenance: AnalyticsProvenance
  overview: AnalyticsOverview
  schedule: AnalyticsSchedule
  recovery: AnalyticsRecovery
  insights: AnalyticsInsight[]
  gaps: { question: string; needed: string }[]
}

export interface PassengerRow {
  booking_id: string
  pnr: string
  name: string
  tier: string
  airline: string
  origin: string
  dest: string
  flights: string
  booking_status: string
  saga_id: string | null
  saga_state: string | null
}

export interface PassengerList {
  total: number
  items: PassengerRow[]
}

export interface PassengerSegment {
  seq: number
  cabin: string
  flight_id: string
  flight_no: string
  status: string
  origin: string
  dest: string
  sched_dep_at: string | null
  dep_at: string | null
}

export interface PassengerDetail {
  booking_id: string
  pnr: string
  booking_status: string
  passenger: {
    name: string
    tier: string
    bags: number
    is_unaccompanied_minor: boolean
    airline: string
  }
  segments: PassengerSegment[]
  others_on_flight: number
  direct_alternatives: number
  saga: { id: string; state: string; run_id: string } | null
  can_disrupt: boolean
}

export interface FlightOption {
  id: string
  flight_no: string
  airline: string
  origin: string
  dest: string
  sched_dep_at: string
  economy_available: number
  business_available: number
  direct_alternatives: number
}

export interface CreatePassengerBody {
  name: string
  flight_id: string
  cabin: string
  tier: string
  bags: number
  is_unaccompanied_minor: boolean
}

export interface CreatePassengerResult {
  booking_id: string
  pnr: string
  name: string
  flight_no: string
}

export interface DisruptResult {
  run_id: string
  flight_no: string
  cause: string
  disrupted_bookings: number
  plan_batches_queued: number
}

/** The API's `detail` text when it sent one, else the raw error message. */
export function apiErrorMessage(err: unknown): string {
  const message = err instanceof Error ? err.message : String(err)
  const body = message.slice(message.indexOf(': ', message.indexOf('->')) + 2)
  try {
    const detail = JSON.parse(body)?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg)
  } catch {
    // not JSON; fall through
  }
  return message
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

  getAnalytics: (params: { runId?: string | null; windowDays?: number | null; topN?: number }) => {
    const q = new URLSearchParams()
    if (params.runId) q.set('run_id', params.runId)
    if (params.windowDays) q.set('window_days', String(params.windowDays))
    if (params.topN) q.set('top_n', String(params.topN))
    const suffix = q.toString()
    return request<AnalyticsResponse>(`/analytics/summary${suffix ? `?${suffix}` : ''}`)
  },

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

  listPassengers: (params: { q?: string; history?: 'all' | 'with'; limit?: number }) => {
    const qs = new URLSearchParams()
    if (params.q) qs.set('q', params.q)
    if (params.history) qs.set('history', params.history)
    if (params.limit) qs.set('limit', String(params.limit))
    return request<PassengerList>(`/passengers?${qs}`)
  },

  getPassenger: (bookingId: string) => request<PassengerDetail>(`/passengers/${bookingId}`),

  listFlights: (params: { q?: string; limit?: number }) => {
    const qs = new URLSearchParams()
    if (params.q) qs.set('q', params.q)
    if (params.limit) qs.set('limit', String(params.limit))
    return request<FlightOption[]>(`/flights?${qs}`)
  },

  createPassenger: (body: CreatePassengerBody) =>
    request<CreatePassengerResult>('/passengers', { method: 'POST', body: JSON.stringify(body) }),

  disruptPassenger: (bookingId: string, cause: string) =>
    request<DisruptResult>(`/passengers/${bookingId}/disrupt`, {
      method: 'POST',
      body: JSON.stringify({ cause }),
    }),

  streamUrl: (runId: string) => `${API_BASE}/runs/${runId}/stream?api_key=${API_KEY}`,
}
