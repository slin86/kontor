import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type ChangeEvent, type FormEvent } from 'react'

import { actualsApi, KIND_LABEL, type Transaction } from '../actualsApi'
import { aiApi, type DepotPreview } from '../aiApi'
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
  const aiStatus = useQuery({ queryKey: ['ai', 'status'], queryFn: aiApi.status, staleTime: 10_000 })
  const [file, setFile] = useState<File | null>(null)
  const [mapping, setMapping] = useState<Record<string, number>>({})
  const [preview, setPreview] = useState<DepotPreview | null>(null)
  const [off, setOff] = useState<Set<string>>(new Set())
  const [done, setDone] = useState<string | null>(null)

  const previewMutation = useMutation({
    mutationFn: (v: { file: File; map: Record<string, number> }) => aiApi.analyzeDepot(v.file, v.map, target?.id ?? 0),
    onSuccess: (p) => {
      setPreview(p)
      // rows the checks could not confirm start unticked; the user decides
      setOff(new Set(p.rows.filter((r) => r.check).map((r) => r.external_id)))
    },
  })
  const chosen = (preview?.rows ?? []).filter((r) => !off.has(r.external_id) && !r.duplicate && r.instrument_id !== null)
  const importMutation = useMutation({
    mutationFn: () => aiApi.importDepot(chosen, mapping, target?.id ?? 0, preview?.method ?? 'ai'),
    onSuccess: async (r) => {
      setDone(`${r.imported} Transaktionen importiert, ${r.duplicates} schon vorhanden, ${r.unmatched} ohne Position übersprungen.`)
      setFile(null)
      setPreview(null)
      setMapping({})
      await invalidate()
    },
  })

  function onFile(e: ChangeEvent<HTMLInputElement>) {
    const picked = e.target.files?.[0]
    if (!picked) return
    setDone(null)
    setFile(picked)
    setMapping({})
    previewMutation.mutate({ file: picked, map: {} })
  }

  function assign(isin: string, instrumentId: number | null) {
    const next = { ...mapping }
    if (instrumentId === null) delete next[isin]
    else next[isin] = instrumentId
    setMapping(next)
    if (file) previewMutation.mutate({ file, map: next })
  }

  const toggle = (id: string) =>
    setOff((all) => {
      const next = new Set(all)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  return (
    <div className="space-y-4">
      {target && people.length > 1 && (
        <p className="text-sm font-medium">
          Import für {target.name}
          {selectedId === null && <span className="font-normal text-tinte-weich"> (Wähle oben eine Person, um für jemand anderen zu importieren.)</span>}
        </p>
      )}
      <label className="block text-sm">
        Datei vom Broker
        <input type="file" accept=".csv,.txt,.pdf,text/csv,text/plain,application/pdf" onChange={onFile} className={`${input} cursor-pointer`} />
        <span className="mt-1 block text-xs text-tinte-weich">
          CSV-Exporte und PDF-Abrechnungen beliebiger Broker. Das Transaktions-CSV von Trade Republic wird ohne KI gelesen; andere Layouts und PDFs liest die lokale KI,
          und jede Zahl wird gegen den Dokumenttext geprüft. Die Datei bleibt auf deinem Server und wird nicht gespeichert.
        </span>
        {aiStatus.data && aiStatus.data.local_configured && !aiStatus.data.local_reachable && (
          <span className="mt-1 block text-xs text-bake">KI-Server nicht erreichbar. Starte den Rechner für PDFs und unbekannte Layouts.</span>
        )}
      </label>
      {previewMutation.isPending && <p className="text-sm text-tinte-weich">Die Datei wird gelesen. Mit lokaler KI kann das einige Minuten dauern.</p>}
      <ErrorLine error={previewMutation.error ?? importMutation.error} />
      {done && <p className="text-sm font-medium text-elbe-dunkel">{done}</p>}

      {preview && file && (
        <div className="space-y-4">
          <p className="text-sm">
            <strong>{file.name}</strong>: {preview.new_count} neue Transaktionen, {preview.duplicate_count} bereits importiert
            {preview.method === 'ai' && ', von der KI gelesen'}.
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
                      {u.isin ?? 'ohne gültige ISIN'} · {u.count === 1 ? '1 Zeile' : `${u.count} Zeilen`}
                    </span>
                    {u.isin && (
                      <select
                        aria-label={`Position für ${u.isin}`}
                        value={mapping[u.isin] ?? ''}
                        onChange={(e) => assign(u.isin!, e.target.value ? Number(e.target.value) : null)}
                        className="ml-auto border border-tinte/30 bg-feld/60 px-2 py-1"
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

          {preview.skipped > 0 && <p className="text-sm text-tinte-weich">{preview.skipped} Zeilen ohne Wertpapier-Bezug nicht übernommen.</p>}

          <div className="max-h-72 overflow-auto">
            <table className="w-full min-w-[34rem] text-left text-sm">
              <thead className="sticky top-0 bg-karte text-tinte-weich">
                <tr>
                  <th className="py-1 pr-2 font-medium">
                    <span className="sr-only">Übernehmen</span>
                  </th>
                  <th className="py-1 pr-3 font-medium">Datum</th>
                  <th className="py-1 pr-3 font-medium">Art</th>
                  <th className="py-1 pr-3 font-medium">Wertpapier</th>
                  <th className="py-1 text-right font-medium">Betrag</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-tinte/10">
                {preview.rows.slice(0, 200).map((r) => {
                  const blocked = r.duplicate || r.instrument_id === null
                  return (
                    <tr key={r.external_id} className={blocked ? 'text-tinte-weich' : ''}>
                      <td className="py-1 pr-2">
                        <input
                          type="checkbox"
                          disabled={blocked}
                          checked={!blocked && !off.has(r.external_id)}
                          onChange={() => toggle(r.external_id)}
                          aria-label={`${r.name ?? r.isin} am ${r.day} übernehmen`}
                        />
                      </td>
                      <td className="py-1 pr-3">{r.day}</td>
                      <td className="py-1 pr-3">{KIND_LABEL[r.kind]}</td>
                      <td className="py-1 pr-3">
                        {r.name ?? r.isin}
                        {r.duplicate && ' (schon importiert)'}
                        {!r.duplicate && r.instrument_id === null && ' (keine Position)'}
                        {r.check && <span className="block text-xs font-medium text-bake">{r.check}</span>}
                      </td>
                      <td className="zahl py-1 text-right">{euro(r.amount, true)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          <div className="flex gap-2">
            <button type="button" disabled={importMutation.isPending || chosen.length === 0} onClick={() => importMutation.mutate()} className={primary}>
              {chosen.length} Transaktionen importieren
            </button>
            <button
              type="button"
              onClick={() => {
                setPreview(null)
                setFile(null)
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
