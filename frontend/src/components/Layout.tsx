import { NavLink, Outlet, useLocation } from 'react-router-dom'

import { AccountMenu } from './AccountMenu'
import { PersonProvider, usePerson } from '../person'
import { Pegel } from './Pegel'
import { PersonSwitcher } from './PersonSwitcher'

const NAV = [
  { to: '/', label: 'Cashflow', end: true },
  { to: '/finanzierungen', label: 'Finanzierungen' },
  { to: '/depot', label: 'Depot' },
  { to: '/ist', label: 'Plan & Ist' },
  { to: '/vermoegen', label: 'Vermögen' },
  { to: '/instrumente', label: 'Instrumente' },
]

/** Pages whose numbers can be shown for one person or for everyone. */
const PERSON_PAGES = ['/', '/details', '/posten', '/finanzierungen', '/depot', '/ist', '/vermoegen']

/** Pages that follow the month ruler: the cashflow views, Depot and Plan & Ist. */
const MONTH_PAGES = ['/', '/details', '/posten', '/depot', '/ist']

/** The cashflow area groups its three views and the category management. */
const CASHFLOW_PATHS = ['/', '/details', '/posten', '/kategorien']

function Main() {
  const { people } = usePerson()
  const withSwitcher = PERSON_PAGES.includes(useLocation().pathname) && people.length > 1
  return (
    <main className={`relative mx-auto max-w-6xl px-4 pb-8 sm:px-6 ${withSwitcher ? 'pt-14' : 'pt-8'}`}>
      {withSwitcher && (
        <div className="absolute right-4 top-3 sm:right-6">
          <PersonSwitcher />
        </div>
      )}
      <Outlet />
    </main>
  )
}

export function Layout() {
  const path = useLocation().pathname
  const inCashflow = CASHFLOW_PATHS.includes(path)

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
                  (n.to === '/' ? inCashflow : isActive) ? 'border-elbe text-tinte' : 'border-transparent text-tinte-weich hover:text-tinte'
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

      {MONTH_PAGES.includes(path) && <Pegel />}

      <PersonProvider>
        <Main />
      </PersonProvider>
    </div>
  )
}
