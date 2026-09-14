import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Field, PrimaryButton, TextInput } from '../components/FormControls'
import { api, getApiErrorMessage } from '../lib/api'

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const token = searchParams.get('token') ?? ''
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [done, setDone] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setIsSubmitting(true)
    try {
      await api.post('/auth/reset-password', { token, new_password: password })
      setDone(true)
      setTimeout(() => navigate('/login'), 1500)
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setIsSubmitting(false)
    }
  }

  if (!token) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--color-concrete)] px-4">
        <div className="rounded-sm border border-[var(--color-line)] bg-white p-6 text-center">
          <p className="text-[var(--color-ink)]">This reset link is missing its token.</p>
          <Link to="/forgot-password" className="mt-2 inline-block text-sm text-[var(--color-steel)] underline">
            Request a new link
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--color-concrete)] px-4">
      <div className="w-full max-w-sm">
        <h1 className="mb-8 text-2xl font-semibold text-[var(--color-ink)]">Choose a new password</h1>
        {done ? (
          <div className="rounded-sm border border-[var(--color-line)] bg-white p-6">
            <p className="text-[var(--color-signal)]">Password updated. Redirecting to sign in…</p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col gap-4 rounded-sm border border-[var(--color-line)] bg-white p-6">
            <Field label="New password" htmlFor="password">
              <TextInput
                id="password"
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>
            {error && <p role="alert" className="text-sm text-[var(--color-rust)]">{error}</p>}
            <PrimaryButton type="submit" isLoading={isSubmitting} className="w-full">
              {isSubmitting ? 'Updating password…' : 'Update password'}
            </PrimaryButton>
          </form>
        )}
      </div>
    </div>
  )
}
