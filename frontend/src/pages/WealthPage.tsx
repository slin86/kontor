import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'

import { AssetForm } from '../components/AssetForms'
import { ConfirmDelete } from '../components/ConfirmDelete'
import { DonutChart } from '../components/DonutChart'
import { input } from '../components/ui'
import { WealthChart } from '../components/WealthChart'
import { euro } from '../format'
import { addMonths, monthLabel } from '../monthUtils'
import { usePerson } from '../person'
import { ASSET_LABEL, wealthApi, type Asset, type WealthPoint } from '../wealthApi'

function Figure({ label, value, tone, note }: { label: string; value: string; tone?: 'plus' | 'minus'; note?: string }) {
  const color = tone === 'minus' ? 'text-bake' : tone === 'plus' ? 'text-elbe-dunkel' : ''
  return (
    <div>
      <div className={`zahl text-3xl font-semibold ${color}`}>{value}</div>
      <div className="text-sm text-tinte-weich">{label}</div>
      {note && <div className="text-xs text-tinte-weich">{note}</div>}
    </div>
  )
}

function AssetRow({ asset, owner, onEdit }: { asset: Asset; owner?: string; onEdit: () => void }) {
  const qc = useQueryClient()
  const remove = useMutation({
    mutationFn: () => wealthApi.removeAsset(asset.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['wealth'] }),
  })
  return (
    <li className="flex flex-wrap items-baseline gap-x-4 gap-y-1 py-3">
      <span className="font-medium">{asset.name}</span>
      <span className="text-sm text-tinte-weich">
        {ASSET_LABEL[asset.kind]}
        {owner && ` · ${owner}`} · Stand {monthLabel(asset.as_of)} · {String(asset.growth_percent).replace('.', ',')} % pro Jahr
      </span>
      <span className="zahl ml-auto">{euro(asset.value)}</span>
      <button type="button" onClick={onEdit} className="text-sm font-medium text-elbe-dunkel hover:underline">
        Bearbeiten
      </button>
      <ConfirmDelete label="Löschen" question={`${asset.name} löschen?`} pending={remove.isPending} error={remove.error} onConfirm={() => remove.mutate()} />
    </li>
  )
}

