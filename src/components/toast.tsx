import { CheckCircle2, CircleAlert, X } from 'lucide-react'
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { cn } from '@/lib/utils'

export type ToastKind = 'success' | 'error'
interface ToastItem {
  id: number
  kind: ToastKind
  message: string
}
interface ToastApi {
  success: (message: string) => void
  error: (message: string) => void
}

const noop: ToastApi = { success: () => {}, error: () => {} }
const ToastContext = createContext<ToastApi>(noop)

/** Safe outside a provider (returns no-ops), so isolated component tests keep working. */
export const useToast = (): ToastApi => useContext(ToastContext)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const nextId = useRef(1)
  const timers = useRef(new Map<number, number>())

  const dismiss = useCallback((id: number) => {
    window.clearTimeout(timers.current.get(id))
    timers.current.delete(id)
    setItems((xs) => xs.filter((x) => x.id !== id))
  }, [])

  const push = useCallback(
    (kind: ToastKind, message: string) => {
      const id = nextId.current++
      setItems((xs) => [...xs.slice(-3), { id, kind, message }])
      timers.current.set(id, window.setTimeout(() => dismiss(id), kind === 'error' ? 7000 : 4000))
    },
    [dismiss],
  )

  useEffect(() => {
    const t = timers.current
    return () => t.forEach((h) => window.clearTimeout(h))
  }, [])

  const api = useMemo<ToastApi>(
    () => ({ success: (m) => push('success', m), error: (m) => push('error', m) }),
    [push],
  )

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        aria-live="polite"
        className="fixed bottom-4 right-4 z-50 flex w-[calc(100vw-2rem)] max-w-sm flex-col gap-2 print:hidden"
      >
        {items.map((t) => (
          <div
            key={t.id}
            role={t.kind === 'error' ? 'alert' : 'status'}
            className={cn(
              'flex items-start gap-3 rounded-lg border bg-card p-3 text-sm shadow-lg',
              t.kind === 'error' ? 'border-destructive/40' : 'border-success/40',
            )}
          >
            {t.kind === 'error' ? (
              <CircleAlert className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden="true" />
            ) : (
              <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-hidden="true" />
            )}
            <p className="flex-1">{t.message}</p>
            <button
              type="button"
              aria-label="Dismiss notification"
              onClick={() => dismiss(t.id)}
              className="rounded p-0.5 text-muted-foreground hover:text-foreground"
            >
              <X className="size-4" aria-hidden="true" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
