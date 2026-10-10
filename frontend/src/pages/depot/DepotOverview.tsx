import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { actualsApi } from '../../actualsApi'
import { DeviationChart, TrackerChart } from '../../components/TrackerChart'
import { input } from '../../components/ui'
import { euro, percent } from '../../format'
import { monthLabel } from '../../monthUtils'
import { usePerson } from '../../person'

const YEAR_CHOICES = Array.from({ length: 10 }, (_, n) => (n + 1) * 5)
const signed = (n: number) => `${n > 0 ? '+' : ''}${euro(n)}`

const VERDICT = {
  ahead: { title: 'Du liegst über Plan', tone: 'text-elbe-dunkel' },
  on_track: { title: 'Du liegst im Plan', tone: 'text-elbe-dunkel' },
  behind: { title: 'Du liegst unter Plan', tone: 'text-bake' },
} as const

/** Is the depot on plan? Verdict first, then the chart with real history, forecast and plan. */
export function DepotOverview() {
  const { selectedId } = usePerson()
  const [years, setYears] = useState(20)
  const query = useQuery({ queryKey: ['actuals', 'overview', selectedId, years], queryFn: () => actualsApi.overview(selectedId, years) })
  const d = query.data
  const hasPositions = (d?.tracked.length ?? 0) + (d?.untracked.length ?? 0) > 0

  return (
    <div className="space-y-8">
      <h1 className="sr-only">Depot im Überblick</h1>

      {d && !hasPositions && (
        <p className="max-w-xl text-tinte-weich">
          Lege zuerst unter <Link to="/depot/plan" className="font-medium text-elbe-dunkel hover:underline">Plan</Link> eine Position an. Danach vergleicht Kontor
          hier deine echten Werte mit dem Plan.
        </p>
      )}

      {d && hasPositions && (
        <>
          <section aria-labelledby="urteil">
            {d.status === 'no_data' ? (
              <>
                <h2 id="urteil" className="text-xl">
                  Noch kein Vergleich möglich
                </h2>
                <p className="mt-2 max-w-2xl text-tinte-weich">
                  Trage unter <Link to="/depot/ist" className="font-medium text-elbe-dunkel hover:underline">Ist-Daten</Link> den Wert deiner Positionen zum Monatsende ein oder
                  importiere deine Käufe aus dem Broker. Dann zeigt Kontor, ob du im Plan liegst, und rechnet ab dem letzten echten Wert weiter.
                </p>
              </>
            ) : (
              <>
                <h2 id="urteil" className={`text-2xl ${VERDICT[d.status].tone}`}>
                  {VERDICT[d.status].title}
                </h2>
                <p className="mt-2 max-w-2xl">
                  Stand {monthLabel(d.anchor!)}: <strong className="zahl">{euro(d.actual_now!)}</strong> statt geplant{' '}
                  <strong className="zahl">{euro(d.plan_now!)}</strong> ({signed(d.deviation!)}, {d.deviation_percent! > 0 ? '+' : ''}
                  {percent(d.deviation_percent! / 100)}).
                </p>
                {d.forecast_end !== null && (
                  <p className="mt-1 max-w-2xl text-tinte-weich">
                    Bleibt es bei den geplanten Sparraten und Renditen, steht das Depot im {monthLabel(d.end)} bei{' '}
                    <strong className="zahl text-tinte">{euro(d.forecast_end)}</strong> statt geplanten {euro(d.plan_end)} ({signed(d.end_gap!)}).
                  </p>
                )}
                {d.anchor !== null && d.anchor < d.today && (
                  <p className="mt-1 text-sm text-tinte-weich">
                    Der letzte vollständige Wert ist von {monthLabel(d.anchor)}. Trage die Werte bis {monthLabel(d.today)} nach, dann stimmt der Vergleich mit heute.
                  </p>
                )}
              </>
            )}
          </section>

          <section aria-labelledby="verlauf">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <h2 id="verlauf" className="text-xl">
                Verlauf und Prognose
              </h2>
              <label className="flex flex-col text-sm">
                Zeitraum
                <select value={years} onChange={(e) => setYears(Number(e.target.value))} className={`${input} !mt-1 w-auto`}>
                  {YEAR_CHOICES.map((y) => (
                    <option key={y} value={y}>
                      {y} Jahre
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="mt-4">
              <TrackerChart data={d} />
            </div>
            <p className="mt-3 max-w-2xl text-sm text-tinte-weich">
              Die dicke Linie vor „Heute“ sind deine echten Monatswerte, die orange Linie rechnet ab dem letzten echten Wert mit den erwarteten Renditen, Kosten und
              geplanten Sparraten weiter. Die gestrichelte Linie ist der Plan, wie er ohne deine echten Werte aussähe. Das sind Annahmen, keine Zusagen.
            </p>
            {d.status !== 'no_data' && d.untracked.length > 0 && (
              <p className="mt-2 max-w-2xl text-sm text-tinte-weich">
                Ohne echte Werte, daher mit ihrem Planwert gerechnet: {d.untracked.join(', ')}.
              </p>
            )}
          </section>

          {d.status !== 'no_data' && (
            <section aria-labelledby="abweichung">
              <h2 id="abweichung" className="text-xl">
                Abweichung vom Plan
              </h2>
              <p className="mt-1 max-w-2xl text-sm text-tinte-weich">Echter Wert minus Planwert je Monat. Oberhalb der Null-Linie liegst du vor dem Plan.</p>
              <div className="mt-3">
                <DeviationChart data={d} />
              </div>
            </section>
          )}
        </>
      )}
    </div>
  )
}
