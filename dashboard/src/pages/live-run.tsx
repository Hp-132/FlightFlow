import { useQuery } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  CloudLightning,
  GitBranch,
  Pause,
  Play,
  RefreshCw,
  Undo2,
  UserRound,
  UsersRound,
  Wrench,
} from 'lucide-react'
import * as React from 'react'
import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { AnimatedNumber } from '@/components/animated-number'
import { ChartTooltip } from '@/components/chart-tooltip'
import { EmptyState } from '@/components/empty-state'
import { StatCard } from '@/components/stat-card'
import { StateDistribution } from '@/components/state-distribution'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { api, type DisruptionEvent } from '@/lib/api'
import { AXIS_TICK } from '@/lib/chart'
import { useActiveRun } from '@/lib/run-context'
import { formatElapsed, useSeedFixture } from '@/lib/seed-fixture'
import { useRunStream } from '@/lib/use-run-stream'
import { cn } from '@/lib/utils'

const NON_TERMINAL = ['PLANNED', 'HOLDING', 'TICKETING', 'BAGGAGE', 'NOTIFYING', 'COMPENSATING']

const CAUSE_META: Record<string, { label: string; icon: typeof CloudLightning; dot: string; text: string }> = {
  WEATHER: { label: 'Weather', icon: CloudLightning, dot: 'bg-secondary', text: 'text-secondary' },
  AOG: { label: 'Aircraft (AOG)', icon: Wrench, dot: 'bg-warning', text: 'text-warning' },
  CREW: { label: 'Crew', icon: UserRound, dot: 'bg-destructive', text: 'text-destructive' },
  CASCADE: { label: 'Cascade', icon: GitBranch, dot: 'bg-primary', text: 'text-primary' },
  ATC: { label: 'ATC', icon: AlertTriangle, dot: 'bg-muted-foreground', text: 'text-muted-foreground' },
}

interface HistoryPoint {
  t: number
  label: string
  completed: number
  inFlight: number
  queueDepth: number
  workers: number
}

const HISTORY_LIMIT = 60

