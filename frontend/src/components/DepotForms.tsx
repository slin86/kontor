import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'

import {
  depotApi,
  KIND_LABEL,
  type Assumptions,
  type InstrumentDetail,
  type InstrumentKind,
  type NewInstrument,
} from '../depotApi'
import type { CatalogEntry } from '../catalogApi'
import { useMonth } from '../month'
import { CatalogPicker } from './CatalogPicker'
import { ErrorLine } from './ErrorLine'
import { decimalString, input, primary, secondary } from './ui'

const show = (v: number | string | null | undefined) => (v === null || v === undefined ? '' : String(v).replace('.', ','))

function useDepotMutation<V>(fn: (v: V) => Promise<InstrumentDetail>, onDone?: (d: InstrumentDetail) => void) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: async (d) => {
      await qc.invalidateQueries({ queryKey: ['depot'] })
      await qc.invalidateQueries({ queryKey: ['cashflow'] })
      onDone?.(d)
    },
  })
}

function Num({
  label,
  name,
  initial,
  hint,
  required = true,
}: {
  label: string
  name: string
  initial?: number | string | null
  hint?: string
  required?: boolean
}) {
  return (
    <label className="block text-sm">
      {label}
      <input
        name={name}
        inputMode="decimal"
        pattern="-?[0-9]+([.,][0-9]+)?"
        required={required}
        defaultValue={show(initial)}
        className={input}
      />
      {hint && <span className="mt-1 block text-xs text-tinte-weich">{hint}</span>}
    </label>
  )
}

function readAssumptions(f: FormData): Assumptions {
  const isin = String(f.get('isin') ?? '').trim()
  return {
    name: String(f.get('name') ?? '').trim(),
    isin: isin || null,
    expected_return_percent: decimalString(f.get('expected_return_percent')),
    cost_percent: decimalString(f.get('cost_percent')),
    entry_fee_percent: decimalString(f.get('entry_fee_percent')),
    tax_exempt_percent: decimalString(f.get('tax_exempt_percent')),
  }
}

function AssumptionFields({ initial, kind }: { initial?: Partial<InstrumentDetail>; kind: InstrumentKind }) {
  return (
    <>
      <label className="block text-sm">
        Bezeichnung
        <input name="name" required defaultValue={initial?.name ?? ''} className={input} />
      </label>
      <label className="block text-sm">
        ISIN
        <input
          name="isin"
          defaultValue={initial?.isin ?? ''}
          pattern="[A-Za-z]{2}[A-Za-z0-9]{9}[0-9]"
          maxLength={12}
          className={input}
        />
        <span className="mt-1 block text-xs text-tinte-weich">Optional. Wird für die spätere Instrumentensuche genutzt.</span>
      </label>
      <Num
        label="Erwartete Rendite in Prozent pro Jahr"
        name="expected_return_percent"
        initial={initial?.expected_return_percent ?? (kind === 'etf' ? 6 : 9)}
        hint="Vor Kosten. Eine Annahme, keine Garantie."
      />
      <Num
        label="Laufende Kosten in Prozent pro Jahr"
        name="cost_percent"
        initial={initial?.cost_percent ?? (kind === 'etf' ? 0.2 : 2)}
        hint={kind === 'etf' ? 'Gesamtkostenquote (TER) des ETFs.' : 'Verwaltungs- und Fondskosten.'}
      />
      <Num
        label="Ausgabeaufschlag in Prozent der Einzahlung"
        name="entry_fee_percent"
        initial={initial?.entry_fee_percent ?? 0}
      />
      <Num
        label="Teilfreistellung in Prozent"
        name="tax_exempt_percent"
        initial={initial?.tax_exempt_percent ?? (kind === 'etf' ? 30 : 0)}
        hint="Steuerfreier Anteil der Erträge. Aktienfonds 30, Mischfonds 15, Anleihefonds 0. Bei Private Equity meist 0."
      />
    </>
  )
}

export interface Prefill {
  kind: InstrumentKind
  name: string
  isin: string | null
  cost_percent: number
}

export function NewInstrumentForm({ onDone, prefill }: { onDone: (d: InstrumentDetail) => void; prefill?: Prefill }) {
  const { current } = useMonth()
  const [kind, setKind] = useState<InstrumentKind>(prefill?.kind ?? 'etf')
  // the entry taken from the catalog search; its values fill the form
  const [picked, setPicked] = useState<Prefill | null>(prefill ?? null)
  const [pickCount, setPickCount] = useState(0)
  const mutation = useDepotMutation((v: NewInstrument) => depotApi.create(v), onDone)

  function pick(e: CatalogEntry) {
    setKind(e.kind)
    setPicked({ kind: e.kind, name: e.name, isin: e.isin, cost_percent: e.ter_percent })
    setPickCount((n) => n + 1)
  }

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    mutation.mutate({
      ...readAssumptions(f),
      kind,
      start: String(f.get('start')),
      start_value: decimalString(f.get('start_value')) || '0',
      monthly_rate: decimalString(f.get('monthly_rate')) || '0',
    })
  }

  return (
    <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
      <CatalogPicker onPick={pick} />
      <fieldset className="sm:col-span-2">
        <legend className="text-sm">Art der Position</legend>
        <div className="mt-1 flex gap-2">
          {(Object.keys(KIND_LABEL) as InstrumentKind[]).map((k) => (
            <button
              key={k}
              type="button"
              aria-pressed={kind === k}
              onClick={() => setKind(k)}
              className={`px-4 py-2 text-sm font-medium ${kind === k ? 'bg-tinte text-karte' : 'border border-tinte/30 hover:bg-feld/60'}`}
            >
              {KIND_LABEL[k]}
            </button>
          ))}
        </div>
      </fieldset>
      {/* remount when the kind changes so the suggested defaults follow */}
      <AssumptionFields key={`${kind}-${pickCount}`} kind={kind} initial={picked?.kind === kind ? picked : undefined} />
      <label className="block text-sm">
        Startmonat
        <input name="start" type="month" required defaultValue={current} className={input} />
      </label>
      <Num label="Wert zu Beginn in Euro" name="start_value" initial={0} hint="Bestand, den die Position im Startmonat schon hat." required={false} />
      <Num label="Sparrate pro Monat in Euro" name="monthly_rate" initial={0} required={false} />
      <div className="flex items-end">
        <button type="submit" disabled={mutation.isPending} className={primary}>
          Position speichern
        </button>
      </div>
      <div className="sm:col-span-2">
        <ErrorLine error={mutation.error} />
      </div>
    </form>
  )
}

