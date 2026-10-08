import { ExpensePie } from '../../components/ExpensePie'
import { SankeyView } from '../../components/SankeyView'
import { euro, percent } from '../../format'
import { useMonth } from '../../month'
import { monthLabel } from '../../monthUtils'
import { usePerson } from '../../person'
import { useCashflowData } from './useCashflowData'

function Figure({ label, value, tone }: { label: string; value: string; tone?: 'bad' }) {
  return (
    <div>
      <div className={`zahl text-3xl font-semibold ${tone === 'bad' ? 'text-bake' : ''}`}>{value}</div>
      <div className="text-sm text-tinte-weich">{label}</div>
    </div>
  )
}

export function OverviewView() {
  const { selected } = useMonth()
  const { selectedId, people } = usePerson()
  const { items, summary: summaryQuery, sankey } = useCashflowData()
  const s = summaryQuery.data
  const empty = items.data?.length === 0

  return (
    <div className="space-y-12">
      <h1 className="sr-only">Cashflow im {monthLabel(selected)}</h1>
      <section aria-label="Kennzahlen">
        {selectedId === null && people.length > 1 && (
          <p className="mb-6 text-sm text-tinte-weich">
            Haushalt gesamt: Übertragungen zwischen Personen heben sich auf und tauchen hier nicht als Einnahme oder Ausgabe auf.
          </p>
        )}
        {s && (
          <div className="flex flex-wrap gap-x-12 gap-y-4">
            <Figure label="Einnahmen pro Monat" value={euro(s.income)} />
            <Figure label="Ausgaben pro Monat" value={euro(s.expenses)} />
            {s.financing > 0 && <Figure label="Finanzierungen pro Monat" value={euro(s.financing)} />}
            <Figure label={s.balance < 0 ? 'Fehlbetrag' : 'Übrig'} value={euro(s.balance)} tone={s.balance < 0 ? 'bad' : undefined} />
            {s.savings_rate !== null && <Figure label="Sparquote" value={percent(s.savings_rate)} />}
          </div>
        )}
      </section>

      {empty ? (
        <p className="max-w-xl text-tinte-weich">
          Für {monthLabel(selected)} gibt es noch keine Posten. Erfasse sie unter „Posten“, dann erscheint hier der Geldfluss.
        </p>
      ) : (
        <div className="grid gap-x-10 gap-y-12 xl:grid-cols-[1fr_20rem]">
          <section aria-labelledby="fluss">
            <h2 id="fluss" className="mb-4 text-xl">
              Wohin das Geld fließt
            </h2>
            {sankey.data && <SankeyView data={sankey.data} />}
          </section>
          {s && s.expense_groups.length > 0 && (
            <section aria-labelledby="kuchen">
              <h2 id="kuchen" className="mb-4 text-xl">
                Ausgaben nach Kategorie
              </h2>
              <ExpensePie groups={s.expense_groups} total={s.expenses} />
            </section>
          )}
        </div>
      )}
    </div>
  )
}
