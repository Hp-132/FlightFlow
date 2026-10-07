import { useQuery } from '@tanstack/react-query'
import {
  AlertTriangle,
  Ban,
  Bell,
  CheckCircle2,
  Luggage,
  RotateCcw,
  Search,
  Ticket,
  Undo2,
  Armchair,
} from 'lucide-react'
import * as React from 'react'

import { PageHeader } from '@/components/page-header'
import { SagaStateBadge } from '@/components/saga-state-badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton, SkeletonText } from '@/components/ui/skeleton'
import { api, type SagaEvent } from '@/lib/api'
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

export function SagaInspectorPage() {
  const [query, setQuery] = React.useState('')
  const [debounced, setDebounced] = React.useState('')
  const [selectedSagaId, setSelectedSagaId] = React.useState<string | null>(null)

  React.useEffect(() => {
    const id = setTimeout(() => setDebounced(query), 250)
    return () => clearTimeout(id)
  }, [query])

  const search = useQuery({
    queryKey: ['saga-search', debounced],
    queryFn: () => api.searchSagas(debounced),
    enabled: debounced.length >= 2,
  })

  const detail = useQuery({
    queryKey: ['saga-detail', selectedSagaId],
    queryFn: () => api.getSagaEvents(selectedSagaId!),
    enabled: !!selectedSagaId,
  })

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Verify"
        title="Passenger history"
        description="Search for a passenger by booking code (PNR) or name to see every step of their rebooking, in order."
      />

      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
        <Input
          className="pl-9"
          placeholder="Search PNR or passenger name…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search sagas by PNR or passenger name"
        />
      </div>

      {/* min-w-0 on the grid children so a long JSON payload scrolls inside
          its own box instead of stretching the whole column. */}
      <div className="grid min-w-0 gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
        <Card className="h-fit min-w-0">
          <CardHeader>
            <CardTitle>
              Results
              {search.data && (
                <span className="ml-2 t-caption font-normal text-muted-foreground">{search.data.length}</span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="flex max-h-[32rem] flex-col gap-1 overflow-y-auto p-2">
            {debounced.length < 2 && (
              <p className="t-caption px-3 py-2 text-muted-foreground">Type at least 2 characters to search.</p>
            )}
            {search.isLoading && debounced.length >= 2 && (
              <div className="space-y-2 p-2">
                <Skeleton className="h-14 w-full" />
                <Skeleton className="h-14 w-full" />
                <Skeleton className="h-14 w-full" />
              </div>
            )}
            {search.data?.length === 0 && (
              <p className="t-caption px-3 py-2 text-muted-foreground">
                No passenger matches “{debounced}”.
              </p>
            )}
            {search.data?.map((r) => (
              <button
                key={r.saga_id}
                onClick={() => setSelectedSagaId(r.saga_id)}
                aria-current={selectedSagaId === r.saga_id}
                className={cn(
                  'flex flex-col items-start gap-1 rounded-md border px-3 py-2 text-left transition-all duration-150',
                  selectedSagaId === r.saga_id
                    ? 'border-secondary/50 bg-secondary/[0.07]'
                    : 'border-transparent hover:border-border hover:bg-muted',
                )}
              >
                <div className="flex w-full items-center justify-between gap-2">
                  <span className="t-section font-mono text-foreground">{r.pnr}</span>
                  <SagaStateBadge state={r.state} />
                </div>
                <span className="t-caption text-muted-foreground">{r.passenger_name}</span>
              </button>
            ))}
          </CardContent>
        </Card>

        <Card className="min-w-0">
          <CardHeader>
            <CardTitle>Timeline</CardTitle>
          </CardHeader>
          <CardContent className="min-w-0">
            {!selectedSagaId && (
              <p className="t-body text-muted-foreground">
                Select a passenger on the left to replay their saga step by step.
              </p>
            )}

            {selectedSagaId && detail.isLoading && <SkeletonText lines={6} />}

            {detail.data && (
              <div className="flex flex-col gap-5">
                <div className="flex flex-wrap items-center gap-3 border-b border-border/70 pb-4">
                  <SagaStateBadge state={detail.data.state} />
                  <span className="t-caption text-muted-foreground">
                    current step:{' '}
                    <span className="font-medium text-foreground">
                      {detail.data.current_step ?? 'none (terminal)'}
                    </span>
                  </span>
                  <span className="t-caption text-muted-foreground">
                    priority: <span className="font-medium text-foreground">{detail.data.priority}</span>
                  </span>
                  <span className="t-caption ml-auto font-mono text-muted-foreground">
                    {detail.data.saga_id.slice(0, 8)}
                  </span>
                </div>

                <EventTimeline events={detail.data.events} />
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
