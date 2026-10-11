import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { cashflowApi, type AuditEntry, type Item } from '../../cashflowApi'
import { ItemEditor, NewItemForm } from '../../components/ItemForms'
import { StatementImport, type ImportMode } from '../../components/StatementImport'
import { euro, FREQUENCY_LABEL } from '../../format'
import { useJobParam } from '../../jobs'
import { useMonth } from '../../month'
import { addMonths, monthLabel } from '../../monthUtils'
import { usePerson } from '../../person'
import { useCashflowData } from './useCashflowData'

const ACTION_LABEL: Record<string, string> = {
  create: 'angelegt',
  backfill: 'rückwirkend angelegt',
  change: 'geändert',
  end: 'beendet',
  update: 'angepasst',
  move: 'verschoben',
  correction: 'korrigiert',
  event_add: 'Ereignis hinzugefügt',
  event_remove: 'Ereignis entfernt',
  rate_change: 'Sparrate geändert',
  oneoff_add: 'Einmalzahlung hinzugefügt',
  oneoff_remove: 'Einmalzahlung entfernt',
  actual_set: 'Ist-Wert erfasst',
  actual_remove: 'Ist-Wert entfernt',
  transaction_add: 'Transaktion erfasst',
  transaction_remove: 'Transaktion entfernt',
  import: 'Import',
  delete: 'gelöscht',
  delete_all: 'alle gelöscht',
}

function AuditList({ entries }: { entries: AuditEntry[] }) {
  if (entries.length === 0) return <p className="text-sm text-tinte-weich">Noch keine Änderungen.</p>
  return (
    <ul className="divide-y divide-tinte/15 text-sm">
      {entries.map((e) => (
        <li key={e.id} className="py-2">
          <span className="font-medium">
            {e.subject ?? (e.entity === 'category' ? 'Kategorie' : 'Eintrag')}: {e.entity === 'cashflow_version' ? 'Betrag ' : ''}
            {ACTION_LABEL[e.action] ?? e.action}
          </span>
          <span className="text-tinte-weich">
            {' '}
            von {e.user_name} am {new Date(e.created_at).toLocaleString('de-DE', { dateStyle: 'medium', timeStyle: 'short' })}
          </span>
          {e.reason && <div className="text-tinte-weich">Begründung: {e.reason}</div>}
        </li>
      ))}
    </ul>
  )
}

