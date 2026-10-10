import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { usePerson } from '../person'
import { useState } from 'react'

import { aiApi, type FinancingDraft } from '../aiApi'
import { ConfirmDelete } from '../components/ConfirmDelete'
import { CorrectionForm, eventLabel, EventForm, NewFinancingForm } from '../components/FinancingForms'
import { OutlookView } from '../components/OutlookView'
import { ScheduleView } from '../components/ScheduleView'
import { primary, input } from '../components/ui'
import { euro } from '../format'
import { financingApi, type Financing, type FinancingDetail, type FinancingEvent } from '../financingApi'
import { monthLabel } from '../monthUtils'

const KIND_LABEL: Record<string, string> = {
  real_estate: 'Immobilienfinanzierung',
  consumer: 'Kredit',
  zero_percent: '0 %-Finanzierung',
  other: 'Kredit',
  building_savings: 'Bausparvertrag',
  credit_line: 'Rahmenkredit',
  prefinanced: 'Bausparfinanzierung',
}

const PHASE_LABEL: Record<Financing['phase'], string> = {
  not_started: 'Noch nicht gestartet',
  saving: 'Sparphase',
  loan: 'Läuft',
  finished: 'Abbezahlt',
}

function eventValue(e: FinancingEvent): string {
  return e.kind === 'rate_change' ? `${String(e.value).replace('.', ',')} % pro Jahr` : euro(e.value, true)
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="zahl text-2xl font-semibold">{value}</div>
      <div className="text-sm text-tinte-weich">{label}</div>
    </div>
  )
}