function DisruptionTimeline({ events }: { events: DisruptionEvent[] }) {
  const byCause = React.useMemo(() => {
    const counts: Record<string, number> = {}
    for (const e of events) counts[e.cause] = (counts[e.cause] ?? 0) + 1
    return counts
  }, [events])

  const { start, span } = React.useMemo(() => {
    const times = events.map((e) => new Date(e.occurred_at).getTime())
    const min = Math.min(...times)
    const max = Math.max(...times)
    return { start: min, span: Math.max(1, max - min) }
  }, [events])

  if (events.length === 0) {
    return <p className="t-body text-muted-foreground">No disruption events recorded yet.</p>
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap gap-2">
        {Object.entries(byCause)
          .sort((a, b) => b[1] - a[1])
          .map(([cause, count]) => {
            const meta = CAUSE_META[cause] ?? CAUSE_META.ATC
            const Icon = meta.icon
            return (
              <span
                key={cause}
                className="flex items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1 shadow-card"
              >
                <Icon className={cn('size-3.5', meta.text)} aria-hidden />
                <span className="t-label text-muted-foreground">{meta.label}</span>
                <span className="t-label font-semibold text-foreground">{count}</span>
              </span>
            )
          })}
      </div>

      {/* Events positioned by when they actually occurred in scenario time. */}
      <div>
        <div className="relative h-14 rounded-lg border border-border bg-surface-alt/25">
          <div className="absolute inset-x-3 top-1/2 h-px -translate-y-1/2 bg-border" aria-hidden />
          {events.map((e) => {
            const meta = CAUSE_META[e.cause] ?? CAUSE_META.ATC
            const pct = ((new Date(e.occurred_at).getTime() - start) / span) * 100
            return (
              <span
                key={e.id}
                title={`${meta.label} · ${e.type} · ${new Date(e.occurred_at).toLocaleString()}`}
                style={{ left: `calc(${Math.min(98, Math.max(1, pct))}% )` }}
                className={cn(
                  'absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-card transition-transform hover:scale-150',
                  meta.dot,
                  e.type === 'CANCELLATION' ? 'opacity-100' : 'opacity-60',
                )}
              />
            )
          })}
        </div>
        <div className="mt-1.5 flex justify-between">
          <span className="t-caption text-muted-foreground">
            {new Date(start).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
          </span>
          <span className="t-caption text-muted-foreground">scenario time →</span>
          <span className="t-caption text-muted-foreground">
            {new Date(start + span).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>
      </div>

      <p className="t-caption text-muted-foreground">
        Solid dots are cancellations, faded dots are delays. Hover any dot for its cause and timestamp.
      </p>
    </div>
  )
}

export function LiveRunPage() {
  const { runId, presetLabel, strategy } = useActiveRun()
  const { data, connected } = useRunStream(runId)
  const [history, setHistory] = React.useState<HistoryPoint[]>([])
  const [paused, setPaused] = React.useState(false)

  // Nothing to show from the live API: either no run was started this
  // session, or there is a run but it has disrupted nobody. Either way the
  // seeded fixture stands in, so the page is never blank on a fresh boot.
  const liveBookings = data?.bookings_by_status ?? {}
  const liveAffected =
    (liveBookings.DISRUPTED ?? 0) + (liveBookings.REBOOKED ?? 0) + (liveBookings.UNRECOVERED ?? 0)
  const liveSagaTotal = Object.values(data?.sagas_by_state ?? {}).reduce((sum, n) => sum + n, 0)
  const liveEmpty = !runId || (!!data && liveAffected === 0 && liveSagaTotal === 0)

  const { fixture, loading: fixtureLoading } = useSeedFixture(liveEmpty)
  const usingFixture = liveEmpty && fixture !== null

  const disruptions = useQuery({
    queryKey: ['disruptions', runId],
    queryFn: () => api.getDisruptions(runId!),
    enabled: !!runId && !usingFixture,
    refetchInterval: paused ? false : 4000,
  })

  React.useEffect(() => {
    if (!data || paused) return
    setHistory((prev) => {
      const sagas = data.sagas_by_state
      const point: HistoryPoint = {
        t: Date.now(),
        label: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
        completed: sagas.COMPLETED ?? 0,
        inFlight: NON_TERMINAL.reduce((sum, s) => sum + (sagas[s] ?? 0), 0),
        queueDepth: data.queue_depth ?? 0,
        workers: data.workers_active ?? 0,
      }
      return [...prev, point].slice(-HISTORY_LIMIT)
    })
  }, [data, paused])

  // A fixture's samples carry offsets from the start of the run rather than
  // wall-clock times, so they get elapsed labels.
  const fixtureHistory = React.useMemo<HistoryPoint[]>(
    () =>
      usingFixture
        ? fixture.history.map((p) => ({
            t: p.offset_seconds,
            label: formatElapsed(p.offset_seconds),
            completed: p.completed,
            inFlight: p.inFlight,
            queueDepth: p.queueDepth,
            workers: p.workers,
          }))
        : [],
    [usingFixture, fixture],
  )

  if (liveEmpty && !usingFixture) {
    if (fixtureLoading) {
      return (
        <div className="flex flex-col gap-6">
          <Skeleton className="h-40 w-full rounded-2xl" />
          <Skeleton className="h-24 w-full" />
        </div>
      )
    }
    return (
      <EmptyState
        title="No run started yet"
        description="Head to Run Control, pick a scenario, and start a run to watch the system react to it live."
        ctaLabel="Go to Run Control"
        ctaTo="/"
      />
    )
  }

  const counters = usingFixture ? fixture.counters : data
  const chartHistory = usingFixture ? fixtureHistory : history
  const timelineEvents = usingFixture ? fixture.disruptions : (disruptions.data ?? [])
  const timelineLoading = !usingFixture && disruptions.isLoading
  const effectiveStrategy = usingFixture ? fixture.params.strategy : strategy
  const effectiveRunId = usingFixture ? fixture.run.run_id : runId
  const effectiveLabel = usingFixture
    ? `${fixture.params.preset} · seed ${fixture.params.seed}`
    : (presetLabel ?? 'Live run')

  const sagas = counters?.sagas_by_state ?? {}
  const bookings = counters?.bookings_by_status ?? {}
  const affected = (bookings.DISRUPTED ?? 0) + (bookings.REBOOKED ?? 0) + (bookings.UNRECOVERED ?? 0)
  const totalSagas = Object.values(sagas).reduce((sum, n) => sum + n, 0)
  const inFlight = NON_TERMINAL.reduce((sum, s) => sum + (sagas[s] ?? 0), 0)
  const completed = sagas.COMPLETED ?? 0
  const settled = totalSagas > 0 && inFlight === 0
  const progressPct = totalSagas > 0 ? ((totalSagas - inFlight) / totalSagas) * 100 : 0
  const recoveredPct = totalSagas > 0 ? (completed / totalSagas) * 100 : 0
  const loading = !usingFixture && !data

  return (
    <div className="flex flex-col gap-6">
      {/* One live region for the whole run: a meaningful sentence rather
          than ten competing badges each announcing a bare number. */}
      <p role="status" aria-atomic="true" className="sr-only">
        {usingFixture
          ? `Showing seeded sample data: ${completed.toLocaleString()} of ${totalSagas.toLocaleString()} sagas completed. Start a run to see live numbers.`
          : loading
            ? 'Connecting to the run stream.'
            : `${completed.toLocaleString()} of ${totalSagas.toLocaleString()} sagas completed, ${inFlight.toLocaleString()} still in flight.`}
      </p>

      {usingFixture ? (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-xl border border-border bg-surface-alt/40 px-4 py-3">
          <Badge variant="warning">Sample data</Badge>
          <p className="t-caption text-muted-foreground">
            No run has been started this session, so this is a seeded{' '}
            {fixture.params.preset}/{fixture.params.strategy} run captured{' '}
            {new Date(fixture.captured_at).toLocaleString(undefined, {
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
            })}
            . Start a run from Run Control to replace it with live numbers.
          </p>
        </div>
      ) : null}

      <section className="hero-grid overflow-hidden rounded-2xl px-5 py-5 text-white shadow-raised sm:px-7 sm:py-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  'flex items-center gap-1.5 rounded-full px-2 py-0.5',
                  !usingFixture && connected && !settled ? 'bg-success/25 text-white' : 'bg-white/15 text-white/90',
                )}
              >
                <span
                  className={cn(
                    'size-1.5 rounded-full',
                    !usingFixture && connected && !settled ? 'bg-success pulse-live' : 'bg-white/70',
                  )}
                  aria-hidden
                />
                <span className="t-caption font-semibold">
                  {usingFixture ? 'sample' : settled ? 'settled' : connected ? 'live' : 'reconnecting'}
                </span>
              </span>
              <span className="t-caption rounded-full bg-white/12 px-2 py-0.5 font-medium uppercase tracking-wide">
                {effectiveStrategy ?? 'greedy'}
              </span>
            </div>
            <h1 className="t-title mt-2 text-white">{effectiveLabel}</h1>
            <p className="t-caption mt-0.5 font-mono text-white/60">{effectiveRunId}</p>
          </div>

          <div className="text-right">
            <p className="t-overline text-white/60">Recovered</p>
            {loading ? (
              <Skeleton className="mt-1 h-9 w-28 bg-white/20" />
            ) : (
              <p className="t-display mt-0.5 text-white">
                <AnimatedNumber value={completed} />
                <span className="t-title font-normal text-white/50"> / {totalSagas.toLocaleString()}</span>
              </p>
            )}
            <p className="t-caption text-white/60">{recoveredPct.toFixed(1)}% of disrupted passengers</p>
          </div>
        </div>

        <div className="mt-5">
          <div className="mb-1.5 flex items-center justify-between">
            <span className="t-caption text-white/70">
              {settled ? 'All sagas terminal' : `${inFlight.toLocaleString()} sagas still working`}
            </span>
            <span className="t-caption tabular-nums text-white/70">{progressPct.toFixed(0)}% settled</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-white/15">
            <motion.div
              className="h-full rounded-full bg-white"
              initial={false}
              animate={{ width: `${progressPct}%` }}
              transition={{ duration: 0.5, ease: 'easeOut' }}
            />
          </div>
        </div>
      </section>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
        <StatCard label="Affected" value={affected} icon={UsersRound} hint="bookings disrupted" loading={loading} />
        <StatCard label="In flight" value={inFlight} total={totalSagas} tone="progress" icon={RefreshCw} loading={loading} />
        <StatCard label="Completed" value={completed} total={totalSagas} tone="success" icon={CheckCircle2} loading={loading} />
        <StatCard label="Compensated" value={sagas.COMPENSATED ?? 0} total={totalSagas} tone="warning" icon={Undo2} loading={loading} />
        <StatCard label="No capacity" value={sagas.FAILED_NO_CAPACITY ?? 0} total={totalSagas} tone="destructive" icon={Ban} loading={loading} />
        <StatCard label="Needs manual" value={sagas.NEEDS_MANUAL ?? 0} total={totalSagas} tone="destructive" icon={AlertTriangle} loading={loading} />
      </div>

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <div>
            <CardTitle>Saga states</CardTitle>
            <CardDescription>Every disrupted booking gets exactly one saga; this is where they all are.</CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? <Skeleton className="h-2.5 w-full" /> : <StateDistribution counts={sagas} />}
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader className="flex-row items-start justify-between">
            <div>
              <CardTitle>Recovery throughput</CardTitle>
              <CardDescription>Completed sagas against those still working.</CardDescription>
            </div>
            {usingFixture ? null : (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPaused((p) => !p)}
                aria-pressed={paused}
              >
                {paused ? <Play className="size-3.5" /> : <Pause className="size-3.5" />}
                {paused ? 'Resume' : 'Pause'}
              </Button>
            )}
          </CardHeader>
          <CardContent className="h-64 pt-2">
            {chartHistory.length === 0 ? (
              <div className="flex h-full items-center justify-center">
                <p className="t-caption text-muted-foreground">Waiting for the first sample…</p>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartHistory} margin={{ top: 4, right: 4, bottom: 0, left: -18 }}>
                  <defs>
                    <linearGradient id="fillCompleted" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="var(--color-success)" stopOpacity={0.28} />
                      <stop offset="100%" stopColor="var(--color-success)" stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="label" tick={AXIS_TICK} tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={40} />
                  <YAxis tick={AXIS_TICK} tickLine={false} axisLine={false} allowDecimals={false} width={44} />
                  <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--color-muted)', opacity: 0.5 }} />
                  <Area type="monotone" dataKey="completed" name="Completed" stroke="var(--color-success)" strokeWidth={2} fill="url(#fillCompleted)" />
                  <Line type="monotone" dataKey="inFlight" name="In flight" stroke="var(--color-secondary)" strokeWidth={2} dot={false} strokeDasharray="4 3" />
                </ComposedChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Workers vs queue depth</CardTitle>
            <CardDescription>
              Live from RabbitMQ and Prometheus — the same signal KEDA scales on.
            </CardDescription>
          </CardHeader>
          <CardContent className="h-64 pt-2">
            {chartHistory.length === 0 ? (
              <div className="flex h-full items-center justify-center">
                <p className="t-caption text-muted-foreground">Waiting for the first sample…</p>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartHistory} margin={{ top: 4, right: 4, bottom: 0, left: -18 }}>
                  <defs>
                    <linearGradient id="fillQueue" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="var(--color-secondary)" stopOpacity={0.45} />
                      <stop offset="100%" stopColor="var(--color-secondary)" stopOpacity={0.12} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="label" tick={AXIS_TICK} tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={40} />
                  <YAxis tick={AXIS_TICK} tickLine={false} axisLine={false} allowDecimals={false} width={44} />
                  <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--color-muted)', opacity: 0.5 }} />
                  <Bar dataKey="queueDepth" name="Queue depth" fill="url(#fillQueue)" radius={[4, 4, 0, 0]} />
                  <Line type="monotone" dataKey="workers" name="Workers active" stroke="var(--color-primary)" strokeWidth={2} dot={false} />
                </ComposedChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Disruption timeline</CardTitle>
          <CardDescription>
            What actually went wrong — the storm, background AOG/CREW noise, and cascading delays down a tail
            number's rotation.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {timelineLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-7 w-72" />
              <Skeleton className="h-14 w-full" />
            </div>
          ) : (
            <AnimatePresence mode="wait">
              <motion.div
                key={timelineEvents.length}
                initial={{ opacity: 0.4 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.2 }}
              >
                <DisruptionTimeline events={timelineEvents} />
              </motion.div>
            </AnimatePresence>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
