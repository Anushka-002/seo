import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { formatDate } from '@/lib/format'
import type { KeywordStat, TrendPoint } from '@/lib/types'

const tick = { fontSize: 12, fill: 'hsl(var(--muted-foreground))' }
const tooltipStyle = {
  background: 'hsl(var(--card))',
  border: '1px solid hsl(var(--border))',
  borderRadius: 8,
  fontSize: 12,
  color: 'hsl(var(--foreground))',
}

export function ScoreTrendChart({ points }: { points: TrendPoint[] }) {
  const data = points.map((p, i) => ({ n: i + 1, score: p.score, keyword: p.keyword, at: p.created_at }))
  const summary = `Score over time for ${points.length} analyses, from ${points[0]?.score} to ${points[points.length - 1]?.score}`
  return (
    <div role="img" aria-label={summary} className="h-[260px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
          <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="n" tick={tick} tickLine={false} axisLine={false} allowDecimals={false} />
          <YAxis domain={[0, 100]} tick={tick} tickLine={false} axisLine={false} width={44} />
          <ChartTooltip
            contentStyle={tooltipStyle}
            labelFormatter={(_, payload) => {
              const p = payload?.[0]?.payload as { keyword: string; at: string } | undefined
              return p ? `${p.keyword} · ${formatDate(p.at)}` : ''
            }}
            formatter={(v) => [String(v), 'Score']}
          />
          <Line
            type="monotone"
            dataKey="score"
            stroke="hsl(var(--primary))"
            strokeWidth={2.5}
            dot={{ r: 3, fill: 'hsl(var(--primary))' }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export function TopKeywordsChart({ keywords }: { keywords: KeywordStat[] }) {
  const data = keywords.map((k) => ({
    name: k.keyword.length > 22 ? `${k.keyword.slice(0, 21)}…` : k.keyword,
    count: k.count,
    avg: k.avg_score,
  }))
  const summary = keywords.map((k) => `${k.keyword} ${k.count}`).join(', ')
  return (
    <div
      role="img"
      aria-label={`Most analysed keywords: ${summary}`}
      style={{ height: Math.max(180, data.length * 38 + 30) }}
      className="w-full"
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" horizontal={false} />
          <XAxis type="number" allowDecimals={false} tick={tick} tickLine={false} axisLine={false} />
          <YAxis type="category" dataKey="name" width={130} tick={tick} tickLine={false} axisLine={false} />
          <ChartTooltip
            cursor={{ fill: 'hsl(var(--muted))' }}
            contentStyle={tooltipStyle}
            formatter={(v, _n, item) => [
              `${v} (avg score ${(item.payload as { avg: number }).avg})`,
              'Analyses',
            ]}
          />
          <Bar dataKey="count" fill="hsl(var(--primary))" radius={[0, 4, 4, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
