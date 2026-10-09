// Estimate of the costs on top of a German property purchase.

/** Grunderwerbsteuer by state, in percent of the purchase price. */
export const TRANSFER_TAX: Record<string, number> = {
  'Baden-Württemberg': 5,
  Bayern: 3.5,
  Berlin: 6,
  Brandenburg: 6.5,
  Bremen: 5.5,
  Hamburg: 5.5,
  Hessen: 6,
  'Mecklenburg-Vorpommern': 6,
  Niedersachsen: 5,
  'Nordrhein-Westfalen': 6.5,
  'Rheinland-Pfalz': 5,
  Saarland: 6.5,
  Sachsen: 5.5,
  'Sachsen-Anhalt': 5,
  'Schleswig-Holstein': 6.5,
  Thüringen: 5,
}

/** Typical notary and land registry fees together, in percent. */
export const NOTARY_PERCENT = 2
/** Buyer's share of a broker commission incl. VAT when it is split in half. */
export const BROKER_PERCENT = 3.57

export interface ClosingCostInput {
  price: number
  state: string
  brokerPercent: number
  notaryPercent: number
  other: number
}

export interface ClosingCostLine {
  label: string
  percent: number | null
  amount: number
}

export function closingCosts(i: ClosingCostInput): { lines: ClosingCostLine[]; total: number } {
  const tax = TRANSFER_TAX[i.state] ?? 0
  const lines: ClosingCostLine[] = [
    { label: `Grunderwerbsteuer (${i.state})`, percent: tax, amount: (i.price * tax) / 100 },
    { label: 'Notar und Grundbuch', percent: i.notaryPercent, amount: (i.price * i.notaryPercent) / 100 },
    { label: 'Maklerprovision', percent: i.brokerPercent, amount: (i.price * i.brokerPercent) / 100 },
    { label: 'Sonstiges (Gutachten, Umzug, Erstausstattung)', percent: null, amount: i.other },
  ].filter((l) => l.amount > 0)
  return { lines, total: lines.reduce((sum, l) => sum + l.amount, 0) }
}

