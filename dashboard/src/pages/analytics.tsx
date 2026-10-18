import { useQuery } from '@tanstack/react-query'
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  CircleHelp,
  Clock,
  Database,
  Lightbulb,
  PlaneTakeoff,
  RefreshCw,
  Timer,
  TrendingUp,
  UsersRound,
} from 'lucide-react'
import * as React from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { ChartTooltip } from '@/components/chart-tooltip'
import { EmptyState } from '@/components/empty-state'
import { PageHeader } from '@/components/page-header'
import { StatCard } from '@/components/stat-card'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import {
  api,
  type AnalyticsInsight,
  type AnalyticsResponse,
  type CauseRow,
  type HourBucket,
  type RecoveryByCauseRow,
} from '@/lib/api'
import { AXIS_TICK } from '@/lib/chart'
import { cn } from '@/lib/utils'

const WINDOWS = [
  { value: '1', label: 'Last 24 hours' },
  { value: '7', label: 'Last 7 days' },
  { value: '30', label: 'Last 30 days' },
  { value: 'all', label: 'All runs' },
]

const ALL_RUNS = 'all'

/** Where a panel's numbers come from, stated under each one. */
function SourceNote({ children }: { children: React.ReactNode }) {
  return (
    <p className="t-caption mt-3 flex items-start gap-1.5 text-muted-foreground/80">
      <Database className="mt-px size-3 shrink-0" aria-hidden />
      <span>{children}</span>
    </p>
  )
}

function ChartEmpty({ message }: { message: string }) {
  return (
    <div className="flex h-full min-h-48 items-center justify-center px-4 text-center">
      <p className="t-caption text-muted-foreground">{message}</p>
    </div>
  )
}

function pct(part: number, whole: number) {
  return whole > 0 ? Math.round((1000 * part) / whole) / 10 : 0
}

// ---- panels ------------------------------------------------------------

function ProvenanceStrip({ data }: { data: AnalyticsResponse }) {
  const { provenance, generated_at } = data
  const seeds = provenance.scenarios.map((s) => s.seed).join(', ')

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-xl border border-border bg-surface-alt/40 px-4 py-3">
      <Badge variant="progress">Live aggregation</Badge>
      {provenance.is_synthetic ? <Badge variant="warning">Synthetic network</Badge> : null}
      {/* basis-full keeps the note on its own line on narrow screens rather
          than letting it squeeze into whatever the badges leave behind. */}
      <p className="t-caption min-w-0 basis-full text-muted-foreground sm:flex-1 sm:basis-0">
        {provenance.note}
        {seeds ? ` Scenario seeds in the database: ${seeds}.` : ''}{' '}
        Computed {new Date(generated_at).toLocaleTimeString()}.
      </p>
    </div>
  )
}

function KpiRow({ data }: { data: AnalyticsResponse }) {
  const o = data.overview
  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
      <StatCard label="Scheduled flights" value={o.total_flights} icon={PlaneTakeoff} hint="in the loaded network" />
      <StatCard
        label="Disrupted"
        value={o.disrupted_flights}
        total={o.total_flights}
        tone="warning"
        icon={AlertTriangle}
        hint={`${o.disrupted_flights_pct}% of the schedule`}
      />
      <StatCard
        label="Undisrupted"
        value={o.on_time_flights}
        total={o.total_flights}
        tone="success"
        icon={CheckCircle2}
        hint={`${o.on_time_pct}% — not "on time" as observed`}
      />
      <StatCard
        label="Avg departure delay"
        value={Math.round(o.avg_delay_minutes)}
        tone="warning"
        icon={Clock}
        hint="minutes, delayed flights only"
      />
      <StatCard
        label="Passengers rebooked"
        value={o.recovered_sagas}
        total={o.sagas}
        tone="success"
        icon={UsersRound}
        hint={`${o.recovery_rate_pct}% of ${o.sagas.toLocaleString()} disrupted`}
      />
      <StatCard
        label="Still unrecovered"
        value={o.unrecovered_bookings}
        total={o.total_bookings}
        tone="destructive"
        icon={RefreshCw}
        hint="bookings marked UNRECOVERED"
      />
    </div>
  )
}

