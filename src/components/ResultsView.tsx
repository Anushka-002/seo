import { Info, TriangleAlert } from 'lucide-react'
import { Section } from '@/components/common'
import {
  CompetitorTable,
  IntentCard,
  PlacementChecks,
  StructureStats,
} from '@/components/CompetitorSection'
import { KeyphraseTable } from '@/components/KeyphraseTable'
import { OutlineList } from '@/components/OutlineSection'
import { ScoreGauge } from '@/components/ScoreGauge'
import { ScoreBars, ScoreRadar } from '@/components/ScoreBreakdown'
import { TitleMeta } from '@/components/TitleMeta'
import { TopicsSection } from '@/components/TopicsSection'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Alert } from '@/components/ui/misc'
import { scoreBand } from '@/lib/format'
import type { AnalysisResult, LlmStatus } from '@/lib/types'
import { cn } from '@/lib/utils'

const NAV = [
  ['overview', 'Overview'],
  ['gaps', 'Content gaps'],
  ['phrases', 'Phrases'],
  ['onpage', 'Title & meta'],
  ['outline', 'Outline'],
  ['competitors', 'Competitors'],
] as const

export function LlmNotice({ status, message }: { status: LlmStatus; message: string }) {
  if (status === 'ok') return null
  if (status === 'skipped')
    return (
      <Alert variant="info">
        <Info aria-hidden="true" />
        <p>
          AI-written advice is turned off on this server, so recommendations below are automatic
          summaries of what competitors cover. The score and gap analysis are unaffected.
        </p>
      </Alert>
    )
  return (
    <Alert variant="warning">
      <TriangleAlert aria-hidden="true" />
      <p>
        {status === 'failed'
          ? 'AI suggestions could not be generated.'
          : 'Some AI suggestions are missing.'}{' '}
        {message} The score and gap analysis are unaffected.
      </p>
    </Alert>
  )
}

export function ResultsView({ result }: { result: AnalysisResult }) {
  const band = scoreBand(result.score)
  const gaps = result.topics.filter((t) => t.is_gap)
  const missingPhrases = result.keyphrases.filter((k) => !k.in_draft).length
  const totalPages = result.competitors.length
  const stats: [string, string | number][] = [
    ['Content gaps', gaps.length],
    ['Missing phrases', missingPhrases],
    ['Pages compared', totalPages],
  ]

  return (
    <div className="space-y-10">
      <nav
        aria-label="On this page"
        className="sticky top-14 z-30 -mx-1 flex gap-1 overflow-x-auto rounded-lg border bg-background/95 p-1 shadow-sm backdrop-blur print:hidden"
      >
        {NAV.map(([id, label]) => (
          <a
            key={id}
            href={`#${id}`}
            className="whitespace-nowrap rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          >
            {label}
          </a>
        ))}
      </nav>

      <section id="overview" aria-labelledby="results-title" className="scroll-mt-20">
        <div className="space-y-4">
          <LlmNotice status={result.llm_status} message={result.llm_message} />
          <Card className="p-6 sm:p-8">
            <div className="flex flex-col items-center gap-8 sm:flex-row">
              <ScoreGauge score={result.score} />
              <div className="min-w-0 flex-1 text-center sm:text-left">
                <Badge
                  variant={
                    band.tone === 'success'
                      ? 'success'
                      : band.tone === 'warning'
                        ? 'warning'
                        : 'destructive'
                  }
                >
                  {band.label}
                </Badge>
                <h1 id="results-title" className="mt-3 text-2xl font-semibold tracking-tight">
                  Your draft for “{result.keyword}”
                </h1>
                <p className="mt-1 text-muted-foreground">{band.blurb}</p>
                <dl className="mt-5 grid grid-cols-3 gap-4">
                  {stats.map(([label, value]) => (
                    <div key={label}>
                      <dd className="text-2xl font-semibold tabular-nums">{value}</dd>
                      <dt className="text-xs text-muted-foreground">{label}</dt>
                    </div>
                  ))}
                </dl>
              </div>
            </div>
          </Card>
          <div className="grid gap-4 lg:grid-cols-5">
            <Card className="p-5 lg:col-span-2">
              <h2 className="text-sm font-semibold">Score profile</h2>
              <ScoreRadar components={result.components} />
            </Card>
            <Card className="p-5 lg:col-span-3">
              <h2 className="mb-4 text-sm font-semibold">How the score was built</h2>
              <ScoreBars components={result.components} />
            </Card>
          </div>
        </div>
      </section>

      <Section
        id="gaps"
        title="Content gaps"
        description="Subtopics that several top-ranking pages cover and your draft covers weakly or not at all. Numbered chips link to the competitor page each suggestion came from."
      >
        <TopicsSection
          topics={result.topics}
          recommendations={result.recommendations}
          sources={result.sources}
          totalPages={totalPages}
        />
      </Section>

      <Section
        id="phrases"
        title="Keyword & phrase coverage"
        description="Terms that appear on many of the top pages. Working in the relevant ones naturally can help topical relevance."
      >
        <KeyphraseTable phrases={result.keyphrases} totalPages={totalPages} />
      </Section>

      <Section id="onpage" title="Title, meta description & placement">
        <div className="space-y-4">
          <TitleMeta
            currentTitle={result.draft_title}
            currentMeta={result.draft_meta_description}
            suggestions={result.suggestions}
          />
          <div className="grid gap-4 md:grid-cols-2">
            <PlacementChecks checks={result.placement} />
            <IntentCard
              serp={result.serp_intent}
              draft={result.draft_intent}
              match={result.intent_match}
            />
          </div>
        </div>
      </Section>

      <Section
        id="outline"
        title="Suggested outline"
        description="A structure that keeps your strong sections and works in the missing topics."
      >
        {result.suggestions ? (
          <OutlineList items={result.suggestions.outline} />
        ) : (
          <Alert variant="info">
            <Info aria-hidden="true" />
            <p>An AI-generated outline is not available for this analysis.</p>
          </Alert>
        )}
      </Section>

      <Section
        id="competitors"
        title="How you compare"
        description="Length, structure and readability next to the pages you are competing with."
      >
        <div className={cn('space-y-4')}>
          <StructureStats s={result.structure} />
          <CompetitorTable competitors={result.competitors} structure={result.structure} />
          <p className="text-xs text-muted-foreground">
            Analysis used {result.n_clusters} shared subtopics and the “
            {result.embedder.split('/').pop()}” embedding model.
          </p>
        </div>
      </Section>
    </div>
  )
}
