import { api } from './api'

export type FinancingKind = 'loan' | 'building_savings'
export type Phase = 'not_started' | 'saving' | 'loan' | 'finished'

export interface Financing {
  id: number
  kind: FinancingKind
  name: string
  purpose: string | null
  start: string
  end_month: string // first month without any payment
  regular_payment: number
  payment_this_month: number
  phase: Phase
  remaining_debt: number | null
  saved: number | null
  total_interest: number
  remaining_interest: number
}

export interface ScheduleRow {
  month: string
  interest: number
  principal: number
  saving: number
  fee: number
  balance: number
  phase: 'saving' | 'loan'
  special: number
}

export interface FinancingEvent {
  id: number
  month: string
  kind: 'special_repayment' | 'payment_change' | 'rate_change'
  value: number // euros, or percent per year for rate changes
  locked: boolean
}

export interface FinancingDetail extends Financing {
  input: Record<string, string | null>
  events: FinancingEvent[]
  schedule: ScheduleRow[]
}

export interface OutlookPoint {
  month: string
  income: number
  expenses: number
  financing: number
  free: number
}

export interface OutlookEvent {
  month: string
  kind: 'financing_end' | 'item_end'
  label: string
  monthly_change: number
}

export interface Outlook {
  start: string
  years: number
  income_growth_percent: number
  expense_growth_percent: number
  points: OutlookPoint[]
  events: OutlookEvent[]
}

export type LoanInput = {
  kind: 'loan'
  name: string
  purpose: 'real_estate' | 'consumer' | 'other'
  principal: string
  annual_rate_percent: string
  monthly_payment?: string
  initial_repayment_percent?: string
  start: string
}

export type BausparInput = {
  kind: 'building_savings'
  name: string
  contract_sum: string
  monthly_saving: string
  start: string
  allocation: string
  fee_percent: string
  deposit_rate_percent: string
  loan_rate_percent: string
  loan_payment: string
}

export type FinancingInput = LoanInput | BausparInput

export const financingApi = {
  list: () => api<Financing[]>('/financings'),
  get: (id: number) => api<FinancingDetail>(`/financings/${id}`),
  create: (json: FinancingInput) => api<FinancingDetail>('/financings', { method: 'POST', json }),
  correct: (id: number, json: { reason: string; data: FinancingInput }) =>
    api<FinancingDetail>(`/financings/${id}/correct`, { method: 'POST', json }),
  addEvent: (id: number, json: { month: string; kind: FinancingEvent['kind']; value: string }) =>
    api<FinancingDetail>(`/financings/${id}/events`, { method: 'POST', json }),
  removeEvent: (id: number, eventId: number) =>
    api<FinancingDetail>(`/financings/${id}/events/${eventId}`, { method: 'DELETE' }),
  outlook: (years: number, incomeGrowth: number, expenseGrowth: number) =>
    api<Outlook>(`/outlook?years=${years}&income_growth=${incomeGrowth}&expense_growth=${expenseGrowth}`),
}