export function AssumptionsForm({ detail, onDone }: { detail: InstrumentDetail; onDone: () => void }) {
  const mutation = useDepotMutation((v: Assumptions) => depotApi.update(detail.id, v), onDone)
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    mutation.mutate(readAssumptions(new FormData(e.currentTarget)))
  }
  return (
    <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
      <AssumptionFields initial={detail} kind={detail.kind} />
      <div className="flex items-end gap-2">
        <button type="submit" disabled={mutation.isPending} className={primary}>
          Annahmen speichern
        </button>
        <button type="button" onClick={onDone} className={secondary}>
          Abbrechen
        </button>
      </div>
      <div className="sm:col-span-2">
        <ErrorLine error={mutation.error} />
      </div>
    </form>
  )
}

export function RateForm({ detail }: { detail: InstrumentDetail }) {
  const { current } = useMonth()
  const min = detail.start > current ? detail.start : current
  const mutation = useDepotMutation((v: { effective_from: string; amount: string }) => depotApi.changeRate(detail.id, v))
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    mutation.mutate({ effective_from: String(f.get('effective_from')), amount: decimalString(f.get('amount')) })
  }
  return (
    <form onSubmit={submit} className="grid items-end gap-4 sm:grid-cols-3">
      <label className="block text-sm">
        Ab Monat
        <input name="effective_from" type="month" required min={min} defaultValue={min} className={input} />
      </label>
      <Num label="Neue Sparrate pro Monat in Euro" name="amount" hint="0 pausiert das Sparen." />
      <button type="submit" disabled={mutation.isPending} className={primary}>
        Sparrate ändern
      </button>
      <div className="sm:col-span-3">
        <ErrorLine error={mutation.error} />
      </div>
    </form>
  )
}

export function OneOffForm({ detail }: { detail: InstrumentDetail }) {
  const { current } = useMonth()
  const min = detail.start > current ? detail.start : current
  const [direction, setDirection] = useState<'in' | 'out'>('in')
  const mutation = useDepotMutation((v: { month: string; amount: string; note: string | null }) =>
    depotApi.addOneOff(detail.id, v),
  )
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    const amount = decimalString(f.get('amount'))
    const note = String(f.get('note') ?? '').trim()
    mutation.mutate({ month: String(f.get('month')), amount: direction === 'out' ? `-${amount}` : amount, note: note || null })
  }
  return (
    <form onSubmit={submit} className="grid items-end gap-4 sm:grid-cols-5">
      <label className="block text-sm">
        Art
        <select value={direction} onChange={(e) => setDirection(e.target.value as 'in' | 'out')} className={input}>
          <option value="in">Einzahlung</option>
          <option value="out">Entnahme</option>
        </select>
      </label>
      <label className="block text-sm">
        Im Monat
        <input name="month" type="month" required min={min} defaultValue={min} className={input} />
      </label>
      <label className="block text-sm">
        Betrag in Euro
        <input name="amount" required inputMode="decimal" pattern="[0-9]+([.,][0-9]+)?" className={input} />
      </label>
      <label className="block text-sm">
        Notiz
        <input name="note" maxLength={200} className={input} />
      </label>
      <button type="submit" disabled={mutation.isPending} className={primary}>
        Hinzufügen
      </button>
      <div className="sm:col-span-5">
        <ErrorLine error={mutation.error} />
      </div>
    </form>
  )
}

export function CorrectionForm({ detail, onDone }: { detail: InstrumentDetail; onDone: () => void }) {
  const mutation = useDepotMutation(
    (v: { start: string; start_value: string; reason: string }) => depotApi.correct(detail.id, v),
    onDone,
  )
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    mutation.mutate({
      start: String(f.get('start')),
      start_value: decimalString(f.get('start_value')) || '0',
      reason: String(f.get('reason') ?? '').trim(),
    })
  }
  return (
    <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
      <label className="block text-sm">
        Startmonat
        <input name="start" type="month" required defaultValue={detail.start} className={input} />
      </label>
      <Num label="Wert zu Beginn in Euro" name="start_value" initial={detail.start_value} required={false} />
      <label className="block text-sm sm:col-span-2">
        Begründung
        <input name="reason" required minLength={3} maxLength={500} className={input} placeholder="z. B. Abgleich mit Depotauszug" />
        <span className="mt-1 block text-xs text-tinte-weich">
          Start und Startwert bilden die Basis des gesamten Plans. Die Korrektur wird im Änderungsprotokoll festgehalten.
        </span>
      </label>
      <div className="flex gap-2 sm:col-span-2">
        <button type="submit" disabled={mutation.isPending} className={primary}>
          Korrektur speichern
        </button>
        <button type="button" onClick={onDone} className={secondary}>
          Abbrechen
        </button>
      </div>
      <div className="sm:col-span-2">
        <ErrorLine error={mutation.error} />
      </div>
    </form>
  )
}
