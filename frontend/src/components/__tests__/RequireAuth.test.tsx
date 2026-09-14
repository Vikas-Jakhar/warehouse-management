import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import RequireAuth from '../RequireAuth'
import { useAuth } from '../../hooks/useAuth'

vi.mock('../../hooks/useAuth')

const mockedUseAuth = vi.mocked(useAuth)

function renderWithRoutes() {
  return render(
    <MemoryRouter initialEntries={['/app/dashboard']}>
      <Routes>
        <Route path="/login" element={<div>Login page</div>} />
        <Route
          path="/app/dashboard"
          element={
            <RequireAuth>
              <div>Secret dashboard content</div>
            </RequireAuth>
          }
        />
      </Routes>
    </MemoryRouter>,
  )
}

describe('RequireAuth', () => {
  it('shows a loading state while auth status is being determined', () => {
    mockedUseAuth.mockReturnValue({
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
      refetchUser: vi.fn(),
      user: null,
      isLoading: true,
      isAuthenticated: false,
    })

    renderWithRoutes()

    expect(screen.getByText(/loading your workspace/i)).toBeInTheDocument()
  })

  it('redirects to /login when the user is not authenticated', () => {
    mockedUseAuth.mockReturnValue({
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
      refetchUser: vi.fn(),
      user: null,
      isLoading: false,
      isAuthenticated: false,
    })

    renderWithRoutes()

    expect(screen.getByText('Login page')).toBeInTheDocument()
    expect(screen.queryByText('Secret dashboard content')).not.toBeInTheDocument()
  })

  it('renders the protected content when the user is authenticated', () => {
    mockedUseAuth.mockReturnValue({
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
      refetchUser: vi.fn(),
      user: {
        id: '1',
        customer_id: '1',
        email: 'owner@acme.example.com',
        full_name: 'Owner',
        role: 'owner',
        is_active: true,
      },
      isLoading: false,
      isAuthenticated: true,
    })

    renderWithRoutes()

    expect(screen.getByText('Secret dashboard content')).toBeInTheDocument()
  })
})
