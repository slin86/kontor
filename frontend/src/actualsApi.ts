import { api } from './api'
import { personQuery } from './peopleApi'

export interface ActualValue {
  id: number
  instrument_id: number
  month: string
  value: number
}

export interface Transaction {
  id: number
  instrument_id: number | null
  day: string
  kind: 'buy' | 'sell' | 'dividend'
  amount: number
  fee: number
  shares: number | null
  isin: string | null
  name: string | null
  source: 'manual' | 'csv'
}

export interface ImportRow {
  line: number
  day: string
  kind: Transaction['kind']
  amount: number
  fee: number
  shares: number | null
  isin: string | null
  name: string | null
  instrument_id: number | null
  duplicate: boolean
}

export interface ImportPreview {
  rows: ImportRow[]
  skipped: Record<string, number>
  errors: string[]
  unmatched: { isin: string | null; name: string | null; count: number }[]
  new_count: number
  duplicate_count: number
}

export interface ImportResult {
  imported: number
  duplicates: number
  unmatched: number
}

export interface InstrumentComparison {
  id: number
  name: string
  planned_value: number
  actual_value: number | null
  actual_month: string | null
  deviation: number | null
  deviation_percent: number | null
  planned_paid_in: number
  actual_net_invested: number | null
}

export interface ComparisonPoint {
  month: string
  planned_total: number
  planned_tracked: number
  actual: number | null
  planned_deposit: number | null
  actual_deposit: number | null
}

export interface Comparison {
  first: string
  last: string
  instruments: InstrumentComparison[]
  points: ComparisonPoint[]
}

export interface OverviewPoint {
  month: string
  plan: number
  actual: number | null
  forecast: number | null
}

export interface Overview {
  status: 'no_data' | 'ahead' | 'on_track' | 'behind'
  first: string
  today: string
  anchor: string | null
  end: string
  plan_now: number | null
  actual_now: number | null
  deviation: number | null
  deviation_percent: number | null
  plan_end: number
  forecast_end: number | null
  end_gap: number | null
  end_gap_percent: number | null
  tracked: string[]
  untracked: string[]
  points: OverviewPoint[]
}

export const KIND_LABEL: Record<Transaction['kind'], string> = {
  buy: 'Kauf',
  sell: 'Verkauf',
  dividend: 'Dividende',
}

export const actualsApi = {
  compare: (person: number | null) => api<Comparison>(`/actuals/compare${personQuery(person, true)}`),
  overview: (person: number | null, years: number) =>
    api<Overview>(`/actuals/overview?years=${years}${personQuery(person)}`),
  setValue: (json: { instrument_id: number; month: string; value: string; reason: string | null }) =>
    api<ActualValue>('/actuals/values', { method: 'PUT', json }),
  transactions: (person: number | null) =>
    api<Transaction[]>(`/actuals/transactions?limit=30${personQuery(person)}`),
  addTransaction: (json: { instrument_id: number; day: string; kind: Transaction['kind']; amount: string; fee: string }) =>
    api<Transaction>('/actuals/transactions', { method: 'POST', json }),
  removeTransaction: (id: number) => api<void>(`/actuals/transactions/${id}`, { method: 'DELETE' }),
  preview: (csv: string, mapping: Record<string, number>, person_id: number) =>
    api<ImportPreview>('/actuals/import/preview', { method: 'POST', json: { csv, mapping, person_id } }),
  importCsv: (csv: string, mapping: Record<string, number>, person_id: number) =>
    api<ImportResult>('/actuals/import', { method: 'POST', json: { csv, mapping, person_id } }),
}
