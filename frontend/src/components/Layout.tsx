import { NavLink, Outlet } from 'react-router-dom'

import { useAuth } from '../auth'
import { useMonth } from '../month'
import { monthLabel } from '../monthUtils'
import { Pegel } from './Pegel'

const NAV = [
  { to: '/', label: 'Cashflow', end: true },
  { to: '/finanzierungen', label: 'Finanzierungen' },
  { to: '/depot', label: 'Depot' },
]

export function Layout() {
  const { me, logout } = useAuth()
  const { selected, current, isLocked } = useMonth()

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
                  isActive ? 'border-elbe text-tinte' : 'border-transparent text-tinte-weich hover:text-tinte'
                }`
              }
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="ml-auto flex items-baseline gap-4 text-sm">
          <span className="text-tinte-weich">{me?.user.display_name}</span>
          <button type="button" onClick={() => void logout()} className="font-medium text-elbe-dunkel hover:underline">
            Abmelden
          </button>
        </div>
      </header>

      <Pegel />

      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        <p className="mb-6 text-sm text-tinte-weich">
          {monthLabel(selected)} ·{' '}
          {isLocked(selected)
            ? 'abgeschlossen. Änderungen sind nur als Korrektur möglich.'
            : selected === current
              ? 'aktueller Monat'
              : 'geplant'}
        </p>
        <Outlet />
      </main>
    </div>
  )
}
