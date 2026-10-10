import { NavLink, Outlet } from 'react-router-dom'

const VIEWS = [
  { to: '/depot', label: 'Übersicht', end: true },
  { to: '/depot/plan', label: 'Plan' },
  { to: '/depot/ist', label: 'Ist-Daten' },
  { to: '/depot/fonds', label: 'Fonds suchen' },
]

/** Frame of the depot area: overview, plan, real data and the fund search. */
export function DepotShell() {
  return (
    <div>
      <nav aria-label="Depot-Bereich" className="mb-8 flex gap-6 overflow-x-auto border-b border-tinte/15 [scrollbar-width:none]">
        {VIEWS.map((v) => (
          <NavLink
            key={v.to}
            to={v.to}
            end={v.end}
            className={({ isActive }) =>
              `-mb-px shrink-0 whitespace-nowrap border-b-2 pb-2 text-base font-medium ${isActive ? 'border-elbe text-tinte' : 'border-transparent text-tinte-weich hover:text-tinte'}`
            }
          >
            {v.label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </div>
  )
}
