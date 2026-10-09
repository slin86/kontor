import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'

import { cashflowApi } from '../cashflowApi'
import { ConfirmDelete } from '../components/ConfirmDelete'
import { decimalString, input, primary, secondary } from '../components/ui'
import { euro } from '../format'
import { financingApi } from '../financingApi'
import { useMonth } from '../month'
import { monthLabel } from '../monthUtils'
import { usePerson } from '../person'
import { propertyApi, USAGE_LABEL, type Property, type Usage } from '../propertyApi'

const num = (v: number) => String(v).replace('.', ',')

function ErrorLine({ error }: { error: unknown }) {
  if (!error) return null
  return (
    <p role="alert" className="text-sm font-medium text-bake">
      {error instanceof Error ? error.message : 'Das hat nicht geklappt.'}
    </p>
  )
}

function Figure({ label, value, tone }: { label: string; value: string; tone?: 'plus' | 'minus' }) {
  const color = tone === 'minus' ? 'text-bake' : tone === 'plus' ? 'text-elbe-dunkel' : ''
  return (
    <div>
      <div className={`zahl text-xl font-semibold ${color}`}>{value}</div>
      <div className="text-sm text-tinte-weich">{label}</div>
    </div>
  )
}

function useRefresh() {
  const qc = useQueryClient()
  return () => Promise.all([qc.invalidateQueries({ queryKey: ['properties'] }), qc.invalidateQueries({ queryKey: ['wealth'] })])
}

