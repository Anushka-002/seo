import { CheckCircle2, ChevronDown, ExternalLink, Lightbulb } from 'lucide-react'
import { useState } from 'react'
import { CitedText, CopyButton } from '@/components/common'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Collapsible, CollapsibleContent, CollapsibleTrigger, Progress } from '@/components/ui/misc'
import { hostname, pct, SEVERITY_LABEL } from '@/lib/format'
import type { GapRecommendation, Severity, Source, TopicGap } from '@/lib/types'
import { cn } from '@/lib/utils'

const SEVERITY_BADGE: Record<Severity, 'destructive' | 'warning' | 'secondary'> = {
  high: 'destructive',
  medium: 'warning',
  low: 'secondary',
}

export function GapCard({
  gap,
  rec,
  sources,
  totalPages,
  defaultOpen = false,
}: {
  gap: TopicGap
  rec?: GapRecommendation
  sources: Source[]
  totalPages: number
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  const covered = Math.round(gap.coverage * 100)
  return (
    <Card className="overflow-hidden">
      <div className="p-5">
        <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
          <div className="min-w-0">
            <h3 className="text-base font-semibold leading-snug">{gap.label}</h3>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Covered by {gap.page_count} of {totalPages} top pages · your draft covers about{' '}
              {covered}%
            </p>
          </div>
          <Badge variant={SEVERITY_BADGE[gap.severity]}>{SEVERITY_LABEL[gap.severity]}</Badge>
        </div>
        <Progress
          value={covered}
          label={`Draft coverage of ${gap.label}`}
          className="mt-3 h-1.5"
          barClassName="bg-warning"
        />

        {rec ? (
          <div className="mt-4 space-y-3">
            <p className="text-sm leading-relaxed">
              <CitedText text={rec.recommendation} sources={sources} />
            </p>
            <div className="flex flex-wrap items-center gap-2 rounded-md bg-muted px-3 py-2 text-sm">
              <Lightbulb className="size-4 text-primary" aria-hidden="true" />
              <span className="text-muted-foreground">Suggested heading:</span>
              <span className="font-medium">{rec.heading_suggestion}</span>
              <CopyButton text={rec.heading_suggestion} className="ml-auto h-7" />
            </div>
            {rec.generated_by === 'template' && (
              <p className="text-xs text-muted-foreground">
                Automatic summary from competitor data (AI-written advice was unavailable).
              </p>
            )}
          </div>
        ) : (
          <p className="mt-4 text-sm text-muted-foreground">
            No recommendation was generated for this topic.
          </p>
        )}
      </div>

      {rec && rec.evidence.length > 0 && (
        <Collapsible open={open} onOpenChange={setOpen} className="border-t bg-muted/40">
          <CollapsibleTrigger className="flex w-full items-center justify-between px-5 py-3 text-sm font-medium text-muted-foreground hover:text-foreground">
            What competitors wrote ({rec.evidence.length} passages)
            <ChevronDown
              className={cn('size-4 transition-transform', open && 'rotate-180')}
              aria-hidden="true"
            />
          </CollapsibleTrigger>
          <CollapsibleContent>
            <ul className="space-y-3 px-5 pb-5">
              {rec.evidence.map((e) => {
                const src = sources.find((s) => s.n === e.source_n)
                return (
                  <li key={e.chunk_id} className="rounded-md border bg-card p-3 text-sm">
                    <p className="leading-relaxed text-muted-foreground">“{e.excerpt}”</p>
                    <p className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
                      <Badge variant="accent">Source {e.source_n}</Badge>
                      {src && (
                        <a
                          href={src.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-primary hover:underline"
                        >
                          {hostname(src.url)}
                          <ExternalLink className="size-3" aria-hidden="true" />
                        </a>
                      )}
                      {e.heading && (
                        <span className="text-muted-foreground">· under “{e.heading}”</span>
                      )}
                    </p>
                  </li>
                )
              })}
            </ul>
          </CollapsibleContent>
        </Collapsible>
      )}
    </Card>
  )
}

export function TopicsSection({
  topics,
  recommendations,
  sources,
  totalPages,
}: {
  topics: TopicGap[]
  recommendations: GapRecommendation[]
  sources: Source[]
  totalPages: number
}) {
  const gaps = topics.filter((t) => t.is_gap)
  const covered = topics.filter((t) => !t.is_gap)
  const recFor = new Map(recommendations.map((r) => [r.cluster_id, r]))

  if (topics.length === 0) {
    return (
      <Card className="p-6 text-sm text-muted-foreground">
        Competitors for this keyword do not share common subtopics, so no gaps could be measured.
      </Card>
    )
  }
  return (
    <div className="space-y-4">
      {gaps.length === 0 ? (
        <Card className="flex items-center gap-3 border-success/30 bg-success/5 p-5 text-sm">
          <CheckCircle2 className="size-5 text-success" aria-hidden="true" />
          <p>
            <span className="font-medium">No major content gaps.</span> Your draft covers every
            subtopic that several top-ranking pages share.
          </p>
        </Card>
      ) : (
        gaps.map((g, i) => (
          <GapCard
            key={g.cluster_id}
            gap={g}
            rec={recFor.get(g.cluster_id)}
            sources={sources}
            totalPages={totalPages}
            defaultOpen={i === 0}
          />
        ))
      )}

      {covered.length > 0 && (
        <Card className="p-5">
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
            <CheckCircle2 className="size-4 text-success" aria-hidden="true" />
            Topics you already cover ({covered.length})
          </h3>
          <ul className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
            {covered.map((t) => (
              <li key={t.cluster_id} className="flex items-center justify-between gap-3 text-sm">
                <span className="truncate">{t.label}</span>
                <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                  {pct(t.coverage)} · {t.page_count}/{totalPages} pages
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}
