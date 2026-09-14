import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

const NAV_ITEMS = [
  { to: '/app/dashboard', label: 'Dashboard' },
  { to: '/app/warehouses', label: 'Warehouses' },
  { to: '/app/skus', label: 'SKUs' },
  { to: '/app/audit-logs', label: 'Audit Logs' },
]

export default function AppShell() {
  const { user, logout } = useAuth()

  return (
    <div className="flex min-h-screen bg-[var(--color-concrete)]">
      <aside className="flex w-56 shrink-0 flex-col border-r border-[var(--color-line)] bg-[var(--color-ink)] text-white">
        <div className="border-b border-white/10 px-5 py-5">
          <p className="font-mono-tabular text-xs tracking-wide text-white/50">WMS-01</p>
          <p className="mt-1 font-semibold">Warehouse Ops</p>
        </div>
        <nav className="flex flex-1 flex-col gap-1 px-3 py-4">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                'rounded-sm px-3 py-2 text-sm font-medium transition-colors ' +
                (isActive ? 'bg-white/10 text-white' : 'text-white/70 hover:bg-white/5 hover:text-white')
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-white/10 px-5 py-4">
          <p className="truncate text-sm text-white">{user?.full_name}</p>
          <p className="truncate text-xs text-white/50">{user?.role}</p>
          <button
            onClick={logout}
            className="mt-3 text-sm text-white/70 underline decoration-white/30 hover:text-white"
          >
            Sign out
          </button>
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  )
}
