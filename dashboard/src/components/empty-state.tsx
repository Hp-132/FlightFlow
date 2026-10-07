import { ArrowRight, PlaneLanding } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/button'

export function EmptyState({
  title,
  description,
  ctaLabel,
  ctaTo,
}: {
  title: string
  description: string
  ctaLabel?: string
  ctaTo?: string
}) {
  return (
    <div className="relative flex min-h-[60vh] flex-col items-center justify-center gap-3 overflow-hidden rounded-2xl border border-dashed border-input bg-card/60 px-6 py-12 text-center">
      <div className="relative mb-2">
        {/* Faint radar rings centred on the icon -- the "waiting for traffic" cue. */}
        {[120, 84].map((size) => (
          <span
            key={size}
            aria-hidden
            className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full border border-secondary/15"
            style={{ width: size, height: size }}
          />
        ))}
        <div className="gradient-primary relative flex size-12 items-center justify-center rounded-2xl text-white shadow-[0_10px_24px_-10px_rgba(24,50,81,0.6)]">
          <PlaneLanding className="size-5" aria-hidden />
        </div>
      </div>
      <h2 className="t-title relative mt-2 text-foreground">{title}</h2>
      <p className="t-body relative max-w-sm text-muted-foreground">{description}</p>
      {ctaLabel && ctaTo && (
        <Button asChild className="relative mt-3">
          <Link to={ctaTo}>
            {ctaLabel}
            <ArrowRight />
          </Link>
        </Button>
      )}
    </div>
  )
}
