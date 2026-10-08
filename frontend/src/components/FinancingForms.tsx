import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'

import {
  financingApi,
  type BausparInput,
  type FinancingDetail,
  type FinancingEvent,
  type FinancingInput,
  type FinancingKind,
  type LoanInput,
} from '../financingApi'
import { useMonth } from '../month'
import { addMonths } from '../monthUtils'
import { usePerson } from '../person'
import { decimalString, input, primary, secondary } from './ui'

function ErrorLine({ error }: { error: unknown }) {
  if (!error) return null
  return (
    <p role="alert" className="text-sm font-medium text-bake">
      {error instanceof Error ? error.message : 'Das hat nicht geklappt.'}
    </p>
  )
}

/** "3.6" -> "3,6" for display in German-style inputs. */
const show = (v: string | null | undefined) => (v ?? '').replace('.', ',')

type Initial = Record<string, string | null> | undefined

function Field({
  label,
  name,
  initial,
  type = 'text',
  hint,
  required = true,
  wide,
}: {
  label: string
  name: string
  initial?: string | null
  type?: string
  hint?: string
  required?: boolean
  wide?: boolean
}) {
  const decimal = type === 'decimal'
  return (
    <label className={`block text-sm ${wide ? 'sm:col-span-2' : ''}`}>
      {label}
      <input
        name={name}
        type={decimal ? 'text' : type}
        inputMode={decimal ? 'decimal' : undefined}
        pattern={decimal ? '[0-9]+([.,][0-9]+)?' : undefined}
        required={required}
        defaultValue={decimal ? show(initial) : (initial ?? '')}
        className={input}
      />
      {hint && <span className="mt-1 block text-xs text-tinte-weich">{hint}</span>}
    </label>
  )
}

export function LoanFields({ initial }: { initial?: Initial }) {
  const [mode, setMode] = useState<'payment' | 'repayment'>(
    initial?.initial_repayment_percent ? 'repayment' : 'payment',
  )
  return (
    <>
      <Field label="Bezeichnung" name="name" initial={initial?.name} />
      <label className="block text-sm">
        Art
        <select name="purpose" defaultValue={initial?.purpose ?? 'real_estate'} className={input}>
          <option value="real_estate">Immobilienfinanzierung</option>
          <option value="consumer">Kredit</option>
          <option value="other">Sonstiges</option>
        </select>
      </label>
      <Field label="Darlehensbetrag in Euro" name="principal" type="decimal" initial={initial?.principal} />
      <Field label="Sollzins in Prozent pro Jahr" name="annual_rate_percent" type="decimal" initial={initial?.annual_rate_percent} />
      <label className="block text-sm">
        Rate festlegen über
        <select value={mode} onChange={(e) => setMode(e.target.value as 'payment' | 'repayment')} className={input}>
          <option value="payment">Monatliche Rate in Euro</option>
          <option value="repayment">Anfangstilgung in Prozent</option>
        </select>
      </label>
      {mode === 'payment' ? (
        <Field label="Monatliche Rate in Euro" name="monthly_payment" type="decimal" initial={initial?.monthly_payment} />
      ) : (
        <Field
          label="Anfangstilgung in Prozent"
          name="initial_repayment_percent"
          type="decimal"
          initial={initial?.initial_repayment_percent}
          hint="Die Rate ergibt sich aus Darlehensbetrag × (Sollzins + Tilgung) / 12."
        />
      )}
      <Field label="Erste Rate im Monat" name="start" type="month" initial={initial?.start} />
    </>
  )
}

export function BausparFields({ initial }: { initial?: Initial }) {
  return (
    <>
      <Field label="Bezeichnung" name="name" initial={initial?.name} />
      <Field label="Bausparsumme in Euro" name="contract_sum" type="decimal" initial={initial?.contract_sum} />
      <Field label="Sparbeitrag pro Monat in Euro" name="monthly_saving" type="decimal" initial={initial?.monthly_saving} />
      <Field label="Vertragsbeginn" name="start" type="month" initial={initial?.start} />
      <Field label="Zuteilung im Monat" name="allocation" type="month" initial={initial?.allocation} />
      <Field label="Abschlussgebühr in Prozent der Summe" name="fee_percent" type="decimal" initial={initial?.fee_percent ?? '1'} />
      <Field label="Guthabenzins in Prozent pro Jahr" name="deposit_rate_percent" type="decimal" initial={initial?.deposit_rate_percent ?? '0'} />
      <Field label="Darlehenszins in Prozent pro Jahr" name="loan_rate_percent" type="decimal" initial={initial?.loan_rate_percent} />
      <Field label="Rate in der Darlehensphase in Euro" name="loan_payment" type="decimal" initial={initial?.loan_payment} />
    </>
  )
}

function readInput(kind: FinancingKind, f: FormData): FinancingInput {
  const s = (k: string) => String(f.get(k) ?? '').trim()
  const d = (k: string) => decimalString(f.get(k))
  if (kind === 'loan') {
    const out: LoanInput = {
      kind: 'loan',
      name: s('name'),
      purpose: s('purpose') as LoanInput['purpose'],
      principal: d('principal'),
      annual_rate_percent: d('annual_rate_percent'),
      start: s('start'),
    }
    if (f.get('monthly_payment')) out.monthly_payment = d('monthly_payment')
    if (f.get('initial_repayment_percent')) out.initial_repayment_percent = d('initial_repayment_percent')
    return out
  }
  const out: BausparInput = {
    kind: 'building_savings',
    name: s('name'),
    contract_sum: d('contract_sum'),
    monthly_saving: d('monthly_saving'),
    start: s('start'),
    allocation: s('allocation'),
    fee_percent: d('fee_percent'),
    deposit_rate_percent: d('deposit_rate_percent'),
    loan_rate_percent: d('loan_rate_percent'),
    loan_payment: d('loan_payment'),
  }
  return out
}

