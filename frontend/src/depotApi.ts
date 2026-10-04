import { api } from './api'

export type InstrumentKind = 'etf' | 'private_equity'

export const KIND_LABEL: Record<InstrumentKind, string> = {
  etf: 'ETF',
  private_equity: 'Private Equity',
}

export interface Instrument {
  id: number
  kind: InstrumentKind
  name: string
  isin: string | null
  expected_return_percent: number
  cost_percent: number
  entry_fee_percent: number
  start: string
  start_value: number
  current_rate: number
  planned_value: number
  paid_in: number
}

export interface Rate {
  id: number
  amount: number
  valid_from: string
  valid_to: string | null
  locked: boolean
}

export interface OneOff {
  id: number
  month: string
  amount: number
  note: string | null
  locked: boolean
}

export interface InstrumentDetail extends Instrument {
  rates: Rate[]
  one_offs: OneOff[]
}

export interface Depot {
  base_rate: number
  planned_value: number
  paid_in: number
  instruments: Instrument[]
}

export interface ProjectionPoint {
  month: string
  value: number
  paid_in: number
  deposit: number
  fees: number
  balances: number[]
}

export interface Projection {
  first: string
  last: string
  return_shift_percent: number
  inflation_percent: number
  base_rate: number
  instruments: { id: number; name: string; kind: InstrumentKind }[]
  points: ProjectionPoint[]
}

export interface Assumptions {
  name: string
  isin: string | null
  expected_return_percent: string
  cost_percent: string
  entry_fee_percent: string
}

export interface NewInstrument extends Assumptions {
  kind: InstrumentKind
  start: string
  start_value: string
  monthly_rate: string
}

export const depotApi = {
  overview: () => api<Depot>('/depot'),
  get: (id: number) => api<InstrumentDetail>(`/depot/instruments/${id}`),
  create: (json: NewInstrument) => api<InstrumentDetail>('/depot/instruments', { method: 'POST', json }),
  update: (id: number, json: Assumptions) => api<InstrumentDetail>(`/depot/instruments/${id}`, { method: 'PUT', json }),
  correct: (id: number, json: { start: string; start_value: string; reason: string }) =>
    api<InstrumentDetail>(`/depot/instruments/${id}/correct`, { method: 'POST', json }),
  changeRate: (id: number, json: { effective_from: string; amount: string }) =>
    api<InstrumentDetail>(`/depot/instruments/${id}/rate`, { method: 'POST', json }),
  addOneOff: (id: number, json: { month: string; amount: string; note: string | null }) =>
    api<InstrumentDetail>(`/depot/instruments/${id}/one-offs`, { method: 'POST', json }),
  removeOneOff: (id: number, oneOffId: number) =>
    api<InstrumentDetail>(`/depot/instruments/${id}/one-offs/${oneOffId}`, { method: 'DELETE' }),
  projection: (years: number, shift: number, inflation: number) =>
    api<Projection>(`/depot/projection?years=${years}&return_shift=${shift}&inflation=${inflation}`),
}
