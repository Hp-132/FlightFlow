import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  Ban,
  Bell,
  CheckCircle2,
  Loader2,
  Luggage,
  PlaneTakeoff,
  RotateCcw,
  Search,
  Ticket,
  Undo2,
  Armchair,
  UserPlus,
} from 'lucide-react'
import * as React from 'react'
import { toast } from 'sonner'

import { AddPassengerForm } from '@/components/add-passenger-form'
import { PageHeader } from '@/components/page-header'
import { SagaStateBadge } from '@/components/saga-state-badge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton, SkeletonText } from '@/components/ui/skeleton'
import {
  api,
  apiErrorMessage,
  type PassengerDetail,
  type PassengerRow,
  type PassengerSegment,
  type SagaEvent,
} from '@/lib/api'
import { formatUtcTime, titleCase } from '@/lib/format'
import { cn } from '@/lib/utils'

/** Event type → icon + tone. Falls back sensibly for anything new. */
function eventMeta(type: string) {
  if (type.endsWith('_RETRY')) return { icon: RotateCcw, tone: 'warning' as const }
  if (type.startsWith('HOLD_SEATS') || type.startsWith('RELEASE_SEATS')) return { icon: Armchair, tone: 'progress' as const }
  if (type.startsWith('ISSUE_TICKET')) return { icon: Ticket, tone: 'progress' as const }
  if (type.startsWith('VOID_TICKET')) return { icon: Undo2, tone: 'warning' as const }
  if (type.startsWith('RETAG_BAGS')) return { icon: Luggage, tone: 'progress' as const }
  if (type === 'COMPLETED') return { icon: CheckCircle2, tone: 'success' as const }
  if (type === 'COMPENSATING' || type === 'COMPENSATED') return { icon: Undo2, tone: 'warning' as const }
  if (type === 'FAILED_NO_CAPACITY') return { icon: Ban, tone: 'destructive' as const }
  if (type === 'NEEDS_MANUAL') return { icon: AlertTriangle, tone: 'destructive' as const }
  if (type === 'NOTIFY' || type.startsWith('NOTIFY')) return { icon: Bell, tone: 'progress' as const }
  return { icon: CheckCircle2, tone: 'neutral' as const }
}

const TONE_CLASS = {
  neutral: 'bg-muted text-muted-foreground ring-card',
  progress: 'bg-secondary/15 text-secondary ring-card',
  success: 'bg-success/15 text-success ring-card',
  warning: 'bg-warning/15 text-warning ring-card',
  destructive: 'bg-destructive/15 text-destructive ring-card',
}

function formatGap(ms: number): string {
  if (ms < 1000) return `+${ms}ms`
  if (ms < 60_000) return `+${(ms / 1000).toFixed(1)}s`
  return `+${Math.round(ms / 60_000)}m`
}

function EventTimeline({ events }: { events: SagaEvent[] }) {
  const first = events.length ? new Date(events[0].created_at).getTime() : 0

  return (
    <ol className="relative ml-4 flex flex-col gap-4 border-l border-border pl-6">
      {events.map((e, i) => {
        const { icon: Icon, tone } = eventMeta(e.type)
        const at = new Date(e.created_at).getTime()
        const sincePrev = i === 0 ? 0 : at - new Date(events[i - 1].created_at).getTime()
        const payloadKeys = Object.keys(e.payload ?? {})

        return (
          <li key={e.seq} className="relative">
            <span
              className={cn(
                'absolute -left-[2.35rem] flex size-6 items-center justify-center rounded-full ring-4',
                TONE_CLASS[tone],
              )}
            >
              <Icon className="size-3" aria-hidden />
            </span>

            <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
              <span className="t-section text-foreground">{e.type.replaceAll('_', ' ').toLowerCase()}</span>
              <span className="t-caption text-muted-foreground">
                {new Date(e.created_at).toLocaleTimeString()}
              </span>
              {i > 0 && (
                <span className="t-caption rounded-full bg-muted px-1.5 py-0.5 tabular-nums text-muted-foreground">
                  {formatGap(sincePrev)}
                </span>
              )}
            </div>

            {payloadKeys.length > 0 && (
              <div className="mt-1.5 overflow-x-auto rounded-md bg-muted">
                <pre className="t-caption w-max px-2.5 py-1.5 font-mono text-muted-foreground">
                  {JSON.stringify(e.payload)}
                </pre>
              </div>
            )}
          </li>
        )
      })}

      {events.length > 1 && (
        <li className="t-caption -ml-1 text-muted-foreground">
          total {formatGap(new Date(events[events.length - 1].created_at).getTime() - first)} end to end
        </li>
      )}
    </ol>
  )
}

