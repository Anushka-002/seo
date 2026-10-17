import { AlertCircle, Check, Loader2 } from 'lucide-react'
import { Progress } from '@/components/ui/misc'
import { activeStepIndex, STAGE_PROGRESS, STEPS } from '@/lib/stages'
import type { ProgressEvent } from '@/lib/types'
import { cn } from '@/lib/utils'

export function ProgressStepper({
  event,
  fallbackStage,
  failed = false,
}: {
  event: ProgressEvent | null
  fallbackStage?: string | null
  failed?: boolean
}) {
  const stage = event?.stage ?? fallbackStage ?? 'queued'
  const active = activeStepIndex(stage)
  const pct = event?.progress ?? STAGE_PROGRESS[stage] ?? 2
  const message =
    stage === 'queued'
      ? 'Waiting for a free analysis slot…'
      : (event?.message ?? STEPS[active]?.detail ?? 'Working…')

  return (
    <div>
      <Progress value={pct} label="Analysis progress" className="mb-2" />
      <p className="mb-6 text-sm text-muted-foreground" aria-live="polite">
        {message}
      </p>
      <ol className="space-y-1">
        {STEPS.map((step, i) => {
          const state =
            failed && i === active
              ? 'failed'
              : i < active
                ? 'done'
                : i === active
                  ? 'active'
                  : 'pending'
          const Icon = step.icon
          return (
            <li
              key={step.stage}
              aria-current={state === 'active' ? 'step' : undefined}
              className={cn(
                'flex items-start gap-3 rounded-lg px-3 py-2.5 transition-colors',
                state === 'active' && 'bg-accent',
                state === 'failed' && 'bg-destructive/10',
              )}
            >
              <span
                className={cn(
                  'mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full border',
                  state === 'done' && 'border-success/40 bg-success/10 text-success',
                  state === 'active' && 'border-primary/40 bg-card text-primary',
                  state === 'failed' && 'border-destructive/40 bg-card text-destructive',
                  state === 'pending' && 'bg-muted text-muted-foreground',
                )}
              >
                {state === 'done' ? (
                  <Check className="size-4" aria-hidden="true" />
                ) : state === 'active' ? (
                  <Loader2
                    className="size-4 animate-spin motion-reduce:animate-none"
                    aria-hidden="true"
                  />
                ) : state === 'failed' ? (
                  <AlertCircle className="size-4" aria-hidden="true" />
                ) : (
                  <Icon className="size-4" aria-hidden="true" />
                )}
              </span>
              <span className="min-w-0">
                <span
                  className={cn(
                    'block text-sm font-medium',
                    state === 'pending' && 'text-muted-foreground',
                  )}
                >
                  {step.label}
                  <span className="sr-only">
                    {state === 'done'
                      ? ' (complete)'
                      : state === 'active'
                        ? ' (in progress)'
                        : state === 'failed'
                          ? ' (failed)'
                          : ''}
                  </span>
                </span>
                {(state === 'active' || state === 'failed') && (
                  <span className="block text-xs text-muted-foreground">{step.detail}</span>
                )}
              </span>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
