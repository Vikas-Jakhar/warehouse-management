import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { BulkUploadPanel } from '../components/BulkUploadPanel'
import { api, getApiErrorMessage } from '../lib/api'

interface SalesRecord {
  id: string
  sku_id: string
  sale_date: string
  quantity_sold: number
  stockout_flag: boolean
}

interface InventoryRecord {
  id: string
  sku_id: string
  quantity: number
  reserved_quantity: number
  available_quantity: number
  status: string
}

function StatusPill({ status }: { status: string }) {
  const colorMap: Record<string, string> = {
    in_stock: 'bg-[var(--color-signal-soft)] text-[var(--color-signal)]',
    awaiting_putaway: 'bg-[var(--color-amber-soft)] text-[var(--color-amber)]',
    damaged: 'bg-[var(--color-rust-soft)] text-[var(--color-rust)]',
    quarantined: 'bg-[var(--color-rust-soft)] text-[var(--color-rust)]',
    reserved: 'bg-[var(--color-concrete-dark)] text-[var(--color-steel)]',
  }
  return (
    <span className={'rounded-sm px-2 py-0.5 text-xs font-medium ' + (colorMap[status] ?? 'bg-[var(--color-concrete-dark)] text-[var(--color-steel)]')}>
      {status.replace('_', ' ')}
    </span>
  )
}

function SalesTab({ warehouseId }: { warehouseId: string }) {
  const queryClient = useQueryClient()
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['sales', warehouseId],
    queryFn: async () => (await api.get<{ items: SalesRecord[]; total: number }>(`/warehouses/${warehouseId}/sales`)).data,
  })

  return (
    <div className="flex flex-col gap-6">
      <BulkUploadPanel
        uploadUrl={`/warehouses/${warehouseId}/sales/upload`}
        templateUrl={`/warehouses/${warehouseId}/sales/upload/template`}
        templateFilename="sales-template.csv"
        successNoun="sales records"
        onCommitted={() => queryClient.invalidateQueries({ queryKey: ['sales', warehouseId] })}
      />

      {isLoading && <div className="h-32 animate-pulse rounded-sm bg-[var(--color-concrete-dark)]" />}
      {isError && (
        <div className="rounded-sm border border-[var(--color-rust)] bg-[var(--color-rust-soft)] p-4">
          <p className="text-sm text-[var(--color-rust)]">{getApiErrorMessage(error)}</p>
          <button onClick={() => refetch()} className="mt-2 text-sm underline">
            Try again
          </button>
        </div>
      )}
      {data && data.items.length === 0 && (
        <p className="rounded-sm border border-dashed border-[var(--color-line)] p-6 text-center text-sm text-[var(--color-steel)]">
          No sales history uploaded for this warehouse yet — forecasting needs this data to run.
        </p>
      )}
      {data && data.items.length > 0 && (
        <table className="w-full border-collapse overflow-hidden rounded-sm border border-[var(--color-line)] bg-white text-left text-sm">
          <thead>
            <tr className="border-b border-[var(--color-line)] text-xs uppercase text-[var(--color-steel-light)]">
              <th className="px-4 py-2 font-medium">Date</th>
              <th className="px-4 py-2 font-medium">Qty sold</th>
              <th className="px-4 py-2 font-medium">Stockout</th>
            </tr>
          </thead>
          <tbody>
            {data.items.slice(0, 25).map((r) => (
              <tr key={r.id} className="border-b border-[var(--color-line)] last:border-0">
                <td className="px-4 py-3 font-mono-tabular text-[var(--color-steel)]">{r.sale_date}</td>
                <td className="px-4 py-3 text-[var(--color-ink)]">{r.quantity_sold}</td>
                <td className="px-4 py-3 text-[var(--color-steel)]">{r.stockout_flag ? 'Yes' : 'No'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {data && data.total > 25 && (
        <p className="text-xs text-[var(--color-steel-light)]">Showing 25 of {data.total} records.</p>
      )}
    </div>
  )
}

function InventoryTab({ warehouseId }: { warehouseId: string }) {
  const queryClient = useQueryClient()
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['inventory', warehouseId],
    queryFn: async () =>
      (await api.get<{ items: InventoryRecord[]; total: number }>(`/warehouses/${warehouseId}/inventory`)).data,
  })

  return (
    <div className="flex flex-col gap-6">
      <BulkUploadPanel
        uploadUrl={`/warehouses/${warehouseId}/inventory/upload`}
        templateUrl={`/warehouses/${warehouseId}/inventory/upload/template`}
        templateFilename="inventory-template.csv"
        successNoun="inventory records"
        onCommitted={() => queryClient.invalidateQueries({ queryKey: ['inventory', warehouseId] })}
      />

      {isLoading && <div className="h-32 animate-pulse rounded-sm bg-[var(--color-concrete-dark)]" />}
      {isError && (
        <div className="rounded-sm border border-[var(--color-rust)] bg-[var(--color-rust-soft)] p-4">
          <p className="text-sm text-[var(--color-rust)]">{getApiErrorMessage(error)}</p>
          <button onClick={() => refetch()} className="mt-2 text-sm underline">
            Try again
          </button>
        </div>
      )}
      {data && data.items.length === 0 && (
        <p className="rounded-sm border border-dashed border-[var(--color-line)] p-6 text-center text-sm text-[var(--color-steel)]">
          No inventory uploaded for this warehouse yet.
        </p>
      )}
      {data && data.items.length > 0 && (
        <table className="w-full border-collapse overflow-hidden rounded-sm border border-[var(--color-line)] bg-white text-left text-sm">
          <thead>
            <tr className="border-b border-[var(--color-line)] text-xs uppercase text-[var(--color-steel-light)]">
              <th className="px-4 py-2 font-medium">Quantity</th>
              <th className="px-4 py-2 font-medium">Reserved</th>
              <th className="px-4 py-2 font-medium">Available</th>
              <th className="px-4 py-2 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {data.items.slice(0, 25).map((r) => (
              <tr key={r.id} className="border-b border-[var(--color-line)] last:border-0">
                <td className="px-4 py-3 font-mono-tabular text-[var(--color-ink)]">{r.quantity}</td>
                <td className="px-4 py-3 font-mono-tabular text-[var(--color-steel)]">{r.reserved_quantity}</td>
                <td className="px-4 py-3 font-mono-tabular text-[var(--color-steel)]">{r.available_quantity}</td>
                <td className="px-4 py-3"><StatusPill status={r.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {data && data.total > 25 && (
        <p className="text-xs text-[var(--color-steel-light)]">Showing 25 of {data.total} records.</p>
      )}
    </div>
  )
}

type Tab = 'sales' | 'inventory'

export default function WarehouseDataPage() {
  const { warehouseId = '' } = useParams()
  const [tab, setTab] = useState<Tab>('sales')

  return (
    <div className="mx-auto max-w-4xl px-8 py-8">
      <h1 className="text-xl font-semibold text-[var(--color-ink)]">Sales & inventory data</h1>
      <p className="mt-1 text-sm text-[var(--color-steel)]">
        Upload historical demand and current stock for this warehouse. Both feed the forecasting and
        slotting engines once they're online.
      </p>

      <div className="mt-6 flex gap-1 border-b border-[var(--color-line)]">
        {(['sales', 'inventory'] as Tab[]).map((t) => (
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
            {t === 'sales' ? 'Sales history' : 'Inventory'}
          </button>
        ))}
      </div>

      <div className="mt-6">{tab === 'sales' ? <SalesTab warehouseId={warehouseId} /> : <InventoryTab warehouseId={warehouseId} />}</div>
    </div>
  )
}
