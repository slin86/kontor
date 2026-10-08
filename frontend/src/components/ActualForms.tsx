import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type ChangeEvent, type FormEvent } from 'react'

import { actualsApi, KIND_LABEL, type ImportPreview, type Transaction } from '../actualsApi'
import { depotApi } from '../depotApi'
import { euro } from '../format'
import { useMonth } from '../month'
import { monthLabel } from '../monthUtils'
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

function useInvalidate() {
  const qc = useQueryClient()
  return async () => {
    await qc.invalidateQueries({ queryKey: ['actuals'] })
    await qc.invalidateQueries({ queryKey: ['depot'] })
    await qc.invalidateQueries({ queryKey: ['cashflow'] })
  }
}

function usePositions() {
  const { selectedId } = usePerson()
  return useQuery({ queryKey: ['depot', 'overview', selectedId], queryFn: () => depotApi.overview(selectedId) })
}

export function ValueForm() {
  const { current } = useMonth()
  const positions = usePositions().data?.instruments ?? []
  const invalidate = useInvalidate()
  const [saved, setSaved] = useState<string | null>(null)
  const mutation = useMutation({
    mutationFn: actualsApi.setValue,
    onSuccess: async (v) => {
      setSaved(`${monthLabel(v.month)}: ${euro(v.value, true)} gespeichert`)
      await invalidate()
    },
  })
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setSaved(null)
    const f = new FormData(e.currentTarget)
    const reason = String(f.get('reason') ?? '').trim()
    mutation.mutate({
      instrument_id: Number(f.get('instrument_id')),
      month: String(f.get('month')),
      value: decimalString(f.get('value')),
      reason: reason || null,
    })
  }
  return (
    <form onSubmit={submit} className="grid items-end gap-4 sm:grid-cols-4">
      <label className="block text-sm">
        Position
        <select name="instrument_id" required className={input}>
          {positions.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </label>
      <label className="block text-sm">
        Stand Ende
        <input name="month" type="month" required max={current} defaultValue={current} className={input} />
      </label>
      <label className="block text-sm">
        Wert in Euro
        <input name="value" required inputMode="decimal" pattern="[0-9]+([.,][0-9]+)?" className={input} />
      </label>
      <button type="submit" disabled={mutation.isPending || positions.length === 0} className={primary}>
        Wert speichern
      </button>
      <label className="block text-sm sm:col-span-4">
        Begründung
        <input name="reason" maxLength={500} className={input} placeholder="Nur nötig, wenn du den Wert eines abgeschlossenen Monats änderst" />
      </label>
      <div className="sm:col-span-4">
        <ErrorLine error={mutation.error} />
        {saved && <p className="text-sm font-medium text-elbe-dunkel">{saved}</p>}
      </div>
    </form>
  )
}

export function TransactionForm() {
  const positions = usePositions().data?.instruments ?? []
  const invalidate = useInvalidate()
  const [today] = useState(() => new Date().toISOString().slice(0, 10))
  const mutation = useMutation({ mutationFn: actualsApi.addTransaction, onSuccess: invalidate })
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    mutation.mutate({
      instrument_id: Number(f.get('instrument_id')),
      day: String(f.get('day')),
      kind: String(f.get('kind')) as Transaction['kind'],
      amount: decimalString(f.get('amount')),
      fee: decimalString(f.get('fee')) || '0',
    })
  }
  return (
    <form onSubmit={submit} className="grid items-end gap-4 sm:grid-cols-6">
      <label className="block text-sm sm:col-span-2">
        Position
        <select name="instrument_id" required className={input}>
          {positions.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </label>
      <label className="block text-sm">
        Art
        <select name="kind" className={input}>
          <option value="buy">Kauf</option>
          <option value="sell">Verkauf</option>
          <option value="dividend">Dividende</option>
        </select>
      </label>
      <label className="block text-sm">
        Datum
        <input name="day" type="date" required max={today} defaultValue={today} className={input} />
      </label>
      <label className="block text-sm">
        Betrag in Euro
        <input name="amount" required inputMode="decimal" pattern="[0-9]+([.,][0-9]+)?" className={input} />
      </label>
      <button type="submit" disabled={mutation.isPending || positions.length === 0} className={primary}>
        Hinzufügen
      </button>
      <input type="hidden" name="fee" value="0" />
      <div className="sm:col-span-6">
        <ErrorLine error={mutation.error} />
      </div>
    </form>
  )
}

