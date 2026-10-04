import { api } from './api'

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

export const KIND_LABEL: Record<Transaction['kind'], string> = {
  buy: 'Kauf',
  sell: 'Verkauf',
  dividend: 'Dividende',
}

export const actualsApi = {
  compare: () => api<Comparison>('/actuals/compare'),
  setValue: (json: { instrument_id: number; month: string; value: string; reason: string | null }) =>
    api<ActualValue>('/actuals/values', { method: 'PUT', json }),
  transactions: () => api<Transaction[]>('/actuals/transactions?limit=30'),
  addTransaction: (json: { instrument_id: number; day: string; kind: Transaction['kind']; amount: string; fee: string }) =>
    api<Transaction>('/actuals/transactions', { method: 'POST', json }),
  removeTransaction: (id: number) => api<void>(`/actuals/transactions/${id}`, { method: 'DELETE' }),
  preview: (csv: string, mapping: Record<string, number>) =>
    api<ImportPreview>('/actuals/import/preview', { method: 'POST', json: { csv, mapping } }),
  importCsv: (csv: string, mapping: Record<string, number>) =>
    api<ImportResult>('/actuals/import', { method: 'POST', json: { csv, mapping } }),
}
