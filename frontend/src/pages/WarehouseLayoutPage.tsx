import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useRef, useState, type FormEvent } from 'react'
import { useParams } from 'react-router-dom'
import { Field, PrimaryButton, TextInput } from '../components/FormControls'
import { api, getApiErrorMessage } from '../lib/api'

interface Zone {
  id: string
  name: string
  zone_code: string
  zone_type: string
}

interface StorageLocation {
  id: string
  zone_id: string | null
  location_code: string
  location_type: string
  storage_type: string
  x: number
  y: number
  width: number
  height: number
  is_active: boolean
  is_blocked: boolean
  is_available: boolean
}

interface RowErrorEntry {
  row: number
  field: string
  message: string
}

interface UploadResult {
  total_rows: number
  valid_rows: number
  invalid_rows: number
  is_valid: boolean
  committed: boolean
  locations_created: number
  zones_created: number
  errors: RowErrorEntry[]
  error_report_csv: string | null
}

const LOCATION_TYPE_COLORS: Record<string, string> = {
  receiving: 'var(--color-signal)',
  dispatch: 'var(--color-rust)',
  storage: 'var(--color-steel)',
  staging: 'var(--color-amber)',
}

function locationColor(loc: StorageLocation): string {
  if (loc.is_blocked || !loc.is_active) return 'var(--color-rust)'
  return LOCATION_TYPE_COLORS[loc.location_type] ?? 'var(--color-steel-light)'
}

function LayoutCanvas({
  locations,
  onCanvasClick,
}: {
  locations: StorageLocation[]
  onCanvasClick: (x: number, y: number) => void
}) {
  const svgRef = useRef<SVGSVGElement>(null)
  const bounds = useMemo(() => {
    if (locations.length === 0) return { maxX: 100, maxY: 100 }
    const maxX = Math.max(...locations.map((l) => l.x + l.width)) + 10
    const maxY = Math.max(...locations.map((l) => l.y + l.height)) + 10
    return { maxX: Math.max(maxX, 100), maxY: Math.max(maxY, 100) }
  }, [locations])

  function handleClick(e: React.MouseEvent<SVGSVGElement>) {
    const svg = svgRef.current
    if (!svg) return
    const rect = svg.getBoundingClientRect()
    const scaleX = bounds.maxX / rect.width
    const scaleY = bounds.maxY / rect.height
    const x = Math.round((e.clientX - rect.left) * scaleX)
    const y = Math.round((e.clientY - rect.top) * scaleY)
    onCanvasClick(x, y)
  }

  return (
    <svg
      ref={svgRef}
      viewBox={`0 0 ${bounds.maxX} ${bounds.maxY}`}
      onClick={handleClick}
      className="h-[420px] w-full cursor-crosshair rounded-sm border border-[var(--color-line)] bg-white"
    >
      <rect x={0} y={0} width={bounds.maxX} height={bounds.maxY} fill="var(--color-concrete)" />
      {locations.map((loc) => (
        <g key={loc.id}>
          <rect
            x={loc.x}
            y={loc.y}
            width={loc.width}
            height={loc.height}
            fill={locationColor(loc)}
            fillOpacity={0.85}
            stroke="white"
            strokeWidth={0.3}
          />
          <text
            x={loc.x + loc.width / 2}
            y={loc.y + loc.height / 2}
            fontSize={Math.min(loc.width, loc.height) * 0.35}
            fill="white"
            textAnchor="middle"
            dominantBaseline="middle"
            style={{ fontFamily: 'var(--font-mono)' }}
          >
            {loc.location_code}
          </text>
        </g>
      ))}
    </svg>
  )
}

