import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'

import { ConfirmDelete } from '../components/ConfirmDelete'
import { DepotChart } from '../components/DepotChart'
import {
  AssumptionsForm,
  CorrectionForm,
  NewInstrumentForm,
  OneOffForm,
  OwnerForm,
  RateForm,
  type Prefill,
} from '../components/DepotForms'
import { input, primary } from '../components/ui'
import { catalogApi } from '../catalogApi'
import { depotApi, KIND_LABEL, type Instrument, type InstrumentDetail, type Rate } from '../depotApi'
import { TaxSettingsForm } from '../components/TaxSettingsForm'
import { euro } from '../format'
import { useMonth } from '../month'
import { PersonSwitcher } from '../components/PersonSwitcher'
import { usePerson } from '../person'
import { monthLabel } from '../monthUtils'

function Figure({ label, value, tone }: { label: string; value: string; tone?: 'plus' | 'minus' }) {
  const color = tone === 'minus' ? 'text-bake' : tone === 'plus' ? 'text-elbe-dunkel' : ''
  return (
    <div>
      <div className={`zahl text-2xl font-semibold ${color}`}>{value}</div>
      <div className="text-sm text-tinte-weich">{label}</div>
    </div>
  )
}

function rateRange(r: Rate): string {
  return r.valid_to ? `${monthLabel(r.valid_from)} bis ${monthLabel(addOne(r.valid_to, -1))}` : `Ab ${monthLabel(r.valid_from)}`
}

// valid_to is exclusive, so the last month with this rate is the one before it
function addOne(key: string, delta: number): string {
  const [y, m] = key.split('-').map(Number)
  const i = y * 12 + (m - 1) + delta
  return `${Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, '0')}`
}

function Projection() {
  const { current } = useMonth()
  const { selectedId, selected } = usePerson()
  const [years, setYears] = useState(30)
  const [spread, setSpread] = useState(2)
  const [inflation, setInflation] = useState(0)

  const base = useQuery({
    queryKey: ['depot', 'projection', selectedId, years, 0, inflation],
    queryFn: () => depotApi.projection(years, 0, inflation, selectedId),
  })
  const low = useQuery({
    queryKey: ['depot', 'projection', selectedId, years, -spread, inflation],
    queryFn: () => depotApi.projection(years, -spread, inflation, selectedId),
    enabled: spread > 0,
  })
  const high = useQuery({
    queryKey: ['depot', 'projection', selectedId, years, spread, inflation],
    queryFn: () => depotApi.projection(years, spread, inflation, selectedId),
    enabled: spread > 0,
  })

  const commit = (set: (n: number) => void, max: number) => (e: { currentTarget: HTMLInputElement }) => {
    const n = Number(e.currentTarget.value.replace(',', '.'))
    if (Number.isFinite(n) && n >= 0 && n <= max) set(n)
  }

  const data = base.data
  const hasPositions = (data?.instruments.length ?? 0) > 0
  const end = data?.points.at(-1)
  const lowEnd = spread > 0 ? low.data?.points.at(-1) : undefined
  const highEnd = spread > 0 ? high.data?.points.at(-1) : undefined

  return (
    <section aria-labelledby="prognose">
      <h2 id="prognose" className="text-xl">
        {selected && selectedId !== null ? `Wie sich das Depot von ${selected.name} entwickelt` : 'Wie sich dein Depot entwickelt'}
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
        <label>
          Szenario-Abstand (Prozentpunkte Rendite)
          <input
            defaultValue={String(spread).replace('.', ',')}
            onBlur={commit(setSpread, 10)}
            onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
            inputMode="decimal"
            className={`${input} !mt-1 !w-24`}
          />
        </label>
        <label>
          Inflation pro Jahr (%)
          <input
            defaultValue={String(inflation).replace('.', ',')}
            onBlur={commit(setInflation, 20)}
            onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
            inputMode="decimal"
            className={`${input} !mt-1 !w-24`}
          />
        </label>
      </div>

      {data && hasPositions && (
        <>
          <div className="mt-6">
            <DepotChart base={data} low={spread > 0 ? low.data : undefined} high={spread > 0 ? high.data : undefined} today={current} />
          </div>
          {end && (
            <div className="mt-4 flex flex-wrap gap-x-10 gap-y-4">
              <Figure label={`Wert ${monthLabel(end.month)}${inflation > 0 ? ' (heutige Kaufkraft)' : ''}`} value={euro(end.value)} />
              {lowEnd && highEnd && (
                <Figure label="Spanne der Szenarien" value={`${euro(lowEnd.value)} bis ${euro(highEnd.value)}`} />
              )}
              <Figure label="Davon eingezahlt" value={euro(end.paid_in)} />
              <Figure label="Rechnerischer Ertrag" value={euro(end.value - end.paid_in)} tone={end.value >= end.paid_in ? 'plus' : 'minus'} />
              <Figure label={`Nach Steuern bei Verkauf ${monthLabel(end.month)}`} value={euro(end.net_value)} />
              <Figure label="Steuern insgesamt" value={euro(end.tax_paid + end.tax_on_sale)} tone="minus" />
            </div>
          )}
          <p className="mt-4 max-w-2xl text-sm text-tinte-weich">
            Grundlage sind die erwarteten Renditen und Kosten deiner Positionen. Das sind Annahmen, keine Zusagen. Die Linien
            für pessimistisch und optimistisch verschieben die Rendite jeder Position um den gewählten Abstand. Die Linie „Nach
            Steuern“ zeigt, was nach Abgeltungsteuer ({String(data.tax_rate_percent).replace('.', ',')} % auf steuerpflichtige
            Erträge) übrig bliebe, wenn du in dem jeweiligen Monat alles verkaufst. Das ist eine Schätzung, keine Steuerberatung.
          </p>
          <TaxSettingsForm person={selected} />
        </>
      )}
      {data && !hasPositions && (
        <p className="mt-4 max-w-xl text-tinte-weich">
          Noch keine Position im Plan. Lege einen ETF oder eine Private-Equity-Beteiligung an, dann siehst du hier, was aus deinen
          Sparraten wird.
        </p>
      )}
    </section>
  )
}

