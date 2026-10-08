import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'

import {
  financingApi,
  type BausparInput,
  type CreditLineInput,
  type FinancingDetail,
  type FinancingEvent,
  type FinancingInput,
  type FinancingKind,
  type LoanInput,
  type Payout,
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

/** A financing without interest, e.g. an installment purchase: amount and term or payment. */
export function ZeroFields({ initial }: { initial?: Initial }) {
  const [mode, setMode] = useState<'months' | 'payment'>(initial?.monthly_payment ? 'payment' : 'months')
  return (
    <>
      <Field label="Bezeichnung" name="name" initial={initial?.name} />
      <input type="hidden" name="purpose" value="zero_percent" />
      <input type="hidden" name="annual_rate_percent" value="0" />
      <Field label="Finanzierter Betrag in Euro" name="principal" type="decimal" initial={initial?.principal} />
      <label className="block text-sm">
        Rate festlegen über
        <select value={mode} onChange={(e) => setMode(e.target.value as 'months' | 'payment')} className={input}>
          <option value="months">Anzahl Monate</option>
          <option value="payment">Monatliche Rate in Euro</option>
        </select>
      </label>
      {mode === 'months' ? (
        <Field
          label="Laufzeit in Monaten"
          name="months"
          type="number"
          hint="Die Rate ergibt sich aus Betrag geteilt durch Monate, aufgerundet auf den Cent."
        />
      ) : (
        <Field label="Monatliche Rate in Euro" name="monthly_payment" type="decimal" initial={initial?.monthly_payment} />
      )}
      <Field label="Erste Rate im Monat" name="start" type="month" initial={initial?.start} />
    </>
  )
}

/** Payouts of the advance loan: from each month on, interest runs on the amount paid out so far. */
function PayoutRows({ initial }: { initial?: Payout[] }) {
  const [rows, setRows] = useState<{ month: string; amount: string }[]>(
    (initial ?? []).map((p) => ({ month: p.month, amount: show(p.amount) })),
  )
  const set = (i: number, patch: Partial<{ month: string; amount: string }>) =>
    setRows(rows.map((r, n) => (n === i ? { ...r, ...patch } : r)))
  return (
    <fieldset className="sm:col-span-2 lg:col-span-3">
      <legend className="text-sm">Auszahlungen des Vorausdarlehens</legend>
      <p className="mb-2 text-xs text-tinte-weich">
        Zinsen fallen ab dem Monat der Auszahlung an, nur auf den bis dahin ausgezahlten Betrag. Ohne Einträge wird die ganze Summe im ersten Monat
        ausgezahlt.
      </p>
      <ul className="space-y-2">
        {rows.map((r, i) => (
          <li key={i} className="flex flex-wrap items-end gap-3">
            <label className="block text-sm">
              Monat
              <input name="payout_month" type="month" required value={r.month} onChange={(e) => set(i, { month: e.target.value })} className={input} />
            </label>
            <label className="block text-sm">
              Betrag in Euro
              <input
                name="payout_amount"
                required
                inputMode="decimal"
                pattern="[0-9]+([.,][0-9]+)?"
                value={r.amount}
                onChange={(e) => set(i, { amount: e.target.value })}
                className={input}
              />
            </label>
            <button type="button" onClick={() => setRows(rows.filter((_, n) => n !== i))} className={secondary}>
              Entfernen
            </button>
          </li>
        ))}
      </ul>
      <button type="button" onClick={() => setRows([...rows, { month: '', amount: '' }])} className={`mt-2 ${secondary}`}>
        Auszahlung hinzufügen
      </button>
    </fieldset>
  )
}

function FeeField({ initial }: { initial?: Initial }) {
  const [unit, setUnit] = useState<'percent' | 'euro'>(initial?.fee_amount ? 'euro' : 'percent')
  return (
    <div className="block text-sm">
      <label htmlFor="fee_value">Abschlussgebühr</label>
      <div className="flex gap-2">
        <input
          id="fee_value"
          name="fee_value"
          key={unit}
          required
          inputMode="decimal"
          pattern="[0-9]+([.,][0-9]+)?"
          defaultValue={show(unit === 'euro' ? initial?.fee_amount : (initial?.fee_percent ?? '1'))}
          className={input}
        />
        <select
          name="fee_unit"
          aria-label="Einheit der Abschlussgebühr"
          value={unit}
          onChange={(e) => setUnit(e.target.value as 'percent' | 'euro')}
          className={`${input} !w-auto`}
        >
          <option value="percent">% der Summe</option>
          <option value="euro">Euro</option>
        </select>
      </div>
      <span className="mt-1 block text-xs text-tinte-weich">
        {unit === 'percent' ? 'Üblich sind 1 bis 2 Prozent, höchstens 5.' : 'Der Betrag, der im ersten Monat anfällt.'}
      </span>
    </div>
  )
}

export function BausparFields({ initial, prefinanced }: { initial?: Initial; prefinanced?: boolean }) {
  return (
    <>
      <Field label="Bezeichnung" name="name" initial={initial?.name} />
      <Field
        label={prefinanced ? 'Bausparsumme und Darlehenssumme in Euro' : 'Bausparsumme in Euro'}
        name="contract_sum"
        type="decimal"
        initial={initial?.contract_sum}
        hint={prefinanced ? 'Zinsen fallen erst ab der ersten Auszahlung an. Trage die Auszahlungen unten ein oder später als Ereignis nach.' : undefined}
      />
      {prefinanced && (
        <Field
          label="Zins des Vorausdarlehens in Prozent pro Jahr"
          name="prefinance_rate_percent"
          type="decimal"
          initial={initial?.prefinance_rate_percent}
          hint="Bis zur Zuteilung zahlst du nur diese Zinsen, keine Tilgung."
        />
      )}
      {prefinanced && <PayoutRows initial={(initial as unknown as { payouts?: Payout[] } | undefined)?.payouts ?? undefined} />}
      <Field label="Sparbeitrag pro Monat in Euro" name="monthly_saving" type="decimal" initial={initial?.monthly_saving} />
      <Field label="Vertragsbeginn" name="start" type="month" initial={initial?.start} />
      <Field label="Zuteilung im Monat" name="allocation" type="month" initial={initial?.allocation} />
      <FeeField initial={initial} />
      <Field label="Guthabenzins in Prozent pro Jahr" name="deposit_rate_percent" type="decimal" initial={initial?.deposit_rate_percent ?? '0'} />
      <Field label="Darlehenszins in Prozent pro Jahr" name="loan_rate_percent" type="decimal" initial={initial?.loan_rate_percent} />
      <Field label="Rate in der Darlehensphase in Euro" name="loan_payment" type="decimal" initial={initial?.loan_payment} />
    </>
  )
}

export function CreditLineFields({ initial }: { initial?: Initial }) {
  return (
    <>
      <Field label="Bezeichnung" name="name" initial={initial?.name} />
      <Field label="Rahmen in Euro" name="limit" type="decimal" initial={initial?.limit} hint="Der Höchstbetrag, den du entnehmen darfst." />
      <Field
        label="Aktuell genutzt in Euro"
        name="balance"
        type="decimal"
        initial={initial?.balance}
        hint="Der Betrag, den du heute schuldest."
      />
      <Field label="Sollzins in Prozent pro Jahr" name="annual_rate_percent" type="decimal" initial={initial?.annual_rate_percent} />
      <Field label="Monatliche Rate in Euro" name="monthly_payment" type="decimal" initial={initial?.monthly_payment} />
      <Field label="Erste Rate im Monat" name="start" type="month" initial={initial?.start} />
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
    if (f.get('months')) {
      const months = Number(f.get('months'))
      out.monthly_payment = (Math.ceil((Number(out.principal) / months) * 100) / 100).toFixed(2)
    }
    if (f.get('initial_repayment_percent')) out.initial_repayment_percent = d('initial_repayment_percent')
    return out
  }
  if (kind === 'credit_line') {
    const out: CreditLineInput = {
      kind: 'credit_line',
      name: s('name'),
      limit: d('limit'),
      balance: d('balance'),
      annual_rate_percent: d('annual_rate_percent'),
      monthly_payment: d('monthly_payment'),
      start: s('start'),
    }
    return out
  }
  const months = f.getAll('payout_month').map(String)
  const amounts = f.getAll('payout_amount').map((v) => decimalString(v))
  const payouts: Payout[] = months.map((month, i) => ({ month, amount: amounts[i] }))
  const out: BausparInput = {
    kind: 'building_savings',
    name: s('name'),
    contract_sum: d('contract_sum'),
    monthly_saving: d('monthly_saving'),
    start: s('start'),
    allocation: s('allocation'),
    ...(f.get('fee_unit') === 'euro' ? { fee_amount: d('fee_value') } : { fee_percent: d('fee_value') }),
    deposit_rate_percent: d('deposit_rate_percent'),
    ...(f.get('prefinance_rate_percent') ? { prefinance_rate_percent: d('prefinance_rate_percent') } : {}),
    ...(payouts.length > 0 ? { payouts } : {}),
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

/** The form tabs. A Bausparfinanzierung is a Bauspar contract that has an advance loan. */
type FormKind = FinancingKind | 'prefinanced' | 'zero'

function KindFields({ kind, initial }: { kind: FormKind; initial?: Initial }) {
  if (kind === 'loan') return <LoanFields initial={initial} />
  if (kind === 'zero') return <ZeroFields initial={initial} />
  if (kind === 'credit_line') return <CreditLineFields initial={initial} />
  return <BausparFields initial={initial} prefinanced={kind === 'prefinanced'} />
}

export function NewFinancingForm({ onDone }: { onDone: (created: FinancingDetail) => void }) {
  const { selected } = useMonth()
  const [kind, setKind] = useState<FormKind>('loan')
  const { people, me, selectedId } = usePerson()
  const [owner, setOwner] = useState<number | undefined>(selectedId ?? me?.id)
  const mutation = useFinancingMutation((v: FinancingInput) => financingApi.create(v, owner), onDone)

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    mutation.mutate(
      readInput(kind === 'prefinanced' ? 'building_savings' : kind === 'zero' ? 'loan' : kind, new FormData(e.currentTarget)),
    )
  }

  const initial = { start: selected, allocation: addMonths(selected, 120) }
  return (
    <form onSubmit={submit} className="border-t-4 border-tinte pt-5">
      <div className="mb-4 flex gap-4 text-sm font-medium">
        {(
          [
            ['loan', 'Kredit oder Immobilienfinanzierung'],
            ['zero', '0 %-Finanzierung'],
            ['credit_line', 'Rahmenkredit'],
            ['building_savings', 'Bausparvertrag'],
            ['prefinanced', 'Bausparfinanzierung'],
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
        <KindFields kind={kind} initial={initial} />
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
        für Eingabefehler. Spätere Änderungen wie Sondertilgungen, Einzahlungen oder Entnahmen trägst du als Ereignis ein.
      </p>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <KindFields kind={detail.prefinanced ? 'prefinanced' : detail.purpose === 'zero_percent' ? 'zero' : detail.kind} initial={detail.input} />
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

const EVENT_LABEL: Record<FinancingEvent['kind'], string> = {
  special_repayment: 'Sondertilgung',
  payment_change: 'Neue monatliche Rate',
  rate_change: 'Neuer Zinssatz',
  drawdown: 'Entnahme',
  payout: 'Auszahlung',
  deposit: 'Sondereinzahlung',
}

/** A credit line talks about deposits and withdrawals instead of special repayments. */
export function eventLabel(kind: FinancingEvent['kind'], financing: FinancingKind): string {
  if (financing === 'credit_line' && kind === 'special_repayment') return 'Einzahlung'
  return EVENT_LABEL[kind]
}

function eventKinds(detail: FinancingDetail): FinancingEvent['kind'][] {
  if (detail.kind === 'credit_line') return ['special_repayment', 'drawdown', 'payment_change', 'rate_change']
  const base: FinancingEvent['kind'][] = ['special_repayment', 'payment_change', 'rate_change']
  const saving: FinancingEvent['kind'][] = detail.kind === 'building_savings' ? ['deposit'] : []
  return detail.prefinanced ? ['payout', ...saving, ...base] : [...saving, ...base]
}

export function EventForm({ detail }: { detail: FinancingDetail }) {
  const { current } = useMonth()
  const [kind, setKind] = useState<FinancingEvent['kind']>('special_repayment')
  const savingPhaseEvent = kind === 'payout' || kind === 'deposit'
  const mutation = useFinancingMutation(
    (v: { month: string; kind: FinancingEvent['kind']; value: string }) => financingApi.addEvent(detail.id, v),
    () => undefined,
  )
  const firstMonth =
    kind === 'payout' || kind === 'deposit' || detail.kind !== 'building_savings' ? String(detail.input.start) : String(detail.input.allocation)
  // payouts and deposits are often only known afterwards, so past months are allowed for them
  const min = savingPhaseEvent ? firstMonth : firstMonth > current ? firstMonth : current

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
          {eventKinds(detail).map((k) => (
            <option key={k} value={k}>
              {eventLabel(k, detail.kind)}
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
