import type { Group } from '../../cashflowApi'
import { euro, FREQUENCY_LABEL } from '../../format'
import { ExpensePie } from '../../components/ExpensePie'
import { GroupBars } from '../../components/GroupBars'
import { SeriesView } from '../../components/SeriesView'
import { monthLabel } from '../../monthUtils'
import { useMonth } from '../../month'
import { useCashflowData } from './useCashflowData'

export function DetailsView() {
  const { selected } = useMonth()
  const { items, summary, series } = useCashflowData()
  const s = summary.data
  const reserves = (items.data ?? []).filter(
    (i) => i.kind === 'expense' && !i.spread && !i.transfer_to_id && i.active && i.active.frequency !== 'monthly',
  )
  const reserveTotal = reserves.reduce((sum, i) => sum + i.active!.monthly, 0)
  const reserveBooked = reserves.reduce((sum, i) => sum + i.booked, 0)
  // financings are spending too: they get their own slice next to the expense groups
  const shares: Group[] = s
    ? [
        ...s.expense_groups,
        ...(s.financing > 0 ? [{ category_id: -1, name: 'Finanzierungen', kind: 'expense' as const, total: s.financing, children: [], direct: false }] : []),
      ].sort((a, b) => b.total - a.total)
    : []
  const shareTotal = s ? s.expenses + s.financing : 0
  const hasLumps = items.data?.some((i) => !i.spread && i.active && i.active.frequency !== 'monthly') ?? false

  if (items.data?.length === 0) {
    return <p className="max-w-xl text-tinte-weich">Für {monthLabel(selected)} gibt es noch keine Posten.</p>
  }
  return (
    <div className="space-y-12">
      <h1 className="sr-only">Details zum Cashflow</h1>
      <section aria-labelledby="verlauf">
        <h2 id="verlauf" className="mb-4 text-xl">
          Verlauf über die Zeit
        </h2>
        {series.data && <SeriesView data={series.data} />}
        <p className="mt-2 max-w-xl text-sm text-tinte-weich">
          Endet ein Posten, etwa eine Kita-Gebühr, steigt der Überschuss ab diesem Monat sichtbar.
          {hasLumps && ' Posten ohne Aufteilung zählen nur in ihrem Fälligkeitsmonat, das zeigen die Ausschläge.'}
        </p>
      </section>

      {reserves.length > 0 && (
        <section aria-labelledby="ruecklage">
          <h2 id="ruecklage" className="text-xl">
            Rücklage pro Monat
          </h2>
          <p className="mt-2 max-w-2xl text-sm text-tinte-weich">
            Diese Posten zählen nur in ihrem Fälligkeitsmonat. Legst du jeden Monat <strong className="zahl">{euro(reserveTotal)}</strong> zurück,
            ist das Geld da, wenn sie fällig werden.
          </p>
          <ul className="mt-3 max-w-2xl divide-y divide-tinte/15 text-sm">
            {reserves.map((i) => (
              <li key={i.id} className="flex flex-wrap items-baseline gap-x-4 py-2">
                <span className="font-medium">{i.name}</span>
                <span className="text-tinte-weich">
                  {euro(i.active!.amount, true)} {FREQUENCY_LABEL[i.active!.frequency]}
                </span>
                <span className="zahl ml-auto">{euro(i.active!.monthly, true)} pro Monat</span>
              </li>
            ))}
          </ul>
          {s && (
            <p className="mt-3 text-sm text-tinte-weich">
              Nach Rücklagen bleiben im Schnitt <span className="zahl font-medium text-tinte">{euro(s.balance + reserveBooked - reserveTotal)}</span> pro Monat.
            </p>
          )}
        </section>
      )}

      {s && shares.length > 0 && (
        <div className="grid gap-x-12 gap-y-10 lg:grid-cols-2">
          <section aria-labelledby="kuchen">
            <h2 id="kuchen" className="mb-4 text-xl">
              Ausgaben nach Kategorie
            </h2>
            <ExpensePie groups={shares} total={shareTotal} height={380} />
          </section>
          <section aria-labelledby="anteile">
            <h2 id="anteile" className="mb-4 text-xl">
              Anteil an den Ausgaben
            </h2>
            <GroupBars groups={shares} total={shareTotal} />
          </section>
        </div>
      )}
    </div>
  )
}
