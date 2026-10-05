import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'

import { EChart } from '../charts/EChart'
import { catalogApi, type CatalogEntry } from '../catalogApi'
import { euro } from '../format'
import { input } from './ui'

const pct = (n: number) => `${n.toFixed(2).replace('.', ',')} %`

function shortName(name: string): string {
  return name.length > 34 ? `${name.slice(0, 33)}…` : name
}

/** Effect of the running costs on a savings plan: same return for everyone, only the TER differs. */
export function CostCompare({
  selected,
  onRemove,
}: {
  selected: CatalogEntry[]
  onRemove: (id: number) => void
}) {
  const [monthly, setMonthly] = useState(300)
  const [years, setYears] = useState(20)
  const [ret, setRet] = useState(6)
  const ids = selected.map((s) => s.id)
  const query = useQuery({
    queryKey: ['catalog', 'compare', ids, monthly, years, ret],
    queryFn: () => catalogApi.compare(ids, monthly, years, ret),
    enabled: ids.length > 0,
  })
  const data = query.data

  const option = useMemo(() => {
    if (!data) return {}
    const rows = [...data.results].sort((a, b) => a.total_costs - b.total_costs)
    return {
      grid: { left: 8, right: 24, top: 8, bottom: 8, containLabel: true },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (v: number) => euro(v) },
      xAxis: {
        type: 'value',
        axisLabel: { color: '#4b5d6e', formatter: (v: number) => euro(v) },
        splitLine: { lineStyle: { color: '#12263a1a' } },
      },
      yAxis: {
        type: 'category',
        inverse: true,
        data: rows.map((r) => shortName(r.entry.name)),
        axisLabel: { color: '#12263a' },
        axisLine: { lineStyle: { color: '#12263a55' } },
      },
      series: [
        {
          name: `Kosten über ${data.years} Jahre`,
          type: 'bar',
          itemStyle: { color: '#d2432f' },
          data: rows.map((r) => r.total_costs),
          label: { show: true, position: 'right', color: '#12263a', formatter: (p: { value: number }) => euro(p.value) },
        },
      ],
    }
  }, [data])

  const number = (set: (n: number) => void, min: number, max: number) => (e: { currentTarget: HTMLInputElement }) => {
    const n = Number(e.currentTarget.value.replace(',', '.'))
    if (Number.isFinite(n) && n >= min && n <= max) set(n)
  }
  const commitOnEnter = (e: React.KeyboardEvent<HTMLInputElement>) => e.key === 'Enter' && e.currentTarget.blur()

  return (
    <section aria-labelledby="vergleich" className="border-l-4 border-elbe pl-4 sm:pl-6">
      <h2 id="vergleich" className="text-xl">
        Kostenvergleich
      </h2>
      <ul className="mt-3 flex flex-wrap gap-2 text-sm">
        {selected.map((s) => (
          <li key={s.id} className="flex items-center gap-2 bg-white/60 px-3 py-1">
            <span>{shortName(s.name)}</span>
            <button
              type="button"
              onClick={() => onRemove(s.id)}
              aria-label={`${s.name} aus dem Vergleich entfernen`}
              className="font-medium text-elbe-dunkel hover:underline"
            >
              Entfernen
            </button>
          </li>
        ))}
      </ul>

      <div className="mt-4 flex flex-wrap items-end gap-x-6 gap-y-3 text-sm">
        <label>
          Sparrate pro Monat in Euro
          <input defaultValue={String(monthly)} onBlur={number(setMonthly, 0, 1_000_000)} onKeyDown={commitOnEnter} inputMode="decimal" className={`${input} !mt-1 !w-28`} />
        </label>
        <label>
          Dauer in Jahren
          <input defaultValue={String(years)} onBlur={number(setYears, 1, 60)} onKeyDown={commitOnEnter} inputMode="numeric" className={`${input} !mt-1 !w-24`} />
        </label>
        <label>
          Rendite vor Kosten in Prozent pro Jahr
          <input defaultValue={String(ret).replace('.', ',')} onBlur={number(setRet, -20, 40)} onKeyDown={commitOnEnter} inputMode="decimal" className={`${input} !mt-1 !w-24`} />
        </label>
      </div>

      {data && (
        <>
          <div className="mt-6">
            <EChart option={option} height={Math.max(140, data.results.length * 52 + 24)} label="Kosten der Fonds über den Zeitraum" />
          </div>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[34rem] text-left text-sm">
              <thead className="text-tinte-weich">
                <tr>
                  <th className="py-2 pr-4 font-medium">Fonds</th>
                  <th className="py-2 pr-4 text-right font-medium">TER</th>
                  <th className="py-2 pr-4 text-right font-medium">Endwert</th>
                  <th className="py-2 pr-4 text-right font-medium">Kosten gesamt</th>
                  <th className="py-2 text-right font-medium">Mehrkosten zum günstigsten</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-tinte/15">
                {data.results.map((r) => (
                  <tr key={r.entry.id}>
                    <td className="py-2 pr-4">{r.entry.name}</td>
                    <td className="zahl py-2 pr-4 text-right">{pct(r.entry.ter_percent)}</td>
                    <td className="zahl py-2 pr-4 text-right">{euro(r.final_value)}</td>
                    <td className="zahl py-2 pr-4 text-right">{euro(r.total_costs)}</td>
                    <td className={`zahl py-2 text-right font-medium ${r.extra_vs_cheapest > 0 ? 'text-bake' : 'text-elbe-dunkel'}`}>
                      {r.extra_vs_cheapest > 0 ? euro(r.extra_vs_cheapest) : 'am günstigsten'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 max-w-2xl text-sm text-tinte-weich">
            Eingezahlt werden {euro(data.paid_in)} über {data.years} Jahre. Alle Fonds bekommen dieselbe Rendite vor Kosten, der
            Unterschied entsteht nur durch die laufenden Kosten (TER). Unterschiede bei Handelskosten, Abweichung zum Index und
            Steuern sind nicht eingerechnet.
          </p>
        </>
      )}
      {query.error && <p role="alert" className="mt-3 text-sm font-medium text-bake">{query.error.message}</p>}
    </section>
  )
}
