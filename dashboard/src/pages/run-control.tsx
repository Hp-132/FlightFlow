import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Check, PlaneTakeoff, Server, Ticket, Zap } from 'lucide-react'
import * as React from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'

import { HowItWorks, PageGuide, RunHero } from '@/components/run-hero'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Slider } from '@/components/ui/slider'
import { api } from '@/lib/api'
import { useActiveRun } from '@/lib/run-context'
import { cn } from '@/lib/utils'

const PRESETS = [
  { value: 'small', title: 'Small', detail: '8 airports · 2 airlines', passengers: '~500 passengers', note: 'Quick test' },
  { value: 'storm', title: 'Storm', detail: '12 airports · 3 airlines', passengers: '~10,000 passengers', note: 'Recommended' },
  { value: 'mega', title: 'Mega', detail: '20 airports · 4 airlines', passengers: '~30,000 passengers', note: 'Heavy load' },
]

const STRATEGIES = [
  { value: 'greedy', title: 'Greedy · fast', detail: 'Helps the most important passengers first, one at a time.' },
  { value: 'cpsat', title: 'CP-SAT · smarter', detail: 'Plans everyone together for less total delay. A little slower.' },
]

function ChoiceCard({
  selected,
  onClick,
  title,
  detail,
  meta,
  note,
}: {
  selected: boolean
  onClick: () => void
  title: string
  detail: string
  meta?: string
  note?: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={cn(
        'group relative rounded-xl border p-4 text-left transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50',
        selected
          ? 'border-primary bg-linear-to-b from-primary/[0.05] to-card shadow-card ring-1 ring-primary/15'
          : 'border-border bg-card hover:-translate-y-0.5 hover:border-secondary/50 hover:shadow-card-hover',
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="t-section text-foreground">{title}</span>
        <span
          className={cn(
            'flex size-4 shrink-0 items-center justify-center rounded-full border transition-colors',
            selected ? 'border-primary bg-primary text-white' : 'border-border bg-card',
          )}
          aria-hidden
        >
          {selected && <Check className="size-2.5" strokeWidth={3} />}
        </span>
      </div>
      <p className="t-caption mt-1 text-muted-foreground">{detail}</p>
      {meta && <p className="t-caption mt-0.5 font-medium text-foreground/80">{meta}</p>}
      {note && (
        <span className="t-caption mt-2 inline-block rounded-full bg-muted px-1.5 py-0.5 text-muted-foreground">
          {note}
        </span>
      )}
    </button>
  )
}

function StepNumber({ n }: { n: number }) {
  return (
    <span className="gradient-primary t-caption flex size-5 items-center justify-center rounded-full font-semibold text-white">
      {n}
    </span>
  )
}

export function RunControlPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { setActiveRun } = useActiveRun()

  const [preset, setPreset] = React.useState('storm')
  const [seed, setSeed] = React.useState(42)
  const [hub, setHub] = React.useState('')
  const [severity, setSeverity] = React.useState([0.8])
  const [cascadeChains, setCascadeChains] = React.useState([3])
  const [strategy, setStrategy] = React.useState('greedy')

  const [crashProbability, setCrashProbability] = React.useState([0])
  const [partnerFailureRate, setPartnerFailureRate] = React.useState([0])

  const chaosQuery = useQuery({ queryKey: ['chaos'], queryFn: api.getChaos })
  React.useEffect(() => {
    if (chaosQuery.data) {
      setCrashProbability([chaosQuery.data.crash_probability])
      setPartnerFailureRate([chaosQuery.data.partner_failure_rate])
    }
  }, [chaosQuery.data])

  const chaosMutation = useMutation({
    mutationFn: api.setChaos,
    onSuccess: (_, vars) => {
      const off = vars.crash_probability === 0 && vars.partner_failure_rate === 0
      toast.success(off ? 'Stress test off' : 'Stress test on', {
        description: off
          ? 'Workers and partners behave normally again.'
          : `Workers crash at ${Math.round(vars.crash_probability * 100)}%, partners fail at ${Math.round(vars.partner_failure_rate * 100)}%.`,
      })
      queryClient.invalidateQueries({ queryKey: ['chaos'] })
    },
    onError: (err: Error) => toast.error('Could not update chaos', { description: err.message }),
  })

  const startMutation = useMutation({
    mutationFn: async () => {
      const scenario = await api.createScenario({
        preset,
        seed,
        hub: hub || null,
        severity: severity[0],
        cascade_chains: cascadeChains[0],
      })
      await api.loadScenario(scenario.id)
      const run = await api.createRun(
        { scenario_id: scenario.id, strategy },
        `${scenario.id}:${Date.now()}`,
      )
      const started = await api.startRun(run.id)
      return { scenario, run, started }
    },
    onSuccess: ({ scenario, run, started }) => {
      setActiveRun({
        runId: run.id,
        scenarioId: scenario.id,
        strategy: run.strategy,
        presetLabel: `${preset} · seed ${seed}`,
      })
      queryClient.invalidateQueries({ queryKey: ['runs'] })
      toast.success('Run started', {
        description: `${started.disrupted_bookings.toLocaleString()} bookings disrupted by ${started.disruption_events} events.`,
      })
      navigate('/live')
    },
    onError: (err: Error) => toast.error('Failed to start run', { description: err.message }),
  })

  const chaosArmed = crashProbability[0] > 0 || partnerFailureRate[0] > 0
  const scenarioRef = React.useRef<HTMLDivElement>(null)

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 lg:gap-8">
      <RunHero onConfigure={() => scenarioRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })} />

      <HowItWorks />

      <div ref={scenarioRef} className="scroll-mt-6 flex flex-col gap-1.5 pt-2">
        <p className="t-overline text-secondary">Start a simulation</p>
        <h2 className="t-headline text-foreground">Set up your storm</h2>
        <p className="t-body max-w-2xl text-muted-foreground">
          The defaults work well — you can just press <span className="font-medium text-foreground">Start run</span> at
          the bottom.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2.5">
            <StepNumber n={1} />
            Choose a scenario
          </CardTitle>
          <CardDescription>The same settings always create exactly the same day, so results can be compared.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <fieldset>
            <legend className="t-overline mb-2.5 text-muted-foreground">How big is the airline?</legend>
            <div className="grid gap-3 sm:grid-cols-3">
              {PRESETS.map((p) => (
                <ChoiceCard
                  key={p.value}
                  selected={preset === p.value}
                  onClick={() => setPreset(p.value)}
                  title={p.title}
                  detail={p.detail}
                  meta={p.passengers}
                  note={p.note}
                />
              ))}
            </div>
          </fieldset>

          <fieldset>
            <legend className="t-overline mb-2.5 text-muted-foreground">How should new flights be chosen?</legend>
            <div className="grid gap-3 sm:grid-cols-2">
              {STRATEGIES.map((s) => (
                <ChoiceCard
                  key={s.value}
                  selected={strategy === s.value}
                  onClick={() => setStrategy(s.value)}
                  title={s.title}
                  detail={s.detail}
                />
              ))}
            </div>
          </fieldset>

          <div className="grid gap-5 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="seed">Scenario number (seed)</Label>
              <Input id="seed" type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value))} />
              <p className="t-caption text-muted-foreground">Same number gives the same day every time.</p>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="hub">Storm airport (optional)</Label>
              <Input
                id="hub"
                placeholder="Leave blank to pick automatically"
                value={hub}
                onChange={(e) => setHub(e.target.value.toUpperCase())}
                maxLength={3}
              />
              <p className="t-caption text-muted-foreground">
                A 3-letter airport code. Airports are made up, so blank is easiest.
              </p>
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label>How bad is the storm?</Label>
                <span className="t-label tabular-nums text-foreground">{Math.round(severity[0] * 100)}%</span>
              </div>
              <Slider min={0.6} max={1} step={0.05} value={severity} onValueChange={setSeverity} aria-label="Storm severity" />
              <p className="t-caption text-muted-foreground">Share of that airport's flights that get cancelled.</p>
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label>Knock-on delays</Label>
                <span className="t-label tabular-nums text-foreground">{cascadeChains[0]}</span>
              </div>
              <Slider min={0} max={10} step={1} value={cascadeChains} onValueChange={setCascadeChains} aria-label="Knock-on delays" />
              <p className="t-caption text-muted-foreground">
                Planes running late, making their next flights late too.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className={cn('transition-colors', chaosArmed ? 'border-warning/50' : 'border-border')}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2.5">
            <StepNumber n={2} />
            <span
              className={cn(
                'flex size-6 items-center justify-center rounded-lg transition-colors',
                chaosArmed ? 'bg-warning/15 text-warning' : 'bg-muted text-muted-foreground',
              )}
            >
              <AlertTriangle className="size-3.5" aria-hidden />
            </span>
            Stress test
            <span className="t-caption font-normal text-muted-foreground">optional</span>
            {chaosArmed && (
              <span className="t-caption rounded-full bg-warning/15 px-2 py-0.5 font-semibold text-warning">
                on
              </span>
            )}
          </CardTitle>
          <CardDescription>
            Break things on purpose to prove the system still recovers. Leave both at 0% for a normal run.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid gap-5 sm:grid-cols-2">
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label className="flex items-center gap-1.5">
                  <Server className="size-3.5 text-muted-foreground" aria-hidden />
                  Crash the servers
                </Label>
                <span className="t-label tabular-nums text-foreground">{Math.round(crashProbability[0] * 100)}%</span>
              </div>
              <Slider min={0} max={1} step={0.05} value={crashProbability} onValueChange={setCrashProbability} aria-label="Crash the servers" />
              <p className="t-caption text-muted-foreground">Chance a background worker is killed in the middle of a task.</p>
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label className="flex items-center gap-1.5">
                  <Ticket className="size-3.5 text-muted-foreground" aria-hidden />
                  Make ticketing fail
                </Label>
                <span className="t-label tabular-nums text-foreground">{Math.round(partnerFailureRate[0] * 100)}%</span>
              </div>
              <Slider min={0} max={1} step={0.05} value={partnerFailureRate} onValueChange={setPartnerFailureRate} aria-label="Make ticketing fail" />
              <p className="t-caption text-muted-foreground">Chance ticket, baggage or message services fail. At 100%, bookings are undone and seats freed.</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                chaosMutation.mutate({
                  crash_probability: crashProbability[0],
                  partner_failure_rate: partnerFailureRate[0],
                })
              }
              disabled={chaosMutation.isPending}
            >
              <Zap className="size-3.5" />
              Apply stress test
            </Button>
            {chaosArmed && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setCrashProbability([0])
                  setPartnerFailureRate([0])
                  chaosMutation.mutate({ crash_probability: 0, partner_failure_rate: 0 })
                }}
              >
                Reset to zero
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      <PageGuide />

      {/* Sticky action bar: the -mb-6/pb bleed keeps it flush with the
          scroll container's padding instead of floating above it. */}
      <div className="sticky bottom-0 z-10 -mx-4 -mb-4 flex flex-col items-stretch gap-3 border-t border-border bg-card/85 px-4 py-3 shadow-[0_-8px_24px_-12px_rgba(16,36,62,0.18)] backdrop-blur-md sm:-mx-6 sm:-mb-6 sm:flex-row sm:items-center sm:justify-between sm:gap-4 sm:px-6 lg:-mx-8 lg:-mb-8 lg:px-8">
        <p className="t-caption text-muted-foreground">
          Ready: <span className="font-medium text-foreground">{preset}</span> airline, scenario{' '}
          <span className="font-medium text-foreground">#{seed}</span>, planned with{' '}
          <span className="font-medium text-foreground">{strategy === 'cpsat' ? 'CP-SAT' : 'Greedy'}</span>
          {chaosArmed && <span className="text-warning"> · stress test on</span>}
        </p>
        <Button
          size="lg"
          className="w-full sm:w-auto"
          onClick={() => startMutation.mutate()}
          disabled={startMutation.isPending}
        >
          <PlaneTakeoff className="size-4" />
          {startMutation.isPending ? 'Starting run…' : 'Start run'}
        </Button>
      </div>
    </div>
  )
}
