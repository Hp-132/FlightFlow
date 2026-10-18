import * as React from 'react'

import type { DisruptionEvent, RunCounters, RunMetrics } from '@/lib/api'

/** One chart sample, as written by scripts/seed_data.py. */
export interface SeedHistoryPoint {
  offset_seconds: number
  completed: number
  inFlight: number
  queueDepth: number
  workers: number
}

export interface SeedFixture {
  fixture_version: number
  generated_by: string
  captured_at: string
  params: { preset: string; seed: number; strategy: string; severity: number }
  run: {
    run_id: string
    scenario_id: string
    status: string | null
    strategy: string
    settled: boolean
    wall_seconds: number
  }
  start: {
    disruption_events: number
    cancelled_flights: number
    delayed_flights: number
    disrupted_bookings: number
    plan_batches_queued: number
  }
  counters: RunCounters
  history: SeedHistoryPoint[]
  disruptions: DisruptionEvent[]
  metrics: RunMetrics
}

// Written by the compose `seeder` service into dashboard/public/fixtures, so
// it is served as a static file next to the bundle.
const FIXTURE_URL = `${import.meta.env.BASE_URL}fixtures/seed42_greedy.json`

// One fetch per page load, shared by every caller.
let pending: Promise<SeedFixture | null> | null = null

function looksLikeFixture(value: unknown): value is SeedFixture {
  const f = value as SeedFixture | null
  return (
    !!f &&
    typeof f.fixture_version === 'number' &&
    Array.isArray(f.history) &&
    !!f.counters &&
    typeof f.counters === 'object'
  )
}

async function fetchFixture(): Promise<SeedFixture | null> {
  try {
    const res = await fetch(FIXTURE_URL, { cache: 'no-store' })
    if (!res.ok) return null
    // Both hosts that serve this app fall back to index.html for unknown
    // paths, so a 200 is not proof the fixture exists -- parse before
    // trusting it.
    const parsed: unknown = JSON.parse(await res.text())
    return looksLikeFixture(parsed) ? parsed : null
  } catch {
    // Missing, unparseable or blocked: the caller falls back to live data.
    return null
  }
}

/** Resolves to the seeded fixture, or null if the stack was never seeded. */
export function loadSeedFixture(): Promise<SeedFixture | null> {
  pending ??= fetchFixture()
  return pending
}

/**
 * Loads the seeded fixture when `enabled`. Stays null until then, so a page
 * with live data never pays for the fetch.
 */
export function useSeedFixture(enabled: boolean) {
  const [fixture, setFixture] = React.useState<SeedFixture | null>(null)
  const [loading, setLoading] = React.useState(false)

  React.useEffect(() => {
    if (!enabled) return
    let cancelled = false
    setLoading(true)
    loadSeedFixture()
      .then((f) => {
        if (!cancelled) setFixture(f)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [enabled])

  return { fixture, loading }
}

/** "1:05" elapsed, since a fixture's samples carry offsets, not wall clocks. */
export function formatElapsed(seconds: number): string {
  const total = Math.max(0, Math.round(seconds))
  const mins = Math.floor(total / 60)
  return `${mins}:${String(total % 60).padStart(2, '0')}`
}
