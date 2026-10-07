import type { ReactNode } from 'react'

export function PageHeader({
  title,
  description,
  eyebrow,
  actions,
}: {
  title: string
  description?: string
  /** Small overline above the title, e.g. the nav group the page lives in. */
  eyebrow?: string
  actions?: ReactNode
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && <p className="t-overline mb-1.5 text-secondary">{eyebrow}</p>}
        <h1 className="t-headline text-foreground">{title}</h1>
        {description && <p className="t-body mt-1.5 max-w-2xl text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}
