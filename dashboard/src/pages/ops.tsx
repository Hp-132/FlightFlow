import { ExternalLink } from 'lucide-react'
import * as React from 'react'

import { PageHeader } from '@/components/page-header'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'

const GRAFANA_URL = import.meta.env.VITE_GRAFANA_URL ?? 'http://localhost:3000'

const DASHBOARDS = [
  {
    uid: 'reflight-ops',
    title: 'Ops',
    description: 'Queue depth vs worker count, saga throughput, step latency, retries and DLQ, invariant status.',
  },
  {
    uid: 'reflight-run-progress',
    title: 'Run Progress',
    description: 'Sagas by state over time and disruption events by cause.',
  },
]

export function OpsPage() {
  const [active, setActive] = React.useState(DASHBOARDS[0])
  const embedUrl = `${GRAFANA_URL}/d/${active.uid}?kiosk&theme=light&refresh=5s`

  return (
    <div className="flex h-full flex-col gap-6">
      <PageHeader
        eyebrow="Analyse"
        title="System health"
        description="Behind-the-scenes charts from Grafana: how busy the servers and message queues are while a run is going."
        actions={
          <Button variant="outline" size="sm" asChild>
            <a href={embedUrl} target="_blank" rel="noreferrer">
              Open in Grafana
              <ExternalLink className="size-3.5" />
            </a>
          </Button>
        }
      />

      <div
        role="tablist"
        aria-label="Grafana dashboard"
        className="inline-flex w-fit gap-1 rounded-xl border border-border bg-card p-1 shadow-xs"
      >
        {DASHBOARDS.map((d) => {
          const selected = d.uid === active.uid
          return (
            <button
              key={d.uid}
              type="button"
              role="tab"
              aria-selected={selected}
              onClick={() => setActive(d)}
              className={cn(
                't-label rounded-lg px-3.5 py-1.5 font-medium transition-all duration-200',
                selected
                  ? 'gradient-primary text-white shadow-[0_4px_10px_-4px_rgba(24,50,81,0.5)]'
                  : 'text-muted-foreground hover:bg-muted hover:text-foreground',
              )}
            >
              {d.title}
            </button>
          )
        })}
      </div>

      <Card className="flex min-h-0 flex-1 flex-col">
        <CardHeader>
          <CardTitle>{active.title}</CardTitle>
          <CardDescription>{active.description}</CardDescription>
        </CardHeader>
        <CardContent className="min-h-0 flex-1 overflow-hidden rounded-b-xl p-0">
          <iframe
            key={active.uid}
            src={embedUrl}
            title={`Grafana ${active.title}`}
            className="h-full min-h-[480px] w-full border-0 bg-muted/30 lg:min-h-[600px]"
          />
        </CardContent>
      </Card>

      <p className="text-xs text-muted-foreground">
        If the frame is blank, Grafana is refusing to be embedded — set{' '}
        <code className="rounded bg-muted px-1 py-0.5">GF_SECURITY_ALLOW_EMBEDDING=true</code> and{' '}
        <code className="rounded bg-muted px-1 py-0.5">GF_AUTH_ANONYMOUS_ENABLED=true</code>, which
        docker-compose.yml already does for local dev.
      </p>
    </div>
  )
}
