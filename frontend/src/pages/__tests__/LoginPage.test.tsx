import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import LoginPage from '../LoginPage'
import { useAuth } from '../../hooks/useAuth'

vi.mock('../../hooks/useAuth')

const mockedUseAuth = vi.mocked(useAuth)

function renderLoginPage() {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <LoginPage />
    </MemoryRouter>,
  )
}

afterEach(() => {
  vi.clearAllMocks()
})

describe('LoginPage', () => {
  it('renders email and password fields', () => {
    mockedUseAuth.mockReturnValue({
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
      refetchUser: vi.fn(),
      user: null,
      isLoading: false,
      isAuthenticated: false,
    })

    renderLoginPage()

    expect(screen.getByLabelText(/email/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
  })

  it('shows a real loading state while signing in, not a fake delay', async () => {
    let resolveLogin: () => void = () => {}
    const loginPromise = new Promise<void>((resolve) => {
      resolveLogin = resolve
    })
    const login = vi.fn().mockReturnValue(loginPromise)

    mockedUseAuth.mockReturnValue({
      login,
      register: vi.fn(),
      logout: vi.fn(),
      refetchUser: vi.fn(),
      user: null,
      isLoading: false,
      isAuthenticated: false,
    })

    renderLoginPage()
    const user = userEvent.setup()

    await user.type(screen.getByLabelText(/email/i), 'owner@acme.example.com')
    await user.type(screen.getByLabelText(/password/i), 'Sup3rSecret!')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByText(/signing you in…/i)).toBeInTheDocument()
    expect(login).toHaveBeenCalledWith('owner@acme.example.com', 'Sup3rSecret!')

    resolveLogin()
    await waitFor(() => expect(screen.queryByText(/signing you in…/i)).not.toBeInTheDocument())
  })

  it('shows an error message when login fails, without crashing', async () => {
    const axiosError = Object.assign(new Error('Request failed'), {
      isAxiosError: true,
      response: { data: { error: { message: 'Invalid email or password' } } },
    })
    const login = vi.fn().mockRejectedValue(axiosError)
    mockedUseAuth.mockReturnValue({
      login,
      register: vi.fn(),
      logout: vi.fn(),
      refetchUser: vi.fn(),
      user: null,
      isLoading: false,
      isAuthenticated: false,
    })

    renderLoginPage()
    const user = userEvent.setup()

    await user.type(screen.getByLabelText(/email/i), 'owner@acme.example.com')
    await user.type(screen.getByLabelText(/password/i), 'wrong-password')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/invalid email or password/i)
  })
})
