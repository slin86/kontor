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

      {s && s.expense_groups.length > 0 && (
        <div className="grid gap-x-12 gap-y-10 lg:grid-cols-2">
          <section aria-labelledby="kuchen">
            <h2 id="kuchen" className="mb-4 text-xl">
              Ausgaben nach Kategorie
            </h2>
            <ExpensePie groups={s.expense_groups} total={s.expenses} height={380} />
          </section>
          <section aria-labelledby="anteile">
            <h2 id="anteile" className="mb-4 text-xl">
              Anteil an den Ausgaben
            </h2>
            <GroupBars groups={s.expense_groups} total={s.expenses} />
          </section>
        </div>
      )}
    </div>
  )
}
