/** Shared Recharts tooltip so every chart in the app reads the same. */
export function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="min-w-36 rounded-lg border border-border bg-card/95 px-3 py-2 shadow-raised backdrop-blur">
      <p className="t-caption mb-1.5 font-medium text-muted-foreground">{label}</p>
      <div className="space-y-1">
        {payload.map((entry: any) => (
          <p key={entry.dataKey} className="t-label flex items-center gap-2">
            <span className="size-2 rounded-full" style={{ background: entry.color }} aria-hidden />
            <span className="text-muted-foreground">{entry.name}</span>
            <span className="ml-auto pl-3 font-semibold tabular-nums text-foreground">
              {typeof entry.value === 'number' ? entry.value.toLocaleString() : entry.value}
            </span>
          </p>
        ))}
      </div>
    </div>
  )
}
