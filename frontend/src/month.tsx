import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'

import { monthKeyOf, type MonthKey } from './monthUtils'

interface MonthState {
  current: MonthKey // the real current month; everything before it is locked history
  selected: MonthKey
  setSelected: (m: MonthKey) => void
  isLocked: (m: MonthKey) => boolean
}

const MonthContext = createContext<MonthState | null>(null)

export function MonthProvider({ children }: { children: ReactNode }) {
  const [current] = useState<MonthKey>(() => monthKeyOf(new Date()))
  const [selected, setSelected] = useState<MonthKey>(current)
  const value = useMemo<MonthState>(
    () => ({ current, selected, setSelected, isLocked: (m) => m < current }),
    [current, selected],
  )
  return <MonthContext.Provider value={value}>{children}</MonthContext.Provider>
}

export function useMonth(): MonthState {
  const ctx = useContext(MonthContext)
  if (!ctx) throw new Error('useMonth must be used inside MonthProvider')
  return ctx
}
