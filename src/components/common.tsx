import { Check, Copy } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { hostname } from '@/lib/format'
import type { Source } from '@/lib/types'
import { cn } from '@/lib/utils'

async function writeClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    try {
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      const ok = document.execCommand('copy')
      ta.remove()
      return ok
    } catch {
      return false
    }
  }
}

export function CopyButton({
  text,
  label = 'Copy',
  className,
}: {
  text: string
  label?: string
  className?: string
}) {
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle')
  const timer = useRef<number>()
  useEffect(() => () => window.clearTimeout(timer.current), [])
  async function onClick() {
    setState((await writeClipboard(text)) ? 'copied' : 'failed')
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setState('idle'), 1800)
  }
  return (
    <Button type="button" variant="outline" size="sm" onClick={onClick} className={className}>
      {state === 'copied' ? <Check className="text-success" /> : <Copy />}
      <span aria-live="polite">
        {state === 'copied' ? 'Copied' : state === 'failed' ? 'Copy failed' : label}
      </span>
    </Button>
  )
}

export function Section({
  id,
  title,
  description,
  action,
  children,
}: {
  id: string
  title: string
  description?: ReactNode
  action?: ReactNode
  children: ReactNode
}) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-20">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id={`${id}-title`} className="text-xl font-semibold tracking-tight">
            {title}
          </h2>
          {description && (
            <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{description}</p>
          )}
        </div>
        {action}
      </div>
      {children}
    </section>
  )
}

export function CharCounter({
  value,
  max,
  className,
}: {
  value: number
  max: number
  className?: string
}) {
  const over = value > max
  return (
    <span
      className={cn(
        'text-xs tabular-nums',
        over ? 'font-medium text-destructive' : 'text-muted-foreground',
        className,
      )}
      aria-label={`${value} of ${max} characters${over ? ', over the limit' : ''}`}
    >
      {value}/{max}
    </span>
  )
}

/** Splits text on [n] markers and renders each as a link chip to the cited competitor page. */
export function CitedText({ text, sources }: { text: string; sources: Source[] }) {
  const byN = new Map(sources.map((s) => [s.n, s]))
  const parts = text.split(/(\[\d+\])/g)
  return (
    <>
      {parts.map((part, i) => {
        const m = /^\[(\d+)\]$/.exec(part)
        if (!m) return <span key={i}>{part}</span>
        const src = byN.get(Number(m[1]))
        if (!src) return <span key={i}>{part}</span>
        return (
          <Tooltip key={i}>
            <TooltipTrigger asChild>
              <a
                href={src.url}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`Source ${src.n}: ${hostname(src.url)}`}
                className="mx-0.5 inline-flex size-[1.15rem] -translate-y-px items-center justify-center rounded-full bg-accent align-middle text-[0.65rem] font-semibold text-accent-foreground no-underline ring-1 ring-primary/20 hover:bg-primary hover:text-primary-foreground"
              >
                {src.n}
              </a>
            </TooltipTrigger>
            <TooltipContent>
              <p className="font-medium">{src.title || hostname(src.url)}</p>
              <p className="text-muted-foreground">
                {hostname(src.url)} · ranks #{src.rank}
              </p>
            </TooltipContent>
          </Tooltip>
        )
      })}
    </>
  )
}
