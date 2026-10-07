import { motion } from 'framer-motion'

import { cn } from '@/lib/utils'

/** Saga states in lifecycle order, with the colour coding used everywhere. */
const STATE_ORDER: { key: string; label: string; className: string }[] = [
  // In-progress states share the steel accent, darkening as the saga moves
  // forward; the floor is high enough that every swatch stays legible.
  { key: 'PLANNED', label: 'Planned', className: 'bg-secondary/55' },
  { key: 'HOLDING', label: 'Holding seats', className: 'bg-secondary/70' },
  { key: 'TICKETING', label: 'Ticketing', className: 'bg-secondary/85' },
  { key: 'BAGGAGE', label: 'Baggage', className: 'bg-secondary' },
  { key: 'NOTIFYING', label: 'Notifying', className: 'bg-primary/80' },
  { key: 'COMPENSATING', label: 'Compensating', className: 'bg-warning/70' },
  { key: 'COMPLETED', label: 'Completed', className: 'bg-success' },
  { key: 'COMPENSATED', label: 'Compensated', className: 'bg-warning' },
  { key: 'FAILED_NO_CAPACITY', label: 'No capacity', className: 'bg-destructive/75' },
  { key: 'NEEDS_MANUAL', label: 'Needs manual', className: 'bg-destructive' },
]

export function StateDistribution({ counts }: { counts: Record<string, number> }) {
  const total = Object.values(counts).reduce((sum, n) => sum + n, 0)
  const present = STATE_ORDER.filter((s) => (counts[s.key] ?? 0) > 0)

  if (total === 0) {
    return (
      <div className="flex h-2.5 items-center overflow-hidden rounded-full bg-muted">
        <span className="sr-only">No sagas yet</span>
      </div>
    )
  }

  return (
    <div>
      <div
        className="flex h-2.5 w-full overflow-hidden rounded-full bg-muted"
        role="img"
        aria-label={present
          .map((s) => `${counts[s.key]} ${s.label.toLowerCase()}`)
          .join(', ')}
      >
        {present.map((s) => (
          <motion.div
            key={s.key}
            layout
            className={cn('h-full first:rounded-l-full last:rounded-r-full', s.className)}
            initial={false}
            animate={{ width: `${((counts[s.key] ?? 0) / total) * 100}%` }}
            transition={{ duration: 0.4, ease: 'easeOut' }}
          />
        ))}
      </div>

      <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5">
        {present.map((s) => (
          <li key={s.key} className="flex items-center gap-1.5">
            <span className={cn('size-2 shrink-0 rounded-full', s.className)} aria-hidden />
            <span className="t-caption text-muted-foreground">
              {s.label} <span className="font-medium text-foreground">{counts[s.key].toLocaleString()}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
