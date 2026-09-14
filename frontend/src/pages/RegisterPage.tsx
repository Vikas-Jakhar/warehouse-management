import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Field, PrimaryButton, TextInput } from '../components/FormControls'
import { useAuth } from '../hooks/useAuth'
import { getApiErrorMessage } from '../lib/api'

export default function RegisterPage() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [customerName, setCustomerName] = useState('')
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setIsSubmitting(true)
    try {
      await register(customerName, fullName, email, password)
      navigate('/app/onboarding', { replace: true })
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--color-concrete)] px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8">
          <p className="font-mono-tabular text-xs tracking-wide text-[var(--color-steel-light)]">WMS-01</p>
          <h1 className="mt-1 text-2xl font-semibold text-[var(--color-ink)]">Create your workspace</h1>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4 rounded-sm border border-[var(--color-line)] bg-white p-6">
          <Field label="Company name" htmlFor="customerName">
            <TextInput id="customerName" required value={customerName} onChange={(e) => setCustomerName(e.target.value)} />
          </Field>
          <Field label="Your full name" htmlFor="fullName">
            <TextInput id="fullName" required value={fullName} onChange={(e) => setFullName(e.target.value)} />
          </Field>
          <Field label="Work email" htmlFor="email">
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
              minLength={8}
              autoComplete="new-password"
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
            {isSubmitting ? 'Creating your workspace…' : 'Create workspace'}
          </PrimaryButton>

          <p className="text-center text-sm text-[var(--color-steel)]">
            Already have an account?{' '}
            <Link to="/login" className="text-[var(--color-ink)] underline">
              Sign in
            </Link>
          </p>
        </form>
      </div>
    </div>
  )
}
