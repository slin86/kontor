import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent, type ReactNode } from 'react'

import { cashflowApi, type Category, type Frequency, type Item } from '../cashflowApi'
import { FREQUENCY_LABEL } from '../format'
import { useMonth } from '../month'
import { addMonths } from '../monthUtils'
import { usePerson } from '../person'
import { ConfirmDelete } from './ConfirmDelete'
import { input, primary, secondary } from './ui'


function useCashflowMutation<V>(fn: (v: V) => Promise<unknown>, onDone: () => void) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['cashflow'] })
      onDone()
    },
  })
}

function ErrorLine({ error }: { error: unknown }) {
  if (!error) return null
  return (
    <p role="alert" className="text-sm font-medium text-bake">
      {error instanceof Error ? error.message : 'Das hat nicht geklappt.'}
    </p>
  )
}

function FrequencySelect({ defaultValue, onChange }: { defaultValue?: Frequency; onChange?: (f: Frequency) => void }) {
  return (
    <select
      name="frequency"
      defaultValue={defaultValue ?? 'monthly'}
      onChange={onChange && ((e) => onChange(e.target.value as Frequency))}
      className={input}
    >
      {Object.entries(FREQUENCY_LABEL).map(([v, label]) => (
        <option key={v} value={v}>
          {label}
        </option>
      ))}
    </select>
  )
}

function SpreadCheckbox({ checked, onChange, start }: { checked: boolean; onChange: (v: boolean) => void; start?: boolean }) {
  return (
    <label className="flex items-start gap-2 text-sm sm:col-span-2">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="mt-1" />
      <span>
        Auf monatliche Kosten aufteilen
        <span className="block text-xs text-tinte-weich">
          {checked
            ? 'Jeder Monat trägt einen gleichen Anteil.'
            : `Der volle Betrag zählt nur in dem Monat, in dem er fällig ist${start ? ' (ab der ersten Zahlung im Rhythmus)' : ''}.`}
        </span>
      </span>
    </label>
  )
}

function parseAmount(raw: FormDataEntryValue | null): string {
  return String(raw ?? '').replace(',', '.').trim()
}

export function NewItemForm({ categories, onDone }: { categories: Category[]; onDone: () => void }) {
  const { selected } = useMonth()
  const { people, me, selectedId } = usePerson()
  const [owner, setOwner] = useState<number | undefined>(selectedId ?? me?.id)
  const [transfer, setTransfer] = useState(false)
  const [frequency, setFrequency] = useState<Frequency>('monthly')
  const [spread, setSpread] = useState(true)
  const mutation = useCashflowMutation(cashflowApi.createItem, onDone)
  const others = people.filter((p) => p.id !== owner)
  const byId = new Map(categories.map((c) => [c.id, c]))
  const label = (c: Category) => (c.parent_id ? `${byId.get(c.parent_id)?.name} › ${c.name}` : c.name)

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    mutation.mutate({
      name: String(f.get('name')).trim(),
      person_id: owner,
      ...(transfer
        ? { transfer_to_id: Number(f.get('transfer_to_id')) }
        : { category_id: Number(f.get('category_id')) }),
      amount: parseAmount(f.get('amount')),
      frequency,
      spread,
      valid_from: String(f.get('valid_from')),
    })
  }

  return (
    <form onSubmit={submit} className="grid gap-4 border-t-4 border-tinte pt-5 sm:grid-cols-2 lg:grid-cols-3">
      <label className="block text-sm">
        Bezeichnung
        <input name="name" required maxLength={120} className={input} />
      </label>
      {people.length > 1 && (
        <label className="block text-sm">
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
      {people.length > 1 && (
        <label className="flex items-center gap-2 self-end pb-2 text-sm">
          <input type="checkbox" checked={transfer} onChange={(e) => setTransfer(e.target.checked)} />
          Übertrag an eine andere Person
        </label>
      )}
      {transfer ? (
        <label className="block text-sm">
          Empfänger
          <select name="transfer_to_id" required className={input} defaultValue={others[0]?.id}>
            {others.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
      ) : (
      <label className="block text-sm">
        Kategorie
        <select name="category_id" required className={input} defaultValue="">
          <option value="" disabled>
            Bitte wählen
          </option>
          {(['income', 'expense'] as const).map((kind) => (
            <optgroup key={kind} label={kind === 'income' ? 'Einnahmen' : 'Ausgaben'}>
              {categories
                .filter((c) => c.kind === kind)
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {label(c)}
                  </option>
                ))}
            </optgroup>
          ))}
        </select>
      </label>
      )}
      <label className="block text-sm">
        Betrag in Euro
        <input name="amount" required inputMode="decimal" pattern="[0-9]+([.,][0-9]{1,2})?" className={input} />
      </label>
      <label className="block text-sm">
        Zahlweise
        <FrequencySelect onChange={setFrequency} />
      </label>
      <label className="block text-sm">
        {frequency === 'monthly' ? 'Gilt ab' : 'Erste Zahlung im'}
        <input name="valid_from" type="month" required defaultValue={selected} className={input} />
      </label>
      {frequency !== 'monthly' && <SpreadCheckbox checked={spread} onChange={setSpread} start />}
      <div className="flex items-end gap-2">
        <button type="submit" disabled={mutation.isPending} className={primary}>
          Posten speichern
        </button>
        <button type="button" onClick={onDone} className={secondary}>
          Abbrechen
        </button>
      </div>
      <div className="sm:col-span-2 lg:col-span-3">
        <ErrorLine error={mutation.error} />
      </div>
    </form>
  )
}

