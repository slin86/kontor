import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { cashflowApi, type AuditEntry, type Item } from '../cashflowApi'
import { GroupBars } from '../components/GroupBars'
import { ItemEditor, NewItemForm } from '../components/ItemForms'
import { SankeyView } from '../components/SankeyView'
import { SeriesView } from '../components/SeriesView'
import { euro, FREQUENCY_LABEL, percent } from '../format'
import { useMonth } from '../month'
import { addMonths, monthLabel } from '../monthUtils'

function Figure({ label, value, tone }: { label: string; value: string; tone?: 'bad' }) {
  return (
    <div>
      <div className={`zahl text-3xl font-semibold ${tone === 'bad' ? 'text-bake' : ''}`}>{value}</div>
      <div className="text-sm text-tinte-weich">{label}</div>
    </div>
  )
}

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

export function CashflowPage() {
  const { selected, isLocked } = useMonth()
  const locked = isLocked(selected)
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)

  const categories = useQuery({ queryKey: ['cashflow', 'categories'], queryFn: cashflowApi.categories })
  const items = useQuery({ queryKey: ['cashflow', 'items', selected], queryFn: () => cashflowApi.items(selected) })
  const summary = useQuery({ queryKey: ['cashflow', 'summary', selected], queryFn: () => cashflowApi.summary(selected) })
  const sankey = useQuery({ queryKey: ['cashflow', 'sankey', selected], queryFn: () => cashflowApi.sankey(selected) })
  const from = addMonths(selected, -6)
  const to = addMonths(selected, 17)
  const series = useQuery({ queryKey: ['cashflow', 'series', from, to], queryFn: () => cashflowApi.series(from, to) })
  const audit = useQuery({ queryKey: ['cashflow', 'audit'], queryFn: cashflowApi.audit })

  const s = summary.data
  const empty = items.data?.length === 0

  const incomeItems = (items.data ?? []).filter((i) => i.kind === 'income')
  const expenseItems = (items.data ?? []).filter((i) => i.kind === 'expense')

  function row(i: Item) {
    const v = i.active!
    const next = v.valid_to ? i.versions.find((x) => x.valid_from === v.valid_to) : undefined
    return (
      <li key={i.id} className="py-3">
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <span className="font-medium">{i.name}</span>
          <span className="text-sm text-tinte-weich">{i.category_name}</span>
          <span className="zahl ml-auto">
            {euro(v.amount, true)}
            <span className="text-sm text-tinte-weich"> {FREQUENCY_LABEL[v.frequency]}</span>
          </span>
          <button
            type="button"
            className="text-sm font-medium text-elbe-dunkel hover:underline"
            onClick={() => setEditing(editing === i.id ? null : i.id)}
          >
            {editing === i.id ? 'Schließen' : locked ? 'Korrigieren' : 'Bearbeiten'}
          </button>
        </div>
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
      <section aria-labelledby="uebersicht">
        <h1 id="uebersicht" className="sr-only">
          Cashflow im {monthLabel(selected)}
        </h1>
        {s && (
          <div className="flex flex-wrap gap-x-12 gap-y-4">
            <Figure label="Einnahmen pro Monat" value={euro(s.income)} />
            <Figure label="Ausgaben pro Monat" value={euro(s.expenses)} />
            {s.financing > 0 && <Figure label="Finanzierungen pro Monat" value={euro(s.financing)} />}
            <Figure label={s.balance < 0 ? 'Fehlbetrag' : 'Übrig'} value={euro(s.balance)} tone={s.balance < 0 ? 'bad' : undefined} />
            {s.savings_rate !== null && <Figure label="Sparquote" value={percent(s.savings_rate)} />}
          </div>
        )}
      </section>

      <section aria-labelledby="fluss">
        <h2 id="fluss" className="mb-4 text-xl">
          Wohin das Geld fließt
        </h2>
        {empty ? (
          <p className="max-w-xl text-tinte-weich">
            Für {monthLabel(selected)} gibt es noch keine Posten. Erfasse unten deine Einnahmen und Ausgaben, dann
            erscheint hier der Geldfluss.
          </p>
        ) : (
          sankey.data && <SankeyView data={sankey.data} />
        )}
      </section>

      {!empty && s && (
        <div className="grid gap-12 lg:grid-cols-[1fr_20rem]">
          <section aria-labelledby="verlauf">
            <h2 id="verlauf" className="mb-4 text-xl">
              Verlauf über die Zeit
            </h2>
            {series.data && <SeriesView data={series.data} />}
            <p className="mt-2 max-w-xl text-sm text-tinte-weich">
              Endet ein Posten, etwa eine Kita-Gebühr, steigt der Überschuss ab diesem Monat sichtbar.
            </p>
          </section>
          <section aria-labelledby="anteile">
            <h2 id="anteile" className="mb-4 text-xl">
              Anteil an den Ausgaben
            </h2>
            <GroupBars groups={s.expense_groups} total={s.expenses} />
          </section>
        </div>
      )}

      <section aria-labelledby="posten">
        <div className="mb-2 flex items-baseline gap-4">
          <h2 id="posten" className="text-xl">
            Posten im {monthLabel(selected)}
          </h2>
          <Link to="/kategorien" className="ml-auto text-sm font-medium text-elbe-dunkel hover:underline">
            Kategorien verwalten
          </Link>
          {!adding && (
            <button type="button" onClick={() => setAdding(true)} className="bg-tinte px-4 py-2 text-sm font-medium text-karte hover:bg-elbe-dunkel">
              Posten hinzufügen
            </button>
          )}
        </div>
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
