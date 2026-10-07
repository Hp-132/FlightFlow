import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { CheckCircle2, ChevronDown, PlayCircle, ShieldAlert, XCircle } from 'lucide-react'
import * as React from 'react'
import { toast } from 'sonner'

import { EmptyState } from '@/components/empty-state'
import { PageHeader } from '@/components/page-header'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { api, type InvariantCheck } from '@/lib/api'
import { useActiveRun } from '@/lib/run-context'
import { cn } from '@/lib/utils'

const CHECKS: Record<string, { title: string; blurb: string }> = {
  I1_no_oversell: {
    title: 'No oversell',
    blurb: 'available = capacity − sold − held, on every flight and cabin.',
  },
  I2_no_lost_bookings: {
    title: 'No lost or duplicated passengers',
    blurb: 'Exactly one saga per disrupted booking, and every saga reached a terminal state.',
  },
  I3_single_confirmed_itinerary: {
    title: 'One confirmed itinerary per booking',
    blurb: 'No passenger holds confirmed seats on two itineraries at once.',
  },
  I4_compensated_no_leaks: {
    title: 'Compensated sagas leak nothing',
    blurb: 'Rolled-back sagas hold no seats and no live ticket at the partner.',
  },
  I5_completed_has_holds_and_ticket: {
    title: 'Completed sagas are real',
    blurb: 'Every completed saga has confirmed seats and an issued ticket.',
  },
  I6_outbox_fully_published: {
    title: 'Outbox fully drained',
    blurb: 'No message was written to the outbox and never published.',
  },
}