function Detail({ instrument }: { instrument: Instrument }) {
  const qc = useQueryClient()
  const [mode, setMode] = useState<'view' | 'assumptions' | 'correct'>('view')
  const query = useQuery({ queryKey: ['depot', 'detail', instrument.id], queryFn: () => depotApi.get(instrument.id) })
  const remove = useMutation({
    mutationFn: (id: number) => depotApi.removeOneOff(instrument.id, id),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['depot'] })
      await qc.invalidateQueries({ queryKey: ['cashflow'] })
    },
  })
  const d: InstrumentDetail | undefined = query.data
  // a catalog entry with the same ISIN offers its TER and a way to compare with similar funds
  const known = useQuery({
    queryKey: ['catalog', 'by-isin', d?.isin],
    queryFn: () => catalogApi.search({ q: d?.isin ?? '', index: '', distribution: '', replication: '', maxTer: '', sort: 'size', kind: '' }),
    enabled: Boolean(d?.isin),
    select: (r) => r.items.find((e) => e.isin === d?.isin),
  })
  const adoptCosts = useMutation({
    mutationFn: (ter: number) =>
      depotApi.update(instrument.id, {
        name: d!.name,
        isin: d!.isin,
        expected_return_percent: String(d!.expected_return_percent),
        cost_percent: String(ter),
        entry_fee_percent: String(d!.entry_fee_percent),
      }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['depot'] })
      await qc.invalidateQueries({ queryKey: ['cashflow'] })
    },
  })
  const drop = useMutation({
    mutationFn: () => depotApi.remove(instrument.id),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['depot'] })
      await qc.invalidateQueries({ queryKey: ['actuals'] })
      await qc.invalidateQueries({ queryKey: ['cashflow'] })
    },
  })
  if (!d) return null
  const entry = known.data

  return (
    <div className="mt-4 space-y-8 border-l-4 border-tinte/20 pl-4 sm:pl-6">
      <div className="flex flex-wrap gap-x-10 gap-y-4">
        <Figure label="Geplanter Wert heute" value={euro(d.planned_value)} />
        <Figure label="Bisher eingezahlt" value={euro(d.paid_in)} />
        <Figure label="Teilfreistellung" value={`${String(d.tax_exempt_percent).replace('.', ',')} %`} />
        <Figure label="Erwartete Rendite" value={`${String(d.expected_return_percent).replace('.', ',')} % pro Jahr`} />
        <Figure
          label="Kosten"
          value={`${String(d.cost_percent).replace('.', ',')} % pro Jahr${d.entry_fee_percent > 0 ? ` + ${String(d.entry_fee_percent).replace('.', ',')} % Aufschlag` : ''}`}
        />
      </div>

      {entry && (
        <p className="text-sm">
          Im Katalog: {entry.name} mit {String(entry.ter_percent).replace('.', ',')} % TER.{' '}
          {Math.abs(entry.ter_percent - d.cost_percent) > 0.0005 && (
            <button
              type="button"
              disabled={adoptCosts.isPending}
              onClick={() => adoptCosts.mutate(entry.ter_percent)}
              className="font-medium text-elbe-dunkel hover:underline"
            >
              Kosten übernehmen
            </button>
          )}{' '}
          <Link to={`/instrumente?compare=${entry.isin}&index=${encodeURIComponent(entry.index_name ?? '')}`} className="font-medium text-elbe-dunkel hover:underline">
            Mit ähnlichen Fonds vergleichen
          </Link>
        </p>
      )}

      <div>
        <h3 className="mb-2 text-lg">Sparrate</h3>
        <ul className="divide-y divide-tinte/15 text-sm">
          {d.rates.map((r) => (
            <li key={r.id} className="flex flex-wrap items-baseline gap-x-4 py-2">
              <span className="text-tinte-weich">{rateRange(r)}</span>
              <span className="zahl ml-auto font-medium">{euro(r.amount, true)} pro Monat</span>
            </li>
          ))}
        </ul>
        <div className="mt-4">
          <RateForm detail={d} />
        </div>
      </div>

      <div>
        <h3 className="mb-2 text-lg">Einmalzahlungen</h3>
        {d.one_offs.length === 0 && <p className="text-sm text-tinte-weich">Keine geplant.</p>}
        <ul className="divide-y divide-tinte/15 text-sm">
          {d.one_offs.map((o) => (
            <li key={o.id} className="flex flex-wrap items-baseline gap-x-4 py-2">
              <span className="w-24 text-tinte-weich">{monthLabel(o.month)}</span>
              <span>{o.amount < 0 ? 'Entnahme' : 'Einzahlung'}</span>
              {o.note && <span className="text-tinte-weich">{o.note}</span>}
              <span className={`zahl ml-auto font-medium ${o.amount < 0 ? 'text-bake' : ''}`}>{euro(o.amount, true)}</span>
              {o.locked ? (
                <span className="text-xs text-tinte-weich">abgeschlossen</span>
              ) : (
                <button
                  type="button"
                  onClick={() => remove.mutate(o.id)}
                  className="font-medium text-elbe-dunkel hover:underline"
                >
                  Entfernen
                </button>
              )}
            </li>
          ))}
        </ul>
        <div className="mt-4">
          <OneOffForm detail={d} />
        </div>
      </div>

      <div className="space-y-4 pb-2">
        {mode === 'view' && (
          <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm font-medium">
            <button type="button" onClick={() => setMode('assumptions')} className="text-elbe-dunkel hover:underline">
              Annahmen ändern
            </button>
            <button type="button" onClick={() => setMode('correct')} className="text-elbe-dunkel hover:underline">
              Start und Startwert korrigieren
            </button>
          </div>
        )}
        {mode === 'view' && (
          <ConfirmDelete
            label="Position löschen"
            question={`„${d.name}“ mit Plan und Ist-Werten löschen? Importierte Transaktionen bleiben erhalten.`}
            pending={drop.isPending}
            error={drop.error}
            onConfirm={() => drop.mutate()}
          />
        )}
        {mode === 'view' && <OwnerForm detail={d} />}
        {mode === 'assumptions' && <AssumptionsForm detail={d} onDone={() => setMode('view')} />}
        {mode === 'correct' && <CorrectionForm detail={d} onDone={() => setMode('view')} />}
      </div>
    </div>
  )
}

