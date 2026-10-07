import * as React from 'react'

interface RunContextValue {
  runId: string | null
  scenarioId: string | null
  strategy: string | null
  presetLabel: string | null
  startedAt: number | null
  setActiveRun: (info: { runId: string; scenarioId: string; strategy: string; presetLabel: string }) => void
  clearActiveRun: () => void
}

const RunContext = React.createContext<RunContextValue | null>(null)

const STORAGE_KEY = 'reflight.activeRun'

export function RunProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = React.useState<Omit<RunContextValue, 'setActiveRun' | 'clearActiveRun'>>(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw) return JSON.parse(raw)
    } catch {
      // ignore
    }
    return { runId: null, scenarioId: null, strategy: null, presetLabel: null, startedAt: null }
  })

  const setActiveRun: RunContextValue['setActiveRun'] = (info) => {
    const next = { ...info, startedAt: Date.now() }
    setState(next)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  }

  const clearActiveRun = () => {
    const next = { runId: null, scenarioId: null, strategy: null, presetLabel: null, startedAt: null }
    setState(next)
    localStorage.removeItem(STORAGE_KEY)
  }

  return (
    <RunContext.Provider value={{ ...state, setActiveRun, clearActiveRun }}>{children}</RunContext.Provider>
  )
}

export function useActiveRun() {
  const ctx = React.useContext(RunContext)
  if (!ctx) throw new Error('useActiveRun must be used within RunProvider')
  return ctx
}
