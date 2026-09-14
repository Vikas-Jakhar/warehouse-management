import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { PrimaryButton } from '../components/FormControls'
import { api, getApiErrorMessage } from '../lib/api'

interface MovementTask {
  id: string
  sku_code: string
  sku_name: string
  from_location_code: string | null
  to_location_code: string
  status: 'pending' | 'in_progress' | 'confirmed' | 'cancelled'
  created_at: string
}

const STATUS_STYLES: Record<string, string> = {
  pending: 'bg-[var(--color-amber-soft)] text-[var(--color-amber)]',
  in_progress: 'bg-[var(--color-amber-soft)] text-[var(--color-amber)]',
  confirmed: 'bg-[var(--color-signal-soft)] text-[var(--color-signal)]',
  cancelled: 'bg-[var(--color-rust-soft)] text-[var(--color-rust)]',
}

function MovementRow({ warehouseId, movement, onChanged }: { warehouseId: string; movement: MovementTask; onChanged: () => void }) {
  const [error, setError] = useState<string | null>(null)
  const [notes, setNotes] = useState('')
  const [showConfirmForm, setShowConfirmForm] = useState(false)

  const start = useMutation({
    mutationFn: async () => api.post(`/warehouses/${warehouseId}/movements/${movement.id}/start`, {}),
    onSuccess: onChanged,
    onError: (err) => setError(getApiErrorMessage(err)),
  })

  const confirm = useMutation({
    mutationFn: async () => api.post(`/warehouses/${warehouseId}/movements/${movement.id}/confirm`, { notes: notes || null }),
    onSuccess: onChanged,
    onError: (err) => setError(getApiErrorMessage(err)),
  })

  const cancel = useMutation({
    mutationFn: async () => api.post(`/warehouses/${warehouseId}/movements/${movement.id}/cancel`, {}),
    onSuccess: onChanged,
    onError: (err) => setError(getApiErrorMessage(err)),
  })

  const isActionable = movement.status === 'pending' || movement.status === 'in_progress'

  return (
    <div className="rounded-sm border border-[var(--color-line)] bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-mono-tabular text-sm text-[var(--color-steel)]">{movement.sku_code}</span>
            <span className="font-medium text-[var(--color-ink)]">{movement.sku_name}</span>
          </div>
          <p className="mt-1 text-sm text-[var(--color-steel)]">
            {movement.from_location_code ? (
              <span className="font-mono-tabular">{movement.from_location_code}</span>
            ) : (
              <span className="italic">Unplaced</span>
            )}
            {' → '}
            <span className="font-mono-tabular font-medium text-[var(--color-ink)]">{movement.to_location_code}</span>
          </p>
        </div>
        <span className={'rounded-sm px-2 py-0.5 text-xs font-medium ' + STATUS_STYLES[movement.status]}>
          {movement.status.replace('_', ' ')}
        </span>
      </div>

      {isActionable && (
        <div className="mt-3 flex flex-col gap-2 border-t border-[var(--color-line)] pt-3">
          {showConfirmForm ? (
            <>
              <input
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Optional notes (e.g. 'placed on shelf')"
                className="w-full rounded-sm border border-[var(--color-line)] p-2 text-sm"
              />
              <div className="flex gap-2">
                <PrimaryButton onClick={() => confirm.mutate()} isLoading={confirm.isPending}>
                  {confirm.isPending ? 'Confirming…' : 'Confirm movement'}
                </PrimaryButton>
                <button onClick={() => setShowConfirmForm(false)} className="text-sm text-[var(--color-steel)] underline">
                  Cancel
                </button>
              </div>
            </>
          ) : (
            <div className="flex gap-2">
              {movement.status === 'pending' && (
                <button
                  onClick={() => start.mutate()}
                  disabled={start.isPending}
                  className="rounded-sm border border-[var(--color-line)] px-4 py-2 text-sm font-medium text-[var(--color-steel)] hover:bg-[var(--color-concrete)]"
                >
                  {start.isPending ? 'Starting…' : 'Start'}
                </button>
              )}
              <PrimaryButton onClick={() => setShowConfirmForm(true)}>Confirm movement</PrimaryButton>
              <button
                onClick={() => cancel.mutate()}
                disabled={cancel.isPending}
                className="rounded-sm border border-[var(--color-line)] px-4 py-2 text-sm font-medium text-[var(--color-rust)] hover:bg-[var(--color-rust-soft)]"
              >
                Cancel task
              </button>
            </div>
          )}
          {error && <p className="text-sm text-[var(--color-rust)]">{error}</p>}
        </div>
      )}
    </div>
  )
}

export default function WarehouseMovementsPage() {
  const { warehouseId = '' } = useParams()
  const queryClient = useQueryClient()

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['movements', warehouseId],
    queryFn: async () => (await api.get<{ items: MovementTask[]; total: number }>(`/warehouses/${warehouseId}/movements`)).data,
  })

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ['movements', warehouseId] })
    queryClient.invalidateQueries({ queryKey: ['inventory', warehouseId] })
  }

  return (
    <div className="mx-auto max-w-4xl px-8 py-8">
      <h1 className="text-xl font-semibold text-[var(--color-ink)]">Movement tasks</h1>
      <p className="mt-1 text-sm text-[var(--color-steel)]">
        The actual inventory location only changes once a movement here is confirmed — accepting a
        recommendation never moves anything by itself.
      </p>

      <div className="mt-6">
        {isLoading && (
          <div className="space-y-2">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-20 animate-pulse rounded-sm bg-[var(--color-concrete-dark)]" />
            ))}
          </div>
        )}

        {isError && (
          <div className="rounded-sm border border-[var(--color-rust)] bg-[var(--color-rust-soft)] p-4">
            <p className="text-sm text-[var(--color-rust)]">{getApiErrorMessage(error)}</p>
            <button onClick={() => refetch()} className="mt-2 text-sm underline">
              Try again
            </button>
          </div>
        )}

        {data && data.items.length === 0 && (
          <div className="rounded-sm border border-dashed border-[var(--color-line)] p-8 text-center">
            <p className="font-medium text-[var(--color-ink)]">No movement tasks</p>
            <p className="mt-1 text-sm text-[var(--color-steel)]">
              Accepting or overriding a recommendation creates a movement task here.
            </p>
          </div>
        )}

        {data && data.items.length > 0 && (
          <div className="flex flex-col gap-3">
            {data.items.map((m) => (
              <MovementRow key={m.id} warehouseId={warehouseId} movement={m} onChanged={invalidate} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
