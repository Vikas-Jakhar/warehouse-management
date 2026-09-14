import { useQuery } from '@tanstack/react-query'
import { api, getApiErrorMessage } from '../lib/api'

interface AuditLogEntry {
  id: string
  entity_type: string
  entity_id: string
  action: string
  created_at: string
}

interface AuditLogResponse {
  items: AuditLogEntry[]
  total: number
}

function ActionPill({ action }: { action: string }) {
  const colorMap: Record<string, string> = {
    create: 'bg-[var(--color-signal-soft)] text-[var(--color-signal)]',
    register: 'bg-[var(--color-signal-soft)] text-[var(--color-signal)]',
    update: 'bg-[var(--color-amber-soft)] text-[var(--color-amber)]',
    deactivate: 'bg-[var(--color-rust-soft)] text-[var(--color-rust)]',
  }
  return (
    <span className={'rounded-sm px-2 py-0.5 text-xs font-medium ' + (colorMap[action] ?? 'bg-[var(--color-concrete-dark)] text-[var(--color-steel)]')}>
      {action}
    </span>
  )
}

export default function AuditLogsPage() {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['audit-logs'],
    queryFn: async () => (await api.get<AuditLogResponse>('/audit-logs')).data,
  })

  return (
    <div className="mx-auto max-w-4xl px-8 py-8">
      <h1 className="text-xl font-semibold text-[var(--color-ink)]">Audit Logs</h1>
      <p className="mt-1 text-sm text-[var(--color-steel)]">
        A complete history of who did what, and when, across this workspace.
      </p>

      <div className="mt-6">
        {isLoading && (
          <div className="space-y-2">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-10 animate-pulse rounded-sm bg-[var(--color-concrete-dark)]" />
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
            <p className="font-medium text-[var(--color-ink)]">No activity recorded yet</p>
            <p className="mt-1 text-sm text-[var(--color-steel)]">
              Actions like creating a warehouse or approving a recommendation will show up here.
            </p>
          </div>
        )}

        {data && data.items.length > 0 && (
          <table className="w-full border-collapse overflow-hidden rounded-sm border border-[var(--color-line)] bg-white text-left text-sm">
            <thead>
              <tr className="border-b border-[var(--color-line)] text-xs uppercase text-[var(--color-steel-light)]">
                <th className="px-4 py-2 font-medium">When</th>
                <th className="px-4 py-2 font-medium">Entity</th>
                <th className="px-4 py-2 font-medium">Action</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((log) => (
                <tr key={log.id} className="border-b border-[var(--color-line)] last:border-0">
                  <td className="px-4 py-3 font-mono-tabular text-[var(--color-steel)]">
                    {new Date(log.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-[var(--color-ink)]">
                    {log.entity_type} <span className="font-mono-tabular text-[var(--color-steel-light)]">#{log.entity_id.slice(0, 8)}</span>
                  </td>
                  <td className="px-4 py-3"><ActionPill action={log.action} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
