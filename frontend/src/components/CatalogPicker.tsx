import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { catalogApi, type CatalogEntry } from '../catalogApi'
import { input } from './ui'

const MAX_HITS = 8

/** Search box for the instrument catalog: name, ISIN or index. Calls ``onPick`` for the chosen entry. */
export function CatalogPicker({ onPick }: { onPick: (entry: CatalogEntry) => void }) {
  const [text, setText] = useState('')
  const [term, setTerm] = useState('')

  // wait for a short pause in typing before asking the server
  useEffect(() => {
    const id = setTimeout(() => setTerm(text.trim()), 250)
    return () => clearTimeout(id)
  }, [text])

  const search = useQuery({
    queryKey: ['catalog', 'picker', term],
    queryFn: () => catalogApi.search({ q: term, index: '', distribution: '', replication: '', maxTer: '', sort: 'size', kind: '' }, MAX_HITS),
    enabled: term.length >= 2,
  })
  const hits = search.data?.items ?? []

  return (
    <div className="sm:col-span-2">
      <label className="block text-sm">
        Instrument suchen
        <input
          type="search"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Name, ISIN oder Index, zum Beispiel MSCI World"
          autoComplete="off"
          className={input}
        />
        <span className="mt-1 block text-xs text-tinte-weich">
          Ein Treffer füllt Bezeichnung, ISIN, Art und laufende Kosten aus. Du kannst alles danach noch ändern.
        </span>
      </label>
      {term.length >= 2 && search.data && hits.length === 0 && (
        <p className="mt-2 text-sm text-tinte-weich">
          Nichts gefunden. Du kannst die Position unten von Hand eintragen oder das Instrument unter „Instrumente" im Katalog anlegen.
        </p>
      )}
      {hits.length > 0 && (
        <ul className="mt-2 divide-y divide-tinte/15 border border-tinte/20 bg-white/60">
          {hits.map((e) => (
            <li key={e.id}>
              <button
                type="button"
                onClick={() => {
                  onPick(e)
                  setText('')
                  setTerm('')
                }}
                className="flex w-full flex-wrap items-baseline gap-x-3 px-3 py-2 text-left text-sm hover:bg-karte-tief"
              >
                <span className="font-medium">{e.name}</span>
                <span className="text-tinte-weich">{[e.isin, e.index_name].filter(Boolean).join(' · ')}</span>
                <span className="zahl ml-auto">{String(e.ter_percent).replace('.', ',')} % TER</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
