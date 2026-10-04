const eur0 = new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 })
const eur2 = new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR', minimumFractionDigits: 2 })
const pct = new Intl.NumberFormat('de-DE', { style: 'percent', maximumFractionDigits: 0 })

export const euro = (n: number, cents = false): string => (cents ? eur2 : eur0).format(n)
export const percent = (n: number): string => pct.format(n)

export const FREQUENCY_LABEL: Record<string, string> = {
  monthly: 'monatlich',
  quarterly: 'vierteljährlich',
  yearly: 'jährlich',
}