function useFinancingMutation<V>(fn: (v: V) => Promise<FinancingDetail>, onDone: (d: FinancingDetail) => void) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: async (detail) => {
      await qc.invalidateQueries({ queryKey: ['financings'] })
      await qc.invalidateQueries({ queryKey: ['cashflow'] })
      onDone(detail)
    },
  })
}

export function NewFinancingForm({ onDone }: { onDone: (created: FinancingDetail) => void }) {
  const { selected } = useMonth()
  const [kind, setKind] = useState<FinancingKind>('loan')
  const { people, me, selectedId } = usePerson()
  const [owner, setOwner] = useState<number | undefined>(selectedId ?? me?.id)
  const mutation = useFinancingMutation((v: FinancingInput) => financingApi.create(v, owner), onDone)

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    mutation.mutate(readInput(kind, new FormData(e.currentTarget)))
  }

  const initial = { start: selected, allocation: addMonths(selected, 120) }
  return (
    <form onSubmit={submit} className="border-t-4 border-tinte pt-5">
      <div className="mb-4 flex gap-4 text-sm font-medium">
        {(
          [
            ['loan', 'Kredit oder Immobilienfinanzierung'],
            ['building_savings', 'Bausparvertrag'],
          ] as const
        ).map(([k, label]) => (
          <button
            key={k}
            type="button"
            onClick={() => setKind(k)}
            className={`border-b-2 pb-0.5 ${kind === k ? 'border-elbe' : 'border-transparent text-tinte-weich'}`}
          >
            {label}
          </button>
        ))}
      </div>
      {people.length > 1 && (
        <label className="mb-4 block max-w-xs text-sm">
          Gehört zu
          <select value={owner ?? ''} onChange={(e) => setOwner(Number(e.target.value))} className={input}>
            {people.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
      )}
      <div key={kind} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {kind === 'loan' ? <LoanFields initial={initial} /> : <BausparFields initial={initial} />}
      </div>
      <div className="mt-5 flex items-center gap-2">
        <button type="submit" disabled={mutation.isPending} className={primary}>
          Finanzierung speichern
        </button>
        <ErrorLine error={mutation.error} />
      </div>
    </form>
  )
}

export function CorrectionForm({ detail, onDone }: { detail: FinancingDetail; onDone: () => void }) {
  const mutation = useFinancingMutation(
    (v: { reason: string; data: FinancingInput }) => financingApi.correct(detail.id, v),
    onDone,
  )
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    mutation.mutate({ reason: String(f.get('reason')).trim(), data: readInput(detail.kind, f) })
  }
  return (
    <form onSubmit={submit} className="border-l-4 border-elbe bg-karte-tief px-4 py-4">
      <p className="mb-4 max-w-xl text-sm text-tinte-weich">
        Eine Korrektur ersetzt die Vertragsdaten und verändert den gesamten Tilgungsplan, auch die Vergangenheit. Nutze sie
        für Eingabefehler. Spätere Änderungen wie Sondertilgungen trägst du als Ereignis ein.
      </p>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {detail.kind === 'loan' ? <LoanFields initial={detail.input} /> : <BausparFields initial={detail.input} />}
        <Field label="Begründung (wird im Protokoll gespeichert)" name="reason" initial="" wide />
      </div>
      <div className="mt-4 flex items-center gap-2">
        <button type="submit" disabled={mutation.isPending} className={primary}>
          Korrektur speichern
        </button>
        <button type="button" onClick={onDone} className={secondary}>
          Abbrechen
        </button>
        <ErrorLine error={mutation.error} />
      </div>
    </form>
  )
}

export const EVENT_LABEL: Record<FinancingEvent['kind'], string> = {
  special_repayment: 'Sondertilgung',
  payment_change: 'Neue monatliche Rate',
  rate_change: 'Neuer Zinssatz',
}

export function EventForm({ detail }: { detail: FinancingDetail }) {
  const { current } = useMonth()
  const [kind, setKind] = useState<FinancingEvent['kind']>('special_repayment')
  const mutation = useFinancingMutation(
    (v: { month: string; kind: FinancingEvent['kind']; value: string }) => financingApi.addEvent(detail.id, v),
    () => undefined,
  )
  const firstMonth = detail.kind === 'loan' ? String(detail.input.start) : String(detail.input.allocation)
  const min = firstMonth > current ? firstMonth : current

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    mutation.mutate({ month: String(f.get('month')), kind, value: decimalString(f.get('value')) })
  }

  return (
    <form onSubmit={submit} className="grid items-end gap-4 sm:grid-cols-4">
      <label className="block text-sm">
        Ereignis
        <select value={kind} onChange={(e) => setKind(e.target.value as FinancingEvent['kind'])} className={input}>
          {Object.entries(EVENT_LABEL).map(([k, label]) => (
            <option key={k} value={k}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label className="block text-sm">
        Im Monat
        <input name="month" type="month" required min={min} defaultValue={min} className={input} />
      </label>
      <label className="block text-sm">
        {kind === 'rate_change' ? 'Zins in Prozent pro Jahr' : 'Betrag in Euro'}
        <input name="value" required inputMode="decimal" pattern="[0-9]+([.,][0-9]+)?" className={input} />
      </label>
      <button type="submit" disabled={mutation.isPending} className={primary}>
        Hinzufügen
      </button>
      <div className="sm:col-span-4">
        <ErrorLine error={mutation.error} />
      </div>
    </form>
  )
}