function PropertyForm({ property, onDone }: { property?: Property; onDone: () => void }) {
  const { current } = useMonth()
  const { people, me, selectedId } = usePerson()
  const refresh = useRefresh()
  const [usage, setUsage] = useState<Usage>(property?.usage ?? 'owner_occupied')
  const [owner, setOwner] = useState<number | undefined>(property?.person_id ?? selectedId ?? me?.id)
  const [ownEntered, setOwnEntered] = useState(property?.own_share_entered ?? false)
  const mutation = useMutation({
    mutationFn: (v: Parameters<typeof propertyApi.create>[0]) => (property ? propertyApi.update(property.id, v) : propertyApi.create(v)),
    onSuccess: async () => {
      await refresh()
      onDone()
    },
  })

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    mutation.mutate({
      name: String(f.get('name')).trim(),
      usage,
      person_id: owner,
      purchase_month: String(f.get('purchase_month')),
      purchase_price: decimalString(f.get('purchase_price')),
      closing_costs: decimalString(f.get('closing_costs')) || '0',
      value: decimalString(f.get('value')),
      value_as_of: String(f.get('value_as_of')),
      growth_percent: decimalString(f.get('growth_percent')) || '0',
      share_percent: decimalString(f.get('share_percent')) || '100',
      own_share_entered: ownEntered,
    })
  }

  return (
    <form onSubmit={submit} className="grid gap-4 border-t-4 border-tinte pt-5 sm:grid-cols-2 lg:grid-cols-3">
      <label className="block text-sm">
        Bezeichnung
        <input name="name" required maxLength={120} defaultValue={property?.name} placeholder="z. B. Eigentumswohnung Altona" className={input} />
      </label>
      <label className="block text-sm">
        Nutzung
        <select value={usage} onChange={(e) => setUsage(e.target.value as Usage)} className={input}>
          {Object.entries(USAGE_LABEL).map(([k, label]) => (
            <option key={k} value={k}>
              {label}
            </option>
          ))}
        </select>
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
      <label className="block text-sm">
        Kaufmonat
        <input name="purchase_month" type="month" required defaultValue={property?.purchase_month ?? current} className={input} />
      </label>
      <label className="block text-sm">
        Kaufpreis in Euro
        <input name="purchase_price" required inputMode="decimal" {...{ pattern: '[0-9.]+([,][0-9]{1,2})?' }} defaultValue={property ? num(property.purchase_price) : ''} className={input} />
      </label>
      <label className="block text-sm">
        Kaufnebenkosten in Euro
        <input name="closing_costs" inputMode="decimal" {...{ pattern: '[0-9.]+([,][0-9]{1,2})?' }} defaultValue={property ? num(property.closing_costs) : ''} className={input} />
        <span className="mt-1 block text-xs text-tinte-weich">Notar, Grunderwerbsteuer, Makler.</span>
      </label>
      <label className="block text-sm">
        Aktueller Wert in Euro
        <input name="value" required inputMode="decimal" {...{ pattern: '[0-9.]+([,][0-9]{1,2})?' }} defaultValue={property ? num(property.value) : ''} className={input} />
        <span className="mt-1 block text-xs text-tinte-weich">Deine Schätzung des Marktwerts.</span>
      </label>
      <label className="block text-sm">
        Stand des Werts
        <input name="value_as_of" type="month" required defaultValue={property?.value_as_of ?? current} className={input} />
      </label>
      <label className="block text-sm">
        Wertentwicklung pro Jahr in Prozent
        <input name="growth_percent" required inputMode="decimal" pattern="-?[0-9]+([.,][0-9]+)?" defaultValue={property ? num(property.growth_percent) : '2'} className={input} />
      </label>
      <label className="block text-sm">
        Dein Anteil in Prozent
        <input name="share_percent" required inputMode="decimal" pattern="[0-9]+([.,][0-9]+)?" defaultValue={property ? num(property.share_percent) : '100'} className={input} />
        <span className="mt-1 block text-xs text-tinte-weich">
          Bei Miteigentum nur dein Teil, zum Beispiel 50 % mit deinem Bruder. Wert, Schulden, Kosten und Miete zählen dann anteilig.
        </span>
      </label>
      <label className="flex items-start gap-2 text-sm sm:col-span-2">
        <input type="checkbox" checked={ownEntered} onChange={(e) => setOwnEntered(e.target.checked)} className="mt-1" />
        <span>
          Verknüpfte Finanzierungen und Posten enthalten schon nur meinen Anteil
          <span className="block text-xs text-tinte-weich">
            Lass das aus, wenn du den ganzen Kredit und alle Kosten des Hauses erfasst hast. Dann rechnet Kontor deinen Anteil heraus.
          </span>
        </span>
      </label>
      <div className="flex items-end gap-2">
        <button type="submit" disabled={mutation.isPending} className={primary}>
          Speichern
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

function WorkSection({ property }: { property: Property }) {
  const { current } = useMonth()
  const refresh = useRefresh()
  const [adding, setAdding] = useState(false)
  const add = useMutation({
    mutationFn: (v: Parameters<typeof propertyApi.addWork>[1]) => propertyApi.addWork(property.id, v),
    onSuccess: async () => {
      await refresh()
      setAdding(false)
    },
  })
  const remove = useMutation({ mutationFn: (id: number) => propertyApi.removeWork(property.id, id), onSuccess: refresh })

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    add.mutate({
      month: String(f.get('month')),
      name: String(f.get('name')).trim(),
      cost: decimalString(f.get('cost')),
      value_gain: decimalString(f.get('value_gain')) || '0',
    })
  }

  return (
    <div>
      <div className="flex items-baseline gap-4">
        <h4 className="text-base font-semibold">Modernisierungen und Reparaturen</h4>
        {!adding && (
          <button type="button" onClick={() => setAdding(true)} className="ml-auto text-sm font-medium text-elbe-dunkel hover:underline">
            Maßnahme hinzufügen
          </button>
        )}
      </div>
      {property.works.length === 0 && !adding && <p className="mt-2 text-sm text-tinte-weich">Noch keine Maßnahmen eingetragen.</p>}
      {property.works.length > 0 && (
        <ul className="mt-1 divide-y divide-tinte/15 text-sm">
          {property.works.map((w) => (
            <li key={w.id} className="flex flex-wrap items-baseline gap-x-4 gap-y-1 py-2">
              <span className="font-medium">{w.name}</span>
              <span className="text-tinte-weich">
                {monthLabel(w.month)}
                {w.value_gain > 0 && ` · Wertsteigerung ${euro(w.value_gain)}`}
              </span>
              <span className="zahl ml-auto">{euro(w.cost)}</span>
              <ConfirmDelete label="Löschen" question={`${w.name} löschen?`} pending={remove.isPending} error={remove.error} onConfirm={() => remove.mutate(w.id)} />
            </li>
          ))}
        </ul>
      )}
      {adding && (
        <form onSubmit={submit} className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="block text-sm">
            Was wurde gemacht?
            <input name="name" required maxLength={120} placeholder="z. B. Neues Bad" className={input} />
          </label>
          <label className="block text-sm">
            Monat
            <input name="month" type="month" required defaultValue={current} className={input} />
          </label>
          <label className="block text-sm">
            Kosten in Euro
            <input name="cost" required inputMode="decimal" pattern="[0-9.]+([,][0-9]{1,2})?" className={input} />
          </label>
          <label className="block text-sm">
            Wertsteigerung in Euro
            <input name="value_gain" inputMode="decimal" pattern="[0-9.]+([,][0-9]{1,2})?" placeholder="0" className={input} />
          </label>
          <div className="flex items-end gap-2 sm:col-span-2 lg:col-span-4">
            <button type="submit" disabled={add.isPending} className={primary}>
              Speichern
            </button>
            <button type="button" onClick={() => setAdding(false)} className={secondary}>
              Abbrechen
            </button>
            <ErrorLine error={add.error} />
          </div>
        </form>
      )}
      <p className="mt-2 max-w-2xl text-xs text-tinte-weich">
        Die Wertsteigerung zählt nur für Maßnahmen nach dem Stand des Werts oben. Ältere stecken schon in deiner Schätzung.
      </p>
    </div>
  )
}

