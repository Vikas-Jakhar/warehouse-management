import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { api, getApiErrorMessage } from '../lib/api'

interface RecentActivityItem {
  entity_type: string
  entity_id: string
  action: string
  created_at: string
}

interface CustomerOverview {
  total_warehouses: number
  total_skus: number
  total_inventory_units: number
  pending_recommendations: number
  pending_movement_tasks: number
  recent_activity: RecentActivityItem[]
}

const ACTION_STYLES: Record<string, string> = {
  create: 'bg-[var(--color-signal-soft)] text-[var(--color-signal)]',
  register: 'bg-[var(--color-signal-soft)] text-[var(--color-signal)]',
  bulk_upload: 'bg-[var(--color-signal-soft)] text-[var(--color-signal)]',
  update: 'bg-[var(--color-amber-soft)] text-[var(--color-amber)]',
  accept: 'bg-[var(--color-signal-soft)] text-[var(--color-signal)]',
  reject: 'bg-[var(--color-rust-soft)] text-[var(--color-rust)]',
  location_confirmed: 'bg-[var(--color-signal-soft)] text-[var(--color-signal)]',
  deactivate: 'bg-[var(--color-rust-soft)] text-[var(--color-rust)]',
}

function StatCard({ label, value, href }: { label: string; value: string | number; href?: string }) {
  const content = (
    <div className="rounded-sm border border-[var(--color-line)] bg-white p-4">
      <p className="text-xs text-[var(--color-steel-light)]">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-[var(--color-ink)]">{value}</p>
    </div>
  )
  return href ? (
    <Link to={href} className="block transition-shadow hover:shadow-sm">
      {content}
    </Link>
  ) : (
    content
  )
}

export default function DashboardPage() {
  const { user } = useAuth()
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['dashboard'],
    queryFn: async () => (await api.get<CustomerOverview>('/dashboard')).data,
  })

  return (
    <div className="mx-auto max-w-4xl px-8 py-8">
      <p className="font-mono-tabular text-xs text-[var(--color-steel-light)]">WORKSPACE OVERVIEW</p>
      <h1 className="mt-1 text-xl font-semibold text-[var(--color-ink)]">Welcome back, {user?.full_name}</h1>

      {isLoading && (
        <div className="mt-6 grid grid-cols-3 gap-4">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-20 animate-pulse rounded-sm bg-[var(--color-concrete-dark)]" />
          ))}
        </div>
      )}

      {isError && (
        <div className="mt-6 rounded-sm border border-[var(--color-rust)] bg-[var(--color-rust-soft)] p-4">
          <p className="text-sm text-[var(--color-rust)]">{getApiErrorMessage(error)}</p>
          <button onClick={() => refetch()} className="mt-2 text-sm underline">
            Try again
          </button>
        </div>
      )}

      {data && (
        <>
          <div className="mt-6 grid grid-cols-3 gap-4">
            <StatCard label="Warehouses" value={data.total_warehouses} href="/app/warehouses" />
            <StatCard label="SKUs" value={data.total_skus} href="/app/skus" />
            <StatCard label="Total inventory units" value={data.total_inventory_units} />
            <StatCard label="Pending recommendations" value={data.pending_recommendations} />
            <StatCard label="Pending movement tasks" value={data.pending_movement_tasks} />
          </div>

          {data.total_warehouses === 0 ? (
            <div className="mt-8 rounded-sm border border-dashed border-[var(--color-line)] p-8 text-center">
              <p className="font-medium text-[var(--color-ink)]">Set up your first warehouse</p>
              <p className="mt-1 text-sm text-[var(--color-steel)]">
                Everything on this dashboard depends on at least one configured warehouse.
              </p>
              <Link
                to="/app/warehouses"
                className="mt-4 inline-block rounded-sm bg-[var(--color-ink)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--color-steel)]"
              >
                Create a warehouse
              </Link>
            </div>
          ) : (
            <div className="mt-8">
              <h2 className="text-sm font-medium text-[var(--color-ink)]">Recent activity</h2>
              {data.recent_activity.length === 0 ? (
                <p className="mt-2 text-sm text-[var(--color-steel)]">No activity recorded yet.</p>
              ) : (
                <ul className="mt-2 divide-y divide-[var(--color-line)] rounded-sm border border-[var(--color-line)] bg-white">
                  {data.recent_activity.map((item, i) => (
                    <li key={i} className="flex items-center justify-between px-4 py-2 text-sm">
                      <span className="text-[var(--color-ink)]">
                        {item.entity_type.replace('_', ' ')}{' '}
                        <span className="font-mono-tabular text-xs text-[var(--color-steel-light)]">
                          {item.entity_id !== 'bulk' ? `#${item.entity_id.slice(0, 8)}` : '(bulk)'}
                        </span>
                      </span>
                      <span className={'rounded-sm px-2 py-0.5 text-xs font-medium ' + (ACTION_STYLES[item.action] ?? 'bg-[var(--color-concrete-dark)] text-[var(--color-steel)]')}>
                        {item.action.replace('_', ' ')}
                      </span>
                      <span className="font-mono-tabular text-xs text-[var(--color-steel-light)]">
                        {new Date(item.created_at).toLocaleString()}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
