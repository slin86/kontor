import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { CostCompare } from '../components/CostCompare'
import { decimalString, input, primary, secondary } from '../components/ui'
import {
  catalogApi,
  DISTRIBUTION_LABEL,
  REPLICATION_LABEL,
  type CatalogEntry,
  type SearchParams,
} from '../catalogApi'
import { KIND_LABEL, type InstrumentKind } from '../depotApi'
import { euro } from '../format'

const pct = (n: number) => `${n.toFixed(2).replace('.', ',')} %`
const MAX_COMPARE = 6

function NewEntryForm({ onDone }: { onDone: () => void }) {
  const qc = useQueryClient()
  const [kind, setKind] = useState<InstrumentKind>('private_equity')
  const mutation = useMutation({
    mutationFn: catalogApi.create,
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['catalog'] })
      onDone()
    },
  })
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    const text = (k: string) => String(f.get(k) ?? '').trim()
    mutation.mutate({
      kind,
      name: text('name'),
      isin: text('isin') || null,
      index_name: text('index_name') || null,
      ter_percent: decimalString(f.get('ter_percent')),
      distribution: text('distribution') || null,
    })
  }
  return (
    <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
      <label className="block text-sm">
        Art
        <select value={kind} onChange={(e) => setKind(e.target.value as InstrumentKind)} className={input}>
          {(Object.keys(KIND_LABEL) as InstrumentKind[]).map((k) => (
            <option key={k} value={k}>
              {KIND_LABEL[k]}
            </option>
          ))}
        </select>
      </label>
      <label className="block text-sm">
        Bezeichnung
        <input name="name" required maxLength={160} className={input} />
      </label>
      <label className="block text-sm">
        ISIN
        <input name="isin" maxLength={12} pattern="[A-Za-z]{2}[A-Za-z0-9]{9}[0-9]" className={input} />
      </label>
      <label className="block text-sm">
        Index oder Strategie
        <input name="index_name" maxLength={80} className={input} />
      </label>
      <label className="block text-sm">
        Laufende Kosten (TER) in Prozent pro Jahr
        <input name="ter_percent" required inputMode="decimal" pattern="[0-9]+([.,][0-9]+)?" className={input} />
      </label>
      <label className="block text-sm">
        Ertragsverwendung
        <select name="distribution" defaultValue="" className={input}>
          <option value="">Unbekannt</option>
          <option value="accumulating">Thesaurierend</option>
          <option value="distributing">Ausschüttend</option>
        </select>
      </label>
      <div className="flex gap-2 sm:col-span-2">
        <button type="submit" disabled={mutation.isPending} className={primary}>
          Eintrag speichern
        </button>
        <button type="button" onClick={onDone} className={secondary}>
          Abbrechen
        </button>
      </div>
      {mutation.error && (
        <p role="alert" className="text-sm font-medium text-bake sm:col-span-2">
          {mutation.error.message}
        </p>
      )}
    </form>
  )
}