function LinkSection({ property }: { property: Property }) {
  const { current } = useMonth()
  const refresh = useRefresh()
  const [editing, setEditing] = useState(false)
  const [fin, setFin] = useState<number[]>([])
  const [items, setItems] = useState<number[]>([])
  const financings = useQuery({ queryKey: ['financings', 'all'], queryFn: () => financingApi.list(null), enabled: editing })
  const cashflow = useQuery({ queryKey: ['cashflow', 'items', current, 'all'], queryFn: () => cashflowApi.items(current, null), enabled: editing })
  const save = useMutation({
    mutationFn: () => propertyApi.setLinks(property.id, { financing_ids: fin, item_ids: items }),
    onSuccess: async () => {
      await refresh()
      setEditing(false)
    },
  })
  const toggle = (list: number[], id: number) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id])

  function open() {
    setFin(property.financings.map((f) => f.id))
    setItems(property.items.map((i) => i.id))
    setEditing(true)
  }

  return (
    <div>
      <div className="flex items-baseline gap-4">
        <h4 className="text-base font-semibold">Finanzierung, Miete und laufende Kosten</h4>
        {!editing && (
          <button type="button" onClick={open} className="ml-auto text-sm font-medium text-elbe-dunkel hover:underline">
            Verknüpfungen ändern
          </button>
        )}
      </div>
      {!editing && property.financings.length === 0 && property.items.length === 0 && (
        <p className="mt-2 max-w-2xl text-sm text-tinte-weich">
          Verknüpfe die Finanzierung und Posten wie Miete, Hausgeld oder Grundsteuer, dann rechnet Kontor Eigenkapital, Rendite und den
          monatlichen Überschuss aus.
        </p>
      )}
      {!editing && (property.financings.length > 0 || property.items.length > 0) && (
        <ul className="mt-1 divide-y divide-tinte/15 text-sm">
          {property.financings.map((f) => (
            <li key={`f${f.id}`} className="flex flex-wrap gap-x-4 py-2">
              <span className="font-medium">{f.name}</span>
              <span className="text-tinte-weich">
                Finanzierung · Restschuld {euro(f.remaining_debt)}
                {f.repaid_percent !== null && ` · ${num(Math.round(f.repaid_percent))} % getilgt`}
                {f.remaining_debt > 0 && ` · bis ${monthLabel(f.end_month)}`}
              </span>
              <span className="zahl ml-auto text-bake">{euro(f.payment_this_month)} / Monat</span>
            </li>
          ))}
          {property.items.map((i) => (
            <li key={`i${i.id}`} className="flex flex-wrap gap-x-4 py-2">
              <span className="font-medium">{i.name}</span>
              <span className="text-tinte-weich">{i.kind === 'income' ? 'Einnahme' : 'Ausgabe'}</span>
              <span className={`zahl ml-auto ${i.kind === 'income' ? 'text-elbe-dunkel' : ''}`}>{euro(i.monthly)} / Monat</span>
            </li>
          ))}
        </ul>
      )}
      {!editing && property.share_percent < 100 && !property.own_share_entered && (property.financings.length > 0 || property.items.length > 0) && (
        <p className="mt-2 text-xs text-tinte-weich">Die Beträge in der Liste gelten für das ganze Haus. In den Kennzahlen oben zählen {num(property.share_percent)} % davon.</p>
      )}
      {editing && (
        <div className="mt-3 grid gap-6 sm:grid-cols-2">
          <fieldset>
            <legend className="text-sm font-medium">Finanzierungen</legend>
            {(financings.data ?? []).length === 0 && <p className="text-sm text-tinte-weich">Keine vorhanden.</p>}
            {(financings.data ?? []).map((f) => (
              <label key={f.id} className="mt-1 flex items-center gap-2 text-sm">
                <input type="checkbox" checked={fin.includes(f.id)} onChange={() => setFin(toggle(fin, f.id))} />
                {f.name}
              </label>
            ))}
          </fieldset>
          <fieldset>
            <legend className="text-sm font-medium">Cashflow-Posten</legend>
            {(cashflow.data ?? []).length === 0 && <p className="text-sm text-tinte-weich">Keine vorhanden.</p>}
            {(cashflow.data ?? [])
              .filter((i) => !i.incoming && i.transfer_to_id === null)
              .map((i) => (
                <label key={i.id} className="mt-1 flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={items.includes(i.id)} onChange={() => setItems(toggle(items, i.id))} />
                  {i.name} <span className="text-tinte-weich">({i.kind === 'income' ? 'Einnahme' : 'Ausgabe'})</span>
                </label>
              ))}
          </fieldset>
          <div className="flex items-center gap-2 sm:col-span-2">
            <button type="button" onClick={() => save.mutate()} disabled={save.isPending} className={primary}>
              Speichern
            </button>
            <button type="button" onClick={() => setEditing(false)} className={secondary}>
              Abbrechen
            </button>
            <ErrorLine error={save.error} />
          </div>
        </div>
      )}
    </div>
  )
}

