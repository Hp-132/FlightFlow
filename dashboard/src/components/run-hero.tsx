import { motion } from 'framer-motion'
import {
  Activity,
  ArrowDown,
  ArrowRight,
  BarChart3,
  GaugeCircle,
  Info,
  Search,
  ShieldCheck,
  Users,
} from 'lucide-react'
import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { useActiveRun } from '@/lib/run-context'

/** Free-licensed photos from Wikimedia Commons; credited where shown. */
const PHOTOS = {
  hero: {
    src: '/images/hero-sunset-landing.jpg',
    credit: 'Jongsun Lee',
    license: 'CC BY 3.0',
    href: 'https://commons.wikimedia.org/wiki/File:Sunset_At_The_Airport_(192242589).jpeg',
  },
  apron: {
    src: '/images/airport-apron.jpg',
    credit: 'Joe Mabel',
    license: 'CC BY-SA 3.0',
    href: 'https://commons.wikimedia.org/wiki/File:SeaTac_Airport_02.jpg',
  },
}

/**
 * Licence attribution kept out of the way: a small info icon on the photo
 * that reveals the credit on hover, keyboard focus or tap. The CC BY /
 * CC BY-SA licences require the credit to be reachable, not prominent.
 */
function PhotoCredit({ photo, className }: { photo: (typeof PHOTOS)['hero']; className?: string }) {
  return (
    <div className={`group/credit absolute z-10 ${className ?? ''}`}>
      <button
        type="button"
        aria-label="Photo credit"
        className="flex size-6 items-center justify-center rounded-full bg-black/25 text-white/70 backdrop-blur-sm transition-colors hover:bg-black/45 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/60"
      >
        <Info className="size-3.5" aria-hidden />
      </button>
      <a
        href={photo.href}
        target="_blank"
        rel="noreferrer"
        className="t-caption pointer-events-none absolute bottom-full right-0 mb-1.5 whitespace-nowrap rounded-md bg-black/70 px-2 py-1 text-white/90 opacity-0 backdrop-blur-sm transition-opacity duration-200 group-hover/credit:pointer-events-auto group-hover/credit:opacity-100 group-focus-within/credit:pointer-events-auto group-focus-within/credit:opacity-100 hover:text-white"
      >
        Photo: {photo.credit} · {photo.license}
      </a>
    </div>
  )
}

export function RunHero({ onConfigure }: { onConfigure: () => void }) {
  const { runId } = useActiveRun()

  return (
    <section className="relative isolate overflow-hidden rounded-2xl bg-primary text-white shadow-raised">
      <img
        src={PHOTOS.hero.src}
        alt="A passenger jet coming in to land against an orange sunset"
        className="absolute inset-0 -z-10 h-full w-full object-cover object-[70%_center]"
      />
      {/* Navy wash so the text side stays readable; the plane side stays bright. */}
      <div
        aria-hidden
        className="absolute inset-0 -z-10 bg-linear-to-r from-[#0f2238]/90 from-25% via-[#0f2238]/45 via-55% to-transparent max-md:bg-linear-to-b max-md:from-[#0f2238]/10 max-md:from-0% max-md:via-[#0f2238]/70 max-md:via-40% max-md:to-[#0f2238]/92"
      />

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, ease: 'easeOut' }}
        className="max-w-xl px-6 pb-10 pt-44 sm:px-10 md:py-20"
      >
        <p className="t-overline text-[#f3c58a]">Airline disruption recovery</p>
        <h1 className="t-hero mt-3 text-white">When flights get cancelled, every passenger still gets home.</h1>
        <p className="t-body mt-4 text-white/80">
          FlightFlow simulates a bad-weather day at an airport. Hundreds of flights are cancelled, and the system
          automatically finds new seats for thousands of stranded passengers — without ever selling the same seat
          twice.
        </p>

        <div className="mt-8 flex flex-wrap items-center gap-3">
          <Button
            size="lg"
            variant="secondary"
            onClick={onConfigure}
            className="bg-white text-primary shadow-[0_8px_20px_-8px_rgba(0,0,0,0.5)] hover:shadow-[0_12px_24px_-8px_rgba(0,0,0,0.55)]"
          >
            Start a simulation
            <ArrowDown />
          </Button>
          {runId && (
            <Button asChild size="lg" variant="ghost" className="glass-panel text-white hover:bg-white/15 hover:text-white">
              <Link to="/live">
                <Activity />
                See the current run
              </Link>
            </Button>
          )}
        </div>
      </motion.div>

      <PhotoCredit photo={PHOTOS.hero} className="bottom-3 right-3" />
    </section>
  )
}

