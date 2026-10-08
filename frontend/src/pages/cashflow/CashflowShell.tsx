import { NavLink, Outlet } from 'react-router-dom'

import { useMonth } from '../../month'
import { monthLabel } from '../../monthUtils'

const VIEWS = [
  { to: '/', label: 'Übersicht', end: true },
  { to: '/details', label: 'Details' },
  { to: '/posten', label: 'Posten' },
]

/** Frame of the cashflow area: a sub-navigation for its three views. */
export function CashflowShell() {
  const { selected } = useMonth()
  return (
    <div>
      <nav aria-label="Ansicht" className="mb-8 flex items-baseline gap-6 border-b border-tinte/15">
        {VIEWS.map((v) => (
          <NavLink
            key={v.to}
            to={v.to}
            end={v.end}
            className={({ isActive }) =>
              `-mb-px border-b-2 pb-2 text-base font-medium ${isActive ? 'border-elbe text-tinte' : 'border-transparent text-tinte-weich hover:text-tinte'}`
            }
          >
            {v.label}
          </NavLink>
        ))}
        <span className="ml-auto pb-2 text-sm text-tinte-weich">{monthLabel(selected)}</span>
      </nav>
      <Outlet />
    </div>
  )
}
