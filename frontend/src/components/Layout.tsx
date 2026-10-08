import { NavLink, Outlet, useLocation } from 'react-router-dom'

import { AccountMenu } from './AccountMenu'
import { PersonProvider } from '../person'
import { Pegel } from './Pegel'

const NAV = [
  { to: '/', label: 'Cashflow', end: true },
  { to: '/finanzierungen', label: 'Finanzierungen' },
  { to: '/depot', label: 'Depot' },
  { to: '/ist', label: 'Plan & Ist' },
  { to: '/instrumente', label: 'Instrumente' },
]

export function Layout() {
  // the category management is part of the cashflow area
  const inCashflow = useLocation().pathname === '/kategorien'

  return (
    <div className="min-h-screen">
      <header className="flex flex-wrap items-baseline gap-x-8 gap-y-2 px-4 py-4 sm:px-6">
        <span className="font-display text-2xl font-bold tracking-tight">Kontor</span>
        <nav className="flex gap-5" aria-label="Hauptnavigation">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={({ isActive }) =>
                `border-b-2 pb-0.5 text-sm font-medium ${
                  isActive || (n.to === '/' && inCashflow) ? 'border-elbe text-tinte' : 'border-transparent text-tinte-weich hover:text-tinte'
                }`
              }
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="ml-auto text-sm">
          <AccountMenu />
        </div>
      </header>

      <Pegel />

      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        <PersonProvider>
          <Outlet />
        </PersonProvider>
      </main>
    </div>
  )
}
