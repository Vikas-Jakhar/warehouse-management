import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { BulkUploadPanel } from '../components/BulkUploadPanel'
import { Field, PrimaryButton, TextInput } from '../components/FormControls'
import { api, getApiErrorMessage } from '../lib/api'

interface Sku {
  id: string
  sku_code: string
  name: string
  category: string | null
  fifo_required: boolean
  fefo_required: boolean
  lifo_permitted: boolean
  is_active: boolean
}

interface SkuListResponse {
  items: Sku[]
  total: number
}

function policyLabel(sku: Sku): string {
  if (sku.fefo_required) return 'FEFO'
  if (sku.lifo_permitted) return 'LIFO'
  if (sku.fifo_required) return 'FIFO'
  return '—'
}

function CreateSkuForm({ onCreated }: { onCreated: () => void }) {
  const [skuCode, setSkuCode] = useState('')
  const [name, setName] = useState('')
  const [category, setCategory] = useState('')
  const [requiresExpiry, setRequiresExpiry] = useState(false)
  const [fefoRequired, setFefoRequired] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: async () =>
      api.post('/skus', {
        sku_code: skuCode,
        name,
        category: category || null,
        requires_expiry: requiresExpiry,
        fefo_required: fefoRequired,
      }),
    onSuccess: () => {
      setSkuCode('')
      setName('')
      setCategory('')
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
      <div className="w-36">
        <Field label="SKU code" htmlFor="sku-code">
          <TextInput id="sku-code" required value={skuCode} onChange={(e) => setSkuCode(e.target.value.toUpperCase())} placeholder="SKU-001" />
        </Field>
      </div>
      <div className="min-w-[180px] flex-1">
        <Field label="Name" htmlFor="sku-name">
          <TextInput id="sku-name" required value={name} onChange={(e) => setName(e.target.value)} placeholder="Widget A" />
        </Field>
      </div>
      <div className="w-40">
        <Field label="Category" htmlFor="sku-category">
          <TextInput id="sku-category" value={category} onChange={(e) => setCategory(e.target.value)} placeholder="Optional" />
        </Field>
      </div>
      <label className="flex items-center gap-2 pb-2 text-sm text-[var(--color-steel)]">
        <input type="checkbox" checked={requiresExpiry} onChange={(e) => setRequiresExpiry(e.target.checked)} />
        Tracks expiry
      </label>
      <label className="flex items-center gap-2 pb-2 text-sm text-[var(--color-steel)]">
        <input
          type="checkbox"
          checked={fefoRequired}
          disabled={!requiresExpiry}
          onChange={(e) => setFefoRequired(e.target.checked)}
        />
        FEFO required
      </label>
      <PrimaryButton type="submit" isLoading={mutation.isPending}>
        {mutation.isPending ? 'Saving SKU…' : 'Add SKU'}
      </PrimaryButton>
      {error && <p className="basis-full text-sm text-[var(--color-rust)]">{error}</p>}
    </form>
  )
}

type Tab = 'list' | 'upload'

export default function SkusPage() {
  const [tab, setTab] = useState<Tab>('list')
  const queryClient = useQueryClient()
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['skus'],
    queryFn: async () => (await api.get<SkuListResponse>('/skus')).data,
  })

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ['skus'] })
  }

  return (
    <div className="mx-auto max-w-4xl px-8 py-8">
      <h1 className="text-xl font-semibold text-[var(--color-ink)]">SKU master</h1>
      <p className="mt-1 text-sm text-[var(--color-steel)]">
        Every product your warehouses stock. Rotation policy and storage requirements here drive both
        forecasting and slotting recommendations downstream.
      </p>

      <div className="mt-6 flex gap-1 border-b border-[var(--color-line)]">
        {(['list', 'upload'] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={
              'px-4 py-2 text-sm font-medium capitalize ' +
              (tab === t
                ? 'border-b-2 border-[var(--color-ink)] text-[var(--color-ink)]'
                : 'text-[var(--color-steel-light)] hover:text-[var(--color-ink)]')
            }
          >
            {t === 'list' ? 'SKUs' : 'Bulk upload'}
          </button>
        ))}
      </div>

      <div className="mt-6">
        {tab === 'list' && (
          <div className="flex flex-col gap-6">
            <CreateSkuForm onCreated={invalidate} />

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
                <p className="font-medium text-[var(--color-ink)]">No SKUs yet</p>
                <p className="mt-1 text-sm text-[var(--color-steel)]">
                  Add products one at a time above, or switch to Bulk upload for a full catalog import.
                </p>
              </div>
            )}

            {data && data.items.length > 0 && (
              <table className="w-full border-collapse overflow-hidden rounded-sm border border-[var(--color-line)] bg-white text-left text-sm">
                <thead>
                  <tr className="border-b border-[var(--color-line)] text-xs uppercase text-[var(--color-steel-light)]">
                    <th className="px-4 py-2 font-medium">Code</th>
                    <th className="px-4 py-2 font-medium">Name</th>
                    <th className="px-4 py-2 font-medium">Category</th>
                    <th className="px-4 py-2 font-medium">Rotation</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((sku) => (
                    <tr key={sku.id} className="border-b border-[var(--color-line)] last:border-0">
                      <td className="px-4 py-3 font-mono-tabular text-[var(--color-steel)]">{sku.sku_code}</td>
                      <td className="px-4 py-3 font-medium text-[var(--color-ink)]">{sku.name}</td>
                      <td className="px-4 py-3 text-[var(--color-steel)]">{sku.category ?? '—'}</td>
                      <td className="px-4 py-3 text-[var(--color-steel)]">{policyLabel(sku)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {tab === 'upload' && (
          <BulkUploadPanel
            uploadUrl="/skus/upload"
            templateUrl="/skus/upload/template"
            templateFilename="sku-template.csv"
            successNoun="SKUs"
            onCommitted={invalidate}
          />
        )}
      </div>
    </div>
  )
}