const TERMINAL = new Set(['COMPLETED', 'COMPENSATED', 'FAILED_NO_CAPACITY', 'NEEDS_MANUAL'])
const POLL_MS = 1500

const CAUSES = [
  { value: 'WEATHER', label: 'Weather' },
  { value: 'AOG', label: 'Aircraft fault (AOG)' },
  { value: 'CREW', label: 'Crew shortage' },
  { value: 'ATC', label: 'Air traffic control' },
]

const HISTORY_FILTERS = [
  { value: 'all', label: 'All passengers' },
  { value: 'with', label: 'Only with rebooking history' },
]

function isPending(row: PassengerRow): boolean {
  return row.saga_state ? !TERMINAL.has(row.saga_state) : row.booking_status === 'DISRUPTED'
}

function RowBadge({ row }: { row: PassengerRow }) {
  if (row.saga_state) return <SagaStateBadge state={row.saga_state} />
  if (row.booking_status === 'DISRUPTED') return <Badge variant="progress">queued</Badge>
  return <Badge variant="neutral">not disrupted</Badge>
}

function Itinerary({ segments }: { segments: PassengerSegment[] }) {
  return (
    <ol className="flex flex-col gap-2">
      {segments.map((s) => (
        <li
          key={s.seq}
          className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-border bg-surface-alt/30 px-3 py-2"
        >
          <span className="t-section font-mono text-foreground">{s.flight_no}</span>
          <span className="t-body text-foreground">
            {s.origin} → {s.dest}
          </span>
          <span className="t-caption text-muted-foreground">
            {formatUtcTime(s.sched_dep_at)} · {titleCase(s.cabin)}
          </span>
          <Badge
            className="ml-auto"
            variant={s.status === 'CANCELLED' ? 'destructive' : s.status === 'DELAYED' ? 'warning' : 'neutral'}
          >
            {titleCase(s.status)}
          </Badge>
        </li>
      ))}
    </ol>
  )
}

