import { api } from './api'

export interface Person {
  id: number
  name: string
  has_login: boolean
  is_me: boolean
  positions: number
}

export interface Member {
  id: number
  email: string
  display_name: string
  is_me: boolean
}

export interface HouseholdDetail {
  id: number
  name: string
  invite_code: string
  members: Member[]
}

export const peopleApi = {
  list: () => api<Person[]>('/people'),
  create: (name: string) => api<Person>('/people', { method: 'POST', json: { name } }),
  rename: (id: number, name: string) => api<Person>(`/people/${id}`, { method: 'PUT', json: { name } }),
  remove: (id: number) => api<void>(`/people/${id}`, { method: 'DELETE' }),
}

export const householdApi = {
  get: () => api<HouseholdDetail>('/household'),
  rename: (name: string) => api<HouseholdDetail>('/household', { method: 'PUT', json: { name } }),
  renewInviteCode: () => api<HouseholdDetail>('/household/invite-code', { method: 'POST' }),
  removeMember: (id: number) => api<void>(`/household/members/${id}`, { method: 'DELETE' }),
  updateProfile: (display_name: string) => api<Member>('/auth/profile', { method: 'PUT', json: { display_name } }),
  changePassword: (current_password: string, new_password: string) =>
    api<void>('/auth/password', { method: 'POST', json: { current_password, new_password } }),
}

/** Query-string part that limits a request to one person; empty means everyone. */
export const personQuery = (person: number | null, first = false) =>
  person === null ? '' : `${first ? '?' : '&'}person=${person}`
