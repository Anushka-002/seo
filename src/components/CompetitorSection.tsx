import { ArrowDown, ArrowUp, Check, ExternalLink, Minus, X } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { hostname, pct } from '@/lib/format'
import type { CompetitorSummary, IntentResult, PlacementCheck, StructureMetrics } from '@/lib/types'
import { cn } from '@/lib/utils'

export function CompetitorTable({
  competitors,
  structure,
}: {
  competitors: CompetitorSummary[]
  structure: StructureMetrics
}) {
  const maxWords = Math.max(structure.draft_words, ...competitors.map((c) => c.word_count), 1)
  const bar = (n: number, you = false) => (
    <div className="flex items-center gap-3">
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-secondary" aria-hidden="true">
        <div
          className={cn('h-full rounded-full', you ? 'bg-primary' : 'bg-muted-foreground/40')}
          style={{ width: `${(n / maxWords) * 100}%` }}
        />
      </div>
      <span className="tabular-nums">{n.toLocaleString()}</span>
    </div>
  )
  return (
    <Card className="overflow-x-auto">
      <table className="w-full text-sm">
        <caption className="sr-only">Top-ranking pages compared with your draft</caption>
        <thead>
          <tr className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground">
            <th scope="col" className="px-4 py-2.5 font-medium">
              #
            </th>
            <th scope="col" className="px-4 py-2.5 font-medium">
              Page
            </th>
            <th scope="col" className="px-4 py-2.5 font-medium">
              Words
            </th>
            <th scope="col" className="px-4 py-2.5 text-right font-medium">
              Headings
            </th>
          </tr>
        </thead>
        <tbody>
          <tr className="border-b bg-accent/50">
            <td className="px-4 py-2.5">
              <Badge>You</Badge>
            </td>
            <td className="px-4 py-2.5 font-medium">Your draft</td>
            <td className="px-4 py-2.5">{bar(structure.draft_words, true)}</td>
            <td className="px-4 py-2.5 text-right tabular-nums">{structure.draft_headings}</td>
          </tr>
          {competitors.map((c) => (
            <tr key={c.url} className="border-b last:border-0">
              <td className="px-4 py-2.5 tabular-nums text-muted-foreground">{c.rank}</td>
              <td className="max-w-[22rem] px-4 py-2.5">
                <a
                  href={c.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="group inline-flex max-w-full items-center gap-1.5 hover:text-primary"
                >
                  <span className="truncate">{c.title || hostname(c.url)}</span>
                  <ExternalLink
                    className="size-3 shrink-0 opacity-50 group-hover:opacity-100"
                    aria-hidden="true"
                  />
                </a>
                <p className="truncate text-xs text-muted-foreground">{hostname(c.url)}</p>
              </td>
              <td className="px-4 py-2.5">{bar(c.word_count)}</td>
              <td className="px-4 py-2.5 text-right tabular-nums">{c.headings}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}

function StatTile({
  label,
  yours,
  median,
  unit,
  higherIsBetter = true,
  hint,
}: {
  label: string
  yours: number
  median: number
  unit?: string
  higherIsBetter?: boolean
  hint?: string
}) {
  const diff = yours - median
  const near = Math.abs(diff) <= Math.max(1, median * 0.1)
  const good = near || (higherIsBetter ? diff > 0 : diff < 0)
  const Icon = near ? Minus : diff > 0 ? ArrowUp : ArrowDown
  return (
    <Card className="p-5">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-1 text-3xl font-semibold tabular-nums tracking-tight">
        {Math.round(yours).toLocaleString()}
        {unit && <span className="ml-1 text-base font-normal text-muted-foreground">{unit}</span>}
      </p>
      <p
        className={cn(
          'mt-2 flex items-center gap-1.5 text-xs',
          good ? 'text-success' : 'text-warning',
        )}
      >
        <Icon className="size-3.5" aria-hidden="true" />
        {near
          ? 'In line with'
          : `${Math.abs(Math.round(diff)).toLocaleString()} ${diff > 0 ? 'above' : 'below'}`}{' '}
        the competitor median ({Math.round(median).toLocaleString()})
      </p>
      {hint && <p className="mt-2 text-xs text-muted-foreground">{hint}</p>}
    </Card>
  )
}

export function StructureStats({ s }: { s: StructureMetrics }) {
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      <StatTile label="Word count" yours={s.draft_words} median={s.median_competitor_words} />
      <StatTile label="Headings" yours={s.draft_headings} median={s.median_competitor_headings} />
      <StatTile
        label="Reading ease"
        yours={s.draft_readability}
        median={s.median_competitor_readability}
        hint="Flesch score: higher is easier to read. Aim to match the pages that rank."
      />
    </div>
  )
}

const PLACEMENT_LABEL: Record<PlacementCheck['element'], string> = {
  title: 'Title tag',
  h1: 'H1 heading',
  first_100_words: 'First 100 words',
  meta_description: 'Meta description',
}

export function PlacementChecks({ checks }: { checks: PlacementCheck[] }) {
  return (
    <Card className="p-5">
      <h3 className="mb-3 text-sm font-semibold">Keyword placement</h3>
      <ul className="space-y-2.5">
        {checks.map((c) => {
          const meta = {
            exact: { icon: Check, cls: 'text-success', text: 'Exact keyword present' },
            partial: { icon: Minus, cls: 'text-warning', text: 'Words present, not as a phrase' },
            missing: { icon: X, cls: 'text-destructive', text: 'Keyword missing' },
            not_provided: {
              icon: Minus,
              cls: 'text-muted-foreground',
              text: 'Not provided, not scored',
            },
          }[c.status]
          const Icon = meta.icon
          return (
            <li key={c.element} className="flex items-center justify-between gap-3 text-sm">
              <span>{PLACEMENT_LABEL[c.element]}</span>
              <span className={cn('flex items-center gap-1.5 text-xs', meta.cls)}>
                <Icon className="size-4" aria-hidden="true" />
                {meta.text}
              </span>
            </li>
          )
        })}
      </ul>
    </Card>
  )
}

export function IntentCard({
  serp,
  draft,
  match,
}: {
  serp: IntentResult
  draft: IntentResult
  match: number
}) {
  return (
    <Card className="p-5">
      <h3 className="mb-3 text-sm font-semibold">Search intent</h3>
      <dl className="space-y-2.5 text-sm">
        <div className="flex items-center justify-between gap-3">
          <dt className="text-muted-foreground">What the results reward</dt>
          <dd>
            <Badge variant="accent" className="capitalize">
              {serp.primary}
            </Badge>
          </dd>
        </div>
        <div className="flex items-center justify-between gap-3">
          <dt className="text-muted-foreground">What your draft reads as</dt>
          <dd>
            <Badge
              variant={draft.primary === serp.primary ? 'success' : 'warning'}
              className="capitalize"
            >
              {draft.primary}
            </Badge>
          </dd>
        </div>
        <div className="flex items-center justify-between gap-3">
          <dt className="text-muted-foreground">Match</dt>
          <dd className="font-medium tabular-nums">{pct(match)}</dd>
        </div>
      </dl>
      {serp.cues.length > 0 && (
        <p className="mt-3 text-xs text-muted-foreground">
          Signals in the results: {serp.cues.join(', ')}.
        </p>
      )}
    </Card>
  )
}