function SimulateDisruption({ detail, onDone }: { detail: PassengerDetail; onDone: () => void }) {
  const [cause, setCause] = React.useState('WEATHER')
  const flight = detail.segments[0]

  const disrupt = useMutation({
    mutationFn: () => api.disruptPassenger(detail.booking_id, cause),
    onSuccess: (r) => {
      toast.success(
        `${r.flight_no} cancelled: ${r.disrupted_bookings} passenger${r.disrupted_bookings === 1 ? '' : 's'} queued for rebooking`,
      )
      onDone()
    },
    onError: (err) => toast.error(apiErrorMessage(err)),
  })

  return (
    <div className="flex flex-col gap-4 rounded-lg border border-dashed border-input bg-card/60 p-4">
      <div>
        <p className="t-section text-foreground">Not disrupted yet</p>
        <p className="t-caption mt-1 text-muted-foreground">
          Cancel {flight.flight_no} ({flight.origin} → {flight.dest}) to put this passenger through the full
          recovery: the planner looks for another direct flight on the same route in the next 48 hours, then the
          workers hold seats, issue the ticket, retag bags and notify the passenger.
          {detail.others_on_flight > 0 &&
            ` ${detail.others_on_flight} other passenger${detail.others_on_flight === 1 ? ' is' : 's are'} booked on ${flight.flight_no} and will be rebooked with them.`}
        </p>
        <p className={cn('t-caption mt-1', detail.direct_alternatives > 0 ? 'text-muted-foreground' : 'text-warning')}>
          {detail.direct_alternatives > 0
            ? `${detail.direct_alternatives} direct alternative${detail.direct_alternatives === 1 ? '' : 's'} available.`
            : 'No direct alternative exists, so the planner can only try a connection and may end with no capacity.'}
        </p>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex min-w-52 flex-col gap-1.5">
          <span className="text-xs font-medium text-muted-foreground">Cause</span>
          <Select value={cause} onValueChange={setCause}>
            <SelectTrigger aria-label="Disruption cause">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {CAUSES.map((c) => (
                <SelectItem key={c.value} value={c.value}>
                  {c.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button onClick={() => disrupt.mutate()} disabled={disrupt.isPending}>
          <PlaneTakeoff />
          {disrupt.isPending ? 'Cancelling…' : `Cancel ${flight.flight_no} and rebook`}
        </Button>
      </div>
    </div>
  )
}

function SagaTimeline({ sagaId }: { sagaId: string }) {
  const saga = useQuery({
    queryKey: ['saga-detail', sagaId],
    queryFn: () => api.getSagaEvents(sagaId),
    refetchInterval: (q) => (q.state.data && !TERMINAL.has(q.state.data.state) ? POLL_MS : false),
  })

  if (saga.isLoading || !saga.data) return <SkeletonText lines={6} />

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3 border-b border-border/70 pb-4">
        <SagaStateBadge state={saga.data.state} />
        <span className="t-caption text-muted-foreground">
          current step:{' '}
          <span className="font-medium text-foreground">{saga.data.current_step ?? 'none (terminal)'}</span>
        </span>
        <span className="t-caption text-muted-foreground">
          priority: <span className="font-medium text-foreground">{saga.data.priority}</span>
        </span>
        <span className="t-caption ml-auto font-mono text-muted-foreground">{saga.data.saga_id.slice(0, 8)}</span>
      </div>
      <EventTimeline events={saga.data.events} />
    </div>
  )
}

function PassengerPanel({ bookingId, onMissing }: { bookingId: string; onMissing: () => void }) {
  const queryClient = useQueryClient()

  const detail = useQuery({
    queryKey: ['passenger', bookingId],
    queryFn: () => api.getPassenger(bookingId),
    retry: false,
    refetchInterval: (q) => {
      const d = q.state.data
      if (!d) return false
      if (d.saga) return TERMINAL.has(d.saga.state) ? false : POLL_MS
      return d.can_disrupt ? false : POLL_MS
    },
  })

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['passenger', bookingId] })
    queryClient.invalidateQueries({ queryKey: ['passengers'] })
  }

  if (detail.isError) {
    return (
      <Card>
        <CardContent className="flex flex-col items-start gap-3 py-6">
          <p className="t-body text-muted-foreground">
            This passenger is no longer in the database. Loading a new scenario replaces every passenger.
          </p>
          <Button variant="outline" size="sm" onClick={onMissing}>
            Back to the list
          </Button>
        </CardContent>
      </Card>
    )
  }

  if (!detail.data) {
    return (
      <Card>
        <CardContent className="py-6">
          <SkeletonText lines={5} />
        </CardContent>
      </Card>
    )
  }

  const d = detail.data
  const waitingForPlanner = !d.saga && !d.can_disrupt

  return (
    <Card className="min-w-0">
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle>{d.passenger.name}</CardTitle>
          <Badge variant="primary">{d.passenger.airline}</Badge>
          {d.passenger.tier !== 'NONE' && <Badge variant="warning">{titleCase(d.passenger.tier)}</Badge>}
          {d.passenger.is_unaccompanied_minor && <Badge variant="neutral">unaccompanied minor</Badge>}
        </div>
        <CardDescription>
          <span title="Passenger Name Record: the booking reference printed on the ticket">PNR</span>{' '}
          <span className="font-mono font-medium text-foreground">{d.pnr}</span> · {d.passenger.bags} checked bag
          {d.passenger.bags === 1 ? '' : 's'}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex min-w-0 flex-col gap-5">
        <div>
          <p className="t-label mb-2 text-muted-foreground">Original itinerary</p>
          <Itinerary segments={d.segments} />
        </div>

        {d.saga && <SagaTimeline sagaId={d.saga.id} />}

        {waitingForPlanner && (
          <p className="t-body flex items-center gap-2 text-muted-foreground" role="status">
            <Loader2 className="size-4 animate-spin" aria-hidden />
            Flight cancelled. Waiting for the planner to pick this booking up…
          </p>
        )}

        {!d.saga && d.can_disrupt && <SimulateDisruption detail={d} onDone={refresh} />}
      </CardContent>
    </Card>
  )
}

