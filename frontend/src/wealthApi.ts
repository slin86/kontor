import { api } from './api'
import { personQuery } from './peopleApi'

export type AssetKind = 'cash' | 'property' | 'vehicle' | 'other'

export const ASSET_LABEL: Record<AssetKind, string> = {
  cash: 'Bargeld und Konten',
  property: 'Immobilie',
  vehicle: 'Fahrzeug',
  other: 'Sonstiges',
}

/** Typical yearly change, used to prefill the form. */
export const ASSET_GROWTH: Record<AssetKind, string> = { cash: '0', property: '2', vehicle: '-10', other: '0' }

export interface Asset {
  id: number
  person_id: number
  name: string
  kind: AssetKind
  value: number
  as_of: string
  growth_percent: number
}

export interface AssetInput {
  name: string
  kind: AssetKind
  value: string
  as_of: string
  growth_percent: string
  person_id?: number
}

export interface WealthSeries {
  key: string
  name: string
  group: 'depot' | 'bauspar' | 'asset' | 'debt'
}

export interface WealthPoint {
  month: string
  values: number[]
  assets: number
  debts: number
  net: number
  net_after_tax: number
}

export interface Wealth {
  first: string
  last: string
  today: string
  inflation_percent: number
  series: WealthSeries[]
  points: WealthPoint[]
}

export const wealthApi = {
  wealth: (years: number, inflation: number, person: number | null) =>
    api<Wealth>(`/wealth?years=${years}&inflation=${inflation}${personQuery(person)}`),
  assets: (person: number | null) => api<Asset[]>(`/assets${personQuery(person, true)}`),
  createAsset: (json: AssetInput) => api<Asset>('/assets', { method: 'POST', json }),
  updateAsset: (id: number, json: AssetInput) => api<Asset>(`/assets/${id}`, { method: 'PUT', json }),
  removeAsset: (id: number) => api<void>(`/assets/${id}`, { method: 'DELETE' }),
}
