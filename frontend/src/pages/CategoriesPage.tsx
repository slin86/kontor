import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { cashflowApi, type Category, type Kind } from '../cashflowApi'
import { ErrorLine } from '../components/ErrorLine'
import { input, primary, secondary } from '../components/ui'

const KIND_TITLE: Record<Kind, string> = { expense: 'Ausgaben', income: 'Einnahmen' }

function useCategoryMutation<V, R>(fn: (v: V) => Promise<R>, onDone?: () => void) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['cashflow'] })
      onDone?.()
    },
  })
}

function EditRow({ cat, groups, onDone }: { cat: Category; groups: Category[]; onDone: () => void }) {
  const mutation = useCategoryMutation(
    (v: { name: string; parent_id: number | null }) => cashflowApi.updateCategory(cat.id, v),
    onDone,
  )
  // a group that has sub-categories cannot move below another group
  const hasChildren = groups.some((g) => g.parent_id === cat.id)
  const targets = groups.filter((g) => g.parent_id === null && g.kind === cat.kind && g.id !== cat.id)

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    const parent = String(f.get('parent') ?? '')
    mutation.mutate({ name: String(f.get('name') ?? '').trim(), parent_id: parent ? Number(parent) : null })
  }

  return (
    <form onSubmit={submit} className="mt-3 grid gap-3 sm:grid-cols-[1fr_1fr_auto]">
      <label className="block text-sm">
        Name
        <input name="name" required defaultValue={cat.name} maxLength={80} className={input} />
      </label>
      <label className="block text-sm">
        Liegt unter
        <select name="parent" defaultValue={cat.parent_id ?? ''} disabled={hasChildren} className={input}>
          <option value="">Oberste Ebene</option>
          {targets.map((g) => (
            <option key={g.id} value={g.id}>
              {g.name}
            </option>
          ))}
        </select>
      </label>
      <div className="flex items-end gap-2">
        <button type="submit" disabled={mutation.isPending} className={primary}>
          Speichern
        </button>
        <button type="button" onClick={onDone} className={secondary}>
          Abbrechen
        </button>
      </div>
      <div className="sm:col-span-3">
        <ErrorLine error={mutation.error} />
      </div>
    </form>
  )
}

function DeleteRow({ cat, all, onDone }: { cat: Category; all: Category[]; onDone: () => void }) {
  const [target, setTarget] = useState('')
  const mutation = useCategoryMutation(() => cashflowApi.deleteCategory(cat.id, target ? Number(target) : null), onDone)
  const hasChildren = all.some((c) => c.parent_id === cat.id)
  const options = all.filter((c) => c.kind === cat.kind && c.id !== cat.id)
  const needsTarget = cat.item_count > 0

  if (hasChildren) {
    return (
      <p className="mt-3 text-sm">
        „{cat.name}“ hat noch Unterkategorien. Verschiebe oder lösche sie zuerst.{' '}
        <button type="button" onClick={onDone} className={secondary}>
          Verstanden
        </button>
      </p>
    )
  }
  return (
    <div className="mt-3 space-y-3 text-sm">
      <p className="font-medium">
        „{cat.name}“ löschen?
        {needsTarget && ` ${cat.item_count} ${cat.item_count === 1 ? 'Posten hängt' : 'Posten hängen'} daran und ${cat.item_count === 1 ? 'zieht' : 'ziehen'} um.`}
      </p>
      {needsTarget && (
        <label className="block max-w-xs">
          Posten übernimmt
          <select value={target} onChange={(e) => setTarget(e.target.value)} className={input}>
            <option value="">Bitte wählen</option>
            {options.map((c) => (
              <option key={c.id} value={c.id}>
                {c.parent_id ? `${all.find((p) => p.id === c.parent_id)?.name} / ` : ''}
                {c.name}
              </option>
            ))}
          </select>
        </label>
      )}
      <div className="flex gap-4">
        <button
          type="button"
          disabled={mutation.isPending || (needsTarget && !target)}
          onClick={() => mutation.mutate(undefined)}
          className="font-medium text-bake hover:underline disabled:opacity-50"
        >
          Ja, löschen
        </button>
        <button type="button" onClick={onDone} className="font-medium text-elbe-dunkel hover:underline">
          Abbrechen
        </button>
      </div>
      <ErrorLine error={mutation.error} />
    </div>
  )
}

