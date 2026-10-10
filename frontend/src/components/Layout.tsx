import { useEffect, useRef } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'

import { AccountMenu } from './AccountMenu'
import { JobNotices } from './JobNotices'
import { PersonProvider, usePerson } from '../person'
import { Pegel } from './Pegel'
import { PersonSwitcher } from './PersonSwitcher'

const NAV = [
  { to: '/', label: 'Cashflow', end: true },
  { to: '/finanzierungen', label: 'Finanzierungen' },
  { to: '/depot', label: 'Depot' },
  { to: '/vermoegen', label: 'Vermögen' },
  { to: '/immobilien', label: 'Immobilien' },
]

/** Pages whose numbers can be shown for one person or for everyone. */
const PERSON_PAGES = ['/', '/details', '/posten', '/finanzierungen', '/depot', '/depot/plan', '/depot/ist', '/vermoegen', '/immobilien']

/** Pages that follow the month ruler: the cashflow views and the depot's plan and real data. */
const MONTH_PAGES = ['/', '/details', '/posten', '/depot/plan', '/depot/ist']

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
  const inDepot = path === '/depot' || path.startsWith('/depot/')
  const nav = useRef<HTMLElement>(null)

  // On a phone the navigation scrolls sideways; keep the current area in view.
  useEffect(() => {
    nav.current?.querySelector('[data-active="true"]')?.scrollIntoView({ inline: 'center', block: 'nearest' })
  }, [path])

  return (
    <div className="min-h-screen">
      <header className="flex flex-wrap items-center gap-x-8 gap-y-1 px-4 pt-3 sm:items-baseline sm:px-6 sm:py-4">
        <span className="font-display text-2xl font-bold tracking-tight">Kontor</span>
        <nav
          ref={nav}
          className="order-3 -mx-4 flex w-[calc(100%+2rem)] gap-6 overflow-x-auto px-4 [scrollbar-width:none] sm:order-none sm:mx-0 sm:w-auto sm:gap-5 sm:overflow-visible sm:px-0 [&::-webkit-scrollbar]:hidden"
          aria-label="Hauptnavigation"
        >
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              data-active={n.to === '/' ? inCashflow : n.to === '/depot' ? inDepot : path === n.to}
              className={({ isActive }) =>
                `shrink-0 whitespace-nowrap border-b-2 py-2.5 text-sm font-medium sm:py-0 sm:pb-0.5 ${
                  (n.to === '/' ? inCashflow : n.to === '/depot' ? inDepot : isActive) ? 'border-elbe text-tinte' : 'border-transparent text-tinte-weich hover:text-tinte'
                }`
              }
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="ml-auto text-sm sm:order-none">
          <AccountMenu />
        </div>
      </header>

      {MONTH_PAGES.includes(path) && <Pegel />}

      <PersonProvider>
        <Main />
      </PersonProvider>
      <JobNotices />
    </div>
  )
}
