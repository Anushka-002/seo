import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { vi } from 'vitest'
import { ToastProvider } from '@/components/toast'
import { TooltipProvider } from '@/components/ui/tooltip'
import type { AnalysisDetail, AnalysisResult } from '@/lib/types'
import weak from './fixtures/weak.json'
import strong from './fixtures/strong.json'
import noLlm from './fixtures/no_llm.json'

export const weakResult = weak as unknown as AnalysisResult
export const strongResult = strong as unknown as AnalysisResult
export const noLlmResult = noLlm as unknown as AnalysisResult

export function renderApp(ui: ReactElement, { route = '/', path = '*' } = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, retryDelay: 0, refetchInterval: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <ToastProvider>
        <MemoryRouter initialEntries={[route]}>
          <Routes>
            <Route path={path} element={ui} />
            <Route path="/analysis/:id" element={<div data-testid="analysis-route" />} />
          </Routes>
        </MemoryRouter>
        </ToastProvider>
      </TooltipProvider>
    </QueryClientProvider>,
  )
}

export function detail(over: Partial<AnalysisDetail> = {}): AnalysisDetail {
  return {
    id: 'abc',
    keyword: 'best running shoes',
    status: 'done',
    score: weakResult.score,
    is_demo: false,
    created_at: '2026-10-10T10:00:00Z',
    country: 'us',
    stage: 'done',
    result: weakResult,
    error: null,
    ...over,
  }
}

export const jsonRes = (body: unknown, init: ResponseInit = {}) =>
  new Response(JSON.stringify(body), { headers: { 'content-type': 'application/json' }, ...init })

export function sseRes(events: { event: string; data: unknown }[]): Response {
  const text = events
    .map((e, i) => `id: ${i}\nevent: ${e.event}\ndata: ${JSON.stringify(e.data)}\n\n`)
    .join('')
  const enc = new TextEncoder()
  return new Response(
    new ReadableStream({
      start(c) {
        c.enqueue(enc.encode(text))
        c.close()
      },
    }),
    { headers: { 'content-type': 'text/event-stream' } },
  )
}

export const progress = (stage: string, pct: number, status = 'running', message = stage) => ({
  event: status === 'running' ? 'progress' : status,
  data: { analysis_id: 'abc', stage, status, message, progress: pct, seq: 0, data: {} },
})

/** Route-table fetch mock: keys are "METHOD /path"; handlers may be consumed in order via arrays. */
export function mockFetch(routes: Record<string, (() => Response) | (() => Response)[]>) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url =
      typeof input === 'string' ? input : input instanceof URL ? input.pathname : input.url
    const key = `${init?.method ?? 'GET'} ${url}`
    const h = routes[key]
    if (!h) throw new Error(`unmocked request: ${key}`)
    if (Array.isArray(h)) return (h.length > 1 ? h.shift()! : h[0])()
    return h()
  })
}