export function SagaInspectorPage() {
  const queryClient = useQueryClient()
  const [query, setQuery] = React.useState('')
  const [debounced, setDebounced] = React.useState('')
  const [history, setHistory] = React.useState<'all' | 'with'>('all')
  const [selectedId, setSelectedId] = React.useState<string | null>(null)
  const [adding, setAdding] = React.useState(false)

  React.useEffect(() => {
    const id = setTimeout(() => setDebounced(query.trim()), 250)
    return () => clearTimeout(id)
  }, [query])

  const passengers = useQuery({
    queryKey: ['passengers', debounced, history],
    queryFn: () => api.listPassengers({ q: debounced, history, limit: 50 }),
    placeholderData: keepPreviousData,
    refetchInterval: (q) => (q.state.data?.items.some(isPending) ? 2500 : false),
  })

  const rows = passengers.data?.items ?? []

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Verify"
        title="Passenger history"
        description="Pick a passenger to replay every step of their rebooking. Each one has a PNR, the booking reference printed on their ticket, so there is nothing to memorise: choose from the list, or add your own."
        actions={
          <Button onClick={() => setAdding(true)} disabled={adding}>
            <UserPlus />
            Add passenger
          </Button>
        }
      />

      <div className="grid min-w-0 gap-4 lg:grid-cols-[340px_minmax(0,1fr)]">
        <Card className="h-fit min-w-0">
          <CardHeader>
            <CardTitle>
              Passengers
              {passengers.data && (
                <span className="ml-2 t-caption font-normal text-muted-foreground">
                  {rows.length} of {passengers.data.total.toLocaleString()}
                </span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 p-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <Input
                className="pl-9"
                placeholder="Search name or PNR…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                aria-label="Search passengers by name or PNR"
              />
            </div>
            <Select value={history} onValueChange={(v) => setHistory(v as 'all' | 'with')}>
              <SelectTrigger aria-label="Which passengers to list">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {HISTORY_FILTERS.map((f) => (
                  <SelectItem key={f.value} value={f.value}>
                    {f.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <div className="flex max-h-[30rem] flex-col gap-1 overflow-y-auto">
              {passengers.isLoading && (
                <div className="space-y-2">
                  <Skeleton className="h-14 w-full" />
                  <Skeleton className="h-14 w-full" />
                  <Skeleton className="h-14 w-full" />
                </div>
              )}
              {passengers.isError && (
                <p className="t-caption px-1 py-2 text-destructive">Couldn't load passengers. Is the API running?</p>
              )}
              {passengers.data && rows.length === 0 && (
                <p className="t-caption px-1 py-2 text-muted-foreground">
                  {debounced
                    ? `No passenger matches “${debounced}”.`
                    : history === 'with'
                      ? 'No passenger has been rebooked yet. Switch to all passengers, or start a run.'
                      : 'No passengers are loaded. Start a run from Run Control, or load a scenario first.'}
                </p>
              )}
              {rows.map((r) => (
                <button
                  key={r.booking_id}
                  type="button"
                  onClick={() => {
                    setAdding(false)
                    setSelectedId(r.booking_id)
                  }}
                  aria-current={selectedId === r.booking_id && !adding}
                  className={cn(
                    'flex flex-col items-stretch gap-1 rounded-md border px-3 py-2 text-left transition-all duration-150',
                    selectedId === r.booking_id && !adding
                      ? 'border-secondary/50 bg-secondary/[0.07]'
                      : 'border-transparent hover:border-border hover:bg-muted',
                  )}
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className="t-section truncate text-foreground">{r.name}</span>
                    <RowBadge row={r} />
                  </span>
                  <span className="t-caption flex items-center justify-between gap-2 text-muted-foreground">
                    <span className="font-mono">{r.pnr}</span>
                    <span className="truncate">
                      {r.origin} → {r.dest} · {r.flights}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          </CardContent>
        </Card>

        <div className="min-w-0">
          {adding ? (
            <AddPassengerForm
              onCancel={() => setAdding(false)}
              onCreated={(created) => {
                toast.success(`Added ${created.name} on ${created.flight_no}. Their PNR is ${created.pnr}.`)
                queryClient.invalidateQueries({ queryKey: ['passengers'] })
                setQuery('')
                setAdding(false)
                setSelectedId(created.booking_id)
              }}
            />
          ) : selectedId ? (
            <PassengerPanel
              key={selectedId}
              bookingId={selectedId}
              onMissing={() => {
                setSelectedId(null)
                queryClient.invalidateQueries({ queryKey: ['passengers'] })
              }}
            />
          ) : (
            <Card>
              <CardContent className="py-8">
                <p className="t-body text-muted-foreground">
                  Select a passenger on the left to see their itinerary and replay their saga step by step. Passengers
                  who have already been rebooked are listed first.
                </p>
                <p className="t-body mt-3 text-muted-foreground">
                  Want a passenger of your own? Use <span className="font-medium text-foreground">Add passenger</span>,
                  then cancel their flight to watch the whole recovery run.
                </p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
