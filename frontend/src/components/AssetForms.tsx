import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'

import { useMonth } from '../month'
import { usePerson } from '../person'
import { ASSET_GROWTH, ASSET_LABEL, wealthApi, type Asset, type AssetKind } from '../wealthApi'
import { decimalString, input, primary, secondary } from './ui'

function ErrorLine({ error }: { error: unknown }) {
  if (!error) return null
  return (
    <p role="alert" className="text-sm font-medium text-bake">
      {error instanceof Error ? error.message : 'Das hat nicht geklappt.'}
    </p>
  )
}

/** Add a new asset or edit an existing one. */
export function AssetForm({ asset, onDone }: { asset?: Asset; onDone: () => void }) {
  const { current } = useMonth()
  const { people, me, selectedId } = usePerson()
  const qc = useQueryClient()
  const [kind, setKind] = useState<AssetKind>(asset?.kind ?? 'cash')
  const [growth, setGrowth] = useState(asset ? String(asset.growth_percent).replace('.', ',') : ASSET_GROWTH.cash)
  const [owner, setOwner] = useState<number | undefined>(asset?.person_id ?? selectedId ?? me?.id)
  const mutation = useMutation({
    mutationFn: (v: Parameters<typeof wealthApi.createAsset>[0]) => (asset ? wealthApi.updateAsset(asset.id, v) : wealthApi.createAsset(v)),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['wealth'] })
      onDone()
    },
  })

  function pickKind(k: AssetKind) {
    setKind(k)
    if (!asset) setGrowth(ASSET_GROWTH[k].replace('.', ','))
  }

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    mutation.mutate({
      name: String(f.get('name')).trim(),
      kind,
      value: decimalString(f.get('value')),
      as_of: String(f.get('as_of')),
      growth_percent: decimalString(growth),
      person_id: owner,
    })
  }

  return (
    <form onSubmit={submit} className="grid gap-4 border-t-4 border-tinte pt-5 sm:grid-cols-2 lg:grid-cols-3">
      <label className="block text-sm">
        Bezeichnung
        <input name="name" required maxLength={120} defaultValue={asset?.name} placeholder="z. B. Tagesgeld oder Eigentumswohnung" className={input} />
      </label>
      <label className="block text-sm">
        Art
        <select value={kind} onChange={(e) => pickKind(e.target.value as AssetKind)} className={input}>
          {Object.entries(ASSET_LABEL)
            .filter(([k]) => k !== 'property' || asset?.kind === 'property')
            .map(([k, label]) => (
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
        Wert in Euro
        <input name="value" required inputMode="decimal" pattern="[0-9.]+([,][0-9]{1,2})?" defaultValue={asset ? String(asset.value).replace('.', ',') : ''} className={input} />
      </label>
      <label className="block text-sm">
        Stand
        <input name="as_of" type="month" required defaultValue={asset?.as_of ?? current} className={input} />
      </label>
      <label className="block text-sm">
        Wertentwicklung pro Jahr in Prozent
        <input value={growth} onChange={(e) => setGrowth(e.target.value)} required inputMode="decimal" pattern="-?[0-9]+([.,][0-9]+)?" className={input} />
        <span className="mt-1 block text-xs text-tinte-weich">Negativ für Wertverlust, etwa bei einem Auto.</span>
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
