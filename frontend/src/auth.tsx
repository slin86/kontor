import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useContext, type ReactNode } from 'react'

import { api, ApiError, type Me } from './api'

interface AuthState {
  me: Me | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (input: RegisterInput) => Promise<void>
  logout: () => Promise<void>
}

export interface RegisterInput {
  email: string
  password: string
  display_name: string
  household_name?: string
  invite_code?: string
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const meQuery = useQuery({
    queryKey: ['me'],
    queryFn: async () => {
      try {
        return await api<Me>('/auth/me')
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null
        throw e
      }
    },
    retry: false,
  })

  const setMe = (me: Me | null) => qc.setQueryData(['me'], me)

  const loginMut = useMutation({
    mutationFn: (v: { email: string; password: string }) => api<Me>('/auth/login', { method: 'POST', json: v }),
    onSuccess: setMe,
  })
  const registerMut = useMutation({
    mutationFn: (v: RegisterInput) => api<Me>('/auth/register', { method: 'POST', json: v }),
    onSuccess: setMe,
  })
  const logoutMut = useMutation({
    mutationFn: () => api<void>('/auth/logout', { method: 'POST' }),
    onSuccess: () => {
      setMe(null)
      qc.clear()
      qc.setQueryData(['me'], null)
    },
  })

  const value: AuthState = {
    me: meQuery.data ?? null,
    loading: meQuery.isLoading,
    login: async (email, password) => void (await loginMut.mutateAsync({ email, password })),
    register: async (input) => void (await registerMut.mutateAsync(input)),
    logout: async () => void (await logoutMut.mutateAsync()),
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
