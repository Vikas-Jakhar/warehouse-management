import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Field, PrimaryButton, TextInput } from '../components/FormControls'
import { api, getApiErrorMessage } from '../lib/api'

interface Warehouse {
  id: string
  name: string
  code: string
  warehouse_type: string
  default_inventory_policy: string
  is_active: boolean
}

interface WarehouseListResponse {
  items: Warehouse[]
  total: number
}

function useWarehouses() {
  return useQuery({
    queryKey: ['warehouses'],
    queryFn: async () => (await api.get<WarehouseListResponse>('/warehouses')).data,
  })
}

function CreateWarehouseForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState('')
  const [code, setCode] = useState('')
  const [policy, setPolicy] = useState('FIFO')
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: async () =>
      api.post('/warehouses', { name, code, default_inventory_policy: policy }),
    onSuccess: () => {
      setName('')
      setCode('')
      onCreated()
    },
    onError: (err) => setError(getApiErrorMessage(err)),
  })

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    mutation.mutate()
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-4 rounded-sm border border-[var(--color-line)] bg-white p-4">
      <div className="min-w-[180px] flex-1">
        <Field label="Warehouse name" htmlFor="wh-name">
          <TextInput id="wh-name" required value={name} onChange={(e) => setName(e.target.value)} placeholder="Main Distribution Center" />
        </Field>
      </div>
      <div className="w-32">
        <Field label="Code" htmlFor="wh-code">
          <TextInput id="wh-code" required value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="DC1" />
        </Field>
      </div>
      <div className="w-40">
        <Field label="Default policy" htmlFor="wh-policy">
          <select
            id="wh-policy"
            value={policy}
            onChange={(e) => setPolicy(e.target.value)}
            className="w-full rounded-sm border border-[var(--color-line)] bg-white px-3 py-2"
          >
            <option value="FIFO">FIFO</option>
            <option value="FEFO">FEFO</option>
            <option value="LIFO">LIFO</option>
          </select>
        </Field>
      </div>
      <PrimaryButton type="submit" isLoading={mutation.isPending}>
        {mutation.isPending ? 'Saving warehouse…' : 'Add warehouse'}
      </PrimaryButton>
      {error && <p className="basis-full text-sm text-[var(--color-rust)]">{error}</p>}
    </form>
  )
}

function StatusPill({ isActive }: { isActive: boolean }) {
  return (
    <span
      className={
        'rounded-sm px-2 py-0.5 text-xs font-medium ' +
        (isActive ? 'bg-[var(--color-signal-soft)] text-[var(--color-signal)]' : 'bg-[var(--color-rust-soft)] text-[var(--color-rust)]')
      }
    >
      {isActive ? 'Active' : 'Inactive'}
    </span>
  )
}

export default function WarehousesPage() {
  const { data, isLoading, isError, error, refetch } = useWarehouses()
  const queryClient = useQueryClient()

  return (
    <div className="mx-auto max-w-4xl px-8 py-8">
      <h1 className="text-xl font-semibold text-[var(--color-ink)]">Warehouses</h1>
      <p className="mt-1 text-sm text-[var(--color-steel)]">
        Every warehouse you configure here becomes selectable across forecasting, slotting, and movement tasks.
      </p>

      <div className="mt-6">
        <CreateWarehouseForm onCreated={() => queryClient.invalidateQueries({ queryKey: ['warehouses'] })} />
      </div>

      <div className="mt-6">
        {isLoading && (
          <div className="space-y-2">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-12 animate-pulse rounded-sm bg-[var(--color-concrete-dark)]" />
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
            <p className="font-medium text-[var(--color-ink)]">No warehouses created yet</p>
            <p className="mt-1 text-sm text-[var(--color-steel)]">
              Add your first warehouse above to start configuring its layout, SKUs, and inventory policies.
            </p>
          </div>
        )}

        {data && data.items.length > 0 && (
          <table className="w-full border-collapse overflow-hidden rounded-sm border border-[var(--color-line)] bg-white text-left text-sm">
            <thead>
              <tr className="border-b border-[var(--color-line)] text-xs uppercase text-[var(--color-steel-light)]">
                <th className="px-4 py-2 font-medium">Name</th>
                <th className="px-4 py-2 font-medium">Code</th>
                <th className="px-4 py-2 font-medium">Policy</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((wh) => (
                <tr key={wh.id} className="border-b border-[var(--color-line)] last:border-0">
                  <td className="px-4 py-3 font-medium text-[var(--color-ink)]">{wh.name}</td>
                  <td className="px-4 py-3 font-mono-tabular text-[var(--color-steel)]">{wh.code}</td>
                  <td className="px-4 py-3 text-[var(--color-steel)]">{wh.default_inventory_policy}</td>
                  <td className="px-4 py-3"><StatusPill isActive={wh.is_active} /></td>
                  <td className="px-4 py-3 text-right">
                    <Link to={`/app/warehouses/${wh.id}/layout`} className="text-sm text-[var(--color-steel)] underline hover:text-[var(--color-ink)]">
                      Layout
                    </Link>
                    <span className="mx-2 text-[var(--color-line)]">|</span>
                    <Link to={`/app/warehouses/${wh.id}/data`} className="text-sm text-[var(--color-steel)] underline hover:text-[var(--color-ink)]">
                      Data
                    </Link>
                    <span className="mx-2 text-[var(--color-line)]">|</span>
                    <Link to={`/app/warehouses/${wh.id}/forecasting`} className="text-sm text-[var(--color-steel)] underline hover:text-[var(--color-ink)]">
                      Forecasting
                    </Link>
                    <span className="mx-2 text-[var(--color-line)]">|</span>
                    <Link to={`/app/warehouses/${wh.id}/recommendations`} className="text-sm text-[var(--color-steel)] underline hover:text-[var(--color-ink)]">
                      Recommendations
                    </Link>
                    <span className="mx-2 text-[var(--color-line)]">|</span>
                    <Link to={`/app/warehouses/${wh.id}/movements`} className="text-sm text-[var(--color-steel)] underline hover:text-[var(--color-ink)]">
                      Movements
                    </Link>
                    <span className="mx-2 text-[var(--color-line)]">|</span>
                    <Link to={`/app/warehouses/${wh.id}/reports`} className="text-sm text-[var(--color-steel)] underline hover:text-[var(--color-ink)]">
                      Reports
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