export function WealthPage() {
  const { selectedId, selected, people } = usePerson()
  const [years, setYears] = useState(20)
  const [real, setReal] = useState(false)
  const [afterTax, setAfterTax] = useState(false)
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)
  const inflation = real ? 2 : 0

  const wealth = useQuery({ queryKey: ['wealth', 'series', selectedId, years, inflation], queryFn: () => wealthApi.wealth(years, inflation, selectedId) })
  const assets = useQuery({ queryKey: ['wealth', 'assets', selectedId], queryFn: () => wealthApi.assets(selectedId) })
  const data = wealth.data

  const net = (p: WealthPoint) => (afterTax ? p.net_after_tax : p.net)
  const view = useMemo(() => {
    if (!data) return undefined
    const at = (month: string) => data.points.find((p) => p.month === month) ?? data.points.at(-1)!
    const now = at(data.today)
    const end = data.points.at(-1)!
    const free = data.points.find((p) => p.month > data.today && p.debts < 0.5 && now.debts > 0.5)
    const positive = now.net < 0 ? data.points.find((p) => p.month > data.today && p.net >= 0) : undefined
    const marks = [0, 5, 10, 20, 30, 40, 50].filter((y) => y <= years).map((y) => ({ years: y, point: y === 0 ? now : at(addMonths(data.today, y * 12)) }))
    const todayIdx = data.points.indexOf(now)
    const slices = data.series
      .map((s, i) => ({ name: s.name, group: s.group, value: now.values[i] }))
      .filter((s) => s.group !== 'debt' && s.value > 0)
    const debts = data.series.map((s, i) => ({ name: s.name, group: s.group, value: now.values[i] })).filter((s) => s.group === 'debt' && s.value > 0)
    return { now, end, free, positive, marks, slices, debts, todayIdx }
  }, [data, years])

  const empty = !!data && (data.series.length === 1 && data.points.every((p) => p.assets === 0 && p.debts === 0))
  const who = selected && selectedId !== null ? selected.name : null

  return (
    <div className="space-y-12">
      <h1 className="sr-only">Vermögen</h1>

      <section aria-labelledby="entwicklung">
        <h2 id="entwicklung" className="text-xl">
          {who ? `Wie sich das Vermögen von ${who} entwickelt` : 'Wie sich dein Vermögen entwickelt'}
        </h2>
        <div className="mt-4 flex flex-wrap items-end gap-x-6 gap-y-3 text-sm">
          <label>
            Zeitraum
            <select value={years} onChange={(e) => setYears(Number(e.target.value))} className={`${input} !mt-1 w-auto`}>
              {[10, 20, 30, 40, 50].map((y) => (
                <option key={y} value={y}>
                  {y} Jahre
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2 pb-2">
            <input type="checkbox" checked={real} onChange={(e) => setReal(e.target.checked)} />
            In heutiger Kaufkraft (2 % Inflation)
          </label>
          <label className="flex items-center gap-2 pb-2">
            <input type="checkbox" checked={afterTax} onChange={(e) => setAfterTax(e.target.checked)} />
            Depot nach Steuern bei Verkauf
          </label>
        </div>

        {data && view && !empty && (
          <>
            <div className="mt-6 flex flex-wrap gap-x-12 gap-y-4">
              <Figure label="Nettovermögen heute" value={euro(net(view.now))} tone={net(view.now) < 0 ? 'minus' : undefined} />
              <Figure label="Vermögenswerte" value={euro(view.now.assets)} />
              <Figure label="Schulden" value={euro(view.now.debts)} tone={view.now.debts > 0 ? 'minus' : undefined} />
              <Figure
                label={`Nettovermögen ${monthLabel(view.end.month)}`}
                value={euro(net(view.end))}
                tone={net(view.end) >= net(view.now) ? 'plus' : 'minus'}
                note={real ? 'in heutiger Kaufkraft' : undefined}
              />
              {view.free && <Figure label="Schuldenfrei ab" value={monthLabel(view.free.month)} />}
              {view.positive && <Figure label="Vermögen übersteigt die Schulden ab" value={monthLabel(view.positive.month)} />}
            </div>
            <div className="mt-6">
              <WealthChart data={data} afterTax={afterTax} />
            </div>
            <p className="mt-2 max-w-2xl text-sm text-tinte-weich">
              Oberhalb der Null-Linie steht, was du besitzt, darunter, was du noch schuldest. Die dunkle Linie ist der Unterschied, dein
              Nettovermögen. Grundlage sind die Annahmen aus Depot, Finanzierungen und den weiteren Vermögenswerten unten. Das sind
              Rechenwerte, keine Zusagen.
            </p>
          </>
        )}
        {data && empty && (
          <p className="mt-6 max-w-xl text-tinte-weich">
            Noch nichts zu zeigen. Lege ein Depot oder eine Finanzierung an oder trage unten Vermögenswerte wie Tagesgeld oder eine
            Immobilie ein.
          </p>
        )}
      </section>

      {data && view && !empty && (
        <div className="grid gap-x-12 gap-y-10 lg:grid-cols-[22rem_1fr]">
          <section aria-labelledby="zusammensetzung">
            <h2 id="zusammensetzung" className="mb-4 text-xl">
              Das besitzt du heute
            </h2>
            <DonutChart slices={view.slices} center={euro(view.now.assets)} caption="Vermögenswerte" height={340} />
          </section>
          <section aria-labelledby="meilensteine">
            <h2 id="meilensteine" className="mb-4 text-xl">
              Stationen
            </h2>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[30rem] text-left text-sm">
                <thead className="text-tinte-weich">
                  <tr>
                    <th className="py-2 pr-4 font-medium">Zeitpunkt</th>
                    <th className="py-2 pr-4 text-right font-medium">Vermögenswerte</th>
                    <th className="py-2 pr-4 text-right font-medium">Schulden</th>
                    <th className="py-2 text-right font-medium">Netto</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-tinte/15">
                  {view.marks.map(({ years: y, point }) => (
                    <tr key={y}>
                      <td className="py-2 pr-4">{y === 0 ? `Heute (${monthLabel(point.month)})` : `In ${y} Jahren (${monthLabel(point.month)})`}</td>
                      <td className="zahl py-2 pr-4 text-right">{euro(point.assets)}</td>
                      <td className="zahl py-2 pr-4 text-right">{point.debts > 0 ? euro(point.debts) : '–'}</td>
                      <td className={`zahl py-2 text-right font-medium ${net(point) < 0 ? 'text-bake' : ''}`}>{euro(net(point))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {view.debts.length > 0 && (
              <>
                <h3 className="mb-1 mt-8 text-base text-tinte-weich">Offene Schulden heute</h3>
                <ul className="divide-y divide-tinte/15 text-sm">
                  {view.debts.map((d) => (
                    <li key={d.name} className="flex justify-between py-2">
                      <span>{d.name}</span>
                      <span className="zahl text-bake">{euro(d.value)}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </section>
        </div>
      )}

      <section aria-labelledby="werte">
        <div className="mb-2 flex items-baseline gap-4">
          <h2 id="werte" className="text-xl">
            Weitere Vermögenswerte
          </h2>
          {!adding && (
            <button type="button" onClick={() => setAdding(true)} className="ml-auto bg-tinte px-4 py-2 text-sm font-medium text-karte hover:bg-elbe-dunkel">
              Vermögenswert hinzufügen
            </button>
          )}
        </div>
        <p className="mb-4 max-w-2xl text-sm text-tinte-weich">
          Depot, Bausparguthaben und Finanzierungen kommen automatisch aus den anderen Bereichen. Hier trägst du dazu, was sonst noch zählt:
          Konten, Immobilien, Fahrzeuge. Der Wert gilt ab dem Stand-Monat und entwickelt sich mit dem Prozentsatz pro Jahr.
        </p>
        {adding && (
          <div className="mb-8">
            <AssetForm onDone={() => setAdding(false)} />
          </div>
        )}
        <ul className="divide-y divide-tinte/15">
          {assets.data?.map((a) =>
            editing === a.id ? (
              <li key={a.id} className="py-3">
                <AssetForm asset={a} onDone={() => setEditing(null)} />
              </li>
            ) : (
              <AssetRow key={a.id} asset={a} owner={selectedId === null && people.length > 1 ? people.find((p) => p.id === a.person_id)?.name : undefined} onEdit={() => setEditing(a.id)} />
            ),
          )}
        </ul>
        {assets.data?.length === 0 && !adding && <p className="text-sm text-tinte-weich">Noch keine eingetragen.</p>}
      </section>
    </div>
  )
}
