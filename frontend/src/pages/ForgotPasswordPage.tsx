import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Field, PrimaryButton, TextInput } from '../components/FormControls'
import { api, getApiErrorMessage } from '../lib/api'

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setIsSubmitting(true)
    try {
      await api.post('/auth/forgot-password', { email })
      setSubmitted(true)
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--color-concrete)] px-4">
      <div className="w-full max-w-sm">
        <h1 className="mb-8 text-2xl font-semibold text-[var(--color-ink)]">Reset your password</h1>

        {submitted ? (
          <div className="rounded-sm border border-[var(--color-line)] bg-white p-6">
            <p className="text-[var(--color-ink)]">
              If an account exists for <span className="font-mono-tabular">{email}</span>, a reset link is on its way.
            </p>
            <Link to="/login" className="mt-4 inline-block text-sm text-[var(--color-steel)] hover:text-[var(--color-ink)]">
              Back to sign in
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col gap-4 rounded-sm border border-[var(--color-line)] bg-white p-6">
            <Field label="Email" htmlFor="email">
              <TextInput
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </Field>
            {error && <p role="alert" className="text-sm text-[var(--color-rust)]">{error}</p>}
            <PrimaryButton type="submit" isLoading={isSubmitting} className="w-full">
              {isSubmitting ? 'Sending link…' : 'Send reset link'}
            </PrimaryButton>
            <Link to="/login" className="text-center text-sm text-[var(--color-steel)] hover:text-[var(--color-ink)]">
              Back to sign in
            </Link>
          </form>
        )}
      </div>
    </div>
  )
}
