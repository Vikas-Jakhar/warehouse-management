import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Field, PrimaryButton, TextInput } from '../components/FormControls'
import { api, getApiErrorMessage } from '../lib/api'

interface ForecastJob {
  id: string
  status: 'queued' | 'running' | 'succeeded' | 'failed'
  stage: string | null
  error: string | null
  skus_processed: number
  skus_skipped: number
}

interface ForecastSummaryItem {
  sku_id: string
  sku_code: string
  sku_name: string
  chosen_model: string | null
  wape: number | null
  last_forecast_date: string | null
  last_generated_at: string | null
}

interface ForecastModelMetric {
  model_name: string
  mae: number
  rmse: number
  mape: number | null
  wape: number
  bias: number
  is_chosen: boolean
}

interface ForecastResultPoint {
  horizon_date: string
  forecast_qty: number
  lower_ci: number | null
  upper_ci: number | null
  model_used: string
}

interface HistoricalPoint {
  date: string
  quantity_sold: number
}

interface ForecastDetail {
  sku_id: string
  sku_code: string
  historical_demand: HistoricalPoint[]
  forecast: ForecastResultPoint[]
  metrics: ForecastModelMetric[]
  chosen_model: string | null
  last_forecast_generated_at: string | null
}

const STAGE_LABELS: Record<string, string> = {
  validating: 'Validating data…',
  preparing: 'Preparing time-series data…',
  training: 'Training models…',
  evaluating: 'Evaluating models…',
  generating: 'Generating forecasts…',
  saving: 'Saving results…',
}

