import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { ApiError, getAnalysis } from '@/lib/api'
import { streamProgress } from '@/lib/sse'
import type { ProgressEvent } from '@/lib/types'

/** Analysis detail. Polls every 2.5s while running as a safety net behind the SSE stream. */
export function useAnalysis(id: string) {
  return useQuery({
    queryKey: ['analysis', id],
    queryFn: () => getAnalysis(id),
    enabled: !!id,
    refetchInterval: (q) => {
      const s = q.state.data?.status
      return s === 'pending' || s === 'running' ? 2500 : false
    },
    retry: (count, err) =>
      !(err instanceof ApiError && err.status >= 400 && err.status < 500) && count < 2,
  })
}

/** Live progress over SSE. Failures are non-fatal: polling in useAnalysis covers them. */
export function useAnalysisProgress(id: string, active: boolean) {
  const [event, setEvent] = useState<ProgressEvent | null>(null)
  const qc = useQueryClient()
  useEffect(() => {
    if (!active || !id) return
    const ctrl = new AbortController()
    let cancelled = false
    streamProgress(id, {
      signal: ctrl.signal,
      onEvent: (e) => {
        if (cancelled) return
        setEvent(e)
        if (e.status !== 'running') void qc.invalidateQueries({ queryKey: ['analysis', id] })
      },
    }).catch(() => {
      /* stream dropped or aborted; polling continues */
    })
    return () => {
      cancelled = true
      ctrl.abort()
    }
  }, [id, active, qc])
  return { event }
}
