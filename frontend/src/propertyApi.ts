import { api } from './api'
import { personQuery } from './peopleApi'

export type Usage = 'owner_occupied' | 'rented'

export const USAGE_LABEL: Record<Usage, string> = {
  owner_occupied: 'Selbst genutzt',
  rented: 'Vermietet',
}

export interface Work {
  id: number
  month: string
  name: string
  cost: number
  value_gain: number
}

export interface LinkedFinancing {
  id: number
  name: string
  remaining_debt: number
  payment_this_month: number
  initial_debt: number | null
  repaid_percent: number | null
  end_month: string
  kind: 'loan' | 'building_savings' | 'credit_line'
  phase: 'not_started' | 'saving' | 'loan' | 'finished'
  prefinanced: boolean
  saved: number | null
  loan_start: string | null
}

export interface LinkedItem {
  id: number
  name: string
  kind: 'income' | 'expense'
  monthly: number
}

export interface Property {
  id: number
  person_id: number
  name: string
  usage: Usage
  purchase_month: string
  purchase_price: number
  closing_costs: number
  value: number
  value_as_of: string
  growth_percent: number
  share_percent: number
  own_share_entered: boolean
  works: Work[]
  current_value: number
  my_value: number
  debt: number
  repaid: number
  repaid_percent: number | null
  equity: number
  invested: number
  value_gain: number
  income: number
  costs: number
  financing_payment: number
  net_cashflow: number
  yield_percent: number | null
  financings: LinkedFinancing[]
  items: LinkedItem[]
}

export interface PropertyInput {
  name: string
  usage: Usage
  person_id?: number
  purchase_month: string
  purchase_price: string
  closing_costs: string
  value: string
  value_as_of: string
  growth_percent: string
  share_percent: string
  own_share_entered: boolean
}

export interface WorkInput {
  month: string
  name: string
  cost: string
  value_gain: string
}

export const propertyApi = {
  list: (person: number | null) => api<Property[]>(`/properties${personQuery(person, true)}`),
  create: (json: PropertyInput) => api<Property>('/properties', { method: 'POST', json }),
  update: (id: number, json: PropertyInput) => api<Property>(`/properties/${id}`, { method: 'PUT', json }),
  remove: (id: number) => api<void>(`/properties/${id}`, { method: 'DELETE' }),
  addWork: (id: number, json: WorkInput) => api<Property>(`/properties/${id}/works`, { method: 'POST', json }),
  removeWork: (id: number, workId: number) => api<Property>(`/properties/${id}/works/${workId}`, { method: 'DELETE' }),
  setLinks: (id: number, json: { financing_ids: number[]; item_ids: number[] }) =>
    api<Property>(`/properties/${id}/links`, { method: 'PUT', json }),
}