const STEPS = [
  {
    title: 'Choose a scenario',
    detail: 'Pick how big the airline is and how bad the storm is.',
  },
  {
    title: 'Press Start',
    detail: 'Flights are cancelled, and the system looks for new flights for everyone affected.',
  },
  {
    title: 'Watch and check',
    detail: 'See passengers being rebooked live, then run a safety check that proves nothing went wrong.',
  },
]

/** Plain-language "how it works": one photo, three steps. */
export function HowItWorks() {
  return (
    <section className="grid items-stretch gap-6 lg:grid-cols-[1fr_1.1fr]">
      <figure className="relative min-h-56 overflow-hidden rounded-2xl shadow-card">
        <img
          src={PHOTOS.apron.src}
          alt="Aerial view of a busy airport with many passenger jets parked at the gates"
          loading="lazy"
          className="absolute inset-0 h-full w-full object-cover contrast-[1.12] saturate-[1.2] transition-transform duration-700 ease-out hover:scale-[1.03]"
        />
        <figcaption className="absolute inset-x-0 bottom-0 bg-linear-to-t from-[#0f2238]/85 to-transparent pb-3 pl-4 pr-12 pt-10">
          <p className="t-section text-white">One storm. Hundreds of flights. Thousands of passengers.</p>
        </figcaption>
        <PhotoCredit photo={PHOTOS.apron} className="bottom-3 right-3" />
      </figure>

      <div className="flex flex-col justify-center">
        <p className="t-overline text-secondary">How it works</p>
        <h2 className="t-headline mt-1.5 text-foreground">Three simple steps</h2>
        <ol className="mt-5 space-y-4">
          {STEPS.map((step, i) => (
            <motion.li
              key={step.title}
              initial={{ opacity: 0, x: 6 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.3, delay: 0.1 + i * 0.06 }}
              className="flex gap-4"
            >
              <span className="gradient-primary t-label flex size-8 shrink-0 items-center justify-center rounded-full font-semibold text-white">
                {i + 1}
              </span>
              <div>
                <p className="t-section text-foreground">{step.title}</p>
                <p className="t-body text-muted-foreground">{step.detail}</p>
              </div>
            </motion.li>
          ))}
        </ol>
      </div>
    </section>
  )
}

const PAGES = [
  { to: '/live', icon: Activity, title: 'Live Run', detail: 'Watch passengers being rebooked in real time.' },
  { to: '/invariants', icon: ShieldCheck, title: 'Safety Checks', detail: 'Prove no seat was double-booked and no one was missed.' },
  { to: '/sagas', icon: Search, title: 'Passenger History', detail: 'Look up any passenger and see every step of their rebooking.' },
  { to: '/compare', icon: BarChart3, title: 'Compare', detail: 'Put two planning methods side by side.' },
  { to: '/tenants', icon: Users, title: 'Airlines', detail: 'Check every airline was treated fairly.' },
  { to: '/ops', icon: GaugeCircle, title: 'System Health', detail: 'Server and queue charts from Grafana.' },
]

/** A short map of the dashboard for first-time visitors. */
export function PageGuide() {
  return (
    <section>
      <p className="t-overline text-secondary">What's in this dashboard</p>
      <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {PAGES.map((p) => (
          <Link
            key={p.to}
            to={p.to}
            className="group flex items-start gap-3 rounded-xl border border-border bg-card p-4 shadow-card transition-all duration-300 hover:-translate-y-0.5 hover:border-secondary/40 hover:shadow-card-hover"
          >
            <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-secondary/12 text-secondary transition-colors duration-300 group-hover:bg-primary group-hover:text-white">
              <p.icon className="size-4" aria-hidden />
            </span>
            <div className="min-w-0 flex-1">
              <p className="t-section flex items-center gap-1 text-foreground">
                {p.title}
                <ArrowRight
                  className="size-3.5 -translate-x-1 opacity-0 transition-all duration-300 group-hover:translate-x-0 group-hover:opacity-100"
                  aria-hidden
                />
              </p>
              <p className="t-caption mt-0.5 text-muted-foreground">{p.detail}</p>
            </div>
          </Link>
        ))}
      </div>
    </section>
  )
}
