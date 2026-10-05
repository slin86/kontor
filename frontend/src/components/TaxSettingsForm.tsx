import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'

import { taxApi } from '../depotApi'
import { ErrorLine } from './ErrorLine'
import { decimalString, input, primary } from './ui'

/** Household-wide inputs for the tax estimate. Collapsed by default: most people keep the defaults. */
export function TaxSettingsForm() {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const settings = useQuery({ queryKey: ['tax', 'settings'], queryFn: taxApi.get })
  const save = useMutation({
    mutationFn: taxApi.save,
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['tax'] })
      await qc.invalidateQueries({ queryKey: ['depot'] })
      setOpen(false)
    },
  })
  const s = settings.data
  if (!s) return null

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    save.mutate({
      church_tax_percent: Number(f.get('church_tax_percent')),
      allowance: decimalString(f.get('allowance')) || '0',
      base_interest_percent: decimalString(f.get('base_interest_percent')) || '0',
    })
  }

  return (
    <div className="mt-4 text-sm">
      <p>
        Steuer-Annahmen: {s.church_tax_percent > 0 ? `Kirchensteuer ${s.church_tax_percent} %` : 'ohne Kirchensteuer'}, Sparer-Pauschbetrag{' '}
        {s.allowance.toLocaleString('de-DE')} € pro Jahr, Basiszins {String(s.base_interest_percent).replace('.', ',')} % für künftige Jahre.{' '}
        {!open && (
          <button type="button" onClick={() => setOpen(true)} className="font-medium text-elbe-dunkel hover:underline">
            Ändern
          </button>
        )}
      </p>
      {open && (
        <form onSubmit={submit} className="mt-3 grid max-w-2xl gap-4 sm:grid-cols-3">
          <label className="block">
            Kirchensteuer
            <select name="church_tax_percent" defaultValue={s.church_tax_percent} className={input}>
              <option value={0}>Keine</option>
              <option value={8}>8 % (Bayern, Baden-Württemberg)</option>
              <option value={9}>9 % (übrige Länder)</option>
            </select>
          </label>
          <label className="block">
            Sparer-Pauschbetrag pro Jahr in Euro
            <input name="allowance" inputMode="decimal" defaultValue={String(s.allowance).replace('.', ',')} className={input} />
            <span className="mt-1 block text-xs text-tinte-weich">1.000 Euro einzeln, 2.000 Euro gemeinsam veranlagt. Gilt hier ganz für dieses Depot.</span>
          </label>
          <label className="block">
            Basiszins ab 2027 in Prozent
            <input name="base_interest_percent" inputMode="decimal" defaultValue={String(s.base_interest_percent).replace('.', ',')} className={input} />
            <span className="mt-1 block text-xs text-tinte-weich">Bis 2026 gelten die veröffentlichten Werte (2026: 3,2 %).</span>
          </label>
          <div className="flex items-center gap-3 sm:col-span-3">
            <button type="submit" disabled={save.isPending} className={primary}>
              Speichern
            </button>
            <button type="button" onClick={() => setOpen(false)} className="font-medium text-elbe-dunkel hover:underline">
              Abbrechen
            </button>
          </div>
          <div className="sm:col-span-3">
            <ErrorLine error={save.error} />
          </div>
        </form>
      )}
    </div>
  )
}
