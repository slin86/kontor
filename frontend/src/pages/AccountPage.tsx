import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'

import { ErrorLine } from '../components/ErrorLine'
import { input, primary } from '../components/ui'
import { api } from '../api'
import { householdApi } from '../peopleApi'
import { useTheme } from '../theme'
import { WEB_VERSION } from '../version'

function AccountSection() {
  const qc = useQueryClient()
  const [saved, setSaved] = useState<string | null>(null)
  const profile = useMutation({
    mutationFn: householdApi.updateProfile,
    onSuccess: async () => {
      setSaved('Name gespeichert')
      await qc.invalidateQueries({ queryKey: ['me'] })
      await qc.invalidateQueries({ queryKey: ['people'] })
      await qc.invalidateQueries({ queryKey: ['household'] })
    },
  })
  const password = useMutation({
    mutationFn: (v: { current: string; next: string }) => householdApi.changePassword(v.current, v.next),
    onSuccess: () => setSaved('Passwort geändert. Auf anderen Geräten musst du dich neu anmelden.'),
  })

  function submitProfile(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setSaved(null)
    const name = String(new FormData(e.currentTarget).get('name') ?? '').trim()
    if (name) profile.mutate(name)
  }
  function submitPassword(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setSaved(null)
    const form = e.currentTarget
    const f = new FormData(form)
    password.mutate(
      { current: String(f.get('current')), next: String(f.get('next')) },
      { onSuccess: () => form.reset() },
    )
  }

  const current = qc.getQueryData<{ user: { display_name: string } } | null>(['me'])
  return (
    <section aria-labelledby="konto">
      <h2 id="konto" className="text-xl">
        Mein Konto
      </h2>
      <form onSubmit={submitProfile} className="mt-3 flex flex-wrap items-end gap-3">
        <label className="block text-sm">
          Anzeigename
          <input name="name" required maxLength={80} defaultValue={current?.user.display_name} className={input} />
        </label>
        <button type="submit" disabled={profile.isPending} className={primary}>
          Speichern
        </button>
      </form>
      <form onSubmit={submitPassword} className="mt-6 flex flex-wrap items-end gap-3">
        <label className="block text-sm">
          Aktuelles Passwort
          <input name="current" type="password" required autoComplete="current-password" className={input} />
        </label>
        <label className="block text-sm">
          Neues Passwort
          <input name="next" type="password" required minLength={10} autoComplete="new-password" className={input} />
        </label>
        <button type="submit" disabled={password.isPending} className={primary}>
          Passwort ändern
        </button>
      </form>
      <div className="mt-2 space-y-1">
        <ErrorLine error={profile.error ?? password.error} />
        {saved && <p className="text-sm font-medium text-elbe-dunkel">{saved}</p>}
      </div>
    </section>
  )
}


function Appearance() {
  const theme = useTheme()
  const label = { auto: 'Automatisch (wie dein System)', light: 'Hell', dark: 'Dunkel' }[theme.mode]
  return (
    <section aria-labelledby="darstellung">
      <h2 id="darstellung" className="text-xl">
        Darstellung
      </h2>
      <p className="mt-3 text-sm">
        Aktuell: {label}.{' '}
        <button type="button" onClick={theme.cycle} className="font-medium text-elbe-dunkel hover:underline">
          Wechseln
        </button>
      </p>
    </section>
  )
}

function Versions() {
  const api_ = useQuery({ queryKey: ['version'], queryFn: () => api<{ version: string }>('/health') })
  return (
    <p className="text-sm text-tinte-weich">
      Version: Oberfläche {WEB_VERSION}, Server {api_.data?.version ?? '…'}
    </p>
  )
}

export function AccountPage() {
  return (
    <div className="space-y-12">
      <h1 className="sr-only">Mein Konto</h1>
      <AccountSection />
      <Appearance />
      <Versions />
    </div>
  )
}
