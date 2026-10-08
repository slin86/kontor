import { Link } from 'react-router-dom'

import { usePerson } from '../person'

/** Chooses whose depot a page shows. Hidden while the household has only one person. */
export function PersonSwitcher() {
  const { people, selectedId, setSelected } = usePerson()
  if (people.length < 2) {
    return (
      <p className="text-sm text-tinte-weich">
        Für Kinder oder weitere Personen mit eigenem Depot:{' '}
        <Link to="/haushalt" className="font-medium text-elbe-dunkel hover:underline">
          Person im Haushalt anlegen
        </Link>
      </p>
    )
  }
  const tabs: { id: number | null; label: string }[] = [
    ...people.map((p) => ({ id: p.id, label: p.name })),
    { id: null, label: 'Alle zusammen' },
  ]
  return (
    <div className="flex flex-wrap items-baseline gap-x-5 gap-y-2" role="group" aria-label="Person wählen">
      {tabs.map((t) => (
        <button
          key={t.id ?? 'all'}
          type="button"
          aria-pressed={selectedId === t.id}
          onClick={() => setSelected(t.id)}
          className={`border-b-2 pb-0.5 text-base font-medium ${
            selectedId === t.id ? 'border-elbe text-tinte' : 'border-transparent text-tinte-weich hover:text-tinte'
          }`}
        >
          {t.label}
        </button>
      ))}
      <Link to="/haushalt" className="ml-auto text-sm font-medium text-elbe-dunkel hover:underline">
        Personen verwalten
      </Link>
    </div>
  )
}