function GenerateForecastControl({ warehouseId, onSettled }: { warehouseId: string; onSettled: () => void }) {
  const [horizonDays, setHorizonDays] = useState('14')
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [settledJob, setSettledJob] = useState<ForecastJob | null>(null)
  const [error, setError] = useState<string | null>(null)

  const generateMutation = useMutation({
    mutationFn: async () =>
      (
        await api.post<ForecastJob>(`/warehouses/${warehouseId}/forecasts/generate`, {
          horizon_days: Number(horizonDays),
        })
      ).data,
    onSuccess: (job) => {
      setError(null)
      setSettledJob(null)
      setActiveJobId(job.id)
    },
    onError: (err) => setError(getApiErrorMessage(err)),
  })

  const { data: job } = useQuery({
    queryKey: ['forecast-job', warehouseId, activeJobId],
    queryFn: async () => (await api.get<ForecastJob>(`/warehouses/${warehouseId}/forecasts/jobs/${activeJobId}`)).data,
    enabled: activeJobId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'queued' || status === 'running' ? 1500 : false
    },
  })

  const isRunning = job?.status === 'queued' || job?.status === 'running'

  useEffect(() => {
    if (job && activeJobId === job.id && (job.status === 'succeeded' || job.status === 'failed')) {
      setSettledJob(job)
      onSettled()
      setActiveJobId(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.status, job?.id])

  const displayJob = isRunning ? job : settledJob

  return (
    <div className="flex flex-wrap items-end gap-4 rounded-sm border border-[var(--color-line)] bg-white p-4">
      <div className="w-32">
        <Field label="Horizon (days)" htmlFor="horizon">
          <TextInput
            id="horizon"
            type="number"
            min={1}
            max={90}
            value={horizonDays}
            onChange={(e) => setHorizonDays(e.target.value)}
            disabled={isRunning}
          />
        </Field>
      </div>
      <PrimaryButton onClick={() => generateMutation.mutate()} isLoading={isRunning} disabled={isRunning}>
        {isRunning ? STAGE_LABELS[job?.stage ?? ''] ?? 'Working…' : 'Generate forecasts'}
      </PrimaryButton>
      {displayJob?.status === 'succeeded' && (
        <p className="text-sm text-[var(--color-signal)]">
          Done — {displayJob.skus_processed} SKU{displayJob.skus_processed === 1 ? '' : 's'} forecast
          {displayJob.skus_skipped > 0 ? `, ${displayJob.skus_skipped} skipped (not enough history)` : ''}.
        </p>
      )}
      {displayJob?.status === 'failed' && <p className="text-sm text-[var(--color-rust)]">{displayJob.error}</p>}
      {error && <p className="text-sm text-[var(--color-rust)]">{error}</p>}
    </div>
  )
}

function ForecastChart({ detail }: { detail: ForecastDetail }) {
  const historicalPoints = detail.historical_demand.map((p) => ({
    date: p.date,
    actual: p.quantity_sold,
    forecast: null as number | null,
    lower: null as number | null,
    upper: null as number | null,
  }))
  const forecastPoints = detail.forecast.map((p) => ({
    date: p.horizon_date,
    actual: null as number | null,
    forecast: p.forecast_qty,
    lower: p.lower_ci,
    upper: p.upper_ci,
  }))
  const chartData = [...historicalPoints, ...forecastPoints]

  return (
    <ResponsiveContainer width="100%" height={320}>
      <ComposedChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="var(--color-line)" strokeDasharray="3 3" />
        <XAxis dataKey="date" tick={{ fontSize: 11, fill: 'var(--color-steel)' }} minTickGap={30} />
        <YAxis tick={{ fontSize: 11, fill: 'var(--color-steel)' }} />
        <Tooltip contentStyle={{ fontSize: 12, fontFamily: 'var(--font-sans)' }} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Area
          dataKey="upper"
          stroke="none"
          fill="var(--color-amber-soft)"
          fillOpacity={0.6}
          name="Confidence interval"
          isAnimationActive={false}
        />
        <Area dataKey="lower" stroke="none" fill="var(--color-card)" fillOpacity={1} legendType="none" isAnimationActive={false} />
        <Line type="monotone" dataKey="actual" stroke="var(--color-steel)" dot={false} name="Historical demand" strokeWidth={2} />
        <Line
          type="monotone"
          dataKey="forecast"
          stroke="var(--color-amber)"
          strokeDasharray="4 3"
          dot={false}
          name="Forecast"
          strokeWidth={2}
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

function ModelMetricsTable({ metrics }: { metrics: ForecastModelMetric[] }) {
  return (
    <table className="w-full border-collapse overflow-hidden rounded-sm border border-[var(--color-line)] bg-white text-left text-sm">
      <thead>
        <tr className="border-b border-[var(--color-line)] text-xs uppercase text-[var(--color-steel-light)]">
          <th className="px-4 py-2 font-medium">Model</th>
          <th className="px-4 py-2 font-medium">MAE</th>
          <th className="px-4 py-2 font-medium">RMSE</th>
          <th className="px-4 py-2 font-medium">WAPE</th>
          <th className="px-4 py-2 font-medium">Bias</th>
        </tr>
      </thead>
      <tbody>
        {[...metrics].sort((a, b) => a.wape - b.wape).map((m) => (
          <tr key={m.model_name} className={'border-b border-[var(--color-line)] last:border-0' + (m.is_chosen ? ' bg-[var(--color-signal-soft)]' : '')}>
            <td className="px-4 py-2 font-medium text-[var(--color-ink)]">
              {m.model_name.replace('_', ' ')} {m.is_chosen && <span className="ml-1 text-xs text-[var(--color-signal)]">(chosen)</span>}
            </td>
            <td className="px-4 py-2 font-mono-tabular text-[var(--color-steel)]">{m.mae.toFixed(2)}</td>
            <td className="px-4 py-2 font-mono-tabular text-[var(--color-steel)]">{m.rmse.toFixed(2)}</td>
            <td className="px-4 py-2 font-mono-tabular text-[var(--color-steel)]">{(m.wape * 100).toFixed(1)}%</td>
            <td className="px-4 py-2 font-mono-tabular text-[var(--color-steel)]">{m.bias.toFixed(2)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default function WarehouseForecastingPage() {
  const { warehouseId = '' } = useParams()
  const queryClient = useQueryClient()
  const [selectedSkuId, setSelectedSkuId] = useState<string | null>(null)

  const { data: summary, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['forecast-summary', warehouseId],
    queryFn: async () => (await api.get<{ items: ForecastSummaryItem[]; total: number }>(`/warehouses/${warehouseId}/forecasts`)).data,
  })

  const { data: detail, isLoading: detailLoading } = useQuery({
    queryKey: ['forecast-detail', warehouseId, selectedSkuId],
    queryFn: async () => (await api.get<ForecastDetail>(`/warehouses/${warehouseId}/forecasts/${selectedSkuId}`)).data,
    enabled: selectedSkuId !== null,
  })

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ['forecast-summary', warehouseId] })
    if (selectedSkuId) queryClient.invalidateQueries({ queryKey: ['forecast-detail', warehouseId, selectedSkuId] })
  }

  return (
    <div className="mx-auto max-w-5xl px-8 py-8">
      <h1 className="text-xl font-semibold text-[var(--color-ink)]">Demand forecasting</h1>
      <p className="mt-1 text-sm text-[var(--color-steel)]">
        Forecasts run as a background job per SKU, automatically selecting and backtesting the best model
        for that SKU's demand pattern.
      </p>

      <div className="mt-6">
        <GenerateForecastControl warehouseId={warehouseId} onSettled={invalidate} />
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

        {summary && summary.items.length === 0 && (
          <div className="rounded-sm border border-dashed border-[var(--color-line)] p-8 text-center">
            <p className="font-medium text-[var(--color-ink)]">No forecasts generated yet</p>
            <p className="mt-1 text-sm text-[var(--color-steel)]">
              Upload sales history for this warehouse, then click "Generate forecasts" above.
            </p>
          </div>
        )}

        {summary && summary.items.length > 0 && (
          <table className="w-full border-collapse overflow-hidden rounded-sm border border-[var(--color-line)] bg-white text-left text-sm">
            <thead>
              <tr className="border-b border-[var(--color-line)] text-xs uppercase text-[var(--color-steel-light)]">
                <th className="px-4 py-2 font-medium">SKU</th>
                <th className="px-4 py-2 font-medium">Model</th>
                <th className="px-4 py-2 font-medium">WAPE</th>
                <th className="px-4 py-2 font-medium">Last forecast</th>
              </tr>
            </thead>
            <tbody>
              {summary.items.map((item) => (
                <tr
                  key={item.sku_id}
                  onClick={() => setSelectedSkuId(item.sku_id)}
                  className={
                    'cursor-pointer border-b border-[var(--color-line)] last:border-0 hover:bg-[var(--color-concrete)] ' +
                    (selectedSkuId === item.sku_id ? 'bg-[var(--color-concrete)]' : '')
                  }
                >
                  <td className="px-4 py-3">
                    <span className="font-mono-tabular text-[var(--color-steel)]">{item.sku_code}</span>{' '}
                    <span className="text-[var(--color-ink)]">{item.sku_name}</span>
                  </td>
                  <td className="px-4 py-3 text-[var(--color-steel)]">{item.chosen_model?.replace('_', ' ') ?? '—'}</td>
                  <td className="px-4 py-3 font-mono-tabular text-[var(--color-steel)]">
                    {item.wape !== null ? `${(item.wape * 100).toFixed(1)}%` : '—'}
                  </td>
                  <td className="px-4 py-3 font-mono-tabular text-[var(--color-steel-light)]">{item.last_forecast_date ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {selectedSkuId && (
        <div className="mt-8 border-t border-[var(--color-line)] pt-6">
          <h2 className="text-lg font-semibold text-[var(--color-ink)]">
            {detail ? `${detail.sku_code} — forecast detail` : 'Loading…'}
          </h2>
          {detailLoading && <div className="mt-4 h-64 animate-pulse rounded-sm bg-[var(--color-concrete-dark)]" />}
          {detail && (
            <div className="mt-4 flex flex-col gap-6">
              <div className="rounded-sm border border-[var(--color-line)] bg-white p-4">
                <ForecastChart detail={detail} />
              </div>
              <div>
                <p className="mb-2 text-sm font-medium text-[var(--color-ink)]">Model comparison (backtest)</p>
                <ModelMetricsTable metrics={detail.metrics} />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
