import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ExportBar } from '@/components/ExportBar'
import { ThemeToggle } from '@/components/ThemeToggle'
import { ToastProvider, useToast } from '@/components/toast'
import AnalysisPage from '@/pages/AnalysisPage'
import AnalyzerPage from '@/pages/AnalyzerPage'
import DashboardPage from '@/pages/DashboardPage'
import HowItWorksPage from '@/pages/HowItWorksPage'
import type { DashboardStats } from '@/lib/types'
import { detail, jsonRes, mockFetch, renderApp, weakResult } from '@/test/utils'

const stats = (over: Partial<DashboardStats> = {}): DashboardStats => ({
  total_analyses: 3,
  avg_score: 56.7,
  best_score: 70,
  latest_score: 60,
  score_change: 20,
  score_trend: [
    { id: 'a', keyword: 'one', score: 40, created_at: '2026-10-01T00:00:00Z' },
    { id: 'b', keyword: 'two', score: 60, created_at: '2026-10-02T00:00:00Z' },
  ],
  top_keywords: [{ keyword: 'running shoes', count: 2, avg_score: 55 }],
  common_gaps: [{ label: 'Price and value', count: 2, share: 0.667 }],
  gap_sample_size: 3,
  ...over,
})

const page = (items: { id: string; keyword: string; score: number | null; status?: string }[]) => ({
  items: items.map((i) => ({
    status: 'done',
    is_demo: false,
    created_at: '2026-10-02T10:00:00Z',
    ...i,
  })),
  total: items.length,
  limit: 10,
  offset: 0,
})

describe('DashboardPage', () => {
  it('shows KPIs, the common gaps and the history table', async () => {
    mockFetch({
      'GET /api/dashboard/stats': () => jsonRes(stats()),
      'GET /api/analyses?limit=10&offset=0&sort=created_at&order=desc': () =>
        jsonRes(page([{ id: 'x1', keyword: 'running shoes', score: 60 }])),
    })
    renderApp(<DashboardPage />)
    expect(await screen.findByText('Average score')).toBeInTheDocument()
    expect(screen.getByText('57')).toBeInTheDocument()
    expect(screen.getByText('Price and value')).toBeInTheDocument()
    expect(await screen.findByRole('link', { name: /open analysis for running shoes/i })).toHaveAttribute(
      'href',
      '/analysis/x1',
    )
  })

  it('shows an empty state with a call to action when there are no analyses', async () => {
    mockFetch({
      'GET /api/dashboard/stats': () =>
        jsonRes(stats({ total_analyses: 0, avg_score: null, best_score: null, latest_score: null, score_change: null, score_trend: [], top_keywords: [], common_gaps: [], gap_sample_size: 0 })),
      'GET /api/analyses?limit=10&offset=0&sort=created_at&order=desc': () => jsonRes(page([])),
    })
    renderApp(<DashboardPage />)
    expect(await screen.findByText(/no analyses yet/i, { selector: 'h2' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /analyze a draft/i })).toHaveAttribute('href', '/')
  })

  it('sorts by score when the column header is clicked', async () => {
    const user = userEvent.setup()
    const f = mockFetch({
      'GET /api/dashboard/stats': () => jsonRes(stats()),
      'GET /api/analyses?limit=10&offset=0&sort=created_at&order=desc': () =>
        jsonRes(page([{ id: 'x1', keyword: 'a', score: 60 }])),
      'GET /api/analyses?limit=10&offset=0&sort=score&order=desc': () =>
        jsonRes(page([{ id: 'x2', keyword: 'b', score: 90 }])),
    })
    renderApp(<DashboardPage />)
    await user.click(await screen.findByRole('button', { name: /^score$/i }))
    expect(await screen.findByRole('link', { name: /open analysis for b/i })).toBeInTheDocument()
    expect(f).toHaveBeenCalledWith(
      '/api/analyses?limit=10&offset=0&sort=score&order=desc',
      expect.anything(),
    )
  })

  it('asks for confirmation before deleting, then removes the row', async () => {
    const user = userEvent.setup()
    const f = mockFetch({
      'GET /api/dashboard/stats': () => jsonRes(stats()),
      'GET /api/analyses?limit=10&offset=0&sort=created_at&order=desc': [
        () => jsonRes(page([{ id: 'x1', keyword: 'running shoes', score: 60 }])),
        () => jsonRes(page([])),
      ],
      'DELETE /api/analyses/x1': () => new Response(null, { status: 204 }),
    })
    renderApp(<DashboardPage />)
    await user.click(await screen.findByRole('button', { name: /delete analysis for running shoes/i }))
    expect(f).not.toHaveBeenCalledWith('/api/analyses/x1', expect.objectContaining({ method: 'DELETE' }))
    await user.click(screen.getByRole('button', { name: /confirm delete running shoes/i }))
    await waitFor(() =>
      expect(f).toHaveBeenCalledWith('/api/analyses/x1', expect.objectContaining({ method: 'DELETE' })),
    )
    expect(await screen.findByText(/analysis deleted/i)).toBeInTheDocument()
  })

  it('shows a retry card when stats fail to load', async () => {
    mockFetch({ 'GET /api/dashboard/stats': () => jsonRes({ detail: 'boom' }, { status: 500 }) })
    renderApp(<DashboardPage />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load the dashboard/i)
  })
})

