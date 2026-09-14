import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api, getApiErrorMessage } from '../lib/api'

interface CategoryQuantity {
  category: string
  quantity: number
}
interface DemandTrendPoint {
  date: string
  quantity_sold: number
}
interface SkuVelocityEntry {
  sku_id: string
  sku_code: string
  name: string
  velocity_30d: number
}
interface StockRiskEntry extends SkuVelocityEntry {
  on_hand: number
  reorder_point: number | null
  max_qty: number | null
}
interface AgingBucket {
  bucket: string
  quantity: number
}
interface ExpiringInventoryEntry {
  sku_code: string
  name: string
  expiry_date: string
  quantity: number
}
interface WarehouseOverview {
  storage_utilization_pct: number
  total_storage_locations: number
  occupied_storage_locations: number
  inventory_by_category: CategoryQuantity[]
  demand_trend: DemandTrendPoint[]
  fast_movers: SkuVelocityEntry[]
  slow_movers: SkuVelocityEntry[]
  stockout_risk_skus: StockRiskEntry[]
  overstock_risk_skus: StockRiskEntry[]
  inventory_aging: AgingBucket[]
  expiring_inventory: ExpiringInventoryEntry[]
  recommendation_status_counts: Record<string, number>
  movement_status_counts: Record<string, number>
  skus_with_sales_history: number
  skus_with_forecast: number
}

const STATUS_COLORS: Record<string, string> = {
  pending_review: '#D98E2C',
  accepted: '#2E8B57',
  overridden: '#2E8B57',
  rejected: '#B4432F',
  movement_confirmed: '#3A4A5C',
  cancelled: '#B4432F',
  expired: '#64748B',
  pending: '#D98E2C',
  in_progress: '#D98E2C',
  confirmed: '#2E8B57',
}

function Card({ title, children, className = '' }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={'rounded-sm border border-[var(--color-line)] bg-white p-4 ' + className}>
      <p className="mb-3 text-sm font-medium text-[var(--color-ink)]">{title}</p>
      {children}
    </div>
  )
}

function EmptyNote({ text }: { text: string }) {
  return <p className="text-sm text-[var(--color-steel-light)]">{text}</p>
}

function StatusPieChart({ counts }: { counts: Record<string, number> }) {
  const data = Object.entries(counts).map(([status, count]) => ({ name: status.replace('_', ' '), status, value: count }))
  if (data.length === 0) return <EmptyNote text="No data yet." />
  return (
    <ResponsiveContainer width="100%" height={200}>
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={70}>
          {data.map((entry, i) => (
            <Cell key={i} fill={STATUS_COLORS[entry.status] ?? '#64748B'} />
          ))}
        </Pie>
        <Tooltip contentStyle={{ fontSize: 12 }} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
      </PieChart>
    </ResponsiveContainer>
  )
}

