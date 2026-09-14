import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { BulkUploadPanel } from '../BulkUploadPanel'
import { api } from '../../lib/api'

vi.mock('../../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../../lib/api')>('../../lib/api')
  return {
    ...actual,
    api: { post: vi.fn(), get: vi.fn() },
  }
})

const mockedApi = vi.mocked(api, true)

function renderPanel(onCommitted = vi.fn()) {
  const queryClient = new QueryClient()
  return render(
    <QueryClientProvider client={queryClient}>
      <BulkUploadPanel
        uploadUrl="/warehouses/wh-1/layout/upload"
        templateUrl="/warehouses/wh-1/layout/template"
        templateFilename="template.csv"
        successNoun="locations"
        onCommitted={onCommitted}
      />
    </QueryClientProvider>,
  )
}

function makeFile(contents: string, name = 'layout.csv') {
  return new File([contents], name, { type: 'text/csv' })
}

afterEach(() => {
  vi.clearAllMocks()
})

describe('BulkUploadPanel', () => {
  it('renders the drop zone and template download link', () => {
    renderPanel()
    expect(screen.getByText(/drop a file here/i)).toBeInTheDocument()
    expect(screen.getByText(/download sample template/i)).toBeInTheDocument()
  })

  it('shows a validating state while the upload is in flight', async () => {
    let resolveUpload: (value: unknown) => void = () => {}
    mockedApi.post.mockReturnValue(
      new Promise((resolve) => {
        resolveUpload = resolve
      }),
    )

    renderPanel()
    const user = userEvent.setup()
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(input, makeFile('a,b\n1,2'))

    expect(await screen.findByText(/validating data…/i)).toBeInTheDocument()

    resolveUpload({
      data: { total_rows: 1, valid_rows: 1, invalid_rows: 0, is_valid: true, committed: true, records_created: 1, errors: [], error_report_csv: null },
    })
    await waitFor(() => expect(screen.queryByText(/validating data…/i)).not.toBeInTheDocument())
  })

  it('shows the validation error table and does not report success when the upload fails validation', async () => {
    mockedApi.post.mockResolvedValue({
      data: {
        total_rows: 2,
        valid_rows: 1,
        invalid_rows: 1,
        is_valid: false,
        committed: false,
        records_created: 0,
        errors: [{ row: 2, field: 'location_type', message: "Missing required field 'location_type'" }],
        error_report_csv: 'row,field,message\n2,location_type,Missing required field',
      },
    })
    const onCommitted = vi.fn()
    renderPanel(onCommitted)

    const user = userEvent.setup()
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(input, makeFile('a,b\n1,2\n3,'))

    expect(await screen.findByText(/validation failed/i)).toBeInTheDocument()
    expect(screen.getByText(/missing required field 'location_type'/i)).toBeInTheDocument()
    expect(screen.getByText(/download error report/i)).toBeInTheDocument()
    expect(onCommitted).not.toHaveBeenCalled()
  })

  it('shows a success message and calls onCommitted when the upload is valid', async () => {
    mockedApi.post.mockResolvedValue({
      data: { total_rows: 3, valid_rows: 3, invalid_rows: 0, is_valid: true, committed: true, records_created: 3, errors: [], error_report_csv: null },
    })
    const onCommitted = vi.fn()
    renderPanel(onCommitted)

    const user = userEvent.setup()
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(input, makeFile('a,b\n1,2'))

    expect(await screen.findByText(/3 locations created/i)).toBeInTheDocument()
    expect(onCommitted).toHaveBeenCalledTimes(1)
  })

  it('shows an error message if the upload request itself fails', async () => {
    const axiosError = Object.assign(new Error('Request failed'), {
      isAxiosError: true,
      response: { data: { error: { message: 'File too large' } } },
    })
    mockedApi.post.mockRejectedValue(axiosError)

    renderPanel()
    const user = userEvent.setup()
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(input, makeFile('a,b\n1,2'))

    expect(await screen.findByText(/file too large/i)).toBeInTheDocument()
  })
})
