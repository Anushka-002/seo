import { AlertCircle, ArrowLeft, FlaskConical, RotateCw } from 'lucide-react'
import { useEffect } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ExportBar } from '@/components/ExportBar'
import { ProgressStepper } from '@/components/ProgressStepper'
import { ResultsView } from '@/components/ResultsView'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Alert, Skeleton } from '@/components/ui/misc'
import { useAnalysis, useAnalysisProgress } from '@/hooks/useAnalysis'
import { ApiError } from '@/lib/api'

function ErrorCard({
  title,
  message,
  retry,
}: {
  title: string
  message: string
  retry?: () => void
}) {
  return (
    <Card className="mx-auto max-w-xl p-8 text-center" role="alert">
      <span className="mx-auto flex size-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
        <AlertCircle aria-hidden="true" />
      </span>
      <h1 className="mt-4 text-xl font-semibold">{title}</h1>
      <p className="mt-2 text-sm text-muted-foreground">{message}</p>
      <div className="mt-6 flex justify-center gap-3">
        {retry && (
          <Button variant="outline" onClick={retry}>
            <RotateCw /> Retry
          </Button>
        )}
        <Button asChild>
          <Link to="/">
            <ArrowLeft /> New analysis
          </Link>
        </Button>
      </div>
    </Card>
  )
}

export default function AnalysisPage() {
  const { id = '' } = useParams()
  const q = useAnalysis(id)
  const detail = q.data
  const active = detail?.status === 'pending' || detail?.status === 'running'
  const { event } = useAnalysisProgress(id, active)

  useEffect(() => {
    document.title = detail?.keyword ? `${detail.keyword} · Seoul` : 'Seoul'
  }, [detail?.keyword])

  if (q.isLoading) {
    return (
      <div className="space-y-4" aria-busy="true" aria-label="Loading analysis">
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    )
  }
  if (q.isError) {
    const notFound = q.error instanceof ApiError && q.error.status === 404
    return (
      <ErrorCard
        title={notFound ? 'Analysis not found' : 'Could not load this analysis'}
        message={
          notFound
            ? 'It may have been deleted, or it was created in a different browser. Analyses are private to the browser that ran them.'
            : q.error.message
        }
        retry={notFound ? undefined : () => void q.refetch()}
      />
    )
  }
  if (!detail) return null

  const streamFailed = event?.status === 'error'
  if (detail.status === 'failed' || streamFailed) {
    return (
      <ErrorCard
        title="The analysis could not be completed"
        message={detail.error ?? event?.message ?? 'Something went wrong. Please try again.'}
      />
    )
  }
  if (active || !detail.result) {
    return (
      <Card className="mx-auto max-w-xl p-6 sm:p-8">
        <h1 className="text-xl font-semibold tracking-tight">Analyzing “{detail.keyword}”</h1>
        <p className="mb-6 mt-1 text-sm text-muted-foreground">
          This usually takes under a minute.
        </p>
        <ProgressStepper event={event} fallbackStage={detail.stage} />
      </Card>
    )
  }
  return (
    <div className="space-y-6">
      {detail.is_demo && (
        <Alert variant="info" className="print:hidden">
          <FlaskConical aria-hidden="true" />
          <p>
            This is a saved example analysis, so it opens instantly. To analyse your own draft,{' '}
            <Link to="/" className="font-medium underline">
              start a new analysis
            </Link>
            .
          </p>
        </Alert>
      )}
      <div className="flex justify-end">
        <ExportBar result={detail.result} />
      </div>
      <ResultsView result={detail.result} />
    </div>
  )
}