function CheckRow({ id, check, index }: { id: string; check: InvariantCheck; index: number }) {
  const [open, setOpen] = React.useState(false)
  const meta = CHECKS[id] ?? { title: id, blurb: '' }
  const code = id.split('_')[0]
  const hasRows = check.violations.length > 0

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, delay: index * 0.03 }}
    >
      <Card className={cn(!check.passed && 'border-destructive/45')}>
        <button
          type="button"
          onClick={() => hasRows && setOpen((o) => !o)}
          aria-expanded={hasRows ? open : undefined}
          disabled={!hasRows}
          className={cn(
            'flex w-full items-center gap-4 px-5 py-4 text-left',
            hasRows ? 'cursor-pointer' : 'cursor-default',
          )}
        >
          <span
            className={cn(
              'flex size-9 shrink-0 items-center justify-center rounded-lg',
              check.passed ? 'bg-success/12 text-success' : 'bg-destructive/12 text-destructive',
            )}
          >
            {check.passed ? <CheckCircle2 className="size-5" aria-hidden /> : <XCircle className="size-5" aria-hidden />}
          </span>

          <div className="min-w-0 flex-1">
            <div className="flex items-baseline gap-2">
              <span className="t-overline text-muted-foreground">{code}</span>
              <span className="t-section text-foreground">{meta.title}</span>
            </div>
            <p className="t-caption mt-0.5 text-muted-foreground">{meta.blurb}</p>
          </div>

          <div className="flex shrink-0 items-center gap-3">
            <span
              className={cn(
                't-caption rounded-full px-2 py-0.5 font-semibold',
                check.passed ? 'bg-success/12 text-success' : 'bg-destructive/12 text-destructive',
              )}
            >
              {check.passed ? 'pass' : `${check.violations.length} offending row${check.violations.length === 1 ? '' : 's'}`}
            </span>
            {hasRows && (
              <ChevronDown
                className={cn('size-4 text-muted-foreground transition-transform duration-200', open && 'rotate-180')}
                aria-hidden
              />
            )}
          </div>
        </button>

        {open && hasRows && (
          <CardContent className="border-t border-border/70 pt-4">
            <div className="max-h-72 overflow-auto rounded-lg border border-border">
              <table className="w-full text-left">
                <thead className="sticky top-0 bg-muted">
                  <tr>
                    {Object.keys(check.violations[0]).map((k) => (
                      <th key={k} className="t-caption px-3 py-2 font-semibold text-muted-foreground">
                        {k}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {check.violations.map((row, i) => (
                    <tr key={i} className="border-t border-border/50 even:bg-surface-alt/25">
                      {Object.values(row).map((v, j) => (
                        <td key={j} className="t-caption px-3 py-1.5 font-mono text-foreground">
                          {String(v)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        )}
      </Card>
    </motion.div>
  )
}

export function InvariantsPage() {
  const { runId } = useActiveRun()
  const queryClient = useQueryClient()

  const query = useQuery({
    queryKey: ['invariants', runId],
    queryFn: () => api.getInvariants(runId!),
    enabled: !!runId,
    retry: false,
  })

  const checkMutation = useMutation({
    mutationFn: () => api.checkInvariants(runId!),
    onSuccess: (report) => {
      queryClient.setQueryData(['invariants', runId], report)
      if (report.passed) {
        toast.success('All invariants hold', {
          description: `0 violations across ${Object.keys(report.checks).length} checks.`,
        })
      } else {
        toast.error('Invariant violation detected', {
          description: `${report.total_violations} offending row${report.total_violations === 1 ? '' : 's'} — expand the failing check to see them.`,
        })
      }
    },
    onError: (err: Error) => toast.error('Checker failed', { description: err.message }),
  })

  if (!runId) {
    return (
      <EmptyState
        title="No run started yet"
        description="Start a run from Run Control, then come back here to prove it stayed correct."
        ctaLabel="Go to Run Control"
        ctaTo="/"
      />
    )
  }

  const report = query.data

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <PageHeader
        eyebrow="Verify"
        title="Safety checks"
        description="Six automatic checks (called invariants) that prove no seat was sold twice and no passenger was forgotten. Run them after a run finishes."
        actions={
          <Button onClick={() => checkMutation.mutate()} disabled={checkMutation.isPending}>
            <PlayCircle className="size-4" />
            {checkMutation.isPending ? 'Running checker…' : 'Run checker'}
          </Button>
        }
      />

      {checkMutation.isPending && !report ? (
        <Skeleton className="h-20 w-full" />
      ) : report ? (
        <motion.div
          key={report.checked_at}
          initial={{ opacity: 0, scale: 0.99 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.25, ease: 'easeOut' }}
          className={cn(
            'flex items-center gap-4 rounded-xl border px-5 py-4',
            report.passed ? 'border-success/30 bg-success/[0.07]' : 'border-destructive/30 bg-destructive/[0.07]',
          )}
        >
          <span
            className={cn(
              'flex size-11 shrink-0 items-center justify-center rounded-xl',
              report.passed ? 'bg-success/15 text-success' : 'bg-destructive/15 text-destructive',
            )}
          >
            {report.passed ? <CheckCircle2 className="size-6" aria-hidden /> : <ShieldAlert className="size-6" aria-hidden />}
          </span>
          <div className="min-w-0">
            <p className={cn('t-section', report.passed ? 'text-success' : 'text-destructive')}>
              {report.passed
                ? 'All invariants hold — zero violations'
                : `${report.total_violations} violation${report.total_violations === 1 ? '' : 's'} found`}
            </p>
            <p className="t-caption mt-0.5 text-muted-foreground">
              Checked {new Date(report.checked_at).toLocaleString()} · run these after a run settles; a run still
              in flight legitimately fails I2.
            </p>
          </div>
        </motion.div>
      ) : (
        <div className="rounded-xl border border-dashed border-border bg-card/60 px-5 py-8 text-center">
          <p className="t-body text-muted-foreground">
            No checks run yet for this run — hit <span className="font-medium text-foreground">Run checker</span>.
          </p>
        </div>
      )}

      {report && (
        <div className="grid gap-3">
          {Object.entries(report.checks).map(([id, check], i) => (
            <CheckRow key={id} id={id} check={check} index={i} />
          ))}
        </div>
      )}
    </div>
  )
}
