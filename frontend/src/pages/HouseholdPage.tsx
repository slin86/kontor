import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'

import { ConfirmDelete } from '../components/ConfirmDelete'
import { input, primary, secondary } from '../components/ui'
import { householdApi, peopleApi, type Person } from '../peopleApi'

function ErrorLine({ error }: { error: unknown }) {
  if (!error) return null
  return (
    <p role="alert" className="text-sm font-medium text-bake">
      {error instanceof Error ? error.message : 'Das hat nicht geklappt.'}
    </p>
  )
}

function PersonRow({ person, onChanged }: { person: Person; onChanged: () => Promise<void> }) {
  const [editing, setEditing] = useState(false)
  const rename = useMutation({
    mutationFn: (name: string) => peopleApi.rename(person.id, name),
    onSuccess: async () => {
      setEditing(false)
      await onChanged()
    },
  })
  const remove = useMutation({ mutationFn: () => peopleApi.remove(person.id), onSuccess: onChanged })

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const name = String(new FormData(e.currentTarget).get('name') ?? '').trim()
    if (name) rename.mutate(name)
  }

  return (
    <li className="py-3">
      {editing ? (
        <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
          <label className="block text-sm">
            Name
            <input name="name" required maxLength={80} defaultValue={person.name} className={input} />
          </label>
          <button type="submit" disabled={rename.isPending} className={primary}>
            Speichern
          </button>
          <button type="button" onClick={() => setEditing(false)} className={secondary}>
            Abbrechen
          </button>
          <ErrorLine error={rename.error} />
        </form>
      ) : (
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <span className="font-medium">{person.name}</span>
          <span className="text-sm text-tinte-weich">
            {person.has_login ? (person.is_me ? 'Du, mit Anmeldung' : 'Mit Anmeldung') : 'Ohne Anmeldung'} ·{' '}
            {person.positions === 1 ? '1 Position' : `${person.positions} Positionen`}
          </span>
          <button type="button" onClick={() => setEditing(true)} className="ml-auto text-sm font-medium text-elbe-dunkel hover:underline">
            Umbenennen
          </button>
          {!person.has_login && (
            <ConfirmDelete
              label="Entfernen"
              question={`${person.name} entfernen?`}
              pending={remove.isPending}
              error={remove.error}
              onConfirm={() => remove.mutate()}
            />
          )}
        </div>
      )}
      {!editing && person.positions > 0 && !person.has_login && (
        <p className="mt-1 text-xs text-tinte-weich">
          Zum Entfernen musst du die Positionen erst löschen oder einer anderen Person zuordnen.
        </p>
      )}
    </li>
  )
}

function PeopleSection() {
  const qc = useQueryClient()
  const people = useQuery({ queryKey: ['people'], queryFn: peopleApi.list })
  const refresh = async () => {
    await qc.invalidateQueries({ queryKey: ['people'] })
    await qc.invalidateQueries({ queryKey: ['household'] })
    await qc.invalidateQueries({ queryKey: ['depot'] })
  }
  const add = useMutation({ mutationFn: peopleApi.create, onSuccess: refresh })

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = e.currentTarget
    const name = String(new FormData(form).get('name') ?? '').trim()
    if (!name) return
    add.mutate(name, { onSuccess: () => form.reset() })
  }

  return (
    <section aria-labelledby="personen">
      <h2 id="personen" className="text-xl">
        Personen mit Depot
      </h2>
      <p className="mt-2 max-w-2xl text-sm text-tinte-weich">
        Jede Person hat ihr eigenes Depot, eigene Ist-Werte, Steuerangaben, Cashflow-Posten und Finanzierungen. Kinder brauchen keine Anmeldung: Du legst sie hier an
        und wechselst oben auf den Seiten zwischen den Personen oder siehst den ganzen Haushalt zusammen. Geld, das eine Person an eine andere überweist, trägst du
        als Übertrag bei den Cashflow-Posten ein.
      </p>
      <ul className="mt-3 divide-y divide-tinte/15">
        {people.data?.map((p) => <PersonRow key={p.id} person={p} onChanged={refresh} />)}
      </ul>
      <form onSubmit={submit} className="mt-4 flex flex-wrap items-end gap-3">
        <label className="block text-sm">
          Neue Person
          <input name="name" required maxLength={80} placeholder="Vorname des Kindes" className={input} />
        </label>
        <button type="submit" disabled={add.isPending} className={primary}>
          Person anlegen
        </button>
      </form>
      <div className="mt-2">
        <ErrorLine error={add.error} />
      </div>
    </section>
  )
}

