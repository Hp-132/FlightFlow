import { useQueries, useQuery } from '@tanstack/react-query'
import * as React from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { ChartTooltip } from '@/components/chart-tooltip'
import { EmptyState } from '@/components/empty-state'
import { PageHeader } from '@/components/page-header'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { api, type RunMetrics, type RunSummary } from '@/lib/api'
import { AXIS_TICK } from '@/lib/chart'

interface Row {
  label: string
  a: string
  b: string
  /** true when a *lower* number is the better one */
  lowerIsBetter?: boolean
  aValue?: number
  bValue?: number
}

function buildRows(a: RunMetrics, b: RunMetrics, aCost?: number | null, bCost?: number | null): Row[] {
  return [
    { label: 'Recovered', a: `${a.recovered} / ${a.total_sagas}`, b: `${b.recovered} / ${b.total_sagas}`, aValue: a.recovered, bValue: b.recovered },
    { label: 'Recovered %', a: `${a.recovered_pct}%`, b: `${b.recovered_pct}%`, aValue: a.recovered_pct, bValue: b.recovered_pct },
    { label: 'Priority-weighted recovered %', a: `${a.weighted_recovered_pct}%`, b: `${b.weighted_recovered_pct}%`, aValue: a.weighted_recovered_pct, bValue: b.weighted_recovered_pct },
    { label: 'Unrecovered', a: `${a.unrecovered}`, b: `${b.unrecovered}`, lowerIsBetter: true, aValue: a.unrecovered, bValue: b.unrecovered },
    { label: 'Total delay (min)', a: a.total_delay_minutes.toLocaleString(), b: b.total_delay_minutes.toLocaleString(), lowerIsBetter: true, aValue: a.total_delay_minutes, bValue: b.total_delay_minutes },
    { label: 'Avg delay (min)', a: `${a.avg_delay_minutes}`, b: `${b.avg_delay_minutes}`, lowerIsBetter: true, aValue: a.avg_delay_minutes, bValue: b.avg_delay_minutes },
    { label: 'Planning time (s)', a: `${a.planning_seconds}`, b: `${b.planning_seconds}`, lowerIsBetter: true, aValue: a.planning_seconds, bValue: b.planning_seconds },
    { label: 'Planner CPU (s)', a: `${a.planner_cpu_seconds}`, b: `${b.planner_cpu_seconds}`, lowerIsBetter: true, aValue: a.planner_cpu_seconds, bValue: b.planner_cpu_seconds },
    { label: 'Seat conflicts at execution', a: `${a.seat_conflicts}`, b: `${b.seat_conflicts}`, lowerIsBetter: true, aValue: a.seat_conflicts, bValue: b.seat_conflicts },
    { label: 'End-to-end recovery (s)', a: a.recovery_seconds != null ? `${a.recovery_seconds}` : '—', b: b.recovery_seconds != null ? `${b.recovery_seconds}` : '—', lowerIsBetter: true, aValue: a.recovery_seconds ?? undefined, bValue: b.recovery_seconds ?? undefined },
    { label: 'Cost per 1,000 recovered (USD)', a: aCost != null ? aCost.toFixed(4) : '—', b: bCost != null ? bCost.toFixed(4) : '—', lowerIsBetter: true, aValue: aCost ?? undefined, bValue: bCost ?? undefined },
    { label: 'Invariants', a: a.invariants_passed == null ? 'not checked' : a.invariants_passed ? 'pass' : 'FAIL', b: b.invariants_passed == null ? 'not checked' : b.invariants_passed ? 'pass' : 'FAIL' },
  ]
}

