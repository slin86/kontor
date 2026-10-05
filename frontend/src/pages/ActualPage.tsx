import { useMutation, useQuery } from '@tanstack/react-query'
import { useQueryClient } from '@tanstack/react-query'

import { actualsApi, KIND_LABEL } from '../actualsApi'
import { DepositChart, ValueChart } from '../components/ComparisonChart'
import { ImportPanel, TransactionForm, ValueForm } from '../components/ActualForms'
import { euro, percent } from '../format'
import { monthLabel } from '../monthUtils'

const signed = (n: number) => `${n > 0 ? '+' : ''}${euro(n)}`

export function ActualPage() {
  const qc = useQueryClient()
  const compare = useQuery({ queryKey: ['actuals', 'compare'], queryFn: actualsApi.compare })
  const transactions = useQuery({ queryKey: ['actuals', 'transactions'], queryFn: actualsApi.transactions })
  const remove = useMutation({
    mutationFn: actualsApi.removeTransaction,
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['actuals'] })
      await qc.invalidateQueries({ queryKey: ['cashflow'] })
    },
  })
  const data = compare.data
  const hasPositions = (data?.instruments.length ?? 0) > 0
  const hasActual = data?.points.some((p) => p.actual !== null) ?? false
  const hasDeposits = data?.points.some((p) => p.actual_deposit !== null) ?? false

  return (
    <div className="space-y-12">
      <h1 className="sr-only">Plan und Ist</h1>

      <section aria-labelledby="vergleich">
        <h2 id="vergleich" className="text-xl">
          Plan und Ist
        </h2>
        {data && !hasPositions && (
          <p className="mt-3 max-w-xl text-tinte-weich">
            Lege zuerst auf der Seite Depot eine Position an. Danach kannst du hier tatsächliche Werte und Käufe eintragen und mit dem Plan vergleichen.
          </p>
        )}
        {data && hasPositions && (
          <>
            <p className="mt-2 max-w-2xl text-sm text-tinte-weich">
              {hasActual
                ? 'Die gestrichelte Linie ist der Plan für die Positionen, zu denen du Werte eingetragen hast. Die durchgezogene Linie zeigt, was sie tatsächlich wert waren.'
                : 'Trage unten den Wert deiner Positionen zum Monatsende ein, dann erscheint hier der Vergleich mit dem Plan.'}
            </p>
            <div className="mt-4">
              <ValueChart data={data} />
            </div>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[38rem] text-left text-sm">
                <thead className="text-tinte-weich">
                  <tr>
                    <th className="py-2 pr-4 font-medium">Position</th>
                    <th className="py-2 pr-4 text-right font-medium">Plan</th>
                    <th className="py-2 pr-4 text-right font-medium">Ist</th>
                    <th className="py-2 pr-4 text-right font-medium">Abweichung</th>
                    <th className="py-2 text-right font-medium">Netto investiert (Ist / Plan)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-tinte/15">
                  {data.instruments.map((r) => (
                    <tr key={r.id}>
                      <td className="py-2 pr-4">{r.name}</td>
                      <td className="zahl py-2 pr-4 text-right">{euro(r.planned_value)}</td>
                      <td className="zahl py-2 pr-4 text-right">
                        {r.actual_value !== null ? (
                          <>
                            {euro(r.actual_value)}
                            <span className="block text-xs text-tinte-weich">Stand {monthLabel(r.actual_month!)}</span>
                          </>
                        ) : (
                          <span className="text-tinte-weich">kein Wert</span>
                        )}
                      </td>
                      <td className={`zahl py-2 pr-4 text-right font-medium ${r.deviation === null ? '' : r.deviation >= 0 ? 'text-elbe-dunkel' : 'text-bake'}`}>
                        {r.deviation !== null ? (
                          <>
                            {signed(r.deviation)}
                            {r.deviation_percent !== null && <span className="block text-xs font-normal">{percent(r.deviation_percent / 100)}</span>}
                          </>
                        ) : (
                          ''
                        )}
                      </td>
                      <td className="zahl py-2 text-right">
                        {r.actual_net_invested !== null ? `${euro(r.actual_net_invested)} / ${euro(r.planned_paid_in)}` : <span className="text-tinte-weich">keine Käufe erfasst</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {hasDeposits && (
              <div className="mt-8">
                <h3 className="mb-1 text-lg">Einzahlungen pro Monat</h3>
                <DepositChart data={data} />
              </div>
            )}
          </>
        )}
      </section>

      <section aria-labelledby="wert">
        <h2 id="wert" className="mb-3 text-xl">
          Wert erfassen
        </h2>
        <p className="mb-4 max-w-2xl text-sm text-tinte-weich">
          Gib den Wert einer Position zum Monatsende ein, so wie ihn dein Broker zeigt. Den aktuellen Monat kannst du jederzeit ändern.
          Bei abgeschlossenen Monaten ist eine Begründung nötig, das Änderungsprotokoll hält sie fest.
        </p>
        <ValueForm />
      </section>

      <section aria-labelledby="kaeufe">
        <h2 id="kaeufe" className="mb-3 text-xl">
          Käufe und Verkäufe
        </h2>
        <TransactionForm />
        {transactions.data && transactions.data.length > 0 && (
          <ul className="mt-6 divide-y divide-tinte/15 text-sm">
            {transactions.data.map((t) => (
              <li key={t.id} className="flex flex-wrap items-baseline gap-x-4 py-2">
                <span className="w-24 text-tinte-weich">{t.day}</span>
                <span className="w-20">{KIND_LABEL[t.kind]}</span>
                <span>{t.name ?? t.isin ?? 'Position'}</span>
                <span className="text-xs text-tinte-weich">{t.source === 'csv' ? 'Import' : 'manuell'}</span>
                <span className="zahl ml-auto font-medium">{euro(t.amount, true)}</span>
                <button type="button" onClick={() => remove.mutate(t.id)} className="font-medium text-elbe-dunkel hover:underline">
                  Entfernen
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="import">
        <h2 id="import" className="mb-3 text-xl">
          Import aus dem Broker
        </h2>
        <ImportPanel />
      </section>
    </div>
  )
}
