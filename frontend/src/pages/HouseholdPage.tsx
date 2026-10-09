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

function HouseholdsSection() {
  const households = useQuery({ queryKey: ['households'], queryFn: householdApi.households })
  // all data on screen belongs to the previous household, so reload after every change
  const done = () => window.location.assign('/haushalt')
  const switchTo = useMutation({ mutationFn: householdApi.switchHousehold, onSuccess: done })
  const create = useMutation({ mutationFn: householdApi.createHousehold, onSuccess: done })
  const join = useMutation({ mutationFn: householdApi.joinHousehold, onSuccess: done })

  return (
    <section aria-labelledby="haushalte">
      <h2 id="haushalte" className="text-xl">
        Meine Haushalte
      </h2>
      <p className="mt-2 max-w-2xl text-sm text-tinte-weich">
        Mit einem Konto kannst du mehrere Haushalte führen, etwa deinen eigenen und ein Ferienhaus mit der Familie. Jeder Haushalt ist vollständig getrennt: eigene
        Personen, Posten, Finanzierungen, Immobilien und Depots. Es fließt nichts zwischen ihnen.
      </p>
      <ul className="mt-3 divide-y divide-tinte/15">
        {households.data?.map((h) => (
          <li key={h.id} className="flex flex-wrap items-baseline gap-x-4 gap-y-1 py-3">
            <span className="font-medium">{h.name}</span>
            {h.is_active ? (
              <span className="ml-auto text-sm text-tinte-weich">Du arbeitest gerade hier</span>
            ) : (
              <button type="button" disabled={switchTo.isPending} onClick={() => switchTo.mutate(h.id)} className="ml-auto text-sm font-medium text-elbe-dunkel hover:underline">
                Wechseln
              </button>
            )}
          </li>
        ))}
      </ul>
      <div className="mt-4 grid gap-6 sm:grid-cols-2">
        <form
          onSubmit={(e) => {
            e.preventDefault()
            const name = String(new FormData(e.currentTarget).get('name') ?? '').trim()
            if (name) create.mutate(name)
          }}
          className="flex flex-wrap items-end gap-3"
        >
          <label className="block text-sm">
            Neuer Haushalt
            <input name="name" required maxLength={120} placeholder="z. B. Ferienhaus" className={input} />
          </label>
          <button type="submit" disabled={create.isPending} className={primary}>
            Anlegen
          </button>
          <ErrorLine error={create.error} />
        </form>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            const code = String(new FormData(e.currentTarget).get('code') ?? '').trim()
            if (code) join.mutate(code)
          }}
          className="flex flex-wrap items-end gap-3"
        >
          <label className="block text-sm">
            Mit Einladungscode beitreten
            <input name="code" required maxLength={64} autoComplete="off" className={input} />
          </label>
          <button type="submit" disabled={join.isPending} className={primary}>
            Beitreten
          </button>
          <ErrorLine error={join.error} />
        </form>
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

export function HouseholdPage() {
  return (
    <div className="space-y-12">
      <h1 className="sr-only">Haushalt</h1>
      <HouseholdsSection />
      <PeopleSection />
      <MembersSection />
    </div>
  )
}