function MembersSection() {
  const qc = useQueryClient()
  const household = useQuery({ queryKey: ['household'], queryFn: householdApi.get })
  const [copied, setCopied] = useState(false)
  const refresh = async () => {
    await qc.invalidateQueries({ queryKey: ['household'] })
    await qc.invalidateQueries({ queryKey: ['people'] })
  }
  const renew = useMutation({
    mutationFn: householdApi.renewInviteCode,
    onSuccess: async (h) => {
      setCopied(false)
      qc.setQueryData(['household'], h)
    },
  })
  const rename = useMutation({
    mutationFn: householdApi.rename,
    onSuccess: async (h) => {
      qc.setQueryData(['household'], h)
      await qc.invalidateQueries({ queryKey: ['me'] })
    },
  })
  const removeMember = useMutation({ mutationFn: householdApi.removeMember, onSuccess: refresh })

  async function copy(code: string) {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
    } catch {
      setCopied(false) // clipboard blocked on plain HTTP: the code stays selectable
    }
  }

  function submitName(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const name = String(new FormData(e.currentTarget).get('name') ?? '').trim()
    if (name) rename.mutate(name)
  }

  const h = household.data
  if (!h) return null
  return (
    <>
      <section aria-labelledby="mitglieder">
        <h2 id="mitglieder" className="text-xl">
          Mitglieder mit Anmeldung
        </h2>
        <ul className="mt-3 divide-y divide-tinte/15">
          {h.members.map((m) => (
            <li key={m.id} className="flex flex-wrap items-baseline gap-x-4 gap-y-1 py-3">
              <span className="font-medium">{m.display_name}</span>
              <span className="text-sm text-tinte-weich">{m.email}</span>
              {m.is_me ? (
                <span className="ml-auto text-sm text-tinte-weich">Du</span>
              ) : (
                <span className="ml-auto">
                  <ConfirmDelete
                    label="Zugang entziehen"
                    question={`${m.display_name} aus dem Haushalt entfernen? Die Person wird abgemeldet, das Depot bleibt erhalten.`}
                    pending={removeMember.isPending}
                    error={removeMember.error}
                    onConfirm={() => removeMember.mutate(m.id)}
                  />
                </span>
              )}
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="beitritt">
        <h2 id="beitritt" className="text-xl">
          Weitere Erwachsene einladen
        </h2>
        <p className="mt-2 max-w-2xl text-sm text-tinte-weich">
          Wer sich mit diesem Code registriert, tritt deinem Haushalt bei und bekommt automatisch ein eigenes Depot. Erneuern macht den alten Code ungültig.
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-4">
          <code className="select-all border border-tinte/30 bg-feld/60 px-3 py-2 text-base tracking-wider">{h.invite_code}</code>
          <button type="button" onClick={() => void copy(h.invite_code)} className={secondary}>
            {copied ? 'Kopiert' : 'Code kopieren'}
          </button>
          <button type="button" disabled={renew.isPending} onClick={() => renew.mutate()} className={secondary}>
            Neuen Code erzeugen
          </button>
        </div>
        <div className="mt-2">
          <ErrorLine error={renew.error} />
        </div>
      </section>

      <section aria-labelledby="haushaltsname">
        <h2 id="haushaltsname" className="text-xl">
          Name des Haushalts
        </h2>
        <form onSubmit={submitName} className="mt-3 flex flex-wrap items-end gap-3">
          <label className="block text-sm">
            Name
            <input name="name" required maxLength={120} defaultValue={h.name} key={h.name} className={input} />
          </label>
          <button type="submit" disabled={rename.isPending} className={primary}>
            Speichern
          </button>
        </form>
        <div className="mt-2">
          <ErrorLine error={rename.error} />
        </div>
      </section>
    </>
  )
}

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

export function HouseholdPage() {
  return (
    <div className="space-y-12">
      <h1 className="sr-only">Haushalt</h1>
      <PeopleSection />
      <MembersSection />
      <AccountSection />
    </div>
  )
}
