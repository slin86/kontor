import { useState } from 'react'

/** Two-step delete: the first click asks, the second one deletes. */
export function ConfirmDelete({
  label,
  question,
  pending,
  error,
  onConfirm,
}: {
  label: string
  question: string
  pending?: boolean
  error?: unknown
  onConfirm: () => void
}) {
  const [asking, setAsking] = useState(false)
  if (!asking) {
    return (
      <button type="button" onClick={() => setAsking(true)} className="text-sm font-medium text-bake hover:underline">
        {label}
      </button>
    )
  }
  return (
    <div className="space-y-2 text-sm">
      <p className="font-medium">{question}</p>
      <div className="flex gap-4">
        <button type="button" disabled={pending} onClick={onConfirm} className="font-medium text-bake hover:underline">
          Ja, löschen
        </button>
        <button type="button" onClick={() => setAsking(false)} className="font-medium text-elbe-dunkel hover:underline">
          Abbrechen
        </button>
      </div>
      {error ? (
        <p role="alert" className="font-medium text-bake">
          {error instanceof Error ? error.message : 'Das hat nicht geklappt.'}
        </p>
      ) : null}
    </div>
  )
}