function Outlook() {
  const { selectedId } = usePerson()
  const [years, setYears] = useState(30)
  const [income, setIncome] = useState(0)
  const [expense, setExpense] = useState(0)
  const query = useQuery({
    queryKey: ['financings', 'outlook', years, income, expense, selectedId],
    queryFn: () => financingApi.outlook(years, income, expense, selectedId),
  })
  const data = query.data
  const first = data?.points[0]
  const last = data?.points.at(-1)

  const commit = (set: (n: number) => void) => (e: { currentTarget: HTMLInputElement }) => {
    const n = Number(e.currentTarget.value.replace(',', '.'))
    if (Number.isFinite(n) && n >= -10 && n <= 20) set(n)
  }

  return (
    <section aria-labelledby="ausblick">
      <h2 id="ausblick" className="mb-2 text-xl">
        Wie sich dein Budget entwickelt
      </h2>
      {first && last && (
        <p className="mb-4 max-w-2xl text-tinte-weich">
          Heute bleiben dir <strong className="zahl text-tinte">{euro(first.free)}</strong> im Monat. In {data.years} Jahren
          sind es <strong className="zahl text-tinte">{euro(last.free)}</strong>, wenn Verträge wie geplant enden.
        </p>
      )}
      <div className="mb-4 flex flex-wrap gap-6 text-sm">
        <label className="flex flex-col">
          Zeitraum
          <select value={years} onChange={(e) => setYears(Number(e.target.value))} className={`${input} !mt-1 w-auto`}>
            {[10, 20, 30, 40].map((y) => (
              <option key={y} value={y}>
                {y} Jahre
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col">
          Einnahmen wachsen pro Jahr um (%)
          <input
            defaultValue={String(income).replace('.', ',')}
            onBlur={commit(setIncome)}
            onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
            inputMode="decimal"
            className={`${input} !mt-1 !w-24`}
          />
        </label>
        <label className="flex flex-col">
          Ausgaben wachsen pro Jahr um (%)
          <input
            defaultValue={String(expense).replace('.', ',')}
            onBlur={commit(setExpense)}
            onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
            inputMode="decimal"
            className={`${input} !mt-1 !w-24`}
          />
        </label>
      </div>
      {data && <OutlookView data={data} />}
      {data && data.events.length > 0 && (
        <ul className="mt-4 divide-y divide-tinte/15 text-sm">
          {data.events.map((e, i) => (
            <li key={`${e.month}-${e.label}-${i}`} className="flex flex-wrap items-baseline gap-x-4 py-2">
              <span className="w-24 text-tinte-weich">{monthLabel(e.month)}</span>
              <span>{e.label}</span>
              <span className={`zahl ml-auto font-medium ${e.monthly_change < 0 ? 'text-bake' : 'text-elbe-dunkel'}`}>
                {e.monthly_change > 0 ? '+' : ''}
                {euro(e.monthly_change)} pro Monat
              </span>
            </li>
          ))}
        </ul>
      )}
      {data && data.events.length === 0 && (
        <p className="mt-4 text-sm text-tinte-weich">
          Im gewählten Zeitraum endet keine Finanzierung und kein Posten. Trage Kredite und Bausparverträge ein, dann siehst du,
          wann Budget frei wird.
        </p>
      )}
      <p className="mt-3 max-w-2xl text-sm text-tinte-weich">
        Grundlage sind deine geplanten Posten und Finanzierungen. Ohne Wachstumsannahme bleiben Einnahmen und Ausgaben auf dem
        heutigen Stand, Inflation ist nicht eingerechnet.
      </p>
    </section>
  )
}

function Detail({ financing }: { financing: Financing }) {
  const qc = useQueryClient()
  const [correcting, setCorrecting] = useState(false)
  const query = useQuery({
    queryKey: ['financings', 'detail', financing.id],
    queryFn: () => financingApi.get(financing.id),
  })
  const remove = useMutation({
    mutationFn: (eventId: number) => financingApi.removeEvent(financing.id, eventId),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['financings'] })
      await qc.invalidateQueries({ queryKey: ['cashflow'] })
    },
  })
  const drop = useMutation({
    mutationFn: () => financingApi.remove(financing.id),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['financings'] })
      await qc.invalidateQueries({ queryKey: ['cashflow'] })
    },
  })
  const d: FinancingDetail | undefined = query.data
  if (!d) return null

  return (
    <div className="mt-4 space-y-8 border-l-4 border-tinte/20 pl-4 sm:pl-6">
      <div className="flex flex-wrap gap-x-10 gap-y-4">
        {d.remaining_debt !== null && (
          <Figure
            label={d.kind === 'credit_line' ? 'Aktuell genutzt' : d.prefinanced && d.phase === 'saving' ? 'Vorausdarlehen ausgezahlt' : 'Restschuld'}
            value={euro(d.remaining_debt)}
          />
        )}
        {d.credit_limit !== null && d.available !== null && (
          <>
            <Figure label="Noch verfügbar" value={euro(d.available)} />
            <Figure label="Rahmen" value={euro(d.credit_limit)} />
          </>
        )}
        {d.saved !== null && <Figure label="Angespart" value={euro(d.saved)} />}
        <Figure label="Rate pro Monat" value={euro(d.regular_payment, true)} />
        <Figure label="Zinsen bis zum Ende" value={euro(d.remaining_interest)} />
        <Figure label="Letzter Monat mit Zahlung" value={monthLabel(d.schedule.at(-1)!.month)} />
      </div>

      <div>
        <h3 className="mb-2 text-base">Verlauf</h3>
        <ScheduleView rows={d.schedule} />
      </div>

      <div>
        <h3 className="mb-2 text-base">Ereignisse</h3>
        {d.events.length === 0 ? (
          <p className="mb-4 max-w-xl text-sm text-tinte-weich">
            Noch keine. {d.kind === 'credit_line'
              ? 'Trage hier Einzahlungen, Entnahmen, eine neue Rate oder einen neuen Zins ein. Die Vergangenheit bleibt dabei unverändert.'
              : 'Plane hier eine Sondertilgung, eine neue Rate oder einen neuen Zins nach Ende der Zinsbindung ein. Die Vergangenheit bleibt dabei unverändert.'}
          </p>
        ) : (
          <ul className="mb-4 divide-y divide-tinte/15 text-sm">
            {d.events.map((e) => (
              <li key={e.id} className="flex flex-wrap items-baseline gap-x-4 py-2">
                <span className="w-24 text-tinte-weich">{monthLabel(e.month)}</span>
                <span>{eventLabel(e.kind, d.kind)}</span>
                <span className="zahl ml-auto">{eventValue(e)}</span>
                {e.locked ? (
                  <span className="w-20 text-right text-tinte-weich">abgeschlossen</span>
                ) : (
                  <button
                    type="button"
                    onClick={() => remove.mutate(e.id)}
                    className="w-20 text-right font-medium text-elbe-dunkel hover:underline"
                  >
                    Entfernen
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
        {remove.error && (
          <p role="alert" className="mb-3 text-sm font-medium text-bake">
            {remove.error.message}
          </p>
        )}
        <EventForm detail={d} />
      </div>

      <div className="space-y-4">
        {correcting ? (
          <CorrectionForm detail={d} onDone={() => setCorrecting(false)} />
        ) : (
          <div className="flex flex-wrap gap-x-6 gap-y-2">
            <button type="button" onClick={() => setCorrecting(true)} className="text-sm font-medium text-elbe-dunkel hover:underline">
              Vertragsdaten korrigieren
            </button>
            <ConfirmDelete
              label="Finanzierung löschen"
              question={`„${d.name}“ mit allen Ereignissen löschen? Cashflow und Prognose rechnen danach ohne sie.`}
              pending={drop.isPending}
              error={drop.error}
              onConfirm={() => drop.mutate()}
            />
          </div>
        )}
      </div>
    </div>
  )
}

export function FinancingsPage() {
  const { selectedId, people } = usePerson()
  const list = useQuery({
    queryKey: ['financings', 'list', selectedId],
    queryFn: () => financingApi.list(selectedId),
  })
  const [adding, setAdding] = useState(false)
  const [reading, setReading] = useState(false)
  const [draft, setDraft] = useState<FinancingDraft | undefined>(undefined)
  const readContract = useMutation({
    mutationFn: aiApi.analyzeFinancing,
    onSuccess: (d) => {
      setDraft(d)
      setReading(false)
      setAdding(true)
    },
  })
  const [open, setOpen] = useState<number | null>(null)

  return (
    <div className="space-y-12">
      <h1 className="sr-only">Finanzierungen</h1>
      <Outlook />

      <section aria-labelledby="vertraege">
        <div className="mb-2 flex items-baseline gap-4">
          <h2 id="vertraege" className="text-xl">
            Kredite, Rahmenkredite und Bausparverträge
          </h2>
          {!adding && !reading && (
            <div className="ml-auto flex gap-2 text-sm">
              <button type="button" onClick={() => setReading(true)} className="border border-tinte/40 px-4 py-2 font-medium hover:border-tinte">
                Aus Vertrag
              </button>
              <button type="button" onClick={() => setAdding(true)} className={primary}>
                Finanzierung hinzufügen
              </button>
            </div>
          )}
        </div>

        {reading && (
          <div className="mb-8 max-w-2xl space-y-3 border-t-4 border-tinte pt-5">
            <h3 className="text-lg">Aus Vertrag anlegen</h3>
            <p className="text-sm text-tinte-weich">
              Lade einen Darlehens-, Bauspar- oder Rahmenkreditvertrag als PDF oder Textdatei hoch. Die lokale KI liest Beträge, Zinsen und Termine und füllt das
              Formular vor; Zahlen, die nicht im Text stehen, werden markiert. Die Datei wird nicht gespeichert und geht nie an einen Online-Dienst.
            </p>
            <label className="block text-sm">
              Datei
              <input
                type="file"
                accept=".pdf,.txt"
                disabled={readContract.isPending}
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file) readContract.mutate(file)
                }}
                className={input}
              />
            </label>
            {readContract.isPending && <p className="text-sm text-tinte-weich">Der Vertrag wird gelesen. Mit lokaler KI kann das einige Minuten dauern.</p>}
            {readContract.error && (
              <p role="alert" className="text-sm font-medium text-bake">
                {readContract.error instanceof Error ? readContract.error.message : 'Das hat nicht geklappt.'}
              </p>
            )}
            <button type="button" onClick={() => setReading(false)} className="text-sm font-medium text-elbe-dunkel hover:underline">
              Abbrechen
            </button>
          </div>
        )}

        {adding && (
          <div className="mb-8">
            <NewFinancingForm
              key={draft ? 'draft' : 'blank'}
              draft={draft}
              onDone={(created) => {
                setAdding(false)
                setDraft(undefined)
                setOpen(created.id)
              }}
            />
            <button
              type="button"
              onClick={() => {
                setAdding(false)
                setDraft(undefined)
              }}
              className="mt-2 text-sm font-medium text-elbe-dunkel hover:underline"
            >
              Abbrechen
            </button>
          </div>
        )}

        {list.data?.length === 0 && !adding && (
          <p className="max-w-xl text-tinte-weich">
            Noch keine Finanzierung erfasst. Füge deine Immobilienfinanzierung, Kredite oder Bausparverträge hinzu. Sie fließen in
            Cashflow und Budget-Prognose ein.
          </p>
        )}

        <ul className="divide-y divide-tinte/15">
          {list.data?.map((f) => (
            <li key={f.id} className="py-4">
              <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
                <span className="font-medium">{f.name}</span>
                <span className="text-sm text-tinte-weich">
                  {KIND_LABEL[f.prefinanced ? 'prefinanced' : f.kind === 'loan' ? (f.purpose ?? 'other') : f.kind]} · {PHASE_LABEL[f.phase]}
                  {selectedId === null && people.length > 1 && <> · {people.find((p) => p.id === f.person_id)?.name}</>}
                </span>
                <span className="zahl ml-auto">
                  {euro(f.payment_this_month, true)}
                  <span className="text-sm text-tinte-weich"> diesen Monat</span>
                </span>
                <button
                  type="button"
                  className="text-sm font-medium text-elbe-dunkel hover:underline"
                  onClick={() => setOpen(open === f.id ? null : f.id)}
                >
                  {open === f.id ? 'Schließen' : 'Details'}
                </button>
              </div>
              <div className="text-sm text-tinte-weich">
                {f.remaining_debt !== null && (
                  <>
                    {f.kind === 'credit_line' ? 'Genutzt' : 'Restschuld'} {euro(f.remaining_debt)} ·{' '}
                  </>
                )}
                {f.available !== null && <>Frei {euro(f.available)} · </>}
                {f.saved !== null && f.phase === 'saving' && <>Angespart {euro(f.saved)} · </>}
                {f.phase === 'finished' ? 'abbezahlt' : `ohne Zahlung ab ${monthLabel(f.end_month)}`}
              </div>
              {open === f.id && <Detail financing={f} />}
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