type Mode = 'change' | 'spread' | 'start' | 'end' | 'correct'

export function ItemEditor({ item, onDone }: { item: Item; onDone: () => void }) {
  const { selected, current, isLocked } = useMonth()
  const locked = isLocked(selected)
  const [mode, setMode] = useState<Mode>(locked ? 'correct' : 'change')
  const active = item.active

  const change = useCashflowMutation(
    (v: { effective_from: string; amount: string; frequency: Frequency }) => cashflowApi.changeItem(item.id, v),
    onDone,
  )
  const [spread, setSpread] = useState(item.spread)
  const remove = useCashflowMutation(() => cashflowApi.deleteItem(item.id), onDone)
  const setSpreadMutation = useCashflowMutation((v: boolean) => cashflowApi.setSpread(item.id, v), onDone)
  const start = useCashflowMutation((v: { start_from: string; reason?: string }) => cashflowApi.startEarlier(item.id, v), onDone)
  const end = useCashflowMutation((v: { end_from: string }) => cashflowApi.endItem(item.id, v), onDone)
  const correct = useCashflowMutation(
    (v: { reason: string; amount?: string; frequency?: Frequency }) =>
      cashflowApi.correctVersion(active!.id, v),
    onDone,
  )

  if (!active) return null
  const firstOpen = selected < current ? current : selected

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    if (mode === 'change') {
      change.mutate({
        effective_from: String(f.get('effective_from')),
        amount: parseAmount(f.get('amount')),
        frequency: String(f.get('frequency')) as Frequency,
      })
    } else if (mode === 'spread') {
      setSpreadMutation.mutate(spread)
    } else if (mode === 'start') {
      const reason = String(f.get('reason') ?? '').trim()
      start.mutate({ start_from: String(f.get('start_from')), ...(reason ? { reason } : {}) })
    } else if (mode === 'end') {
      end.mutate({ end_from: String(f.get('end_from')) })
    } else {
      correct.mutate({
        reason: String(f.get('reason')).trim(),
        amount: parseAmount(f.get('amount')),
        frequency: String(f.get('frequency')) as Frequency,
      })
    }
  }

  const isFirst = item.versions[0]?.id === active.id
  const periodic = active.frequency !== 'monthly'
  const tabs: [Mode, string][] = [
    ['change', 'Ab einem Monat ändern'],
    ...(periodic ? ([['spread', 'Aufteilung']] as [Mode, string][]) : []),
    ...(isFirst ? ([['start', 'Früher beginnen']] as [Mode, string][]) : []),
    ['end', 'Beenden'],
    ['correct', 'Korrigieren'],
  ]
  const error = { change: change.error, spread: setSpreadMutation.error, start: start.error, end: end.error, correct: correct.error }[mode]
  const pending = change.isPending || end.isPending || correct.isPending || setSpreadMutation.isPending || start.isPending

  let fields: ReactNode
  if (mode === 'change') {
    fields = (
      <>
        <label className="block text-sm">
          Neuer Betrag in Euro
          <input
            name="amount"
            required
            inputMode="decimal"
            pattern="[0-9]+([.,][0-9]{1,2})?"
            defaultValue={String(active.amount).replace('.', ',')}
            className={input}
          />
        </label>
        <label className="block text-sm">
          Zahlweise
          <FrequencySelect defaultValue={active.frequency} />
        </label>
        <label className="block text-sm">
          Gilt ab
          <input name="effective_from" type="month" required min={current} defaultValue={firstOpen} className={input} />
        </label>
      </>
    )
  } else if (mode === 'spread') {
    fields = <SpreadCheckbox checked={spread} onChange={setSpread} />
  } else if (mode === 'start') {
    fields = (
      <>
        <label className="block text-sm">
          Neuer erster Monat
          <input name="start_from" type="month" required max={addMonths(active.valid_from, -1)} defaultValue={addMonths(active.valid_from, -1)} className={input} />
        </label>
        <label className="block text-sm sm:col-span-2">
          Begründung (nötig für abgeschlossene Monate)
          <input name="reason" minLength={3} maxLength={500} placeholder="z. B. Vorjahr nachgetragen" className={input} />
        </label>
        <p className="max-w-xl text-sm text-tinte-weich sm:col-span-3">
          Der Posten gilt mit demselben Betrag schon ab diesem Monat. So trägst du Vergangenheit nach, ohne die Posten einzeln anzulegen.
        </p>
      </>
    )
  } else if (mode === 'end') {
    fields = (
      <label className="block text-sm">
        Erster Monat ohne diesen Posten
        <input name="end_from" type="month" required min={addMonths(current, 0)} defaultValue={addMonths(firstOpen, 1)} className={input} />
      </label>
    )
  } else {
    fields = (
      <>
        <label className="block text-sm">
          Richtiger Betrag in Euro
          <input
            name="amount"
            required
            inputMode="decimal"
            pattern="[0-9]+([.,][0-9]{1,2})?"
            defaultValue={String(active.amount).replace('.', ',')}
            className={input}
          />
        </label>
        <label className="block text-sm">
          Zahlweise
          <FrequencySelect defaultValue={active.frequency} />
        </label>
        <label className="block text-sm sm:col-span-2">
          Begründung (wird im Protokoll gespeichert)
          <input name="reason" required minLength={3} maxLength={500} className={input} />
        </label>
      </>
    )
  }

  return (
    <form onSubmit={submit} className="border-l-4 border-elbe bg-karte-tief px-4 py-4">
      <div className="mb-4 flex flex-wrap gap-4 text-sm font-medium">
        {tabs.map(([m, label]) => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            className={`border-b-2 pb-0.5 ${mode === m ? 'border-elbe' : 'border-transparent text-tinte-weich'}`}
          >
            {label}
          </button>
        ))}
      </div>
      {mode === 'correct' && (
        <p className="mb-3 max-w-xl text-sm text-tinte-weich">
          Eine Korrektur ändert den Betrag dieser Version rückwirkend, auch in abgeschlossenen Monaten. Wenn sich der Betrag
          wirklich geändert hat, nutze stattdessen „Ab einem Monat ändern“.
        </p>
      )}
      <div className="grid gap-4 sm:grid-cols-3">{fields}</div>
      <div className="mt-4 flex items-center gap-2">
        <button type="submit" disabled={pending} className={primary}>
          {mode === 'change' ? 'Änderung speichern' : mode === 'spread' ? 'Aufteilung speichern' : mode === 'start' ? 'Beginn vorverlegen' : mode === 'end' ? 'Posten beenden' : 'Korrektur speichern'}
        </button>
        <button type="button" onClick={onDone} className={secondary}>
          Abbrechen
        </button>
      </div>
      <div className="mt-3">
        <ErrorLine error={error} />
      </div>
      <div className="mt-4 border-t border-tinte/15 pt-3">
        <ConfirmDelete
          label="Posten komplett löschen"
          question={`„${item.name}“ mit allen Beträgen und allen Monaten, auch den abgeschlossenen, endgültig löschen? Das lässt sich nicht rückgängig machen. Wenn der Posten nur ab einem Monat wegfällt, nutze „Beenden“.`}
          pending={remove.isPending}
          error={remove.error}
          onConfirm={() => remove.mutate()}
        />
      </div>
    </form>
  )
}
