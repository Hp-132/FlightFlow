import {
  Activity,
  BarChart3,
  GaugeCircle,
  PlaneTakeoff,
  Search,
  Settings2,
  ShieldCheck,
  Users,
  X,
} from 'lucide-react'
import * as React from 'react'
import { NavLink } from 'react-router-dom'

import { cn } from '@/lib/utils'

const NAV_GROUPS = [
  {
    label: 'Operate',
    items: [
      { to: '/', label: 'Home', icon: Settings2, end: true },
      { to: '/live', label: 'Live Run', icon: Activity },
    ],
  },
  {
    label: 'Verify',
    items: [
      { to: '/invariants', label: 'Safety Checks', icon: ShieldCheck },
      { to: '/sagas', label: 'Passenger History', icon: Search },
    ],
  },
  {
    label: 'Analyse',
    items: [
      { to: '/compare', label: 'Compare', icon: BarChart3 },
      { to: '/tenants', label: 'Airlines', icon: Users },
      { to: '/ops', label: 'System Health', icon: GaugeCircle },
    ],
  },
]

/**
 * Persistent rail on desktop; an off-canvas drawer below `lg` that the
 * header's menu button opens. Navigating closes the drawer.
 */
export function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  React.useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  return (
    <>
      <div
        aria-hidden
        onClick={onClose}
        className={cn(
          'fixed inset-0 z-40 bg-[#0d1d31]/40 backdrop-blur-[2px] transition-opacity duration-300 lg:hidden',
          open ? 'opacity-100' : 'pointer-events-none opacity-0',
        )}
      />

      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-50 flex w-64 shrink-0 flex-col border-r border-border bg-card shadow-raised transition-transform duration-300 ease-out',
          'lg:static lg:z-auto lg:w-60 lg:translate-x-0 lg:shadow-none',
          open ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <div className="hero-surface flex h-14 shrink-0 items-center gap-2.5 px-5 text-white">
          <span className="flex size-8 items-center justify-center rounded-lg bg-white/12 ring-1 ring-white/20 ring-inset">
            <PlaneTakeoff className="size-4" aria-hidden />
          </span>
          <div className="min-w-0 flex-1">
            <p className="t-section leading-none text-white">FlightFlow</p>
            <p className="t-caption mt-1 leading-none text-white/60">disruption recovery</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex size-8 items-center justify-center rounded-md text-white/70 transition-colors hover:bg-white/10 hover:text-white lg:hidden"
            aria-label="Close navigation"
          >
            <X className="size-4" />
          </button>
        </div>

        <nav aria-label="Main" className="scroll-quiet flex-1 overflow-y-auto px-3 py-5">
          {NAV_GROUPS.map((group) => (
            <div key={group.label} className="mb-6 last:mb-0">
              <p className="t-overline mb-2 px-3 text-muted-foreground/70">{group.label}</p>
              <ul className="space-y-0.5">
                {group.items.map((item) => (
                  <li key={item.to}>
                    <NavLink
                      to={item.to}
                      end={item.end}
                      onClick={onClose}
                      className={({ isActive }) =>
                        cn(
                          'group relative flex items-center gap-2.5 rounded-lg px-3 py-2 transition-all duration-200',
                          isActive
                            ? 'gradient-primary text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.12),0_6px_14px_-6px_rgba(24,50,81,0.5)]'
                            : 'text-foreground/70 hover:bg-muted hover:text-foreground',
                        )
                      }
                    >
                      {({ isActive }) => (
                        <>
                          <item.icon
                            className={cn(
                              'size-4 shrink-0 transition-transform duration-200',
                              isActive ? 'text-white' : 'text-muted-foreground group-hover:translate-x-0.5 group-hover:text-foreground',
                            )}
                            aria-hidden
                          />
                          <span className="t-body font-medium">{item.label}</span>
                        </>
                      )}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>

        <div className="border-t border-border px-5 py-3.5">
          <p className="t-caption flex items-center gap-2 text-muted-foreground">
            <span className="size-1.5 rounded-full bg-success" aria-hidden />
            FlightFlow v0.1 · local stack
          </p>
        </div>
      </aside>
    </>
  )
}