function Row({ cat, siblings, all }: { cat: Category; siblings: Category[]; all: Category[] }) {
  const [mode, setMode] = useState<'view' | 'edit' | 'delete'>('view')
  const index = siblings.findIndex((c) => c.id === cat.id)
  const move = useCategoryMutation((direction: 'up' | 'down') => cashflowApi.moveCategory(cat.id, direction))

  return (
    <li className="py-3">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <span className={cat.parent_id ? 'pl-6' : 'font-medium'}>{cat.name}</span>
        <span className="text-sm text-tinte-weich">{cat.item_count > 0 ? `${cat.item_count} Posten` : 'leer'}</span>
        <span className="ml-auto flex gap-4 text-sm font-medium text-elbe-dunkel">
          <button type="button" aria-label={`${cat.name} nach oben`} disabled={index === 0 || move.isPending} onClick={() => move.mutate('up')} className="hover:underline disabled:opacity-30">
            Hoch
          </button>
          <button type="button" aria-label={`${cat.name} nach unten`} disabled={index === siblings.length - 1 || move.isPending} onClick={() => move.mutate('down')} className="hover:underline disabled:opacity-30">
            Runter
          </button>
          <button type="button" onClick={() => setMode(mode === 'edit' ? 'view' : 'edit')} className="hover:underline">
            Bearbeiten
          </button>
          <button type="button" onClick={() => setMode(mode === 'delete' ? 'view' : 'delete')} className="text-bake hover:underline">
            Löschen
          </button>
        </span>
      </div>
      {mode === 'edit' && <EditRow cat={cat} groups={all} onDone={() => setMode('view')} />}
      {mode === 'delete' && <DeleteRow cat={cat} all={all} onDone={() => setMode('view')} />}
    </li>
  )
}

function NewCategory({ all }: { all: Category[] }) {
  const [kind, setKind] = useState<Kind>('expense')
  const mutation = useCategoryMutation((v: { name: string; kind: Kind; parent_id: number | null }) => cashflowApi.createCategory(v))
  const groups = all.filter((c) => c.parent_id === null && c.kind === kind)

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = e.currentTarget
    const f = new FormData(form)
    const parent = String(f.get('parent') ?? '')
    mutation.mutate(
      { name: String(f.get('name') ?? '').trim(), kind, parent_id: parent ? Number(parent) : null },
      { onSuccess: () => form.reset() },
    )
  }

  return (
    <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
      <fieldset className="sm:col-span-2">
        <legend className="text-sm">Art</legend>
        <div className="mt-1 flex gap-2">
          {(Object.keys(KIND_TITLE) as Kind[]).map((k) => (
            <button
              key={k}
              type="button"
              aria-pressed={kind === k}
              onClick={() => setKind(k)}
              className={`px-4 py-2 text-sm font-medium ${kind === k ? 'bg-tinte text-karte' : 'border border-tinte/30 hover:bg-white/60'}`}
            >
              {KIND_TITLE[k]}
            </button>
          ))}
        </div>
      </fieldset>
      <label className="block text-sm">
        Name
        <input name="name" required maxLength={80} className={input} />
      </label>
      <label className="block text-sm">
        Liegt unter
        <select key={kind} name="parent" className={input}>
          <option value="">Oberste Ebene</option>
          {groups.map((g) => (
            <option key={g.id} value={g.id}>
              {g.name}
            </option>
          ))}
        </select>
      </label>
      <div className="sm:col-span-2">
        <button type="submit" disabled={mutation.isPending} className={primary}>
          Kategorie anlegen
        </button>
      </div>
      <div className="sm:col-span-2">
        <ErrorLine error={mutation.error} />
      </div>
    </form>
  )
}

export function CategoriesPage() {
  const categories = useQuery({ queryKey: ['cashflow', 'categories'], queryFn: cashflowApi.categories })
  const all = categories.data ?? []

  return (
    <div className="space-y-12">
      <div>
        <h1 className="text-2xl">Kategorien</h1>
        <p className="mt-2 max-w-xl text-sm text-tinte-weich">
          Posten gehören zu einer Kategorie, das Sankey-Diagramm gruppiert danach. Es gibt zwei Ebenen: Gruppen und
          Unterkategorien. Umbenennen und Umsortieren ändert keine Beträge. Wer eine Kategorie löscht, bestimmt, wohin ihre Posten
          wandern.
        </p>
        <Link to="/" className="mt-2 inline-block text-sm font-medium text-elbe-dunkel hover:underline">
          Zurück zum Cashflow
        </Link>
      </div>

      {(['expense', 'income'] as Kind[]).map((kind) => {
        const tops = all.filter((c) => c.parent_id === null && c.kind === kind)
        return (
          <section key={kind} aria-labelledby={`k-${kind}`}>
            <h2 id={`k-${kind}`} className="text-xl">
              {KIND_TITLE[kind]}
            </h2>
            <ul className="mt-2 divide-y divide-tinte/15">
              {tops.flatMap((top) => {
                const children = all.filter((c) => c.parent_id === top.id)
                return [
                  <Row key={top.id} cat={top} siblings={tops} all={all} />,
                  ...children.map((c) => <Row key={c.id} cat={c} siblings={children} all={all} />),
                ]
              })}
            </ul>
          </section>
        )
      })}

      <section aria-labelledby="neu">
        <h2 id="neu" className="mb-4 text-xl">
          Neue Kategorie
        </h2>
        <NewCategory all={all} />
      </section>
    </div>
  )
}
