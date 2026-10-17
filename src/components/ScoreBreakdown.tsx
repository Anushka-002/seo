import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
} from 'recharts'
import { Progress } from '@/components/ui/misc'
import type { ScoreComponent } from '@/lib/types'

const SHORT: Record<string, string> = {
  'Topic coverage': 'Topics',
  'Keyword & phrase coverage': 'Phrases',
  'Keyword placement': 'Placement',
  'Structure & length': 'Structure',
  'Search intent match': 'Intent',
  Readability: 'Readability',
}

const pctOf = (c: ScoreComponent) => (c.max_score ? (c.score / c.max_score) * 100 : 0)

export function ScoreRadar({ components }: { components: ScoreComponent[] }) {
  const data = components.map((c) => ({
    name: SHORT[c.name] ?? c.name,
    value: Math.round(pctOf(c)),
  }))
  const summary = data.map((d) => `${d.name} ${d.value}%`).join(', ')
  return (
    <div role="img" aria-label={`Score profile: ${summary}`} className="h-[280px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart data={data} outerRadius="72%">
          <PolarGrid stroke="hsl(var(--border))" />
          <PolarAngleAxis
            dataKey="name"
            tick={{ fontSize: 12, fill: 'hsl(var(--muted-foreground))' }}
          />
          <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
          <Radar
            dataKey="value"
            stroke="hsl(var(--primary))"
            fill="hsl(var(--primary))"
            fillOpacity={0.22}
            strokeWidth={2}
            isAnimationActive={false}
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  )
}

export function ScoreBars({ components }: { components: ScoreComponent[] }) {
  return (
    <ul className="space-y-4">
      {components.map((c) => {
        const p = pctOf(c)
        const tone = p >= 75 ? 'bg-success' : p >= 40 ? 'bg-warning' : 'bg-destructive'
        return (
          <li key={c.name}>
            <div className="mb-1.5 flex items-baseline justify-between gap-3">
              <span className="text-sm font-medium">{c.name}</span>
              <span className="text-sm tabular-nums text-muted-foreground">
                <span className="font-semibold text-foreground">{c.score.toFixed(1)}</span> /{' '}
                {c.max_score}
              </span>
            </div>
            <Progress value={p} label={`${c.name} score`} barClassName={tone} className="h-1.5" />
            <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{c.reason}</p>
          </li>
        )
      })}
    </ul>
  )
}
