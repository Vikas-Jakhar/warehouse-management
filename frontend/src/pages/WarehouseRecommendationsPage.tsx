import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { PrimaryButton } from '../components/FormControls'
import { api, getApiErrorMessage } from '../lib/api'

interface RecommendationJob {
  id: string
  status: 'queued' | 'running' | 'succeeded' | 'failed'
  stage: string | null
  error: string | null
  recommendations_created: number
  inventory_records_evaluated: number
}

interface Recommendation {
  id: string
  sku_code: string
  sku_name: string
  current_location_code: string | null
  recommended_location_code: string
  reason: string[]
  expected_benefit: number
  distance_reduction: number | null
  demand_classification: 'fast_mover' | 'medium_mover' | 'slow_mover'
  confidence_score: number
  status: string
}

const STAGE_LABELS: Record<string, string> = {
  validating: 'Validating inventory…',
  scoring: 'Scoring candidate locations…',
  applying_stability_rules: 'Applying stability rules…',
  saving: 'Saving recommendations…',
}

const CLASSIFICATION_STYLES: Record<string, string> = {
  fast_mover: 'bg-[var(--color-signal-soft)] text-[var(--color-signal)]',
  medium_mover: 'bg-[var(--color-amber-soft)] text-[var(--color-amber)]',
  slow_mover: 'bg-[var(--color-concrete-dark)] text-[var(--color-steel)]',
}

