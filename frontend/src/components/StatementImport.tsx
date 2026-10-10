import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { aiApi, type Analysis, type Candidate, type ContractAnalysis } from '../aiApi'
import { cashflowApi, type Category, type Frequency } from '../cashflowApi'
import { FREQUENCY_LABEL } from '../format'
import { JobProgress, useFinishJob, useJob, useJobParam, useStartJob } from '../jobs'
import { useMonth } from '../month'
import { monthLabel } from '../monthUtils'
import { usePerson } from '../person'
import { input, primary, secondary } from './ui'

interface Row extends Candidate {
  on: boolean
}

/** What the same review table is used for: a bank statement or a contract, policy or invoice. */
export type ImportMode = 'statement' | 'contract'

const FORMAT_LABEL = { csv: 'CSV', camt: 'CAMT', mt940: 'MT940', pdf: 'PDF' } as const

function ServerLine({ needsAi }: { needsAi: boolean }) {
  const status = useQuery({ queryKey: ['ai', 'status'], queryFn: aiApi.status, staleTime: 10_000, refetchInterval: 15_000 })
  const s = status.data
  if (!s) return null
  if (!s.local_configured) {
    return <p className="text-sm text-tinte-weich">{needsAi ? 'Kein KI-Server eingerichtet. Ohne KI lassen sich Dokumente nicht lesen.' : 'Kein KI-Server eingerichtet. CSV, CAMT und MT940 lassen sich trotzdem einlesen, Kategorien musst du selbst wählen.'}</p>
  }
  return (
    <p className="text-sm text-tinte-weich">
      <span aria-hidden className={s.local_reachable ? 'text-elbe-dunkel' : 'text-bake'}>
        ●{' '}
      </span>
      {s.local_reachable
        ? `KI-Server erreichbar${s.local_model ? ` (${s.local_model})` : ''}`
        : 'KI-Server nicht erreichbar. Starte den Rechner, wenn Kategorien vorgeschlagen werden sollen oder du ein PDF einlesen willst.'}
    </p>
  )
}

