import { Badge } from '@/components/ui/badge'

const IN_PROGRESS = new Set(['PLANNED', 'HOLDING', 'TICKETING', 'BAGGAGE', 'NOTIFYING'])
const WARNING = new Set(['COMPENSATING', 'COMPENSATED'])
const DESTRUCTIVE = new Set(['FAILED_NO_CAPACITY', 'NEEDS_MANUAL'])

export function sagaStateVariant(state: string) {
  if (state === 'COMPLETED') return 'success' as const
  if (WARNING.has(state)) return 'warning' as const
  if (DESTRUCTIVE.has(state)) return 'destructive' as const
  if (IN_PROGRESS.has(state)) return 'progress' as const
  return 'neutral' as const
}

export function SagaStateBadge({ state }: { state: string }) {
  return <Badge variant={sagaStateVariant(state)}>{state.replaceAll('_', ' ')}</Badge>
}