function PropertyCard({ property: p, owner }: { property: Property; owner?: string }) {
  const refresh = useRefresh()
  const [editing, setEditing] = useState(false)
  const remove = useMutation({ mutationFn: () => propertyApi.remove(p.id), onSuccess: refresh })

  return (
    <article className="space-y-6 border-t-4 border-tinte pt-4">
      <header className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <h3 className="text-xl">{p.name}</h3>
        <span className="text-sm text-tinte-weich">
          {USAGE_LABEL[p.usage]}
          {owner && ` · ${owner}`} · gekauft {monthLabel(p.purchase_month)}
          {p.share_percent < 100 && ` · Anteil ${num(p.share_percent)} %`}
        </span>
        <button type="button" onClick={() => setEditing(!editing)} className="ml-auto text-sm font-medium text-elbe-dunkel hover:underline">
          Bearbeiten
        </button>
        <ConfirmDelete label="Löschen" question={`${p.name} löschen?`} pending={remove.isPending} error={remove.error} onConfirm={() => remove.mutate()} />
      </header>
      {editing && <PropertyForm property={p} onDone={() => setEditing(false)} />}
      <div className="flex flex-wrap gap-x-10 gap-y-4">
        <Figure label="Marktwert heute" value={euro(p.current_value)} />
        {p.share_percent < 100 && <Figure label="Dein Anteil" value={euro(p.my_value)} />}
        <Figure label="Restschuld" value={p.debt > 0 ? euro(p.debt) : '–'} tone={p.debt > 0 ? 'minus' : undefined} />
        {p.repaid_percent !== null && <Figure label={`Abbezahlt (${num(Math.round(p.repaid_percent))} %)`} value={euro(p.repaid)} tone="plus" />}
        <Figure label="Eigenkapital" value={euro(p.equity)} tone={p.equity < 0 ? 'minus' : 'plus'} />
        <Figure label="Investiert (Kauf, Nebenkosten, Maßnahmen)" value={euro(p.invested)} />
        <Figure label="Wertgewinn gesamt" value={euro(p.value_gain)} tone={p.value_gain < 0 ? 'minus' : 'plus'} />
      </div>
      {p.repaid_percent !== null && (
        <div>
          <div className="h-3 w-full max-w-xl bg-tinte/10" role="img" aria-label={`${num(Math.round(p.repaid_percent))} Prozent der Schulden abbezahlt`}>
            <div className="h-full bg-elbe" style={{ width: `${Math.min(100, p.repaid_percent)}%` }} />
          </div>
          <p className="mt-1 text-xs text-tinte-weich">
            {num(Math.round(p.repaid_percent))} % der Finanzierung{p.share_percent < 100 && !p.own_share_entered ? ' (dein Anteil)' : ''} sind abbezahlt.
          </p>
        </div>
      )}
      {(p.items.length > 0 || p.financings.length > 0) && (
        <div className="flex flex-wrap gap-x-10 gap-y-4">
          {p.usage === 'rented' && <Figure label="Einnahmen pro Monat" value={euro(p.income)} />}
          <Figure label="Laufende Kosten pro Monat" value={euro(p.costs)} />
          <Figure label="Rate der Finanzierung" value={euro(p.financing_payment)} />
          <Figure label="Bleibt im Monat" value={euro(p.net_cashflow)} tone={p.net_cashflow < 0 ? 'minus' : 'plus'} />
          {p.usage === 'rented' && p.yield_percent !== null && <Figure label="Rendite vor Finanzierung" value={`${num(p.yield_percent)} %`} />}
        </div>
      )}
      <WorkSection property={p} />
      <LinkSection property={p} />
    </article>
  )
}