function GenerateControl({ warehouseId, onSettled }: { warehouseId: string; onSettled: () => void }) {
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [settledJob, setSettledJob] = useState<RecommendationJob | null>(null)
  const [error, setError] = useState<string | null>(null)

  const generateMutation = useMutation({
    mutationFn: async () => (await api.post<RecommendationJob>(`/warehouses/${warehouseId}/recommendations/generate`)).data,
    onSuccess: (job) => {
      setError(null)
      setSettledJob(null)
      setActiveJobId(job.id)
    },
    onError: (err) => setError(getApiErrorMessage(err)),
  })

  const { data: job } = useQuery({
    queryKey: ['recommendation-job', warehouseId, activeJobId],
    queryFn: async () =>
      (await api.get<RecommendationJob>(`/warehouses/${warehouseId}/recommendations/jobs/${activeJobId}`)).data,
    enabled: activeJobId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'queued' || status === 'running' ? 1200 : false
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
    <div className="flex flex-wrap items-center gap-4 rounded-sm border border-[var(--color-line)] bg-white p-4">
      <PrimaryButton onClick={() => generateMutation.mutate()} isLoading={isRunning} disabled={isRunning}>
        {isRunning ? STAGE_LABELS[job?.stage ?? ''] ?? 'Working…' : 'Generate recommendations'}
      </PrimaryButton>
      {displayJob?.status === 'succeeded' && (
        <p className="text-sm text-[var(--color-signal)]">
          Evaluated {displayJob.inventory_records_evaluated} inventory record
          {displayJob.inventory_records_evaluated === 1 ? '' : 's'} — {displayJob.recommendations_created} recommendation
          {displayJob.recommendations_created === 1 ? '' : 's'} now open.
        </p>
      )}
      {displayJob?.status === 'failed' && <p className="text-sm text-[var(--color-rust)]">{displayJob.error}</p>}
      {error && <p className="text-sm text-[var(--color-rust)]">{error}</p>}
    </div>
  )
}

function ConfidenceBar({ score }: { score: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-[var(--color-concrete-dark)]">
        <div className="h-full bg-[var(--color-steel)]" style={{ width: `${Math.round(score * 100)}%` }} />
      </div>
      <span className="font-mono-tabular text-xs text-[var(--color-steel-light)]">{Math.round(score * 100)}%</span>
    </div>
  )
}

function RecommendationActions({
  warehouseId,
  recommendationId,
  onDecided,
}: {
  warehouseId: string
  recommendationId: string
  onDecided: () => void
}) {
  const [mode, setMode] = useState<'idle' | 'reject' | 'override'>('idle')
  const [rejectionReason, setRejectionReason] = useState('')
  const [overrideCode, setOverrideCode] = useState('')
  const [error, setError] = useState<string | null>(null)

  const { data: locations } = useQuery({
    queryKey: ['locations', warehouseId],
    queryFn: async () => (await api.get<{ id: string; location_code: string }[]>(`/warehouses/${warehouseId}/locations`)).data,
    enabled: mode === 'override',
  })

  const accept = useMutation({
    mutationFn: async () =>
      api.post(`/warehouses/${warehouseId}/recommendations/${recommendationId}/accept`, {}),
    onSuccess: onDecided,
    onError: (err) => setError(getApiErrorMessage(err)),
  })

  const reject = useMutation({
    mutationFn: async () =>
      api.post(`/warehouses/${warehouseId}/recommendations/${recommendationId}/reject`, {
        rejection_reason: rejectionReason,
      }),
    onSuccess: onDecided,
    onError: (err) => setError(getApiErrorMessage(err)),
  })

  const override = useMutation({
    mutationFn: async () => {
      const target = locations?.find((l) => l.location_code.toUpperCase() === overrideCode.toUpperCase())
      if (!target) throw new Error('No location with that code exists in this warehouse.')
      return api.post(`/warehouses/${warehouseId}/recommendations/${recommendationId}/override`, {
        override_location_id: target.id,
      })
    },
    onSuccess: onDecided,
    onError: (err) => setError(err instanceof Error ? err.message : getApiErrorMessage(err)),
  })

  if (mode === 'reject') {
    return (
      <div className="mt-3 flex flex-col gap-2 border-t border-[var(--color-line)] pt-3">
        <textarea
          value={rejectionReason}
          onChange={(e) => setRejectionReason(e.target.value)}
          placeholder="Why are you rejecting this recommendation?"
          className="w-full rounded-sm border border-[var(--color-line)] p-2 text-sm"
          rows={2}
        />
        <div className="flex gap-2">
          <PrimaryButton
            onClick={() => reject.mutate()}
            isLoading={reject.isPending}
            disabled={!rejectionReason.trim()}
            className="bg-[var(--color-rust)] hover:bg-[var(--color-rust)]"
          >
            Confirm rejection
          </PrimaryButton>
          <button onClick={() => setMode('idle')} className="text-sm text-[var(--color-steel)] underline">
            Cancel
          </button>
        </div>
        {error && <p className="text-sm text-[var(--color-rust)]">{error}</p>}
      </div>
    )
  }

  if (mode === 'override') {
    return (
      <div className="mt-3 flex flex-col gap-2 border-t border-[var(--color-line)] pt-3">
        <input
          value={overrideCode}
          onChange={(e) => setOverrideCode(e.target.value)}
          placeholder="Location code to use instead, e.g. BIN-A2"
          className="w-full rounded-sm border border-[var(--color-line)] p-2 text-sm font-mono"
          list="location-codes"
        />
        <datalist id="location-codes">
          {locations?.map((l) => (
            <option key={l.id} value={l.location_code} />
          ))}
        </datalist>
        <div className="flex gap-2">
          <PrimaryButton onClick={() => override.mutate()} isLoading={override.isPending} disabled={!overrideCode.trim()}>
            Confirm override
          </PrimaryButton>
          <button onClick={() => setMode('idle')} className="text-sm text-[var(--color-steel)] underline">
            Cancel
          </button>
        </div>
        {error && <p className="text-sm text-[var(--color-rust)]">{error}</p>}
      </div>
    )
  }

  return (
    <div className="mt-3 flex gap-2 border-t border-[var(--color-line)] pt-3">
      <PrimaryButton onClick={() => accept.mutate()} isLoading={accept.isPending}>
        {accept.isPending ? 'Accepting…' : 'Accept'}
      </PrimaryButton>
      <button
        onClick={() => setMode('reject')}
        className="rounded-sm border border-[var(--color-line)] px-4 py-2 text-sm font-medium text-[var(--color-steel)] hover:bg-[var(--color-concrete)]"
      >
        Reject
      </button>
      <button
        onClick={() => setMode('override')}
        className="rounded-sm border border-[var(--color-line)] px-4 py-2 text-sm font-medium text-[var(--color-steel)] hover:bg-[var(--color-concrete)]"
      >
        Override location
      </button>
      {error && <p className="ml-2 self-center text-sm text-[var(--color-rust)]">{error}</p>}
    </div>
  )
}

export default function WarehouseRecommendationsPage() {
  const { warehouseId = '' } = useParams()
  const queryClient = useQueryClient()

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['recommendations', warehouseId],
    queryFn: async () =>
      (await api.get<{ items: Recommendation[]; total: number }>(`/warehouses/${warehouseId}/recommendations`)).data,
  })

  return (
    <div className="mx-auto max-w-5xl px-8 py-8">
      <h1 className="text-xl font-semibold text-[var(--color-ink)]">Slotting recommendations</h1>
      <p className="mt-1 text-sm text-[var(--color-steel)]">
        Every recommendation here is a suggestion only — nothing moves until you accept or override it,
        and an operator confirms the physical move on the Movements page.
      </p>

      <div className="mt-6">
        <GenerateControl
          warehouseId={warehouseId}
          onSettled={() => queryClient.invalidateQueries({ queryKey: ['recommendations', warehouseId] })}
        />
      </div>

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
            <p className="font-medium text-[var(--color-ink)]">No pending recommendations</p>
            <p className="mt-1 text-sm text-[var(--color-steel)]">
              Upload layout and inventory data for this warehouse, then click "Generate recommendations" above.
            </p>
          </div>
        )}

        {data && data.items.length > 0 && (
          <div className="flex flex-col gap-3">
            {data.items.map((rec) => (
              <div key={rec.id} className="rounded-sm border border-[var(--color-line)] bg-white p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono-tabular text-sm text-[var(--color-steel)]">{rec.sku_code}</span>
                      <span className="font-medium text-[var(--color-ink)]">{rec.sku_name}</span>
                      <span className={'rounded-sm px-2 py-0.5 text-xs font-medium ' + CLASSIFICATION_STYLES[rec.demand_classification]}>
                        {rec.demand_classification.replace('_', ' ')}
                      </span>
                    </div>
                    <p className="mt-2 text-sm text-[var(--color-steel)]">
                      {rec.current_location_code ? (
                        <>
                          <span className="font-mono-tabular">{rec.current_location_code}</span>
                          {' → '}
                        </>
                      ) : (
                        <span className="italic">Awaiting put-away → </span>
                      )}
                      <span className="font-mono-tabular font-medium text-[var(--color-ink)]">{rec.recommended_location_code}</span>
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-[var(--color-steel-light)]">Confidence</p>
                    <ConfidenceBar score={rec.confidence_score} />
                  </div>
                </div>

                <ul className="mt-3 flex flex-wrap gap-2">
                  {rec.reason.map((r, i) => (
                    <li key={i} className="rounded-sm bg-[var(--color-concrete)] px-2 py-1 text-xs text-[var(--color-steel)]">
                      {r}
                    </li>
                  ))}
                </ul>

                {rec.distance_reduction !== null && rec.distance_reduction > 0 && (
                  <p className="mt-2 text-xs text-[var(--color-signal)]">
                    Distance reduction: {rec.distance_reduction.toFixed(1)} units
                  </p>
                )}

                <RecommendationActions
                  warehouseId={warehouseId}
                  recommendationId={rec.id}
                  onDecided={() => queryClient.invalidateQueries({ queryKey: ['recommendations', warehouseId] })}
                />
              </div>
            ))}
          </div>
        )}
      </div>

      <p className="mt-8 text-sm text-[var(--color-steel)]">
        Accepted and overridden recommendations create movement tasks — track and confirm them on the{' '}
        <Link to={`/app/warehouses/${warehouseId}/movements`} className="underline hover:text-[var(--color-ink)]">
          Movements
        </Link>{' '}
        page.
      </p>
    </div>
  )
}
