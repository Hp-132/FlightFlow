import { useQuery } from '@tanstack/react-query'
import { Clock, Menu, Radio, ShieldCheck, ShieldX } from 'lucide-react'
import * as React from 'react'
import { Link } from 'react-router-dom'

import { api } from '@/lib/api'
import { useActiveRun } from '@/lib/run-context'
import { cn } from '@/lib/utils'

function formatElapsed(startedAt: number | null): string {
  if (!startedAt) return '--:--'
  const seconds = Math.max(0, Math.floor((Date.now() - startedAt) / 1000))
  const m = Math.floor(seconds / 60)
    .toString()
    .padStart(2, '0')
  const s = (seconds % 60).toString().padStart(2, '0')
  return `${m}:${s}`
}

export function Header({ onMenuClick }: { onMenuClick: () => void }) {
  const { runId, presetLabel, strategy, startedAt } = useActiveRun()
  const [, tick] = React.useState(0)

  React.useEffect(() => {
    if (!runId) return
    const id = setInterval(() => tick((n) => n + 1), 1000)
    return () => clearInterval(id)
  }, [runId])

  const run = useQuery({
    queryKey: ['run-status', runId],
    queryFn: () => api.getRun(runId!),
    enabled: !!runId,
    refetchInterval: 5000,
  })

  const invariants = useQuery({
    queryKey: ['invariants', runId],
    queryFn: () => api.getInvariants(runId!),
    enabled: !!runId,
    retry: false,
  })

  const status = run.data?.status
  const finished = status === 'FINISHED'

  return (
    <header className="relative z-30 flex h-14 shrink-0 items-center gap-3 border-b border-border bg-card/85 px-4 backdrop-blur-md supports-[backdrop-filter]:bg-card/75 sm:px-6">
      <button
        type="button"
        onClick={onMenuClick}
        className="-ml-1 flex size-9 shrink-0 items-center justify-center rounded-lg text-foreground/80 transition-colors hover:bg-muted hover:text-foreground lg:hidden"
        aria-label="Open navigation"
      >
        <Menu className="size-5" />
      </button>

      <div className="flex min-w-0 flex-1 items-center justify-between gap-4">
      {runId ? (
        <>
          <div className="flex min-w-0 items-center gap-2.5 sm:gap-3">
            <span
              className={cn(
                'flex items-center gap-1.5 rounded-full px-2 py-0.5',
                finished ? 'bg-muted text-muted-foreground' : 'bg-success/12 text-success',
              )}
            >
              <span
                className={cn('size-1.5 rounded-full', finished ? 'bg-muted-foreground' : 'bg-success pulse-live')}
                aria-hidden
              />
              <span className="t-caption font-semibold">{finished ? 'finished' : 'running'}</span>
            </span>

            <span className="t-section truncate text-foreground">{presetLabel ?? 'Run'}</span>

            <span className="t-caption hidden rounded-full bg-secondary/12 px-2 py-0.5 font-semibold uppercase tracking-wide text-secondary sm:inline">
              {strategy}
            </span>
          </div>

          <div className="flex shrink-0 items-center gap-3 sm:gap-4">
            {invariants.data && (
              <Link
                to="/invariants"
                className={cn(
                  'flex items-center gap-1.5 rounded-full px-2 py-0.5 transition-colors',
                  invariants.data.passed
                    ? 'bg-success/12 text-success hover:bg-success/20'
                    : 'bg-destructive/12 text-destructive hover:bg-destructive/20',
                )}
              >
                {invariants.data.passed ? (
                  <ShieldCheck className="size-3.5" aria-hidden />
                ) : (
                  <ShieldX className="size-3.5" aria-hidden />
                )}
                <span className="t-caption hidden font-semibold sm:inline">
                  {invariants.data.passed
                    ? 'invariants pass'
                    : `${invariants.data.total_violations} violation${invariants.data.total_violations === 1 ? '' : 's'}`}
                </span>
              </Link>
            )}

            <span className="t-caption flex items-center gap-1.5 text-muted-foreground">
              <Clock className="size-3.5" aria-hidden />
              <span className="tabular-nums">{formatElapsed(startedAt)}</span>
            </span>

            <Link
              to="/live"
              className="t-caption hidden items-center gap-1.5 rounded-md px-1.5 py-1 font-mono text-muted-foreground transition-colors hover:bg-muted hover:text-foreground md:flex"
            >
              <Radio className="size-3.5" aria-hidden />
              {runId.slice(0, 8)}
            </Link>
          </div>
        </>
      ) : (
        <>
          <span className="t-body truncate text-muted-foreground">No run started yet</span>
          <Link
            to="/"
            className="t-label shrink-0 font-medium text-secondary underline-offset-4 transition-colors hover:text-primary hover:underline"
          >
            Start one →
          </Link>
        </>
      )}
      </div>
    </header>
  )
}