export default function WarehouseReportsPage() {
  const { warehouseId = '' } = useParams()

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['reports-overview', warehouseId],
    queryFn: async () => (await api.get<WarehouseOverview>(`/warehouses/${warehouseId}/reports/overview`)).data,
  })

  if (isLoading) {
    return (
      <div className="mx-auto max-w-5xl px-8 py-8">
        <div className="grid grid-cols-2 gap-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-64 animate-pulse rounded-sm bg-[var(--color-concrete-dark)]" />
          ))}
        </div>
      </div>
    )
  }

  if (isError) {
    return (
      <div className="mx-auto max-w-5xl px-8 py-8">
        <div className="rounded-sm border border-[var(--color-rust)] bg-[var(--color-rust-soft)] p-4">
          <p className="text-sm text-[var(--color-rust)]">{getApiErrorMessage(error)}</p>
          <button onClick={() => refetch()} className="mt-2 text-sm underline">
            Try again
          </button>
        </div>
      </div>
    )
  }

  if (!data) return null

  return (
    <div className="mx-auto max-w-5xl px-8 py-8">
      <h1 className="text-xl font-semibold text-[var(--color-ink)]">Reports</h1>
      <p className="mt-1 text-sm text-[var(--color-steel)]">
        A live view of utilization, demand, risk, and workflow activity for this warehouse.
      </p>

      <div className="mt-6 grid grid-cols-4 gap-4">
        <Card title="Storage utilization">
          <p className="text-3xl font-semibold text-[var(--color-ink)]">{data.storage_utilization_pct}%</p>
          <p className="mt-1 text-xs text-[var(--color-steel-light)]">
            {data.occupied_storage_locations} of {data.total_storage_locations} locations occupied
          </p>
        </Card>
        <Card title="Forecast coverage">
          <p className="text-3xl font-semibold text-[var(--color-ink)]">{data.skus_with_forecast}</p>
          <p className="mt-1 text-xs text-[var(--color-steel-light)]">of {data.skus_with_sales_history} SKUs with sales history</p>
        </Card>
        <Card title="Stockout risk">
          <p className="text-3xl font-semibold text-[var(--color-rust)]">{data.stockout_risk_skus.length}</p>
          <p className="mt-1 text-xs text-[var(--color-steel-light)]">SKUs at or below reorder point</p>
        </Card>
        <Card title="Overstock risk">
          <p className="text-3xl font-semibold text-[var(--color-amber)]">{data.overstock_risk_skus.length}</p>
          <p className="mt-1 text-xs text-[var(--color-steel-light)]">SKUs above max storage qty</p>
        </Card>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-4">
        <Card title="Demand trend (last 30 days)">
          {data.demand_trend.length === 0 ? (
            <EmptyNote text="No sales recorded in the last 30 days." />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={data.demand_trend}>
                <CartesianGrid stroke="var(--color-line)" strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={20} />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip contentStyle={{ fontSize: 12 }} />
                <Line type="monotone" dataKey="quantity_sold" stroke="var(--color-steel)" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title="Inventory by category">
          {data.inventory_by_category.length === 0 ? (
            <EmptyNote text="No inventory uploaded yet." />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={data.inventory_by_category}>
                <CartesianGrid stroke="var(--color-line)" strokeDasharray="3 3" />
                <XAxis dataKey="category" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip contentStyle={{ fontSize: 12 }} />
                <Bar dataKey="quantity" fill="var(--color-steel)" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title="Inventory aging">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={data.inventory_aging}>
              <CartesianGrid stroke="var(--color-line)" strokeDasharray="3 3" />
              <XAxis dataKey="bucket" tick={{ fontSize: 10 }} label={{ value: 'days', position: 'insideBottom', offset: -2, fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} />
              <Tooltip contentStyle={{ fontSize: 12 }} />
              <Bar dataKey="quantity" fill="var(--color-amber)" />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Recommendation status">
          <StatusPieChart counts={data.recommendation_status_counts} />
        </Card>

        <Card title="Movement activity">
          <StatusPieChart counts={data.movement_status_counts} />
        </Card>

        <Card title="SKU velocity">
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <p className="mb-1 font-medium text-[var(--color-signal)]">Fast movers</p>
              {data.fast_movers.length === 0 ? (
                <EmptyNote text="None yet." />
              ) : (
                <ul className="space-y-1">
                  {data.fast_movers.map((s) => (
                    <li key={s.sku_id} className="font-mono-tabular text-xs text-[var(--color-steel)]">
                      {s.sku_code} — {s.velocity_30d.toFixed(0)}/30d
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div>
              <p className="mb-1 font-medium text-[var(--color-steel-light)]">Slow movers</p>
              {data.slow_movers.length === 0 ? (
                <EmptyNote text="None yet." />
              ) : (
                <ul className="space-y-1">
                  {data.slow_movers.map((s) => (
                    <li key={s.sku_id} className="font-mono-tabular text-xs text-[var(--color-steel)]">
                      {s.sku_code} — {s.velocity_30d.toFixed(0)}/30d
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </Card>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-4">
        <Card title="Stockout risk">
          {data.stockout_risk_skus.length === 0 ? (
            <EmptyNote text="No SKUs currently at risk." />
          ) : (
            <ul className="divide-y divide-[var(--color-line)] text-sm">
              {data.stockout_risk_skus.map((s) => (
                <li key={s.sku_id} className="flex justify-between py-1.5">
                  <span className="font-mono-tabular text-[var(--color-steel)]">{s.sku_code}</span>
                  <span className="text-[var(--color-rust)]">
                    {s.on_hand} on hand (reorder at {s.reorder_point})
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Expiring inventory (next 30 days)">
          {data.expiring_inventory.length === 0 ? (
            <EmptyNote text="Nothing expiring soon." />
          ) : (
            <ul className="divide-y divide-[var(--color-line)] text-sm">
              {data.expiring_inventory.map((e, i) => (
                <li key={i} className="flex justify-between py-1.5">
                  <span className="font-mono-tabular text-[var(--color-steel)]">{e.sku_code}</span>
                  <span className="text-[var(--color-amber)]">
                    {e.quantity} units — expires {e.expiry_date}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  )
}