export function InstrumentsPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [filters, setFilters] = useState<SearchParams>({
    q: '',
    index: params.get('index') ?? '',
    distribution: '',
    replication: '',
    maxTer: '',
    sort: 'size',
    kind: '',
  })
  const [chosen, setChosen] = useState<CatalogEntry[]>([])
  const [adding, setAdding] = useState(false)
  const set = <K extends keyof SearchParams>(key: K, value: SearchParams[K]) => setFilters((f) => ({ ...f, [key]: value }))

  const result = useQuery({ queryKey: ['catalog', 'search', filters], queryFn: () => catalogApi.search(filters) })
  // a comparison started from a position: preselect its catalog entry once, by ISIN
  const preselectIsin = params.get('compare') ?? ''
  const applied = useRef(false)
  const preselected = useQuery({
    queryKey: ['catalog', 'preselect', preselectIsin],
    queryFn: () => catalogApi.search({ q: preselectIsin, index: '', distribution: '', replication: '', maxTer: '', sort: 'size', kind: '' }),
    enabled: preselectIsin !== '',
    select: (r) => r.items.find((e) => e.isin === preselectIsin.toUpperCase()),
  })
  useEffect(() => {
    const entry = preselected.data
    if (entry && !applied.current) {
      applied.current = true
      setChosen((c) => [entry, ...c.filter((x) => x.id !== entry.id)])
    }
  }, [preselected.data])
  const entries = chosen

  const remove = useMutation({
    mutationFn: catalogApi.remove,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['catalog'] }),
  })

  const facets = result.data?.facets
  const isChosen = (e: CatalogEntry) => entries.some((c) => c.id === e.id)
  const toggle = (e: CatalogEntry) => {
    if (isChosen(e)) {
      setChosen(entries.filter((c) => c.id !== e.id))
    } else if (entries.length < MAX_COMPARE) {
      setChosen([...entries, e])
    }
  }

  return (
    <div className="space-y-10">
      <h1 className="sr-only">Instrumente</h1>
      {preselectIsin && (
        <Link to="/depot" className="inline-block text-sm font-medium text-elbe-dunkel hover:underline">
          ← Zurück zum Depot
        </Link>
      )}

      <section aria-labelledby="suche">
        <h2 id="suche" className="text-xl">
          Fonds suchen
        </h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <label className="block text-sm sm:col-span-2 lg:col-span-4">
            Name, ISIN oder Index
            <input
              type="search"
              value={filters.q}
              onChange={(e) => set('q', e.target.value)}
              placeholder="z. B. MSCI World oder IE00B4L5Y983"
              className={input}
            />
          </label>
          <label className="block text-sm">
            Index
            <select value={filters.index} onChange={(e) => set('index', e.target.value)} className={input}>
              <option value="">Alle</option>
              {facets?.indexes.map((i) => (
                <option key={i} value={i}>
                  {i}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            Ertragsverwendung
            <select value={filters.distribution} onChange={(e) => set('distribution', e.target.value)} className={input}>
              <option value="">Alle</option>
              {facets?.distributions.map((d) => (
                <option key={d} value={d}>
                  {DISTRIBUTION_LABEL[d] ?? d}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            Replikation
            <select value={filters.replication} onChange={(e) => set('replication', e.target.value)} className={input}>
              <option value="">Alle</option>
              {facets?.replications.map((r) => (
                <option key={r} value={r}>
                  {REPLICATION_LABEL[r] ?? r}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            Höchstens TER in Prozent
            <input
              inputMode="decimal"
              value={filters.maxTer}
              onChange={(e) => set('maxTer', e.target.value.replace(',', '.').replace(/[^0-9.]/g, ''))}
              className={input}
            />
          </label>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
          <label>
            Sortieren nach{' '}
            <select value={filters.sort} onChange={(e) => set('sort', e.target.value as SearchParams['sort'])} className="border border-tinte/30 bg-feld/60 px-2 py-1">
              <option value="size">Fondsgröße</option>
              <option value="ter">Kosten (TER)</option>
              <option value="name">Name</option>
            </select>
          </label>
          <span className="text-tinte-weich" aria-live="polite">
            {result.data ? `${result.data.total} Treffer` : ''}
          </span>
          {!adding && (
            <button type="button" onClick={() => setAdding(true)} className="ml-auto font-medium text-elbe-dunkel hover:underline">
              Eigenen Eintrag anlegen
            </button>
          )}
        </div>
        {adding && (
          <div className="mt-6">
            <NewEntryForm onDone={() => setAdding(false)} />
          </div>
        )}
      </section>

      {entries.length > 0 && <CostCompare selected={entries} onRemove={(id) => setChosen(entries.filter((e) => e.id !== id))} />}

      <section aria-label="Suchergebnisse">
        {result.data?.items.length === 0 && (
          <p className="max-w-xl text-tinte-weich">
            Nichts gefunden. Lockere die Filter, oder lege den Fonds als eigenen Eintrag an. Das geht auch für Private Equity.
          </p>
        )}
        <ul className="divide-y divide-tinte/15">
          {result.data?.items.map((e) => (
            <li key={e.id} className="py-3">
              <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
                <label className="flex items-baseline gap-3">
                  <input
                    type="checkbox"
                    checked={isChosen(e)}
                    disabled={!isChosen(e) && entries.length >= MAX_COMPARE}
                    onChange={() => toggle(e)}
                    aria-label={`${e.name} vergleichen`}
                  />
                  <span className="font-medium">{e.name}</span>
                </label>
                <span className="zahl ml-auto font-medium">
                  {pct(e.ter_percent)}
                  <span className="text-sm font-normal text-tinte-weich"> TER</span>
                </span>
              </div>
              <div className="ml-7 mt-1 flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm text-tinte-weich">
                <span>{[e.isin, KIND_LABEL[e.kind], e.index_name].filter(Boolean).join(' · ')}</span>
                <span>
                  {[
                    e.distribution && (DISTRIBUTION_LABEL[e.distribution] ?? e.distribution),
                    e.replication && (REPLICATION_LABEL[e.replication] ?? e.replication),
                    e.domicile,
                    e.fund_size_m_eur !== null && `${euro(e.fund_size_m_eur)} Mio. Fondsvolumen`,
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
                <button
                  type="button"
                  className="ml-auto font-medium text-elbe-dunkel hover:underline"
                  onClick={() =>
                    navigate('/depot', {
                      state: {
                        prefill: { kind: e.kind, name: e.name, isin: e.isin, cost_percent: e.ter_percent },
                      },
                    })
                  }
                >
                  In den Depotplan übernehmen
                </button>
                {!e.builtin && (
                  <button type="button" className="font-medium text-bake hover:underline" onClick={() => remove.mutate(e.id)}>
                    Eintrag löschen
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
        <p className="mt-6 max-w-2xl text-sm text-tinte-weich">
          Die Fondsdaten stammen aus den Vergleichstabellen von justETF (Stand {result.data?.items.find((e) => e.builtin)?.as_of ?? '2026-10'}).
          Kosten und Fondsvolumen ändern sich, prüfe sie vor einem Kauf beim Anbieter. Eigene Einträge sieht nur dein Haushalt.
        </p>
      </section>
    </div>
  )
}
