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
      <Link
        to="/haushalt"
        aria-label="Personen verwalten"
        title="Personen verwalten"
        className="ml-auto text-tinte-weich hover:text-tinte"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M12 20h9" />
          <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
        </svg>
      </Link>
    </div>
  )
}
