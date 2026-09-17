import axios, { type AxiosError, type AxiosInstance } from 'axios'

const ACCESS_KEY = 'wp_access_token'
const REFRESH_KEY = 'wp_refresh_token'

export const tokenStore = {
  getAccess: () => localStorage.getItem(ACCESS_KEY),
  getRefresh: () => localStorage.getItem(REFRESH_KEY),
  set: (access: string, refresh: string) => {
    localStorage.setItem(ACCESS_KEY, access)
    localStorage.setItem(REFRESH_KEY, refresh)
  },
  clear: () => {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}

export interface ApiErrorShape {
  error: { code: number; message: string; details: unknown }
}

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || '/api/v1'

export const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
})

api.interceptors.request.use((config) => {
  const token = tokenStore.getAccess()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

let refreshPromise: Promise<string | null> | null = null

async function refreshAccessToken(): Promise<string | null> {
  const refresh = tokenStore.getRefresh()
  if (!refresh) return null
  try {
    const resp = await axios.post(`${API_BASE_URL}/auth/refresh`, {
  refresh_token: refresh,
})
    const { access_token, refresh_token } = resp.data
    tokenStore.set(access_token, refresh_token)
    return access_token
  } catch {
    tokenStore.clear()
    return null
  }
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config
    if (error.response?.status === 401 && original && !(original as { _retried?: boolean })._retried) {
      ;(original as { _retried?: boolean })._retried = true
      if (!refreshPromise) {
        refreshPromise = refreshAccessToken().finally(() => {
          refreshPromise = null
        })
      }
      const newToken = await refreshPromise
      if (newToken) {
        original.headers = original.headers ?? {}
        original.headers.Authorization = `Bearer ${newToken}`
        return api.request(original)
      }
    }
    return Promise.reject(error)
  },
)

export function getApiErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as ApiErrorShape | { detail?: unknown } | undefined
    if (data && 'error' in data && data.error?.message) return data.error.message
    if (data && 'detail' in data) {
      const detail = data.detail
      if (typeof detail === 'string') return detail
      if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg
    }
    if (error.message) return error.message
  }
  return 'Something went wrong. Please try again.'
}