export function ItemsView() {
  const { selected, isLocked } = useMonth()
  const { selectedId, people } = usePerson()
  const locked = isLocked(selected)
  const [adding, setAdding] = useState(false)
  const [importing, setImporting] = useState<ImportMode | null>(null)
  const { jobId } = useJobParam()
  // arriving from a notice: open the review panel for that job and keep it after the job is done
  useEffect(() => {
    if (jobId) setImporting((m) => m ?? 'statement')
  }, [jobId])
  const [editing, setEditing] = useState<number | null>(null)

  const categories = useQuery({ queryKey: ['cashflow', 'categories'], queryFn: cashflowApi.categories })
  const { items } = useCashflowData()
  const audit = useQuery({ queryKey: ['cashflow', 'audit'], queryFn: cashflowApi.audit })

  const incomeItems = (items.data ?? []).filter((i) => i.kind === 'income')
  const expenseItems = (items.data ?? []).filter((i) => i.kind === 'expense')

  function row(i: Item) {
    const v = i.active!
    const next = v.valid_to ? i.versions.find((x) => x.valid_from === v.valid_to) : undefined
    return (
      <li key={i.id} className="py-3">
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <span className="font-medium">{i.name}</span>
          <span className="text-sm text-tinte-weich">
            {i.transfer_to_name && !i.incoming ? `Übertrag an ${i.transfer_to_name}` : i.category_name}
            {selectedId === null && people.length > 1 && ` · ${people.find((p) => p.id === i.person_id)?.name}`}
          </span>
          <span className="zahl ml-auto">
            {euro(v.amount, true)}
            <span className="text-sm text-tinte-weich"> {FREQUENCY_LABEL[v.frequency]}</span>
          </span>
          {i.incoming ? (
            <span className="text-sm text-tinte-weich">wird beim Absender bearbeitet</span>
          ) : (
            <button
              type="button"
              className="text-sm font-medium text-elbe-dunkel hover:underline"
              onClick={() => setEditing(editing === i.id ? null : i.id)}
            >
              {editing === i.id ? 'Schließen' : locked ? 'Korrigieren' : 'Bearbeiten'}
            </button>
          )}
        </div>
        {v.frequency !== 'monthly' && (
          <div className="text-sm text-tinte-weich">
            {i.spread
              ? `Auf ${monthLabel(selected)} entfallen ${euro(i.booked, true)}, auf monatliche Kosten aufgeteilt`
              : i.due_now
                ? `Fällig im ${monthLabel(selected)}: der volle Betrag zählt in diesem Monat`
                : 'In diesem Monat nicht fällig, der Betrag zählt nur im Fälligkeitsmonat'}
          </div>
        )}
        {v.valid_to &&
          (next ? (
            <div className="text-sm text-tinte-weich">
              Ab {monthLabel(next.valid_from)}: {euro(next.amount, true)} {FREQUENCY_LABEL[next.frequency]}
            </div>
          ) : (
            <div className="text-sm text-tinte-weich">Läuft bis {monthLabel(addMonths(v.valid_to, -1))}</div>
          ))}
        {editing === i.id && (
          <div className="mt-3">
            <ItemEditor item={i} onDone={() => setEditing(null)} />
          </div>
        )}
      </li>
    )
  }

  return (
    <div className="space-y-12">
      <h1 className="sr-only">Posten im {monthLabel(selected)}</h1>
      <section aria-labelledby="posten">
        <div className="mb-2 flex items-baseline gap-4">
          <h2 id="posten" className="text-xl">
            Posten im {monthLabel(selected)}
          </h2>
          <Link to="/kategorien" className="ml-auto text-sm font-medium text-elbe-dunkel hover:underline">
            Kategorien verwalten
          </Link>
          {!importing && !jobId && (
            <>
              <button type="button" onClick={() => setImporting('contract')} className="border border-tinte/40 px-4 py-2 text-sm font-medium hover:border-tinte">
                Aus Dokument
              </button>
              <button type="button" onClick={() => setImporting('statement')} className="border border-tinte/40 px-4 py-2 text-sm font-medium hover:border-tinte">
                Aus Kontoauszug
              </button>
            </>
          )}
          {!adding && (
            <button type="button" onClick={() => setAdding(true)} className="bg-tinte px-4 py-2 text-sm font-medium text-karte hover:bg-elbe-dunkel">
              Posten hinzufügen
            </button>
          )}
        </div>
        {(importing || jobId) && categories.data && (
          <div className="mb-8">
            <StatementImport mode={importing ?? 'statement'} categories={categories.data} onDone={() => setImporting(null)} />
          </div>
        )}
        {adding && categories.data && (
          <div className="mb-8">
            <NewItemForm categories={categories.data} onDone={() => setAdding(false)} />
          </div>
        )}
        {incomeItems.length > 0 && (
          <>
            <h3 className="mt-6 text-base text-tinte-weich">Einnahmen</h3>
            <ul className="divide-y divide-tinte/15">{incomeItems.map(row)}</ul>
          </>
        )}
        {expenseItems.length > 0 && (
          <>
            <h3 className="mt-6 text-base text-tinte-weich">Ausgaben</h3>
            <ul className="divide-y divide-tinte/15">{expenseItems.map(row)}</ul>
          </>
        )}
      </section>

      <section aria-labelledby="protokoll">
        <details>
          <summary id="protokoll" className="cursor-pointer text-xl font-semibold font-display">
            Änderungsprotokoll
          </summary>
          <div className="mt-4">{audit.data && <AuditList entries={audit.data} />}</div>
        </details>
      </section>
    </div>
  )
}
