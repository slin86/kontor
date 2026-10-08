import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

export type ThemeMode = 'auto' | 'light' | 'dark'

const STORAGE_KEY = 'kontor.theme'
const MODES: ThemeMode[] = ['auto', 'light', 'dark']

interface ThemeState {
  mode: ThemeMode
  dark: boolean
  cycle: () => void
}

const ThemeContext = createContext<ThemeState | null>(null)

function readMode(): ThemeMode {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    return v === 'light' || v === 'dark' ? v : 'auto'
  } catch {
    return 'auto' // blocked storage: follow the system
  }
}

const systemQuery = () => window.matchMedia('(prefers-color-scheme: dark)')

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<ThemeMode>(readMode)
  const [system, setSystem] = useState(() => systemQuery().matches)

  useEffect(() => {
    const query = systemQuery()
    const onChange = () => setSystem(query.matches)
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])

  const dark = mode === 'dark' || (mode === 'auto' && system)
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? 'dark' : 'light'
  }, [dark])

  const cycle = useCallback(() => {
    const next = MODES[(MODES.indexOf(mode) + 1) % MODES.length]
    setMode(next)
    try {
      if (next === 'auto') localStorage.removeItem(STORAGE_KEY)
      else localStorage.setItem(STORAGE_KEY, next)
    } catch {
      /* not remembered */
    }
  }, [mode])

  const value = useMemo(() => ({ mode, dark, cycle }), [mode, dark, cycle])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeState {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used inside ThemeProvider')
  return ctx
}
