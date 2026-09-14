import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { api, getApiErrorMessage } from '../lib/api'

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
  records_created: number
  errors: RowErrorEntry[]
  error_report_csv: string | null
}

export function BulkUploadPanel({
  uploadUrl,
  templateUrl,
  templateFilename,
  successNoun,
  onCommitted,
}: {
  uploadUrl: string
  templateUrl: string
  templateFilename: string
  successNoun: string
  onCommitted: () => void
}) {
  const [result, setResult] = useState<UploadResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isDragging, setIsDragging] = useState(false)

  const mutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      const resp = await api.post<UploadResult>(uploadUrl, formData, {
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
    a.download = 'upload-errors.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  async function downloadTemplate() {
    const resp = await api.get(templateUrl, { responseType: 'blob' })
    const url = URL.createObjectURL(resp.data)
    const a = document.createElement('a')
    a.href = url
    a.download = templateFilename
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-[var(--color-steel)]">Upload a CSV, Excel, or JSON file.</p>
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

      {error && <div className="rounded-sm bg-[var(--color-rust-soft)] px-4 py-3 text-sm text-[var(--color-rust)]">{error}</div>}

      {result && (
        <div className="rounded-sm border border-[var(--color-line)] bg-white p-4">
          <div className="flex items-center gap-4 text-sm">
            <span className="font-medium text-[var(--color-ink)]">{result.total_rows} rows parsed</span>
            <span className="text-[var(--color-signal)]">{result.valid_rows} valid</span>
            <span className="text-[var(--color-rust)]">{result.invalid_rows} invalid</span>
          </div>

          {result.committed ? (
            <p className="mt-2 rounded-sm bg-[var(--color-signal-soft)] px-3 py-2 text-sm text-[var(--color-signal)]">
              {result.records_created} {successNoun} created.
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
