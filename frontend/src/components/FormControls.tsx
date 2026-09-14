import type { ButtonHTMLAttributes, InputHTMLAttributes, LabelHTMLAttributes, ReactNode } from 'react'

export function Field({
  label,
  htmlFor,
  error,
  children,
}: {
  label: string
  htmlFor: string
  error?: string
  children: ReactNode
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-sm font-medium text-[var(--color-steel)]">
        {label}
      </label>
      {children}
      {error && <p className="text-sm text-[var(--color-rust)]">{error}</p>}
    </div>
  )
}

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={
        'w-full rounded-sm border border-[var(--color-line)] bg-white px-3 py-2 text-[var(--color-ink)] ' +
        'placeholder:text-[var(--color-steel-light)] focus-visible:border-[var(--color-amber)] ' +
        (props.className ?? '')
      }
    />
  )
}

export function PrimaryButton({
  children,
  isLoading,
  className,
  ...rest
}: { children: ReactNode; isLoading?: boolean } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...rest}
      disabled={isLoading || rest.disabled}
      className={
        'inline-flex items-center justify-center gap-2 rounded-sm bg-[var(--color-ink)] px-4 py-2 ' +
        'font-medium text-white transition-colors hover:bg-[var(--color-steel)] disabled:cursor-not-allowed ' +
        'disabled:opacity-60 ' +
        (className ?? '')
      }
    >
      {isLoading && (
        <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" />
      )}
      {children}
    </button>
  )
}

export function LabelTag(props: LabelHTMLAttributes<HTMLSpanElement>) {
  return <span {...props} />
}
