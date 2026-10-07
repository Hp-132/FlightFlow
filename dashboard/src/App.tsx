import * as React from 'react'
import { Route, Routes } from 'react-router-dom'
import { Toaster } from 'sonner'

import { Header } from '@/components/layout/header'
import { Sidebar } from '@/components/layout/sidebar'
import { ComparePage } from '@/pages/compare'
import { InvariantsPage } from '@/pages/invariants'
import { LiveRunPage } from '@/pages/live-run'
import { OpsPage } from '@/pages/ops'
import { RunControlPage } from '@/pages/run-control'
import { SagaInspectorPage } from '@/pages/saga-inspector'
import { TenantsPage } from '@/pages/tenants'

export default function App() {
  const [navOpen, setNavOpen] = React.useState(false)
  const closeNav = React.useCallback(() => setNavOpen(false), [])

  return (
    <div className="flex h-dvh w-full overflow-hidden bg-background">
      <Sidebar open={navOpen} onClose={closeNav} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header onMenuClick={() => setNavOpen(true)} />
        <main className="app-canvas flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">
          <Routes>
            <Route path="/" element={<RunControlPage />} />
            <Route path="/live" element={<LiveRunPage />} />
            <Route path="/invariants" element={<InvariantsPage />} />
            <Route path="/sagas" element={<SagaInspectorPage />} />
            <Route path="/compare" element={<ComparePage />} />
            <Route path="/tenants" element={<TenantsPage />} />
            <Route path="/ops" element={<OpsPage />} />
          </Routes>
        </main>
      </div>
      <Toaster position="bottom-right" richColors />
    </div>
  )
}
