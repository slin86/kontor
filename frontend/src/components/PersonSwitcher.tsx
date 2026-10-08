import { usePerson } from '../person'

/** Two letters only when the first letters of two names collide. */
function initials(names: string[]): string[] {
  return names.map((name) => {
    const first = name.trim().charAt(0).toUpperCase()
    const clash = names.filter((n) => n.trim().charAt(0).toUpperCase() === first).length > 1
    return clash ? name.trim().slice(0, 2) : first
  })
}

const chip =
  'flex h-9 min-w-9 items-center justify-center rounded-full px-2 text-sm font-semibold transition-colors focus-visible:outline-offset-2'

/**
 * Chooses whose books a page shows: one chip per person plus one for everyone together.
 * Only there when the household has more than one person.
 */
export function PersonSwitcher() {
  const { people, selectedId, setSelected } = usePerson()
  if (people.length < 2) return null
  const letters = initials(people.map((p) => p.name))
  return (
    <div className="flex items-center gap-1.5" role="group" aria-label="Person wählen">
      {people.map((p, i) => (
        <button
          key={p.id}
          type="button"
          title={p.name}
          aria-label={p.name}
          aria-pressed={selectedId === p.id}
          onClick={() => setSelected(p.id)}
          className={`${chip} ${selectedId === p.id ? 'bg-tinte text-karte' : 'border border-tinte/30 text-tinte-weich hover:border-tinte hover:text-tinte'}`}
        >
          {letters[i]}
        </button>
      ))}
      <button
        type="button"
        title="Alle zusammen"
        aria-label="Alle zusammen"
        aria-pressed={selectedId === null}
        onClick={() => setSelected(null)}
        className={`${chip} ${selectedId === null ? 'bg-tinte text-karte' : 'border border-tinte/30 text-tinte-weich hover:border-tinte hover:text-tinte'}`}
      >
        Alle
      </button>
    </div>
  )
}