describe('demo', () => {
  it('Try demo calls POST /api/demo and opens the analysis', async () => {
    const user = userEvent.setup()
    const f = mockFetch({
      'POST /api/demo': () =>
        jsonRes({ analysis_id: 'demo-id', status: 'done', events_url: '/e' }),
    })
    renderApp(<AnalyzerPage />)
    await user.click(screen.getByRole('button', { name: /try demo/i }))
    expect(await screen.findByTestId('analysis-route')).toBeInTheDocument()
    expect(f).toHaveBeenCalledWith('/api/demo', expect.objectContaining({ method: 'POST' }))
  })

  it('shows a toast if the demo is unavailable', async () => {
    const user = userEvent.setup()
    mockFetch({
      'POST /api/demo': () => jsonRes({ detail: 'The demo analysis is not available.' }, { status: 503 }),
    })
    renderApp(<AnalyzerPage />)
    await user.click(screen.getByRole('button', { name: /try demo/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/demo analysis is not available/i)
  })

  it('a demo analysis page explains it is an example and offers export', async () => {
    mockFetch({ 'GET /api/analyses/demo-id': () => jsonRes(detail({ id: 'demo-id', is_demo: true })) })
    renderApp(<AnalysisPage />, { route: '/analysis/demo-id', path: '/analysis/:id' })
    expect(await screen.findByText(/saved example analysis/i)).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /markdown/i })[0]).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /pdf/i })).toBeInTheDocument()
  })
})

describe('ExportBar', () => {
  it('downloads a markdown file and confirms with a toast', async () => {
    const user = userEvent.setup()
    const create = vi.fn(() => 'blob:x')
    ;(URL as unknown as { createObjectURL: unknown }).createObjectURL = create
    ;(URL as unknown as { revokeObjectURL: unknown }).revokeObjectURL = vi.fn()
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    renderApp(<ExportBar result={weakResult} />)
    await user.click(screen.getByRole('button', { name: /markdown/i }))
    expect(create).toHaveBeenCalledTimes(1)
    expect(click).toHaveBeenCalled()
    expect(await screen.findByText(/markdown report downloaded/i)).toBeInTheDocument()
  })

  it('PDF opens the print dialog', async () => {
    const user = userEvent.setup()
    const print = vi.spyOn(window, 'print').mockImplementation(() => {})
    renderApp(<ExportBar result={weakResult} />)
    await user.click(screen.getByRole('button', { name: /pdf/i }))
    expect(print).toHaveBeenCalledTimes(1)
  })
})

describe('ThemeToggle', () => {
  it('toggles the dark class and remembers the choice', async () => {
    const user = userEvent.setup()
    document.documentElement.classList.remove('dark')
    renderApp(<ThemeToggle />)
    await user.click(screen.getByRole('button', { name: /switch to dark mode/i }))
    expect(document.documentElement).toHaveClass('dark')
    expect(window.localStorage.getItem('ranklens.theme')).toBe('dark')
    await user.click(screen.getByRole('button', { name: /switch to light mode/i }))
    expect(document.documentElement).not.toHaveClass('dark')
  })
})

describe('toast', () => {
  function Demo() {
    const t = useToast()
    return <button onClick={() => t.error('Nope')}>go</button>
  }
  it('renders an alert that can be dismissed', async () => {
    const user = userEvent.setup()
    const { container } = renderApp(
      <ToastProvider>
        <Demo />
      </ToastProvider>,
    )
    await user.click(screen.getByText('go'))
    const alert = await screen.findByRole('alert')
    await user.click(within(alert).getByRole('button', { name: /dismiss/i }))
    expect(screen.queryByRole('alert')).toBeNull()
    expect(container).toBeTruthy()
  })
})

describe('HowItWorksPage', () => {
  it('lists every pipeline node and the six score weights', () => {
    renderApp(<HowItWorksPage />)
    for (const n of ['fetch_serp', 'scrape_pages', 'build_index', 'analyze_draft', 'generate_recommendations'])
      expect(screen.getByText(n)).toBeInTheDocument()
    expect(screen.getByText('Topic coverage')).toBeInTheDocument()
    expect(screen.getByText('30')).toBeInTheDocument()
  })
})
