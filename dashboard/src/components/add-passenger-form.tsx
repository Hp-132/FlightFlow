import { keepPreviousData, useMutation, useQuery } from '@tanstack/react-query'
import { Search, UserPlus } from 'lucide-react'
import * as React from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { api, apiErrorMessage, type CreatePassengerResult, type FlightOption } from '@/lib/api'
import { formatUtcTime } from '@/lib/format'
import { cn } from '@/lib/utils'

const CABINS = [
  { value: 'ECONOMY', label: 'Economy' },
  { value: 'BUSINESS', label: 'Business' },
]

const TIERS = [
  { value: 'NONE', label: 'Standard' },
  { value: 'SILVER', label: 'Silver' },
  { value: 'GOLD', label: 'Gold' },
]

export function AddPassengerForm({
  onCreated,
  onCancel,
}: {
  onCreated: (created: CreatePassengerResult) => void
  onCancel: () => void
}) {
  const nameId = React.useId()
  const filterId = React.useId()
  const bagsId = React.useId()

  const [name, setName] = React.useState('')
  const [filter, setFilter] = React.useState('')
  const [debouncedFilter, setDebouncedFilter] = React.useState('')
  const [flight, setFlight] = React.useState<FlightOption | null>(null)
  const [cabin, setCabin] = React.useState('ECONOMY')
  const [tier, setTier] = React.useState('NONE')
  const [bags, setBags] = React.useState(1)
  const [minor, setMinor] = React.useState(false)

  React.useEffect(() => {
    const id = setTimeout(() => setDebouncedFilter(filter.trim()), 250)
    return () => clearTimeout(id)
  }, [filter])

  const flights = useQuery({
    queryKey: ['flights', debouncedFilter],
    queryFn: () => api.listFlights({ q: debouncedFilter, limit: 40 }),
    placeholderData: keepPreviousData,
  })

  const create = useMutation({
    mutationFn: () =>
      api.createPassenger({
        name: name.trim(),
        flight_id: flight!.id,
        cabin,
        tier,
        bags,
        is_unaccompanied_minor: minor,
      }),
    onSuccess: onCreated,
  })

  const seats = flight ? (cabin === 'BUSINESS' ? flight.business_available : flight.economy_available) : 0
  const canSubmit = name.trim().length >= 2 && !!flight && seats > 0 && !create.isPending

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <span className="flex size-6 items-center justify-center rounded-lg bg-secondary/12 text-secondary">
            <UserPlus className="size-3.5" aria-hidden />
          </span>
          Add a passenger
        </CardTitle>
        <CardDescription>
          Books a new passenger on a real flight from the loaded network. A booking reference (PNR) is
          generated for them, and you can then cancel their flight to watch the rebooking run end to end.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="flex flex-col gap-5"
          onSubmit={(e) => {
            e.preventDefault()
            if (canSubmit) create.mutate()
          }}
        >
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={nameId}>Full name</Label>
            <Input
              id={nameId}
              value={name}
              maxLength={60}
              placeholder="e.g. Priya Sharma"
              autoComplete="off"
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor={filterId}>Flight</Label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <Input
                id={filterId}
                className="pl-9"
                value={filter}
                placeholder="Filter by flight number or airport, e.g. KB236 or GGO"
                autoComplete="off"
                onChange={(e) => setFilter(e.target.value)}
              />
            </div>

            <div
              role="radiogroup"
              aria-label="Flight"
              className="flex max-h-60 flex-col gap-1 overflow-y-auto rounded-lg border border-border bg-card p-1.5"
            >
              {flights.isLoading && (
                <div className="space-y-1.5 p-1">
                  <Skeleton className="h-11 w-full" />
                  <Skeleton className="h-11 w-full" />
                  <Skeleton className="h-11 w-full" />
                </div>
              )}
              {flights.isError && (
                <p className="t-caption px-2 py-2 text-destructive">Couldn't load flights. Is a scenario loaded?</p>
              )}
              {flights.data?.length === 0 && (
                <p className="t-caption px-2 py-2 text-muted-foreground">
                  {debouncedFilter ? `No flight matches “${debouncedFilter}”.` : 'No flights with free seats are loaded.'}
                </p>
              )}
              {flights.data?.map((f) => {
                const selected = flight?.id === f.id
                return (
                  <button
                    key={f.id}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    onClick={() => setFlight(f)}
                    className={cn(
                      'flex flex-wrap items-center justify-between gap-x-3 gap-y-1 rounded-md border px-3 py-2 text-left transition-colors duration-150',
                      selected
                        ? 'border-secondary/50 bg-secondary/[0.07]'
                        : 'border-transparent hover:border-border hover:bg-muted',
                    )}
                  >
                    <span className="flex items-baseline gap-2">
                      <span className="t-section font-mono text-foreground">{f.flight_no}</span>
                      <span className="t-body text-foreground">
                        {f.origin} → {f.dest}
                      </span>
                      <span className="t-caption text-muted-foreground">{formatUtcTime(f.sched_dep_at)}</span>
                    </span>
                    <span className="flex items-center gap-2">
                      <span className="t-caption text-muted-foreground">
                        {f.economy_available} economy · {f.business_available} business
                      </span>
                      {f.direct_alternatives > 0 ? (
                        <Badge variant="success">
                          {f.direct_alternatives} rebooking option{f.direct_alternatives === 1 ? '' : 's'}
                        </Badge>
                      ) : (
                        <Badge variant="warning">no direct alternative</Badge>
                      )}
                    </span>
                  </button>
                )
              })}
            </div>
            <p className="t-caption text-muted-foreground">
              {flight
                ? `Selected ${flight.flight_no}, ${flight.origin} → ${flight.dest}. Rebooking options are other direct flights on the same route in the next 48 hours.`
                : 'Pick the flight this passenger is booked on.'}
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <div className="flex flex-col gap-1.5">
              <Label>Cabin</Label>
              <Select value={cabin} onValueChange={setCabin}>
                <SelectTrigger aria-label="Cabin">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CABINS.map((c) => (
                    <SelectItem key={c.value} value={c.value}>
                      {c.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Loyalty tier</Label>
              <Select value={tier} onValueChange={setTier}>
                <SelectTrigger aria-label="Loyalty tier">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TIERS.map((t) => (
                    <SelectItem key={t.value} value={t.value}>
                      {t.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor={bagsId}>Checked bags</Label>
              <Input
                id={bagsId}
                type="number"
                min={0}
                max={5}
                value={bags}
                onChange={(e) => setBags(Math.min(5, Math.max(0, Math.trunc(Number(e.target.value)) || 0)))}
              />
            </div>
          </div>

          <label className="t-caption flex items-center gap-2 text-muted-foreground">
            <input
              type="checkbox"
              className="size-4 accent-[var(--color-secondary)]"
              checked={minor}
              onChange={(e) => setMinor(e.target.checked)}
            />
            Unaccompanied minor. Minors and Gold or Silver members are rebooked first.
          </label>

          {flight && seats === 0 && (
            <p role="alert" className="t-caption text-warning">
              {flight.flight_no} has no {cabin.toLowerCase()} seats left. Choose another cabin or flight.
            </p>
          )}
          {create.isError && (
            <p role="alert" className="t-caption text-destructive">
              {apiErrorMessage(create.error)}
            </p>
          )}

          <div className="flex flex-wrap items-center justify-end gap-2">
            <Button type="button" variant="ghost" onClick={onCancel}>
              Cancel
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              <UserPlus />
              {create.isPending ? 'Adding…' : 'Add passenger'}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  )
}
