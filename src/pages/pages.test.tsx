import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { EXAMPLE_KEYWORD } from '@/lib/example'
import AnalysisPage from '@/pages/AnalysisPage'
import AnalyzerPage from '@/pages/AnalyzerPage'
import { detail, jsonRes, mockFetch, progress, renderApp, sseRes } from '@/test/utils'

const words = (n: number) => Array.from({ length: n }, (_, i) => `word${i}`).join(' ')

// ---------------------------------------------------------------- analyzer form
describe('AnalyzerPage', () => {
  it('shows field errors only after the first submit and does not call the API', async () => {
    const user = userEvent.setup()
    const f = mockFetch({})
    renderApp(<AnalyzerPage />)
    expect(screen.queryByText(/enter the keyword/i)).toBeNull()
    await user.click(screen.getByRole('button', { name: /analyze my draft/i }))
    expect(await screen.findByText(/enter the keyword you want to rank for/i)).toBeInTheDocument()
    expect(screen.getByText(/paste at least 100 words \(you have 0\)/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/target keyword/i)).toHaveAttribute('aria-invalid', 'true')
    expect(f).not.toHaveBeenCalled()
  })

  it('counts words live and marks the minimum as met', async () => {
    const user = userEvent.setup()
    renderApp(<AnalyzerPage />)
    const box = screen.getByLabelText('Your draft')
    await user.click(box)
    await user.paste(words(30))
    expect(screen.getByText(/30 words · min 100/)).toBeInTheDocument()
    await user.clear(box)
    await user.paste(words(120))
    expect(screen.getByText(/120 words · min 100/)).toHaveClass('text-success')
  })

  it('loads the example draft', async () => {
    const user = userEvent.setup()
    renderApp(<AnalyzerPage />)
    await user.click(screen.getByRole('button', { name: /try an example draft/i }))
    expect(screen.getByLabelText(/target keyword/i)).toHaveValue(EXAMPLE_KEYWORD)
    expect((screen.getByLabelText('Your draft') as HTMLTextAreaElement).value).toMatch(
      /^# Best Running Shoes/,
    )
  })

  it('submits pasted text with optional title/meta and navigates to the analysis', async () => {
    const user = userEvent.setup()
    const f = mockFetch({
      'POST /api/analyze': () =>
        jsonRes({ analysis_id: 'new-id', status: 'pending', events_url: '/e' }, { status: 202 }),
    })
    renderApp(<AnalyzerPage />)
    await user.type(screen.getByLabelText(/target keyword/i), '  best   shoes ')
    await user.click(screen.getByLabelText('Your draft'))
    await user.paste(words(110))
    await user.click(screen.getByRole('button', { name: /add title tag/i }))
    await user.type(screen.getByLabelText('Title tag'), 'My title')
    await user.selectOptions(screen.getByLabelText(/search country/i), 'in')
    await user.click(screen.getByRole('button', { name: /analyze my draft/i }))

    expect(await screen.findByTestId('analysis-route')).toBeInTheDocument()
    const [, init] = f.mock.calls[0]
    const body = JSON.parse(init!.body as string)
    expect(body).toMatchObject({ keyword: 'best shoes', country: 'in', draft_title: 'My title' })
    expect(body.draft_text.split(' ')).toHaveLength(110)
    expect(body).not.toHaveProperty('meta_description')
    expect(body).not.toHaveProperty('draft_url')
  })

  it('switches to URL mode, validates it, and sends only the URL', async () => {
    const user = userEvent.setup()
    const f = mockFetch({
      'POST /api/analyze': () =>
        jsonRes({ analysis_id: 'u1', status: 'pending', events_url: '/e' }, { status: 202 }),
    })
    renderApp(<AnalyzerPage />)
    await user.type(screen.getByLabelText(/target keyword/i), 'seo tips')
    await user.click(screen.getByRole('tab', { name: /from url/i }))
    await user.type(screen.getByLabelText('Draft URL'), 'not-a-url')
    await user.click(screen.getByRole('button', { name: /analyze my draft/i }))
    expect(await screen.findByText(/enter a full public url/i)).toBeInTheDocument()
    expect(f).not.toHaveBeenCalled()

    await user.clear(screen.getByLabelText('Draft URL'))
    await user.type(screen.getByLabelText('Draft URL'), 'https://example.com/post')
    await user.click(screen.getByRole('button', { name: /analyze my draft/i }))
    await screen.findByTestId('analysis-route')
    const body = JSON.parse(f.mock.calls[0][1]!.body as string)
    expect(body).toEqual({
      keyword: 'seo tips',
      country: 'us',
      draft_url: 'https://example.com/post',
    })
  })

  it('shows the server message and retry hint on a rate limit, and keeps the form usable', async () => {
    const user = userEvent.setup()
    mockFetch({
      'POST /api/analyze': () =>
        jsonRes(
          { detail: 'Rate limit reached (10 analyses per hour). Try again later.' },
          { status: 429, headers: { 'Retry-After': '1500' } },
        ),
    })
    renderApp(<AnalyzerPage />)
    await user.click(screen.getByRole('button', { name: /try an example draft/i }))
    await user.click(screen.getByRole('button', { name: /analyze my draft/i }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/rate limit reached/i)
    expect(alert).toHaveTextContent(/try again in about 25 minutes/i)
    expect(alert).not.toHaveTextContent(/try again later/i) // no duplicated advice
    expect(screen.getByRole('button', { name: /analyze my draft/i })).toBeEnabled()
    expect(screen.getByLabelText(/target keyword/i)).toHaveValue(EXAMPLE_KEYWORD)
  })

  it('shows a friendly message when the server is unreachable', async () => {
    const user = userEvent.setup()
    mockFetch({
      'POST /api/analyze': () => {
        throw new TypeError('Failed to fetch')
      },
    })
    renderApp(<AnalyzerPage />)
    await user.click(screen.getByRole('button', { name: /try an example draft/i }))
    await user.click(screen.getByRole('button', { name: /analyze my draft/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/cannot reach the server/i)
  })

  it('disables the button and shows progress while the request is in flight', async () => {
    const user = userEvent.setup()
    let release!: (r: Response) => void
    mockFetch({
      'POST /api/analyze': () => {
        throw new Error('replaced below')
      },
    })
    const pending = new Promise<Response>((res) => (release = res))
    ;(
      globalThis.fetch as unknown as { mockImplementation: (f: () => Promise<Response>) => void }
    ).mockImplementation(() => pending)
    renderApp(<AnalyzerPage />)
    await user.click(screen.getByRole('button', { name: /try an example draft/i }))
    await user.click(screen.getByRole('button', { name: /analyze my draft/i }))
    const btn = await screen.findByRole('button', { name: /starting/i })
    expect(btn).toBeDisabled()
    release(jsonRes({ analysis_id: 'z', status: 'pending', events_url: '/e' }, { status: 202 }))
    await screen.findByTestId('analysis-route')
  })
})

// ---------------------------------------------------------------- analysis page
const route = { route: '/analysis/abc', path: '/analysis/:id' }
const GET = '/api/analyses/abc'
const EVENTS = '/api/analyses/abc/events'

describe('AnalysisPage', () => {
  it('shows a skeleton, then the full results for a finished analysis', async () => {
    mockFetch({ [`GET ${GET}`]: () => jsonRes(detail()) })
    renderApp(<AnalysisPage />, route)
    expect(screen.getByLabelText(/loading analysis/i)).toBeInTheDocument()
    expect(await screen.findByRole('img', { name: /SEO score 12.3/ })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Content gaps', level: 2 })).toBeInTheDocument()
    expect(document.title).toMatch(/best running shoes · (Seoul|RankLens)/)
  })

  it('does not open an event stream for a finished analysis', async () => {
    const f = mockFetch({ [`GET ${GET}`]: () => jsonRes(detail()) })
    renderApp(<AnalysisPage />, route)
    await screen.findByRole('img', { name: /SEO score/ })
    expect(f.mock.calls.some(([u]) => String(u).endsWith('/events'))).toBe(false)
  })

  it('follows a running analysis live and swaps to results when the stream reports done', async () => {
    const running = detail({ status: 'running', stage: 'scraping', result: null, score: null })
    mockFetch({
      [`GET ${GET}`]: [() => jsonRes(running), () => jsonRes(detail())],
      [`GET ${EVENTS}`]: () =>
        sseRes([
          progress('queued', 2),
          progress('searching', 10),
          progress('indexing', 50, 'running', 'Chunking and embedding'),
          progress('done', 100, 'done'),
        ]),
    })
    renderApp(<AnalysisPage />, route)
    // after the stream's done event the query is refetched and results appear
    expect(await screen.findByRole('img', { name: /SEO score/ })).toBeInTheDocument()
  })

  it('shows live stage and message while the stream is still in progress', async () => {
    const running = detail({ status: 'running', stage: 'queued', result: null, score: null })
    mockFetch({
      [`GET ${GET}`]: () => jsonRes(running),
      [`GET ${EVENTS}`]: () =>
        sseRes([
          progress('searching', 10),
          progress('indexing', 50, 'running', 'Chunking and embedding'),
        ]),
    })
    renderApp(<AnalysisPage />, route)
    expect(
      await screen.findByRole('heading', { name: /analyzing “best running shoes”/i }),
    ).toBeInTheDocument()
    await waitFor(() =>
      expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '50'),
    )
    expect(screen.getByText('Chunking and embedding')).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')[2]).toHaveAttribute('aria-current', 'step')
  })

  it('falls back to the polled stage when the event stream fails', async () => {
    const running = detail({ status: 'running', stage: 'analyzing', result: null, score: null })
    mockFetch({
      [`GET ${GET}`]: () => jsonRes(running),
      [`GET ${EVENTS}`]: () => jsonRes({ detail: 'nope' }, { status: 500 }),
    })
    renderApp(<AnalysisPage />, route)
    await screen.findByRole('heading', { name: /analyzing/i })
    await waitFor(() =>
      expect(screen.getAllByRole('listitem')[3]).toHaveAttribute('aria-current', 'step'),
    )
  })

  it('shows the failure message from the server', async () => {
    mockFetch({
      [`GET ${GET}`]: () =>
        jsonRes(
          detail({
            status: 'failed',
            result: null,
            score: null,
            error: 'Search results are temporarily unavailable. Please try again shortly.',
          }),
        ),
    })
    renderApp(<AnalysisPage />, route)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/could not be completed/i)
    expect(alert).toHaveTextContent(/temporarily unavailable/i)
    expect(screen.getByRole('link', { name: /new analysis/i })).toHaveAttribute('href', '/')
  })

  it('shows an error immediately when the stream reports one, before polling catches up', async () => {
    const running = detail({ status: 'running', stage: 'scraping', result: null, score: null })
    mockFetch({
      [`GET ${GET}`]: () => jsonRes(running),
      [`GET ${EVENTS}`]: () =>
        sseRes([
          progress('scraping', 25),
          progress('error', 0, 'error', 'Only 2 of 10 competitor pages could be read.'),
        ]),
    })
    renderApp(<AnalysisPage />, route)
    expect(await screen.findByRole('alert')).toHaveTextContent(/only 2 of 10 competitor pages/i)
  })

  it('explains a 404 as private to the browser that ran it', async () => {
    mockFetch({ [`GET ${GET}`]: () => jsonRes({ detail: 'Analysis not found.' }, { status: 404 }) })
    renderApp(<AnalysisPage />, route)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/analysis not found/i)
    expect(alert).toHaveTextContent(/different browser/i)
    expect(screen.queryByRole('button', { name: /retry/i })).toBeNull()
  })

  it('retries transient errors automatically, then offers a manual retry', async () => {
    const user = userEvent.setup()
    const boom = () => jsonRes({ detail: 'Server hiccup' }, { status: 500 })
    // initial request + 2 automatic retries fail; the manual retry then succeeds
    const f = mockFetch({ [`GET ${GET}`]: [boom, boom, boom, () => jsonRes(detail())] })
    renderApp(<AnalysisPage />, route)
    expect(await screen.findByRole('alert')).toHaveTextContent(/server hiccup/i)
    expect(f.mock.calls.filter(([u]) => String(u) === GET)).toHaveLength(3)
    await user.click(screen.getByRole('button', { name: /retry/i }))
    expect(await screen.findByRole('img', { name: /SEO score/ })).toBeInTheDocument()
  })
})