function AddLocationForm({
  warehouseId,
  zones,
  clickedPoint,
  onCreated,
}: {
  warehouseId: string
  zones: Zone[]
  clickedPoint: { x: number; y: number } | null
  onCreated: () => void
}) {
  const [code, setCode] = useState('')
  const [locationType, setLocationType] = useState('storage')
  const [storageType, setStorageType] = useState('bin')
  const [zoneId, setZoneId] = useState('')
  const [width, setWidth] = useState('5')
  const [height, setHeight] = useState('5')
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: async () => {
      if (!clickedPoint) throw new Error('Click on the canvas to place this location first.')
      return api.post(`/warehouses/${warehouseId}/locations`, {
        location_code: code,
        location_type: locationType,
        storage_type: storageType,
        zone_id: zoneId || null,
        x: clickedPoint.x,
        y: clickedPoint.y,
        width: Number(width),
        height: Number(height),
      })
    },
    onSuccess: () => {
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
    <form onSubmit={handleSubmit} className="flex flex-col gap-3 rounded-sm border border-[var(--color-line)] bg-white p-4">
      <p className="text-sm font-medium text-[var(--color-ink)]">Add a location</p>
      <p className="text-xs text-[var(--color-steel)]">
        {clickedPoint
          ? `Placing at x=${clickedPoint.x}, y=${clickedPoint.y}. Click the canvas again to reposition.`
          : 'Click anywhere on the canvas to choose a position.'}
      </p>
      <Field label="Location code" htmlFor="loc-code">
        <TextInput id="loc-code" required value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="A-01-01" />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Type" htmlFor="loc-type">
          <select
            id="loc-type"
            value={locationType}
            onChange={(e) => setLocationType(e.target.value)}
            className="w-full rounded-sm border border-[var(--color-line)] bg-white px-3 py-2"
          >
            {['storage', 'receiving', 'dispatch', 'staging', 'putaway', 'picking', 'packing', 'entrance'].map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Storage type" htmlFor="storage-type">
          <select
            id="storage-type"
            value={storageType}
            onChange={(e) => setStorageType(e.target.value)}
            className="w-full rounded-sm border border-[var(--color-line)] bg-white px-3 py-2"
          >
            {['bin', 'shelf', 'rack', 'pallet', 'floor', 'bulk', 'cold_unit'].map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <Field label="Zone" htmlFor="zone">
          <select
            id="zone"
            value={zoneId}
            onChange={(e) => setZoneId(e.target.value)}
            className="w-full rounded-sm border border-[var(--color-line)] bg-white px-3 py-2"
          >
            <option value="">None</option>
            {zones.map((z) => (
              <option key={z.id} value={z.id}>
                {z.zone_code}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Width" htmlFor="width">
          <TextInput id="width" type="number" min={0.1} step={0.1} value={width} onChange={(e) => setWidth(e.target.value)} />
        </Field>
        <Field label="Height" htmlFor="height">
          <TextInput id="height" type="number" min={0.1} step={0.1} value={height} onChange={(e) => setHeight(e.target.value)} />
        </Field>
      </div>
      {error && <p className="text-sm text-[var(--color-rust)]">{error}</p>}
      <PrimaryButton type="submit" isLoading={mutation.isPending} disabled={!clickedPoint}>
        {mutation.isPending ? 'Saving location…' : 'Add location'}
      </PrimaryButton>
    </form>
  )
}

function UploadPanel({ warehouseId, onCommitted }: { warehouseId: string; onCommitted: () => void }) {
  const [result, setResult] = useState<UploadResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isDragging, setIsDragging] = useState(false)

  const mutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      const resp = await api.post<UploadResult>(`/warehouses/${warehouseId}/layout/upload`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      return resp.data
    },
    onSuccess: (data) => {
      setResult(data)
      setError(null)
      if (data.committed) onCommitted()
    },
    onError: (err) => setError(getApiErrorMessage(err)),
  })

  function handleFiles(files: FileList | null) {
    const file = files?.[0]
    if (!file) return
    setResult(null)
    mutation.mutate(file)
  }

  function downloadErrorReport() {
    if (!result?.error_report_csv) return
    const blob = new Blob([result.error_report_csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'layout-upload-errors.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  async function downloadTemplate() {
    const resp = await api.get(`/warehouses/${warehouseId}/layout/template`, { responseType: 'blob' })
    const url = URL.createObjectURL(resp.data)
    const a = document.createElement('a')
    a.href = url
    a.download = 'layout-template.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-[var(--color-steel)]">Upload a CSV, Excel, or JSON layout file.</p>
        <button onClick={downloadTemplate} className="text-sm text-[var(--color-steel)] underline hover:text-[var(--color-ink)]">
          Download sample template
        </button>
      </div>

      <label
        onDragOver={(e) => {
          e.preventDefault()
          setIsDragging(true)
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setIsDragging(false)
          handleFiles(e.dataTransfer.files)
        }}
        className={
          'flex cursor-pointer flex-col items-center justify-center rounded-sm border-2 border-dashed p-10 text-center ' +
          (isDragging ? 'border-[var(--color-amber)] bg-[var(--color-amber-soft)]' : 'border-[var(--color-line)] bg-white')
        }
      >
        <input type="file" accept=".csv,.xlsx,.xls,.json" className="hidden" onChange={(e) => handleFiles(e.target.files)} />
        <p className="font-medium text-[var(--color-ink)]">
          {mutation.isPending ? 'Validating data…' : 'Drop a file here, or click to browse'}
        </p>
        <p className="mt-1 text-sm text-[var(--color-steel)]">.csv, .xlsx, or .json</p>
      </label>

      {error && (
        <div className="rounded-sm bg-[var(--color-rust-soft)] px-4 py-3 text-sm text-[var(--color-rust)]">{error}</div>
      )}

      {result && (
        <div className="rounded-sm border border-[var(--color-line)] bg-white p-4">
          <div className="flex items-center gap-4 text-sm">
            <span className="font-medium text-[var(--color-ink)]">{result.total_rows} rows parsed</span>
            <span className="text-[var(--color-signal)]">{result.valid_rows} valid</span>
            <span className="text-[var(--color-rust)]">{result.invalid_rows} invalid</span>
          </div>

          {result.committed ? (
            <p className="mt-2 rounded-sm bg-[var(--color-signal-soft)] px-3 py-2 text-sm text-[var(--color-signal)]">
              Layout applied: {result.locations_created} locations and {result.zones_created} zones created.
            </p>
          ) : (
            <div className="mt-3">
              <p className="rounded-sm bg-[var(--color-rust-soft)] px-3 py-2 text-sm text-[var(--color-rust)]">
                Validation failed — nothing was saved. Fix the errors below and re-upload.
              </p>
              <div className="mt-3 max-h-64 overflow-y-auto rounded-sm border border-[var(--color-line)]">
                <table className="w-full text-left text-sm">
                  <thead className="bg-[var(--color-concrete)] text-xs uppercase text-[var(--color-steel-light)]">
                    <tr>
                      <th className="px-3 py-2">Row</th>
                      <th className="px-3 py-2">Field</th>
                      <th className="px-3 py-2">Message</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.errors.map((e, i) => (
                      <tr key={i} className="border-t border-[var(--color-line)]">
                        <td className="px-3 py-2 font-mono-tabular">{e.row || '—'}</td>
                        <td className="px-3 py-2 font-mono-tabular">{e.field}</td>
                        <td className="px-3 py-2">{e.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <button onClick={downloadErrorReport} className="mt-2 text-sm text-[var(--color-steel)] underline hover:text-[var(--color-ink)]">
                Download error report
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ZonesPanel({ warehouseId }: { warehouseId: string }) {
  const queryClient = useQueryClient()
  const { data: zones } = useQuery({
    queryKey: ['zones', warehouseId],
    queryFn: async () => (await api.get<Zone[]>(`/warehouses/${warehouseId}/zones`)).data,
  })
  const [name, setName] = useState('')
  const [code, setCode] = useState('')
  const [zoneType, setZoneType] = useState('storage')
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: async () => api.post(`/warehouses/${warehouseId}/zones`, { name, zone_code: code, zone_type: zoneType }),
    onSuccess: () => {
      setName('')
      setCode('')
      queryClient.invalidateQueries({ queryKey: ['zones', warehouseId] })
    },
    onError: (err) => setError(getApiErrorMessage(err)),
  })

  return (
    <div className="flex flex-col gap-4">
      <form
        onSubmit={(e) => {
          e.preventDefault()
          setError(null)
          mutation.mutate()
        }}
        className="flex flex-wrap items-end gap-3 rounded-sm border border-[var(--color-line)] bg-white p-4"
      >
        <div className="min-w-[160px] flex-1">
          <Field label="Zone name" htmlFor="zone-name">
            <TextInput id="zone-name" required value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
        </div>
        <div className="w-32">
          <Field label="Code" htmlFor="zone-code">
            <TextInput id="zone-code" required value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} />
          </Field>
        </div>
        <div className="w-40">
          <Field label="Type" htmlFor="zone-type">
            <select
              id="zone-type"
              value={zoneType}
              onChange={(e) => setZoneType(e.target.value)}
              className="w-full rounded-sm border border-[var(--color-line)] bg-white px-3 py-2"
            >
              {['receiving', 'staging', 'storage', 'picking', 'packing', 'dispatch', 'returns', 'cold_storage'].map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <PrimaryButton type="submit" isLoading={mutation.isPending}>
          Add zone
        </PrimaryButton>
        {error && <p className="basis-full text-sm text-[var(--color-rust)]">{error}</p>}
      </form>

      {zones && zones.length === 0 && (
        <p className="text-sm text-[var(--color-steel)]">No zones yet — add one above, or upload a layout that defines zones.</p>
      )}
      {zones && zones.length > 0 && (
        <ul className="divide-y divide-[var(--color-line)] rounded-sm border border-[var(--color-line)] bg-white">
          {zones.map((z) => (
            <li key={z.id} className="flex items-center justify-between px-4 py-2 text-sm">
              <span className="font-medium text-[var(--color-ink)]">{z.name}</span>
              <span className="font-mono-tabular text-[var(--color-steel)]">{z.zone_code}</span>
              <span className="text-[var(--color-steel-light)]">{z.zone_type}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

type Tab = 'builder' | 'upload' | 'zones'

export default function WarehouseLayoutPage() {
  const { warehouseId = '' } = useParams()
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<Tab>('builder')
  const [clickedPoint, setClickedPoint] = useState<{ x: number; y: number } | null>(null)

  const { data: locations, isLoading } = useQuery({
    queryKey: ['locations', warehouseId],
    queryFn: async () => (await api.get<StorageLocation[]>(`/warehouses/${warehouseId}/locations`)).data,
  })
  const { data: zones } = useQuery({
    queryKey: ['zones', warehouseId],
    queryFn: async () => (await api.get<Zone[]>(`/warehouses/${warehouseId}/zones`)).data,
  })

  function invalidateAll() {
    queryClient.invalidateQueries({ queryKey: ['locations', warehouseId] })
    queryClient.invalidateQueries({ queryKey: ['zones', warehouseId] })
  }

  return (
    <div className="mx-auto max-w-5xl px-8 py-8">
      <h1 className="text-xl font-semibold text-[var(--color-ink)]">Warehouse layout</h1>
      <p className="mt-1 text-sm text-[var(--color-steel)]">
        Design your layout visually, or upload it in bulk. Every location here becomes eligible for slotting
        recommendations once demand data is available.
      </p>

      <div className="mt-6 flex gap-1 border-b border-[var(--color-line)]">
        {(['builder', 'upload', 'zones'] as Tab[]).map((t) => (
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
            {t === 'builder' ? 'Layout builder' : t === 'upload' ? 'Bulk upload' : 'Zones'}
          </button>
        ))}
      </div>

      <div className="mt-6">
        {tab === 'builder' && (
          <div className="grid grid-cols-3 gap-6">
            <div className="col-span-2">
              {isLoading ? (
                <div className="h-[420px] animate-pulse rounded-sm bg-[var(--color-concrete-dark)]" />
              ) : locations && locations.length === 0 ? (
                <div className="flex h-[420px] flex-col items-center justify-center rounded-sm border border-dashed border-[var(--color-line)] text-center">
                  <p className="font-medium text-[var(--color-ink)]">No locations yet</p>
                  <p className="mt-1 max-w-xs text-sm text-[var(--color-steel)]">
                    Use the form on the right to place your first location — start with a receiving and dispatch point.
                  </p>
                </div>
              ) : (
                <LayoutCanvas locations={locations ?? []} onCanvasClick={(x, y) => setClickedPoint({ x, y })} />
              )}
            </div>
            <div>
              <AddLocationForm
                warehouseId={warehouseId}
                zones={zones ?? []}
                clickedPoint={clickedPoint}
                onCreated={() => {
                  invalidateAll()
                  setClickedPoint(null)
                }}
              />
            </div>
          </div>
        )}

        {tab === 'upload' && <UploadPanel warehouseId={warehouseId} onCommitted={invalidateAll} />}

        {tab === 'zones' && <ZonesPanel warehouseId={warehouseId} />}
      </div>
    </div>
  )
}