function DeparturesByHour({ rows }: { rows: HourBucket[] }) {
  const data = React.useMemo(
    // disrupted_pct is a display ratio of two server-side counts, not a
    // second aggregation.
    () => rows.map((r) => ({ ...r, label: `${String(r.hour).padStart(2, '0')}:00`, disrupted_pct: pct(r.disrupted, r.flights) })),
    [rows],
  )

  return (
    <Card>
      <CardHeader>
        <CardTitle>Departures by hour of day</CardTitle>
        <CardDescription>
          Which departure windows carry the most flights, and what share of each window was hit. Bars are
          flights (left axis); the line is the disrupted share (right axis, %).
        </CardDescription>
      </CardHeader>
      <CardContent className="h-72 pt-2">
        {data.length === 0 ? (
          <ChartEmpty message="No flights loaded yet." />
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
              <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="label" tick={AXIS_TICK} tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={24} />
              <YAxis yAxisId="left" tick={AXIS_TICK} tickLine={false} axisLine={false} allowDecimals={false} width={44} />
              <YAxis yAxisId="right" orientation="right" unit="%" tick={AXIS_TICK} tickLine={false} axisLine={false} width={44} domain={[0, 100]} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--color-muted)', opacity: 0.5 }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar yAxisId="left" dataKey="flights" name="Flights scheduled" fill="var(--color-secondary)" fillOpacity={0.35} radius={[4, 4, 0, 0]} />
              <Bar yAxisId="left" dataKey="disrupted" name="Delayed or cancelled" fill="var(--color-warning)" radius={[4, 4, 0, 0]} />
              <Line yAxisId="right" type="monotone" dataKey="disrupted_pct" name="Disrupted %" stroke="var(--color-destructive)" strokeWidth={2} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </CardContent>
      <CardContent className="pt-0">
        <SourceNote>
          <code>flights</code> grouped by <code>EXTRACT(HOUR FROM sched_dep_at)</code>. Live database
          aggregation over the currently loaded network.
        </SourceNote>
      </CardContent>
    </Card>
  )
}

function DelayDistribution({
  rows,
  avg,
  max,
}: {
  rows: { bucket: string; flights: number }[]
  avg: number
  max: number
}) {
  const total = rows.reduce((sum, r) => sum + r.flights, 0)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Delay distribution</CardTitle>
        <CardDescription>
          How severe the delays are, in minutes past scheduled departure. Mean {avg} min across{' '}
          {total.toLocaleString()} delayed flights; worst {max} min.
        </CardDescription>
      </CardHeader>
      <CardContent className="h-72 pt-2">
        {total === 0 ? (
          <ChartEmpty message="No departure has been pushed back yet — load a scenario and start a run." />
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
              <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="bucket" tick={AXIS_TICK} tickLine={false} axisLine={false} unit=" min" />
              <YAxis tick={AXIS_TICK} tickLine={false} axisLine={false} allowDecimals={false} width={44} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--color-muted)', opacity: 0.5 }} />
              <Bar dataKey="flights" name="Flights" radius={[4, 4, 0, 0]}>
                {rows.map((row, i) => (
                  <Cell
                    key={row.bucket}
                    fill={i >= 3 ? 'var(--color-destructive)' : i >= 1 ? 'var(--color-warning)' : 'var(--color-secondary)'}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </CardContent>
      <CardContent className="pt-0">
        <SourceNote>
          <code>flights.dep_at - flights.sched_dep_at</code>, bucketed in SQL. A departure is only late
          where a scenario injected a delay.
        </SourceNote>
      </CardContent>
    </Card>
  )
}

function DisruptionCauses({ rows }: { rows: CauseRow[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Disruption causes</CardTitle>
        <CardDescription>
          What drove the disruption in the selected runs — cancellations against delays, by cause.
        </CardDescription>
      </CardHeader>
      <CardContent className="h-72 pt-2">
        {rows.length === 0 ? (
          <ChartEmpty message="No disruption events in the selected window." />
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
              <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="cause" tick={AXIS_TICK} tickLine={false} axisLine={false} />
              <YAxis tick={AXIS_TICK} tickLine={false} axisLine={false} allowDecimals={false} width={44} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--color-muted)', opacity: 0.5 }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="cancellations" name="Cancellations" stackId="events" fill="var(--color-destructive)" radius={[0, 0, 0, 0]} />
              <Bar dataKey="delays" name="Delays" stackId="events" fill="var(--color-warning)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </CardContent>
      <CardContent className="pt-0">
        <SourceNote>
          <code>disruption_events</code> for the selected runs, grouped by cause and type.
        </SourceNote>
      </CardContent>
    </Card>
  )
}

function RecoveryByCause({ rows }: { rows: RecoveryByCauseRow[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Recovery outcome by disruption cause</CardTitle>
        <CardDescription>
          Whether passengers hit by each cause got rebooked. A booking hit by more than one cause is
          counted under each.
        </CardDescription>
      </CardHeader>
      <CardContent className="h-72 pt-2">
        {rows.length === 0 ? (
          <ChartEmpty message="No recovered sagas to attribute yet." />
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
              <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="cause" tick={AXIS_TICK} tickLine={false} axisLine={false} />
              <YAxis tick={AXIS_TICK} tickLine={false} axisLine={false} allowDecimals={false} width={44} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--color-muted)', opacity: 0.5 }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="completed" name="Rebooked" stackId="o" fill="var(--color-success)" />
              <Bar dataKey="compensated" name="Compensated" stackId="o" fill="var(--color-warning)" />
              <Bar dataKey="failed_no_capacity" name="No capacity" stackId="o" fill="var(--color-destructive)" />
              <Bar dataKey="needs_manual" name="Needs manual" stackId="o" fill="var(--color-muted-foreground)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </CardContent>
      <CardContent className="pt-0">
        <SourceNote>
          <code>disruption_events</code> joined to <code>sagas</code> through the booking's original
          itinerary (<code>booking_segments</code>), which rebooking never rewrites.
        </SourceNote>
      </CardContent>
    </Card>
  )
}

function RouteTable({ data }: { data: AnalyticsResponse }) {
  const rows = data.schedule.routes

  return (
    <Card>
      <CardHeader>
        <CardTitle>Worst-hit routes</CardTitle>
        <CardDescription>
          Routes ordered by how many of their flights were cancelled or delayed.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <ChartEmpty message="No flights loaded yet." />
        ) : (
          <div className="-mx-2 overflow-x-auto">
            <table className="w-full min-w-[32rem] border-collapse">
              <thead>
                <tr className="border-b border-border">
                  <th className="t-label px-2 py-2 text-left font-medium text-muted-foreground">Route</th>
                  <th className="t-label px-2 py-2 text-right font-medium text-muted-foreground">Flights</th>
                  <th className="t-label px-2 py-2 text-right font-medium text-muted-foreground">Cancelled</th>
                  <th className="t-label px-2 py-2 text-right font-medium text-muted-foreground">Delayed</th>
                  <th className="t-label px-2 py-2 text-right font-medium text-muted-foreground">Avg delay</th>
                  <th className="t-label px-2 py-2 text-right font-medium text-muted-foreground">Hit rate</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const hit = r.cancelled + r.delayed
                  const rate = pct(hit, r.flights)
                  return (
                    <tr key={r.route} className="border-b border-border/60 last:border-0">
                      <td className="px-2 py-2 font-mono text-sm text-foreground">{r.route}</td>
                      <td className="t-body px-2 py-2 text-right tabular-nums">{r.flights}</td>
                      <td className="t-body px-2 py-2 text-right tabular-nums text-destructive">{r.cancelled || '—'}</td>
                      <td className="t-body px-2 py-2 text-right tabular-nums text-warning">{r.delayed || '—'}</td>
                      <td className="t-body px-2 py-2 text-right tabular-nums text-muted-foreground">
                        {r.avg_delay_minutes ? `${r.avg_delay_minutes} min` : '—'}
                      </td>
                      <td className="px-2 py-2 text-right">
                        <span
                          className={cn(
                            't-label tabular-nums',
                            rate >= 50 ? 'text-destructive' : rate > 0 ? 'text-warning' : 'text-muted-foreground',
                          )}
                        >
                          {rate}%
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
        <SourceNote>
          <code>flights</code> joined to <code>airports</code> on origin and destination. Live aggregation,
          top {data.filters.top_n} rows.
        </SourceNote>
      </CardContent>
    </Card>
  )
}

function AirportTable({ data }: { data: AnalyticsResponse }) {
  const rows = data.schedule.airports

  return (
    <Card>
      <CardHeader>
        <CardTitle>Departure airports</CardTitle>
        <CardDescription>Where the schedule is concentrated, and which fields lost departures.</CardDescription>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <ChartEmpty message="No flights loaded yet." />
        ) : (
          <ul className="space-y-2.5">
            {rows.map((a) => {
              const hit = a.cancelled + a.delayed
              const rate = pct(hit, a.departures)
              return (
                <li key={a.iata}>
                  <div className="mb-1 flex items-center gap-2">
                    <span className="font-mono text-sm font-medium text-foreground">{a.iata}</span>
                    {a.is_hub ? <Badge variant="primary">hub</Badge> : null}
                    <span className="t-caption ml-auto text-muted-foreground tabular-nums">
                      {hit} of {a.departures} departures hit ({rate}%)
                    </span>
                  </div>
                  <div className="flex h-1.5 overflow-hidden rounded-full bg-muted">
                    <span style={{ width: `${pct(a.cancelled, a.departures)}%` }} className="bg-destructive" />
                    <span style={{ width: `${pct(a.delayed, a.departures)}%` }} className="bg-warning" />
                  </div>
                </li>
              )
            })}
          </ul>
        )}
        <SourceNote>
          <code>flights</code> grouped by origin airport. Red is cancelled, amber delayed.
        </SourceNote>
      </CardContent>
    </Card>
  )
}

const TONE_STYLES: Record<AnalyticsInsight['tone'], string> = {
  neutral: 'border-l-muted-foreground/40',
  success: 'border-l-success',
  warning: 'border-l-warning',
}

function InsightsPanel({ insights }: { insights: AnalyticsInsight[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <span className="flex size-6 items-center justify-center rounded-lg bg-secondary/12 text-secondary">
            <Lightbulb className="size-3.5" aria-hidden />
          </span>
          What the data shows
        </CardTitle>
        <CardDescription>
          Observations computed from the aggregations on this page. Each carries the counts behind it;
          none of them is a prediction.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {insights.length === 0 ? (
          <ChartEmpty message="Nothing to observe yet — load a scenario and start a run to populate the analytics." />
        ) : (
          <ul className="space-y-3">
            {insights.map((insight) => (
              <li
                key={insight.key}
                className={cn('rounded-r-lg border-l-2 bg-surface-alt/30 py-2.5 pl-3.5 pr-3', TONE_STYLES[insight.tone])}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <p className="t-body font-medium text-foreground">{insight.headline}</p>
                  {insight.limited_data ? <Badge variant="neutral">Limited data</Badge> : null}
                </div>
                <p className="t-caption mt-1 text-muted-foreground">{insight.detail}</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {Object.entries(insight.support).map(([key, value]) => (
                    <span
                      key={key}
                      className="t-caption rounded-md bg-muted px-1.5 py-0.5 font-mono text-muted-foreground"
                    >
                      {key}={String(value)}
                    </span>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

function GapsPanel({ gaps }: { gaps: { question: string; needed: string }[] }) {
  if (gaps.length === 0) return null
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <span className="flex size-6 items-center justify-center rounded-lg bg-muted text-muted-foreground">
            <CircleHelp className="size-3.5" aria-hidden />
          </span>
          What this data can't answer yet
        </CardTitle>
        <CardDescription>
          Questions a real scheduling analytics product would answer, and the field FlightFlow would need
          to answer them. Listed rather than approximated.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <dl className="space-y-3">
          {gaps.map((gap) => (
            <div key={gap.question} className="border-l-2 border-l-border pl-3.5">
              <dt className="t-body font-medium text-foreground">{gap.question}</dt>
              <dd className="t-caption mt-0.5 text-muted-foreground">{gap.needed}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  )
}

function RecoveryStats({ data }: { data: AnalyticsResponse }) {
  const o = data.overview
  const stats = [
    { label: 'Mean time to rebook', value: `${o.avg_recovery_seconds}s`, hint: 'saga created → completed', icon: Timer },
    { label: 'Added passenger delay', value: `${o.avg_rebooked_delay_minutes} min`, hint: 'mean over rebooked itineraries', icon: Clock },
    { label: 'Sagas needing a retry', value: `${o.retry_rate_pct}%`, hint: `${data.recovery.sagas.retried} of ${o.sagas}`, icon: RefreshCw },
    { label: 'Dead letters', value: `${o.dead_letters}`, hint: 'steps parked after exhausting retries', icon: AlertTriangle },
  ]

  return (
    <Card>
      <CardHeader>
        <CardTitle>Recovery performance</CardTitle>
        <CardDescription>How the saga machinery behaved across the selected runs.</CardDescription>
      </CardHeader>
      <CardContent>
        <dl className="grid gap-4 sm:grid-cols-2">
          {stats.map((s) => (
            <div key={s.label} className="flex items-start gap-2.5">
              <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                <s.icon className="size-3.5" aria-hidden />
              </span>
              <div className="min-w-0">
                <dt className="t-label text-muted-foreground">{s.label}</dt>
                <dd className="t-section tabular-nums text-foreground">{s.value}</dd>
                <p className="t-caption text-muted-foreground">{s.hint}</p>
              </div>
            </div>
          ))}
        </dl>
        <SourceNote>
          <code>sagas</code> and <code>dead_letters</code> for the selected runs. Wall-clock time, so the
          date filter applies here.
        </SourceNote>
      </CardContent>
    </Card>
  )
}

function LoadingSkeleton() {
  return (
    <div className="flex flex-col gap-6">
      <Skeleton className="h-12 w-full rounded-xl" />
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="h-28 rounded-xl" />
        ))}
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <Skeleton className="h-80 rounded-xl" />
        <Skeleton className="h-80 rounded-xl" />
      </div>
    </div>
  )
}

// ---- page --------------------------------------------------------------

export function AnalyticsPage() {
  const [window, setWindow] = React.useState('30')
  const [runId, setRunId] = React.useState(ALL_RUNS)

  const windowDays = window === 'all' ? null : Number(window)

  const runs = useQuery({ queryKey: ['runs', 50], queryFn: () => api.listRuns(50) })

  const analytics = useQuery({
    queryKey: ['analytics', runId, windowDays],
    queryFn: () =>
      api.getAnalytics({ runId: runId === ALL_RUNS ? null : runId, windowDays, topN: 8 }),
    refetchInterval: 15000,
  })

  if (analytics.isLoading) return <LoadingSkeleton />

  if (analytics.isError) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader eyebrow="Analyse" title="Flight analytics" description="Scheduling and operations analytics over the FlightFlow database." />
        <Card>
          <CardHeader>
            <CardTitle>Analytics unavailable</CardTitle>
            <CardDescription>
              The API did not return analytics. Check that the stack is running, then retry.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="t-caption font-mono text-destructive">{(analytics.error as Error).message}</p>
          </CardContent>
        </Card>
      </div>
    )
  }

  const data = analytics.data!

  if (!data.provenance.has_flight_data) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader
          eyebrow="Analyse"
          title="Flight analytics"
          description="Scheduling and operations analytics over the FlightFlow database."
        />
        <EmptyState
          title="No flight network loaded"
          description="Analytics reads the flights, bookings and sagas in Postgres. Generate a scenario and load it from Run Control — or run `make seed` — and this page fills in."
          ctaLabel="Go to Run Control"
          ctaTo="/"
        />
      </div>
    )
  }

  const runOptions = runs.data ?? []

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Analyse"
        title="Flight analytics"
        description="Scheduling and operations analytics computed over the FlightFlow database: what the schedule looks like, where disruption landed, and how well passengers were recovered."
      />

      <ProvenanceStrip data={data} />

      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-48">
          <label className="t-label mb-1.5 block text-muted-foreground" htmlFor="analytics-window">
            Run window
          </label>
          <Select value={window} onValueChange={setWindow}>
            <SelectTrigger id="analytics-window">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {WINDOWS.map((w) => (
                <SelectItem key={w.value} value={w.value}>
                  {w.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="min-w-56">
          <label className="t-label mb-1.5 block text-muted-foreground" htmlFor="analytics-run">
            Run
          </label>
          <Select value={runId} onValueChange={setRunId}>
            <SelectTrigger id="analytics-run">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_RUNS}>All runs in window</SelectItem>
              {runOptions.map((r) => (
                <SelectItem key={r.id} value={r.id}>
                  {(r.preset ?? 'run')} · {r.strategy} · seed {r.seed}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <p className="t-caption flex items-center gap-1.5 pb-2 text-muted-foreground">
          <CalendarClock className="size-3.5" aria-hidden />
          {data.provenance.runs_covered} run{data.provenance.runs_covered === 1 ? '' : 's'} in scope. The
          filters apply to recovery analytics; the flight schedule itself is one synthetic day.
        </p>
      </div>

      <KpiRow data={data} />

      {!data.provenance.has_recovery_data ? (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-xl border border-dashed border-input bg-card/60 px-4 py-3">
          <Badge variant="neutral">No runs in scope</Badge>
          <p className="t-caption text-muted-foreground">
            The schedule panels below are populated, but recovery analytics need a run. Widen the window
            or start a run from Run Control.
          </p>
        </div>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-2">
        <DeparturesByHour rows={data.schedule.by_hour} />
        <DelayDistribution
          rows={data.schedule.delay_histogram}
          avg={data.schedule.flights.avg_delay_minutes}
          max={data.schedule.flights.max_delay_minutes}
        />
        <DisruptionCauses rows={data.recovery.disruption_causes} />
        <RecoveryByCause rows={data.recovery.recovery_by_cause} />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <RouteTable data={data} />
        <AirportTable data={data} />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <InsightsPanel insights={data.insights} />
        <div className="flex flex-col gap-4">
          <RecoveryStats data={data} />
          <GapsPanel gaps={data.gaps} />
        </div>
      </div>

      <p className="t-caption flex items-center gap-1.5 text-muted-foreground">
        <TrendingUp className="size-3.5" aria-hidden />
        Refreshes every 15 seconds while this page is open.
      </p>
    </div>
  )
}
