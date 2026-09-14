import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, tokenStore } from '../lib/api'

export interface CurrentUser {
  id: string
  customer_id: string
  email: string
  full_name: string
  role: string
  is_active: boolean
}

interface AuthContextValue {
  user: CurrentUser | null
  isLoading: boolean
  isAuthenticated: boolean
  login: (email: string, password: string) => Promise<void>
  register: (customerName: string, fullName: string, email: string, password: string) => Promise<void>
  logout: () => void
  refetchUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  async function fetchMe() {
    try {
      const resp = await api.get<CurrentUser>('/users/me')
      setUser(resp.data)
    } catch {
      setUser(null)
    }
  }

  useEffect(() => {
    const hasToken = Boolean(tokenStore.getAccess())
    if (!hasToken) {
      setIsLoading(false)
      return
    }
    fetchMe().finally(() => setIsLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function login(email: string, password: string) {
    const resp = await api.post('/auth/login', { email, password })
    tokenStore.set(resp.data.access_token, resp.data.refresh_token)
    await fetchMe()
  }

  async function register(customerName: string, fullName: string, email: string, password: string) {
    const resp = await api.post('/auth/register', {
      customer_name: customerName,
      full_name: fullName,
      email,
      password,
    })
    tokenStore.set(resp.data.access_token, resp.data.refresh_token)
    await fetchMe()
  }

  function logout() {
    tokenStore.clear()
    setUser(null)
  }

  return (
    <AuthContext.Provider
      value={{ user, isLoading, isAuthenticated: Boolean(user), login, register, logout, refetchUser: fetchMe }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
