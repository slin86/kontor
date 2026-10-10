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
  source: 'pattern' | 'ai'
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
}