export function ImportPanel() {
  const { selectedId, me, people } = usePerson()
  // an import always belongs to one person: the chosen one, or the own person when everyone is shown
  const target = people.find((p) => p.id === (selectedId ?? me?.id))
  const positions = usePositions().data?.instruments ?? []
  const invalidate = useInvalidate()
  const [csv, setCsv] = useState<string | null>(null)
  const [fileName, setFileName] = useState('')
  const [mapping, setMapping] = useState<Record<string, number>>({})
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [done, setDone] = useState<string | null>(null)

  const previewMutation = useMutation({
    mutationFn: (v: { text: string; map: Record<string, number> }) => actualsApi.preview(v.text, v.map, target?.id ?? 0),
    onSuccess: setPreview,
  })
  const importMutation = useMutation({
    mutationFn: () => actualsApi.importCsv(csv ?? '', mapping, target?.id ?? 0),
    onSuccess: async (r) => {
      setDone(`${r.imported} Transaktionen importiert, ${r.duplicates} schon vorhanden, ${r.unmatched} ohne Position übersprungen.`)
      setCsv(null)
      setPreview(null)
      setMapping({})
      await invalidate()
    },
  })

  async function onFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setDone(null)
    setFileName(file.name)
    const text = await file.text()
    setCsv(text)
    setMapping({})
    previewMutation.mutate({ text, map: {} })
  }

  function assign(isin: string, instrumentId: number | null) {
    const next = { ...mapping }
    if (instrumentId === null) delete next[isin]
    else next[isin] = instrumentId
    setMapping(next)
    if (csv) previewMutation.mutate({ text: csv, map: next })
  }

  const skipped = preview ? Object.entries(preview.skipped) : []
  return (
    <div className="space-y-4">
      {target && people.length > 1 && (
        <p className="text-sm font-medium">
          Import für {target.name}
          {selectedId === null && <span className="font-normal text-tinte-weich"> (Wähle oben eine Person, um für jemand anderen zu importieren.)</span>}
        </p>
      )}
      <label className="block text-sm">
        CSV-Export des Brokers
        <input type="file" accept=".csv,text/csv,text/plain" onChange={onFile} className={`${input} cursor-pointer`} />
        <span className="mt-1 block text-xs text-tinte-weich">
          Gebaut für den Transaktionsexport von Trade Republic. Es werden Käufe, Verkäufe, Sparpläne und Dividenden übernommen. Die Datei
          bleibt auf deinem Server.
        </span>
      </label>
      <ErrorLine error={previewMutation.error ?? importMutation.error} />
      {done && <p className="text-sm font-medium text-elbe-dunkel">{done}</p>}

      {preview && (
        <div className="space-y-4">
          <p className="text-sm">
            <strong>{fileName}</strong>: {preview.new_count} neue Transaktionen, {preview.duplicate_count} bereits importiert
            {preview.errors.length > 0 && `, ${preview.errors.length} nicht lesbar`}.
          </p>

          {preview.unmatched.length > 0 && (
            <div>
              <h3 className="text-base font-medium">Ohne Position</h3>
              <p className="text-sm text-tinte-weich">Ordne diese Wertpapiere einer Position zu, sonst werden sie übersprungen.</p>
              <ul className="mt-2 divide-y divide-tinte/15 text-sm">
                {preview.unmatched.map((u) => (
                  <li key={u.isin ?? 'none'} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-2">
                    <span>{u.name ?? 'Unbekannt'}</span>
                    <span className="text-tinte-weich">
                      {u.isin ?? 'ohne ISIN'} · {u.count === 1 ? '1 Zeile' : `${u.count} Zeilen`}
                    </span>
                    {u.isin && (
                      <select
                        aria-label={`Position für ${u.isin}`}
                        value={mapping[u.isin] ?? ''}
                        onChange={(e) => assign(u.isin!, e.target.value ? Number(e.target.value) : null)}
                        className="ml-auto border border-tinte/30 bg-white/60 px-2 py-1"
                      >
                        <option value="">Überspringen</option>
                        {positions.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.name}
                          </option>
                        ))}
                      </select>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {skipped.length > 0 && (
            <p className="text-sm text-tinte-weich">
              Nicht übernommen: {skipped.map(([k, n]) => `${k} (${n})`).join(', ')}.
            </p>
          )}
          {preview.errors.length > 0 && (
            <ul className="text-sm text-bake">
              {preview.errors.slice(0, 5).map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          )}

          <div className="max-h-64 overflow-auto">
            <table className="w-full min-w-[30rem] text-left text-sm">
              <thead className="sticky top-0 bg-karte text-tinte-weich">
                <tr>
                  <th className="py-1 pr-3 font-medium">Datum</th>
                  <th className="py-1 pr-3 font-medium">Art</th>
                  <th className="py-1 pr-3 font-medium">Wertpapier</th>
                  <th className="py-1 text-right font-medium">Betrag</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-tinte/10">
                {preview.rows.slice(0, 100).map((r) => (
                  <tr key={r.line} className={r.duplicate || r.instrument_id === null ? 'text-tinte-weich' : ''}>
                    <td className="py-1 pr-3">{r.day}</td>
                    <td className="py-1 pr-3">{KIND_LABEL[r.kind]}</td>
                    <td className="py-1 pr-3">
                      {r.name ?? r.isin}
                      {r.duplicate && ' (schon importiert)'}
                      {!r.duplicate && r.instrument_id === null && ' (keine Position)'}
                    </td>
                    <td className="zahl py-1 text-right">{euro(r.amount, true)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex gap-2">
            <button type="button" disabled={importMutation.isPending || preview.new_count === 0} onClick={() => importMutation.mutate()} className={primary}>
              {preview.new_count} Transaktionen importieren
            </button>
            <button
              type="button"
              onClick={() => {
                setPreview(null)
                setCsv(null)
              }}
              className={secondary}
            >
              Verwerfen
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
