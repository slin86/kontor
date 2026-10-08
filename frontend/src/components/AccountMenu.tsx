import { useQuery } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '../api'
import { useAuth } from '../auth'
import { useTheme } from '../theme'
import { WEB_VERSION } from '../version'

const THEME_LABEL = { auto: 'Automatisch', light: 'Hell', dark: 'Dunkel' } as const

const item = 'block w-full px-4 py-2 text-left text-sm hover:bg-tinte/10 focus-visible:bg-tinte/10'

/** The user's name in the header; hovering or focusing it opens the personal menu. */
export function AccountMenu() {
  const { me, logout } = useAuth()
  const theme = useTheme()
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const server = useQuery({
    queryKey: ['version'],
    queryFn: () => api<{ version: string }>('/health'),
    enabled: open,
    staleTime: Infinity,
  })

  return (
    <div
      ref={root}
      className="relative"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onBlur={(e) => {
        if (!root.current?.contains(e.relatedTarget as Node | null)) setOpen(false)
      }}
      onKeyDown={(e) => {
        if (e.key === 'Escape') setOpen(false)
      }}
    >
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="font-medium text-tinte hover:text-elbe-dunkel"
      >
        {me?.user.display_name} <span aria-hidden>▾</span>
      </button>
      {open && (
        <div role="menu" className="absolute right-0 top-full z-20 w-60 border border-tinte/20 bg-karte shadow-lg">
          <Link role="menuitem" to="/konto" onClick={() => setOpen(false)} className={item}>
            Mein Konto
          </Link>
          <Link role="menuitem" to="/haushalt" onClick={() => setOpen(false)} className={item}>
            Haushalt und Personen
          </Link>
          <button role="menuitem" type="button" onClick={theme.cycle} className={item}>
            Darstellung: {THEME_LABEL[theme.mode]}
          </button>
          <button role="menuitem" type="button" onClick={() => void logout()} className={`${item} font-medium text-elbe-dunkel`}>
            Abmelden
          </button>
          <p className="border-t border-tinte/15 px-4 py-2 text-xs text-tinte-weich">
            Version {WEB_VERSION}
            {server.data && server.data.version !== WEB_VERSION && ` · Server ${server.data.version}`}
          </p>
        </div>
      )}
    </div>
  )
}