function RunPicker({
  label,
  runs,
  value,
  onChange,
}: {
  label: string
  runs: RunSummary[]
  value: string | undefined
  onChange: (v: string) => void
}) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger>
          <SelectValue placeholder="Pick a run…" />
        </SelectTrigger>
        <SelectContent>
          {runs.map((r) => (
            <SelectItem key={r.id} value={r.id}>
              {r.strategy} · {r.preset ?? '—'} · seed {r.seed} · {r.id.slice(0, 8)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}

export function ComparePage() {
  const runs = useQuery({ queryKey: ['runs'], queryFn: () => api.listRuns(25) })
  const [aId, setAId] = React.useState<string>()
  const [bId, setBId] = React.useState<string>()

  // Default to the two most recent runs with different strategies, which is
  // almost always the greedy/CP-SAT pair someone just produced.
  React.useEffect(() => {
    if (!runs.data || aId || bId) return
    const greedy = runs.data.find((r) => r.strategy === 'greedy')
    const cpsat = runs.data.find((r) => r.strategy === 'cpsat')
    if (greedy && cpsat) {
      setAId(greedy.id)
      setBId(cpsat.id)
    } else if (runs.data.length >= 2) {
      setAId(runs.data[1].id)
      setBId(runs.data[0].id)
    }
  }, [runs.data, aId, bId])

  const comparison = useQuery({
    queryKey: ['compare', aId, bId],
    queryFn: () => api.compareRuns(aId!, bId!),
    enabled: !!aId && !!bId,
  })

  const costs = useQueries({
    queries: [aId, bId].filter(Boolean).map((id) => ({
      queryKey: ['finops', id],
      queryFn: () => api.getFinops(id as string),
      retry: false,
    })),
  })

  if (runs.isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <Skeleton className="h-14 w-72" />
        <Skeleton className="h-24 w-full rounded-xl" />
        <Skeleton className="h-80 w-full rounded-xl" />
      </div>
    )
  }

  if (!runs.data || runs.data.length < 2) {
    return (
      <EmptyState
        title="Need two runs to compare"
        description="Start the same scenario twice from Run Control — once with Greedy, once with CP-SAT — and they'll show up here side by side."
        ctaLabel="Go to Run Control"
        ctaTo="/"
      />
    )
  }

  const a = comparison.data?.a
  const b = comparison.data?.b
  const aCost = costs[0]?.data?.cost_per_1000_recovered
  const bCost = costs[1]?.data?.cost_per_1000_recovered
  const rows = a && b ? buildRows(a, b, aCost, bCost) : []

  // Fixed A/B data keys so two runs of the same strategy don't collide;
  // the legend carries the strategy names.
  const chartData =
    a && b
      ? [
          { metric: 'Recovered %', A: a.recovered_pct, B: b.recovered_pct },
          { metric: 'Weighted %', A: a.weighted_recovered_pct, B: b.weighted_recovered_pct },
          { metric: 'Avg delay (min)', A: a.avg_delay_minutes, B: b.avg_delay_minutes },
          { metric: 'Planning CPU (s×100)', A: a.planner_cpu_seconds * 100, B: b.planner_cpu_seconds * 100 },
        ]
      : []

  const seriesA = `A · ${a?.strategy ?? ''}`
  const seriesB = `B · ${b?.strategy ?? ''}`

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Analyse"
        title="Compare"
        description="Put two runs side by side — usually the same storm planned with Greedy and with CP-SAT — to see which rebooked more people with less delay."
      />

      <Card>
        <CardContent className="grid gap-5 py-5 sm:grid-cols-2">
          <RunPicker label="Run A" runs={runs.data} value={aId} onChange={setAId} />
          <RunPicker label="Run B" runs={runs.data} value={bId} onChange={setBId} />
        </CardContent>
      </Card>

      {a && b && (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Metrics</CardTitle>
              <CardDescription>The better value in each row is highlighted.</CardDescription>
            </CardHeader>
            <CardContent className="scroll-quiet overflow-x-auto p-0">
              <table className="w-full min-w-[30rem] text-sm">
                <thead className="border-b border-border bg-muted/50 text-xs text-muted-foreground">
                  <tr>
                    <th className="t-overline px-5 py-3 text-left font-semibold">Metric</th>
                    <th className="t-overline px-5 py-3 text-left font-semibold">
                      <span className="mr-1.5 inline-block size-2 rounded-full bg-primary align-middle" aria-hidden />A · {a.strategy}
                    </th>
                    <th className="t-overline px-5 py-3 text-left font-semibold">
                      <span className="mr-1.5 inline-block size-2 rounded-full bg-secondary align-middle" aria-hidden />B · {b.strategy}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => {
                    const aWins =
                      row.aValue != null && row.bValue != null && row.aValue !== row.bValue
                        ? row.lowerIsBetter
                          ? row.aValue < row.bValue
                          : row.aValue > row.bValue
                        : false
                    const bWins =
                      row.aValue != null && row.bValue != null && row.aValue !== row.bValue && !aWins
                    return (
                      <tr key={row.label} className="border-b border-border/60 transition-colors last:border-0 hover:bg-muted/40">
                        <td className="px-5 py-2.5 text-muted-foreground">{row.label}</td>
                        <td className="px-5 py-2.5 tabular-nums">
                          <span className={aWins ? 'rounded-md bg-success/10 px-1.5 py-0.5 font-semibold text-success' : ''}>{row.a}</span>
                        </td>
                        <td className="px-5 py-2.5 tabular-nums">
                          <span className={bWins ? 'rounded-md bg-success/10 px-1.5 py-0.5 font-semibold text-success' : ''}>{row.b}</span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Side by side</CardTitle>
              <CardDescription>Planner CPU is scaled ×100 so it shares an axis with the percentages.</CardDescription>
            </CardHeader>
            <CardContent className="h-80 pt-4">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} barGap={4} margin={{ top: 4, right: 4, bottom: 0, left: -12 }}>
                  <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="metric" tick={AXIS_TICK} tickLine={false} axisLine={false} interval={0} />
                  <YAxis tick={AXIS_TICK} tickLine={false} axisLine={false} />
                  <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--color-muted)', opacity: 0.6 }} />
                  <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
                  <Bar dataKey="A" name={seriesA} fill="var(--color-primary)" radius={[5, 5, 0, 0]} maxBarSize={44} />
                  <Bar dataKey="B" name={seriesB} fill="var(--color-secondary)" radius={[5, 5, 0, 0]} maxBarSize={44} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}
