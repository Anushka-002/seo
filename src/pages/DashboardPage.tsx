import { ArrowDownRight, ArrowUpRight, Minus, Search } from 'lucide-react'
import { useEffect, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Section } from '@/components/common'
import { ScoreTrendChart, TopKeywordsChart } from '@/components/DashboardCharts'
import { HistoryTable } from '@/components/HistoryTable'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Progress, Skeleton } from '@/components/ui/misc'
import { useDashboardStats } from '@/hooks/useDashboard'
import { pct } from '@/lib/format'
import type { DashboardStats } from '@/lib/types'

function Kpi({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <Card className="p-5">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-1 text-3xl font-semibold tabular-nums tracking-tight">{value}</p>
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
    </Card>
  )
}

function Change({ value }: { value: number | null }) {
  if (value === null) return <>Run two or more analyses to see a trend</>
  const Icon = value > 0 ? ArrowUpRight : value < 0 ? ArrowDownRight : Minus
  const tone = value > 0 ? 'text-success' : value < 0 ? 'text-destructive' : ''
  return (
    <span className={`inline-flex items-center gap-1 ${tone}`}>
      <Icon className="size-3.5" aria-hidden="true" />
      {value > 0 ? '+' : ''}
      {value} since the first shown analysis
    </span>
  )
}

function Kpis({ s }: { s: DashboardStats }) {
  const fmt = (n: number | null) => (n === null ? '–' : Math.round(n))
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <Kpi label="Analyses" value={s.total_analyses} />
      <Kpi label="Average score" value={fmt(s.avg_score)} />
      <Kpi label="Best score" value={fmt(s.best_score)} />
      <Kpi label="Latest score" value={fmt(s.latest_score)} hint={<Change value={s.score_change} />} />
    </div>
  )
}

function EmptyState() {
  return (
    <Card className="mx-auto max-w-xl p-8 text-center">
      <span className="mx-auto flex size-12 items-center justify-center rounded-full bg-accent text-accent-foreground">
        <Search aria-hidden="true" />
      </span>
      <h2 className="mt-4 text-xl font-semibold">No analyses yet</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        Your scores, trends and most common content gaps will appear here after your first analysis.
        History is private to this browser.
      </p>
      <Button asChild className="mt-6">
        <Link to="/">Analyze a draft</Link>
      </Button>
    </Card>
  )
}

export default function DashboardPage() {
  const stats = useDashboardStats()
  useEffect(() => {
    document.title = 'Dashboard · Seoul'
  }, [])

  if (stats.isLoading) {
    return (
      <div className="space-y-6" aria-busy="true" aria-label="Loading dashboard">
        <Skeleton className="h-9 w-48" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
        <Skeleton className="h-72" />
      </div>
    )
  }
  if (stats.isError || !stats.data) {
    return (
      <Card className="mx-auto max-w-xl p-8 text-center" role="alert">
        <h1 className="text-xl font-semibold">Could not load the dashboard</h1>
        <p className="mt-2 text-sm text-muted-foreground">{stats.error?.message ?? 'No data available.'}</p>
        <Button variant="outline" className="mt-6" onClick={() => void stats.refetch()}>
          Retry
        </Button>
      </Card>
    )
  }
  const s = stats.data
  const empty = s.total_analyses === 0

  return (
    <div className="space-y-10">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Dashboard</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Your analyses over time. Stored for this browser only.
        </p>
      </div>
      {empty ? (
        <EmptyState />
      ) : (
        <>
          <Kpis s={s} />
          <div className="grid gap-4 lg:grid-cols-2">
            <Card className="p-5">
              <h2 className="mb-3 text-sm font-semibold">Score over time</h2>
              {s.score_trend.length > 1 ? (
                <ScoreTrendChart points={s.score_trend} />
              ) : (
                <p className="py-16 text-center text-sm text-muted-foreground">
                  Run another analysis to see your trend.
                </p>
              )}
            </Card>
            <Card className="p-5">
              <h2 className="mb-3 text-sm font-semibold">Top keywords</h2>
              <TopKeywordsChart keywords={s.top_keywords} />
            </Card>
          </div>
          <Section
            id="common-gaps"
            title="Most common content gaps"
            description={`Topics competitors cover that your drafts missed, across your latest ${s.gap_sample_size} ${s.gap_sample_size === 1 ? 'analysis' : 'analyses'}.`}
          >
            {s.common_gaps.length === 0 ? (
              <p className="text-sm text-muted-foreground">No content gaps found. Nice work.</p>
            ) : (
              <Card className="p-5">
                <ul className="space-y-4">
                  {s.common_gaps.map((g) => (
                    <li key={g.label}>
                      <div className="mb-1.5 flex items-baseline justify-between gap-3 text-sm">
                        <span className="font-medium">{g.label}</span>
                        <span className="tabular-nums text-muted-foreground">
                          {g.count} of {s.gap_sample_size} · {pct(g.share)}
                        </span>
                      </div>
                      <Progress value={g.share * 100} label={`${g.label} gap frequency`} className="h-1.5" />
                    </li>
                  ))}
                </ul>
              </Card>
            )}
          </Section>
        </>
      )}
      <Section id="history" title="History">
        <HistoryTable />
      </Section>
    </div>
  )
}
