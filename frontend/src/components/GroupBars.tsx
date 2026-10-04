import type { Group } from '../cashflowApi'
import { euro, percent } from '../format'

/** Share of each expense group in the total, as plain bars (no chart library needed). */
export function GroupBars({ groups, total }: { groups: Group[]; total: number }) {
  if (groups.length === 0 || total <= 0) return null
  return (
    <ul className="space-y-3">
      {groups.map((g) => (
        <li key={g.category_id}>
          <div className="flex items-baseline justify-between gap-4 text-sm">
            <span className="font-medium">{g.name}</span>
            <span className="zahl text-tinte-weich">
              {euro(g.total)} · {percent(g.total / total)}
            </span>
          </div>
          <div className="mt-1 h-2 bg-tinte/10" aria-hidden>
            <div className="h-full bg-sand" style={{ width: `${(g.total / total) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  )
}
