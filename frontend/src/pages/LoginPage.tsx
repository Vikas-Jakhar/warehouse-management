import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Field, PrimaryButton, TextInput } from '../components/FormControls'
import { useAuth } from '../hooks/useAuth'
import { getApiErrorMessage } from '../lib/api'

export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const from = (location.state as { from?: string } | null)?.from ?? '/app/dashboard'

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setIsSubmitting(true)
    try {
      await login(email, password)
      navigate(from, { replace: true })
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--color-concrete)] px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8">
          <p className="font-mono-tabular text-xs tracking-wide text-[var(--color-steel-light)]">WMS-01</p>
          <h1 className="mt-1 text-2xl font-semibold text-[var(--color-ink)]">Sign in to your workspace</h1>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4 rounded-sm border border-[var(--color-line)] bg-white p-6">
          <Field label="Email" htmlFor="email">
            <TextInput
              id="email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </Field>
          <Field label="Password" htmlFor="password">
            <TextInput
              id="password"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>

          {error && (
            <p role="alert" className="rounded-sm bg-[var(--color-rust-soft)] px-3 py-2 text-sm text-[var(--color-rust)]">
              {error}
            </p>
          )}

          <PrimaryButton type="submit" isLoading={isSubmitting} className="mt-2 w-full">
            {isSubmitting ? 'Signing you in…' : 'Sign in'}
          </PrimaryButton>

          <div className="flex items-center justify-between text-sm">
            <Link to="/forgot-password" className="text-[var(--color-steel)] hover:text-[var(--color-ink)]">
              Forgot password?
            </Link>
            <Link to="/register" className="text-[var(--color-steel)] hover:text-[var(--color-ink)]">
              Create workspace
            </Link>
          </div>
        </form>
      </div>
    </div>
  )
}
