import { useQuery } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'

import { peopleApi, type Person } from './peopleApi'

const STORAGE_KEY = 'kontor.person'

interface PersonState {
  people: Person[]
  me: Person | undefined
  /** The person whose depot is shown; ``null`` means everyone together. */
  selectedId: number | null
  selected: Person | undefined
  setSelected: (id: number | null) => void
}

const PersonContext = createContext<PersonState | null>(null)

function readStored(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null // private window or blocked storage: the choice just is not remembered
  }
}

export function PersonProvider({ children }: { children: ReactNode }) {
  const query = useQuery({ queryKey: ['people'], queryFn: peopleApi.list })
  const people = useMemo(() => query.data ?? [], [query.data])
  const me = people.find((p) => p.is_me)
  const [choice, setChoice] = useState<string | null>(readStored)

  const setSelected = useCallback((id: number | null) => {
    const value = id === null ? 'all' : String(id)
    setChoice(value)
    try {
      localStorage.setItem(STORAGE_KEY, value)
    } catch {
      /* not remembered */
    }
  }, [])

  const value = useMemo<PersonState>(() => {
    // fall back to the own person when the remembered one no longer exists
    const wanted = choice === 'all' && people.length > 1 ? null : Number(choice)
    const known = wanted === null || people.some((p) => p.id === wanted)
    const selectedId = wanted === null ? null : known ? wanted : (me?.id ?? null)
    return {
      people,
      me,
      selectedId,
      selected: people.find((p) => p.id === selectedId),
      setSelected,
    }
  }, [choice, people, me, setSelected])

  return <PersonContext.Provider value={value}>{children}</PersonContext.Provider>
}

export function usePerson(): PersonState {
  const ctx = useContext(PersonContext)
  if (!ctx) throw new Error('usePerson must be used inside PersonProvider')
  return ctx
}