export function DepotPage() {
  const { selectedId, people } = usePerson()
  const overview = useQuery({ queryKey: ['depot', 'overview', selectedId], queryFn: () => depotApi.overview(selectedId) })
  const ownerName = (id: number) => people.find((p) => p.id === id)?.name
  const prefill = (useLocation().state as { prefill?: Prefill } | null)?.prefill
  const [adding, setAdding] = useState(Boolean(prefill))
  const [open, setOpen] = useState<number | null>(null)
  const d = overview.data
  const gain = d ? d.planned_value - d.paid_in : 0

  return (
    <div className="space-y-12">
      <h1 className="sr-only">Depot</h1>
      <PersonSwitcher />

      {d && d.instruments.length > 0 && (
        <div className="flex flex-wrap gap-x-10 gap-y-4">
          <Figure label="Sparrate pro Monat (Summe aller Positionen)" value={euro(d.base_rate, true)} />
          <Figure label="Geplanter Wert heute" value={euro(d.planned_value)} />
          <Figure label="Bisher eingezahlt" value={euro(d.paid_in)} />
          <Figure label="Rechnerischer Ertrag" value={euro(gain)} tone={gain >= 0 ? 'plus' : 'minus'} />
        </div>
      )}

      <Projection />

      <section aria-labelledby="positionen">
        <div className="mb-2 flex items-baseline gap-4">
          <h2 id="positionen" className="text-xl">
            Positionen
          </h2>
          {!adding && (
            <button type="button" onClick={() => setAdding(true)} className={`ml-auto text-sm ${primary}`}>
              Position hinzufügen
            </button>
          )}
        </div>

        {adding && (
          <div className="mb-8">
            {prefill && (
              <Link to="/instrumente" className="mb-3 inline-block text-sm font-medium text-elbe-dunkel hover:underline">
                ← Zurück zu den Instrumenten
              </Link>
            )}
            <NewInstrumentForm
              prefill={prefill}
              onDone={(created) => {
                setAdding(false)
                setOpen(created.id)
              }}
            />
            <button type="button" onClick={() => setAdding(false)} className="mt-2 text-sm font-medium text-elbe-dunkel hover:underline">
              Abbrechen
            </button>
          </div>
        )}

        <ul className="divide-y divide-tinte/15">
          {d?.instruments.map((i) => (
            <li key={i.id} className="py-4">
              <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
                <span className="font-medium">{i.name}</span>
                <span className="text-sm text-tinte-weich">
                  {KIND_LABEL[i.kind]}
                  {i.isin ? ` · ${i.isin}` : ''}
                  {selectedId === null && people.length > 1 && ownerName(i.person_id) ? ` · ${ownerName(i.person_id)}` : ''}
                </span>
                <span className="zahl ml-auto">
                  {euro(i.current_rate, true)}
                  <span className="text-sm text-tinte-weich"> pro Monat</span>
                </span>
                <button
                  type="button"
                  className="text-sm font-medium text-elbe-dunkel hover:underline"
                  onClick={() => setOpen(open === i.id ? null : i.id)}
                >
                  {open === i.id ? 'Schließen' : 'Details'}
                </button>
              </div>
              <div className="text-sm text-tinte-weich">
                Geplanter Wert {euro(i.planned_value)} · eingezahlt {euro(i.paid_in)} · Start {monthLabel(i.start)}
              </div>
              {open === i.id && <Detail instrument={i} />}
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
