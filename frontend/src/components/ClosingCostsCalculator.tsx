import { useState } from 'react'

import { BROKER_PERCENT, closingCosts, NOTARY_PERCENT, TRANSFER_TAX } from '../closingCosts'
import { euro } from '../format'
import { decimalString, input, primary, secondary } from './ui'

const toNumber = (raw: string): number => {
  const n = Number(decimalString(raw))
  return Number.isFinite(n) ? n : 0
}
const text = (n: number) => String(n).replace('.', ',')

/** Estimates the costs on top of the purchase price and hands the sum to the form. */
export function ClosingCostsCalculator({
  price,
  onApply,
  onClose,
}: {
  price: string
  onApply: (amount: string) => void
  onClose: () => void
}) {
  const [priceText, setPrice] = useState(price)
  const [state, setState] = useState('Hamburg')
  const [broker, setBroker] = useState(text(BROKER_PERCENT))
  const [notary, setNotary] = useState(text(NOTARY_PERCENT))
  const [other, setOther] = useState('')

  const result = closingCosts({
    price: toNumber(priceText),
    state,
    brokerPercent: toNumber(broker),
    notaryPercent: toNumber(notary),
    other: toNumber(other),
  })
  const share = toNumber(priceText) > 0 ? (result.total / toNumber(priceText)) * 100 : 0

  return (
    <div className="space-y-4 border-l-4 border-elbe bg-feld/60 p-4 sm:col-span-2 lg:col-span-3" role="group" aria-label="Kaufnebenkosten-Rechner">
      <h4 className="text-base font-semibold">Kaufnebenkosten berechnen</h4>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <label className="block text-sm">
          Kaufpreis in Euro
          <input value={priceText} onChange={(e) => setPrice(e.target.value)} inputMode="decimal" className={input} />
        </label>
        <label className="block text-sm">
          Bundesland
          <select value={state} onChange={(e) => setState(e.target.value)} className={input}>
            {Object.entries(TRANSFER_TAX).map(([name, pct]) => (
              <option key={name} value={name}>
                {name} ({text(pct)} %)
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm">
          Notar und Grundbuch in %
          <input value={notary} onChange={(e) => setNotary(e.target.value)} inputMode="decimal" className={input} />
        </label>
        <label className="block text-sm">
          Makler in %
          <input value={broker} onChange={(e) => setBroker(e.target.value)} inputMode="decimal" className={input} />
          <span className="mt-1 block text-xs text-tinte-weich">0 ohne Makler.</span>
        </label>
        <label className="block text-sm">
          Sonstiges in Euro
          <input value={other} onChange={(e) => setOther(e.target.value)} inputMode="decimal" className={input} />
        </label>
      </div>
      {result.lines.length > 0 && (
        <table className="w-full max-w-xl text-left text-sm">
          <tbody className="divide-y divide-tinte/15">
            {result.lines.map((l) => (
              <tr key={l.label}>
                <td className="py-1.5 pr-4">{l.label}</td>
                <td className="py-1.5 pr-4 text-right text-tinte-weich">{l.percent !== null ? `${text(l.percent)} %` : ''}</td>
                <td className="zahl py-1.5 text-right">{euro(l.amount)}</td>
              </tr>
            ))}
            <tr className="font-semibold">
              <td className="py-2 pr-4">Summe</td>
              <td className="py-2 pr-4 text-right text-tinte-weich">{text(Math.round(share * 10) / 10)} %</td>
              <td className="zahl py-2 text-right">{euro(result.total)}</td>
            </tr>
          </tbody>
        </table>
      )}
      <p className="max-w-2xl text-xs text-tinte-weich">
        Das ist eine Schätzung. Die Grunderwerbsteuer legt das Land fest, Notar und Grundbuch liegen meist bei 1,5 bis 2 %, die Maklerprovision
        ist Verhandlungssache. Nimm im Zweifel die Zahlen aus dem Kaufvertrag oder der Notarrechnung.
      </p>
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={result.total <= 0}
          onClick={() => {
            onApply(text(Math.round(result.total)))
            onClose()
          }}
          className={primary}
        >
          In das Formular übernehmen
        </button>
        <button type="button" onClick={onClose} className={secondary}>
          Schließen
        </button>
      </div>
    </div>
  )
}
