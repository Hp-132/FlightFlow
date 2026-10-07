import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Scale } from 'lucide-react'
import * as React from 'react'
import { toast } from 'sonner'

import { EmptyState } from '@/components/empty-state'
import { PageHeader } from '@/components/page-header'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { api } from '@/lib/api'
import { useActiveRun } from '@/lib/run-context'
import { cn } from '@/lib/utils'

export function TenantsPage() {
  const { runId } = useActiveRun()
  const queryClient = useQueryClient()
  const [defaultCap, setDefaultCap] = React.useState(8)

  const tenants = useQuery({
    queryKey: ['tenants', runId],
    queryFn: () => api.getTenants(runId!),
    enabled: !!runId,
    refetchInterval: 3000,
  })

  const fairness = useQuery({ queryKey: ['fairness'], queryFn: api.getFairness, refetchInterval: 3000 })

  const capMutation = useMutation({
    mutationFn: (cap: number) => api.setFairness({ default_cap: cap }),
    onSuccess: () => {
      toast.success('Concurrency cap updated')
      queryClient.invalidateQueries({ queryKey: ['fairness'] })
    },
    onError: (err: Error) => toast.error(err.message),
  })

  if (!runId) {
    return (
      <EmptyState
        title="No run started yet"
        description="Tenants shows how fairly the workers are split across airlines during a run. Start one first."
        ctaLabel="Go to Run Control"
        ctaTo="/"
      />
    )
  }

  const rows = tenants.data ?? []
  const caps = fairness.data?.caps ?? {}
  const inFlight = fairness.data?.in_flight ?? {}

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Analyse"
        title="Airlines"
        description="How well each airline's passengers were rebooked. A per-airline limit makes sure one busy airline can't slow down the others."
      />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <span className="flex size-6 items-center justify-center rounded-lg bg-secondary/12 text-secondary">
              <Scale className="size-3.5" aria-hidden />
            </span>
            Fairness cap
          </CardTitle>
          <CardDescription>
            Maximum saga steps any one airline may have in flight at once. 0 means unlimited. Steps over the cap
            are parked on a 2-second delay queue rather than dropped.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-4">
          <div className="w-40 space-y-1.5">
            <Label>Default cap</Label>
            <Input
              type="number"
              min={0}
              value={defaultCap}
              onChange={(e) => setDefaultCap(Number(e.target.value))}
            />
          </div>
          <Button variant="outline" onClick={() => capMutation.mutate(defaultCap)}>
            Apply
          </Button>
          <div className="flex flex-wrap items-center gap-1.5 sm:ml-auto">
            <span className="t-caption text-muted-foreground">current</span>
            {Object.entries(caps).length === 0 ? (
              <span className="t-caption text-muted-foreground">—</span>
            ) : (
              Object.entries(caps).map(([k, v]) => (
                <span key={k} className="t-caption rounded-full bg-muted px-2 py-0.5 font-mono text-foreground">
                  {k}={v}
                </span>
              ))
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Per-airline</CardTitle>
          <CardDescription>Refreshes every 3 seconds while the run is in flight.</CardDescription>
        </CardHeader>
        <CardContent className="scroll-quiet overflow-x-auto p-0">
          {rows.length === 0 ? (
            <p className="px-5 py-6 text-sm text-muted-foreground">
              No sagas for this run yet — the planner may still be working.
            </p>
          ) : (
            <table className="w-full min-w-[46rem] text-sm">
              <thead className="border-b border-border bg-muted/50 text-xs text-muted-foreground">
                <tr>
                  <th className="t-overline px-5 py-3 text-left font-semibold">Airline</th>
                  <th className="t-overline px-5 py-3 text-right font-semibold">Sagas</th>
                  <th className="t-overline px-5 py-3 text-right font-semibold">Recovered</th>
                  <th className="t-overline px-5 py-3 text-right font-semibold">Recovered %</th>
                  <th className="t-overline px-5 py-3 text-right font-semibold">Avg delay (min)</th>
                  <th className="t-overline px-5 py-3 text-right font-semibold">Avg recovery (s)</th>
                  <th className="t-overline px-5 py-3 text-right font-semibold">In flight</th>
                  <th className="t-overline px-5 py-3 text-left font-semibold">Queue share</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.airline} className="border-b border-border/60 transition-colors last:border-0 hover:bg-muted/40">
                    <td className="px-5 py-2.5 font-medium">
                      {r.airline}
                      {inFlight[r.airline] != null && (
                        <span className="ml-2 text-[11px] text-muted-foreground">
                          ({inFlight[r.airline]} leased)
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-2.5 text-right tabular-nums">{r.sagas.toLocaleString()}</td>
                    <td className="px-5 py-2.5 text-right tabular-nums">{r.recovered.toLocaleString()}</td>
                    <td
                      className={cn(
                        'px-5 py-2.5 text-right tabular-nums font-medium',
                        r.recovered_pct >= 80 ? 'text-success' : r.recovered_pct >= 50 ? 'text-warning' : 'text-destructive',
                      )}
                    >
                      {r.recovered_pct}%
                    </td>
                    <td className="px-5 py-2.5 text-right tabular-nums">{r.avg_delay_minutes}</td>
                    <td className="px-5 py-2.5 text-right tabular-nums">{r.avg_recovery_seconds}</td>
                    <td className="px-5 py-2.5 text-right tabular-nums">{r.in_flight}</td>
                    <td className="px-5 py-2.5">
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 w-24 overflow-hidden rounded-full bg-muted">
                          <div
                            className="gradient-primary h-full rounded-full transition-all duration-500 ease-out"
                            style={{ width: `${Math.min(100, r.queue_share_pct)}%` }}
                          />
                        </div>
                        <span className="text-xs tabular-nums text-muted-foreground">{r.queue_share_pct}%</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
