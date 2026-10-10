import { api } from './api'
import type { Frequency } from './cashflowApi'

export interface AiStatus {
  local_configured: boolean
  local_reachable: boolean
  local_model: string | null
  cloud_configured: boolean
}

export interface Suggestion {
  category_id: number | null
  recurring: boolean | null
  frequency: Frequency | null
  reason: string | null
  source: 'existing' | 'local' | 'cloud' | 'none'
}

export interface Candidate {
  name: string
  amount: number
  income: boolean
  frequency: Frequency
  category_id: number | null
  reason: string | null
  occurrences: number
  first: string
  last: string
  source: 'pattern' | 'ai' | 'document'
  check: string | null
  existing_item_id: number | null
  existing_item_name: string | null
}

export interface Analysis {
  format: 'csv' | 'camt' | 'mt940' | 'pdf'
  lines: number
  period_from: string
  period_to: string
  candidates: Candidate[]
  unrated: number
  ai: { used: boolean; note: string | null }
}

export interface ContractAnalysis {
  candidates: Candidate[]
  ai: { used: boolean; note: string | null }
}

export type FinancingFormKind = 'loan' | 'zero' | 'credit_line' | 'building_savings' | 'prefinanced'

export interface FinancingDraft {
  form_kind: FinancingFormKind
  fields: Record<string, string>
  unverified: string[]
  missing_note: string | null
}

export interface DepotRow {
  day: string
  kind: 'buy' | 'sell' | 'dividend'
  amount: number
  fee: number
  shares: number | null
  isin: string | null
  name: string | null
  external_id: string
  instrument_id: number | null
  duplicate: boolean
  check: string | null
}

export interface DepotPreview {
  rows: DepotRow[]
  unmatched: { isin: string | null; name: string | null; count: number }[]
  skipped: number
  method: 'csv' | 'ai'
  new_count: number
  duplicate_count: number
}

/** The file as base64, in chunks so a few MB do not blow the call stack. */
async function toBase64(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer())
  let binary = ''
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000))
  return btoa(binary)
}

export const aiApi = {
  status: () => api<AiStatus>('/ai/status'),
  suggest: (json: { name: string; income?: boolean | null }) => api<Suggestion>('/ai/suggest', { method: 'POST', json }),
  analyze: async (file: File) =>
    api<Analysis>('/ai/statements/analyze', { method: 'POST', json: { filename: file.name, content_base64: await toBase64(file) } }),
  analyzeContract: async (file: File) =>
    api<ContractAnalysis>('/ai/contracts/analyze', { method: 'POST', json: { filename: file.name, content_base64: await toBase64(file) } }),
  analyzeFinancing: async (file: File) =>
    api<FinancingDraft>('/ai/financings/analyze', { method: 'POST', json: { filename: file.name, content_base64: await toBase64(file) } }),
  analyzeDepot: async (file: File, mapping: Record<string, number>, person_id: number) =>
    api<DepotPreview>('/ai/depot/analyze', {
      method: 'POST',
      json: { filename: file.name, content_base64: await toBase64(file), mapping, person_id },
    }),
  importDepot: (rows: DepotRow[], mapping: Record<string, number>, person_id: number, method: 'csv' | 'ai') =>
    api<{ imported: number; duplicates: number; unmatched: number }>('/ai/depot/import', {
      method: 'POST',
      json: {
        rows: rows.map(({ day, kind, amount, fee, shares, isin, name, external_id }) => ({ day, kind, amount, fee, shares, isin, name, external_id })),
        mapping,
        person_id,
        source: method,
      },
    }),
}