export function PropertiesPage() {
  const { selectedId, people } = usePerson()
  const [adding, setAdding] = useState(false)
  const list = useQuery({ queryKey: ['properties', selectedId], queryFn: () => propertyApi.list(selectedId) })
  const names = new Map(people.map((p) => [p.id, p.name]))
  const data = list.data ?? []
  const total = data.reduce((sum, p) => sum + p.equity, 0)

  return (
    <div className="space-y-10">
      <div className="flex flex-wrap items-baseline gap-4">
        <h1 className="text-2xl">Immobilien</h1>
        {data.length > 0 && <span className="text-sm text-tinte-weich">Eigenkapital insgesamt {euro(total)}</span>}
        {!adding && (
          <button type="button" onClick={() => setAdding(true)} className="ml-auto bg-tinte px-4 py-2 text-sm font-medium text-karte hover:bg-elbe-dunkel">
            Immobilie hinzufügen
          </button>
        )}
      </div>
      {adding && <PropertyForm onDone={() => setAdding(false)} />}
      {list.isSuccess && data.length === 0 && !adding && (
        <p className="max-w-xl text-tinte-weich">
          Noch keine Immobilie. Trage selbst genutztes oder vermietetes Eigentum ein, mit Modernisierungen, Finanzierung und Mieteinnahmen.
          Der Wert fließt ins Vermögen ein.
        </p>
      )}
      {data.map((p) => (
        <PropertyCard key={p.id} property={p} owner={people.length > 1 ? names.get(p.person_id) : undefined} />
      ))}
    </div>
  )
}
