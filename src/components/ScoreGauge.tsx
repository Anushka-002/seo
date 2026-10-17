import { animate, motion, useReducedMotion } from 'framer-motion'
import { useEffect, useState } from 'react'
import { scoreBand, type Tone } from '@/lib/format'

const TONE_COLOR: Record<Tone, string> = {
  success: 'hsl(var(--success))',
  warning: 'hsl(var(--warning))',
  danger: 'hsl(var(--destructive))',
}

export function ScoreGauge({ score, size = 184 }: { score: number; size?: number }) {
  const reduced = useReducedMotion()
  const band = scoreBand(score)
  const stroke = 14
  const r = (size - stroke) / 2
  const circ = 2 * Math.PI * r
  const [shown, setShown] = useState(0)

  useEffect(() => {
    if (reduced) return
    const controls = animate(0, score, { duration: 1.1, ease: 'easeOut', onUpdate: setShown })
    return () => controls.stop()
  }, [score, reduced])
  // With reduced motion there is no count-up: show the final value directly.
  const display = reduced ? score : shown

  return (
    <div
      role="img"
      aria-label={`SEO score ${score} out of 100: ${band.label}`}
      className="relative shrink-0"
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="hsl(var(--secondary))"
          strokeWidth={stroke}
        />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={TONE_COLOR[band.tone]}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circ}
          initial={{ strokeDashoffset: reduced ? circ * (1 - score / 100) : circ }}
          animate={{ strokeDashoffset: circ * (1 - score / 100) }}
          transition={{ duration: reduced ? 0 : 1.1, ease: 'easeOut' }}
        />
      </svg>
      <div
        className="absolute inset-0 flex flex-col items-center justify-center"
        aria-hidden="true"
      >
        <span className="text-5xl font-semibold tabular-nums tracking-tight">
          {display.toFixed(0)}
        </span>
        <span className="text-xs text-muted-foreground">out of 100</span>
      </div>
    </div>
  )
}