/** Reads a bank statement and proposes the payments that come back as items. */
export function StatementImport({ categories, onDone, mode = 'statement' }: { categories: Category[]; onDone: () => void; mode?: ImportMode }) {
  const qc = useQueryClient()
  const { current, selected } = useMonth()
  const { me, selectedId } = usePerson()
  const { jobId } = useJobParam()
  const job = useJob<Analysis | ContractAnalysis>(jobId)
  const finish = useFinishJob()
  const contract = job.data ? job.data.kind === 'contract' : mode === 'contract'
  const start = useStartJob(contract ? 'contract' : 'statement')
  const [rows, setRows] = useState<Row[] | null>(null)
  const [from, setFrom] = useState(selected < current ? current : selected)
  const [done, setDone] = useState<string | null>(null)
  const byId = new Map(categories.map((c) => [c.id, c]))
  const parents = new Set(categories.map((c) => c.parent_id).filter((p) => p !== null))
  const label = (c: Category) => (c.parent_id ? `${byId.get(c.parent_id)?.name} › ${c.name}` : c.name)

  const [summary, setSummary] = useState<{ text: string; note: string | null; unrated: number } | null>(null)
  const result = job.data?.status === 'done' ? job.data : null
  const resultId = result?.id
  // the finished job fills the review table; rows the checks could not confirm start unticked
  useEffect(() => {
    if (!result?.result) return
    const a = result.result
    const n = a.candidates.length
    if (result.kind === 'contract') {
      setSummary({ text: `${n} regelmäßige Zahlungen im Dokument gefunden.`, note: a.ai.note, unrated: 0 })
    } else {
      const s = a as Analysis
      setSummary({
        text: `${s.lines} Buchungen (${FORMAT_LABEL[s.format]}, ${s.period_from} bis ${s.period_to}) gelesen, ${n === 0 ? 'keine wiederkehrende Zahlung erkannt.' : `${n} wiederkehrende Zahlungen gefunden.`}`,
        note: a.ai.note,
        unrated: s.unrated,
      })
    }
    setRows(a.candidates.map((c) => ({ ...c, on: c.existing_item_id === null && !c.check })))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resultId])
  const create = useMutation({
    mutationFn: async (selectedRows: Row[]) => {
      for (const r of selectedRows) {
        await cashflowApi.createItem({
          name: r.name.trim(),
          category_id: r.category_id!,
          person_id: selectedId ?? me?.id,
          amount: String(r.amount),
          frequency: r.frequency,
          spread: true,
          valid_from: from,
        })
      }
      return selectedRows.length
    },
    onSuccess: async (n) => {
      await qc.invalidateQueries({ queryKey: ['cashflow'] })
      setDone(`${n} Posten angelegt.`)
      setRows(null)
      setSummary(null)
      await finish(jobId)
    },
  })

  const patch = (i: number, p: Partial<Row>) => setRows((all) => all && all.map((r, j) => (j === i ? { ...r, ...p } : r)))
  const chosen = (rows ?? []).filter((r) => r.on)
  const incomplete = chosen.some((r) => r.category_id === null || !r.name.trim())

  return (
    <section aria-labelledby="kontoauszug" className="space-y-4 border-t-4 border-tinte pt-5">
      <div className="flex flex-wrap items-baseline gap-4">
        <h3 id="kontoauszug" className="text-lg">
          {contract ? 'Aus Dokument anlegen' : 'Aus Kontoauszug anlegen'}
        </h3>
        <button
          type="button"
          onClick={async () => {
            await finish(jobId)
            onDone()
          }}
          className={`${secondary} ml-auto`}
        >
          Schließen
        </button>
      </div>
      <p className="max-w-2xl text-sm text-tinte-weich">
        {contract
          ? 'Lade einen Vertrag, eine Police oder eine Rechnung als PDF oder Textdatei hoch, etwa Versicherung, Strom, Internet, Kita oder Abo. Die KI liest Betrag und Zahlweise und schlägt Posten vor; jeder Betrag wird gegen den Text des Dokuments geprüft.'
          : 'Lade einen Kontoauszug als CSV, CAMT, MT940 oder PDF hoch, am besten mehrere Monate. Kontor sucht Zahlungen, die regelmäßig wiederkehren, und schlägt sie als Posten vor. Auch unbekannte CSV-Layouts werden mit der lokalen KI gelesen.'}{' '}
        Die Datei wird nicht gespeichert und geht nie an einen Online-Dienst.
      </p>
      {!jobId && <ServerLine needsAi={contract} />}

      {!jobId && (
        <label className="block text-sm">
          Datei
          <input
            type="file"
            accept={contract ? '.pdf,.txt' : '.csv,.xml,.sta,.mt940,.txt,.pdf'}
            disabled={start.isPending}
            onChange={(e) => {
              const file = e.target.files?.[0]
              setDone(null)
              if (file) start.mutate({ file })
            }}
            className={input}
          />
        </label>
      )}
      {start.isPending && <p className="text-sm text-tinte-weich">Die Datei wird hochgeladen.</p>}
      {start.error && (
        <p role="alert" className="text-sm font-medium text-bake">
          {start.error instanceof Error ? start.error.message : 'Das hat nicht geklappt.'}
        </p>
      )}
      {job.error && (
        <p role="alert" className="text-sm font-medium text-bake">
          Das Ergebnis ist nicht mehr da (nach einem Neustart oder nach 24 Stunden). Lade die Datei noch einmal hoch.
        </p>
      )}
      {job.data && job.data.status !== 'done' && (
        <div className="space-y-2">
          <p className="text-sm font-medium">{job.data.filename}</p>
          <JobProgress job={job.data} />
          <button type="button" onClick={() => finish(jobId)} className={secondary}>
            {job.data.status === 'failed' ? 'Andere Datei wählen' : 'Abbrechen'}
          </button>
        </div>
      )}
      {done && <p className="text-sm font-medium text-elbe-dunkel">{done}</p>}

      {summary && rows && (
        <div className="space-y-3">
          <p className="text-sm">{summary.text}</p>
          {summary.note && <p className="text-sm text-tinte-weich">{summary.note}</p>}
          {summary.unrated > 0 && <p className="text-sm text-tinte-weich">{summary.unrated} einzelne Zahlungen wurden nicht bewertet.</p>}

          <ul className="divide-y divide-tinte/15">
            {rows.map((r, i) => (
              <li key={`${r.name}-${i}`} className="grid gap-x-4 gap-y-2 py-3 sm:grid-cols-[auto_1fr_8rem] lg:grid-cols-[auto_1fr_9rem_9rem_14rem]">
                <input type="checkbox" checked={r.on} onChange={(e) => patch(i, { on: e.target.checked })} aria-label={`${r.name} übernehmen`} className="mt-3" />
                <label className="block text-sm">
                  Bezeichnung
                  <input value={r.name} maxLength={120} onChange={(e) => patch(i, { name: e.target.value })} className={input} />
                </label>
                <label className="block text-sm">
                  {r.income ? 'Einnahme' : 'Betrag'} in Euro
                  <input
                    defaultValue={r.amount.toFixed(2).replace('.', ',')}
                    inputMode="decimal"
                    onChange={(e) => {
                      const n = Number(e.target.value.replace(',', '.'))
                      if (Number.isFinite(n)) patch(i, { amount: n })
                    }}
                    className={input}
                  />
                </label>
                <label className="block text-sm">
                  Zahlweise
                  <select value={r.frequency} onChange={(e) => patch(i, { frequency: e.target.value as Frequency })} className={input}>
                    {Object.entries(FREQUENCY_LABEL).map(([v, l]) => (
                      <option key={v} value={v}>
                        {l}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block text-sm">
                  Kategorie
                  <select
                    value={r.category_id ?? ''}
                    onChange={(e) => patch(i, { category_id: e.target.value ? Number(e.target.value) : null })}
                    className={input}
                  >
                    <option value="">Bitte wählen</option>
                    {categories
                      .filter((c) => (c.kind === 'income') === r.income && !parents.has(c.id))
                      .map((c) => (
                        <option key={c.id} value={c.id}>
                          {label(c)}
                        </option>
                      ))}
                  </select>
                </label>
                <p className="text-xs text-tinte-weich sm:col-span-3 sm:col-start-2 lg:col-span-4">
                  {r.check && <strong className="text-bake">Bitte prüfen: {r.check}. </strong>}
                  {r.existing_item_id !== null
                    ? `Passt zu deinem Posten „${r.existing_item_name}“, daher nicht vorausgewählt. `
                    : r.source === 'document'
                      ? ''
                      : r.source === 'ai'
                        ? 'Kam nur einmal vor, die KI hält es für wiederkehrend. '
                        : `${r.occurrences}-mal erkannt, zuletzt am ${r.last}. `}
                  {r.reason}
                </p>
              </li>
            ))}
          </ul>

          {rows.length > 0 && (
            <div className="flex flex-wrap items-end gap-4">
              <label className="block text-sm">
                Gilt ab
                <input type="month" value={from} min={current} onChange={(e) => setFrom(e.target.value)} className={input} />
              </label>
              <button type="button" disabled={create.isPending || chosen.length === 0 || incomplete} onClick={() => create.mutate(chosen)} className={primary}>
                {chosen.length} Posten ab {monthLabel(from)} anlegen
              </button>
              {incomplete && <span className="text-sm text-tinte-weich">Für jede gewählte Zeile braucht es Name und Kategorie.</span>}
            </div>
          )}
          {create.error && (
            <p role="alert" className="text-sm font-medium text-bake">
              {create.error instanceof Error ? create.error.message : 'Das hat nicht geklappt.'}
            </p>
          )}
        </div>
      )}
    </section>
  )
}
