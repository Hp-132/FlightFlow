import { motion } from 'framer-motion'
import type { LucideIcon } from 'lucide-react'

import { AnimatedNumber } from '@/components/animated-number'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

export type StatTone = 'neutral' | 'progress' | 'success' | 'warning' | 'destructive'

const TONE: Record<StatTone, { value: string; icon: string; rail: string }> = {
  neutral: { value: 'text-foreground', icon: 'bg-muted text-muted-foreground', rail: 'bg-muted-foreground/30' },
  progress: { value: 'text-secondary', icon: 'bg-secondary/12 text-secondary', rail: 'bg-secondary' },
  success: { value: 'text-success', icon: 'bg-success/12 text-success', rail: 'bg-success' },
  warning: { value: 'text-warning', icon: 'bg-warning/12 text-warning', rail: 'bg-warning' },
  destructive: { value: 'text-destructive', icon: 'bg-destructive/12 text-destructive', rail: 'bg-destructive' },
}

export function StatCard({
  label,
  value,
  total,
  tone = 'neutral',
  icon: Icon,
  hint,
  loading,
}: {
  label: string
  value: number
  /** When given, draws a share-of-total rail under the number. */
  total?: number
  tone?: StatTone
  icon?: LucideIcon
  hint?: string
  loading?: boolean
}) {
  const palette = TONE[tone]
  const share = total && total > 0 ? Math.min(100, (value / total) * 100) : null

  if (loading) {
    return (
      <div className="rounded-xl border border-border bg-card p-4 shadow-card">
        <Skeleton className="h-3 w-20" />
        <Skeleton className="mt-3 h-8 w-16" />
        <Skeleton className="mt-3 h-1 w-full" />
      </div>
    )
  }

  return (
    <motion.div
      layout
      className="group relative overflow-hidden rounded-xl border border-border bg-card p-4 shadow-card transition-[box-shadow,transform] duration-300 ease-out hover:-translate-y-0.5 hover:shadow-card-hover"
    >
      {/* Hairline of the tone colour along the top edge. */}
      <span aria-hidden className={cn('absolute inset-x-0 top-0 h-0.5 opacity-70', palette.rail)} />
      <div className="flex items-start justify-between gap-2">
        <span className="t-label text-muted-foreground">{label}</span>
        {Icon && (
          <span
            className={cn(
              'flex size-7 shrink-0 items-center justify-center rounded-lg transition-transform duration-300 group-hover:scale-110',
              palette.icon,
            )}
          >
            <Icon className="size-3.5" aria-hidden />
          </span>
        )}
      </div>

      <AnimatedNumber value={value} className={cn('t-metric mt-2 block', palette.value)} />

      {share !== null ? (
        <div className="mt-3 h-1 overflow-hidden rounded-full bg-muted">
          <motion.div
            className={cn('h-full rounded-full', palette.rail)}
            initial={false}
            animate={{ width: `${share}%` }}
            transition={{ duration: 0.4, ease: 'easeOut' }}
          />
        </div>
      ) : (
        <div className="mt-3 h-1" />
      )}

      {hint && <p className="t-caption mt-2 text-muted-foreground">{hint}</p>}
    </motion.div>
  )
}
