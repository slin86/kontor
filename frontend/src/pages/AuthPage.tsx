import { useQuery } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Navigate } from 'react-router-dom'

import { api } from '../api'
import { useAuth } from '../auth'

type Mode = 'login' | 'new-household' | 'join'

const field =
  'mt-1 w-full border border-tinte/30 bg-feld/60 px-3 py-2 text-base focus:border-elbe focus:bg-feld'

export function AuthPage() {
  const { me, loading, login, register } = useAuth()
  const [mode, setMode] = useState<Mode>('login')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // the server may only accept invite codes (after the first household exists)
  const config = useQuery({ queryKey: ['auth', 'config'], queryFn: () => api<{ new_households_allowed: boolean }>('/auth/config') })
  const newAllowed = config.data?.new_households_allowed ?? true

  if (loading) return null
  if (me) return <Navigate to="/" replace />

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    const get = (k: string) => String(f.get(k) ?? '').trim()
    setBusy(true)
    setError(null)
    try {
      if (mode === 'login') {
        await login(get('email'), String(f.get('password') ?? ''))
      } else {
        await register({
          email: get('email'),
          password: String(f.get('password') ?? ''),
          display_name: get('display_name'),
          ...(mode === 'new-household' ? { household_name: get('household_name') } : { invite_code: get('invite_code') }),
        })
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Das hat nicht geklappt. Bitte versuche es erneut.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto grid min-h-screen max-w-5xl content-center gap-12 px-6 py-12 md:grid-cols-[1fr_22rem]">
      <div className="self-center">
        <h1 className="font-display text-6xl font-bold tracking-tight sm:text-7xl">Kontor</h1>
        <p className="mt-6 max-w-md text-lg text-tinte-weich">
          Wohin fließt das Geld des Haushalts, und was bleibt in zehn Jahren übrig? Kontor rechnet es aus, Monat für
          Monat.
        </p>
      </div>

      <form onSubmit={onSubmit} className="border-t-4 border-tinte pt-6" aria-label={mode === 'login' ? 'Anmelden' : 'Registrieren'}>
        <div className="mb-6 flex gap-4 text-sm font-medium">
          {(
            [
              ['login', 'Anmelden'],
              ...(newAllowed ? [['new-household', 'Neuer Haushalt']] : []),
              ['join', 'Haushalt beitreten'],
            ] as [Mode, string][]
          ).map(([m, label]) => (
            <button
              key={m}
              type="button"
              onClick={() => {
                setMode(m)
                setError(null)
              }}
              className={`border-b-2 pb-0.5 ${mode === m ? 'border-elbe' : 'border-transparent text-tinte-weich'}`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="space-y-4">
          {mode !== 'login' && (
            <label className="block text-sm">
              Dein Name
              <input name="display_name" required maxLength={80} autoComplete="name" className={field} />
            </label>
          )}
          {mode === 'new-household' && (
            <label className="block text-sm">
              Name des Haushalts
              <input name="household_name" required maxLength={120} className={field} />
            </label>
          )}
          {mode === 'join' && (
            <label className="block text-sm">
              Einladungscode
              <input name="invite_code" required autoComplete="off" className={field} />
            </label>
          )}
          <label className="block text-sm">
            E-Mail
            <input name="email" type="email" required autoComplete="email" className={field} />
          </label>
          <label className="block text-sm">
            Passwort{mode !== 'login' && ' (mindestens 10 Zeichen)'}
            <input
              name="password"
              type="password"
              required
              minLength={mode === 'login' ? undefined : 10}
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              className={field}
            />
          </label>
        </div>

        {error && (
          <p role="alert" className="mt-4 text-sm font-medium text-bake">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={busy}
          className="mt-6 w-full bg-tinte px-4 py-2.5 font-medium text-karte hover:bg-elbe-dunkel disabled:opacity-60"
        >
          {mode === 'login' ? 'Anmelden' : 'Konto anlegen'}
        </button>
      </form>
    </div>
  )
}
