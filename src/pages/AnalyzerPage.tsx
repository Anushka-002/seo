import { useMutation } from '@tanstack/react-query'
import {
  ChevronDown,
  FileText,
  Link2,
  Loader2,
  Search,
  ShieldCheck,
  Play,
  Sparkles,
  Wand2,
} from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { CharCounter } from '@/components/common'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input, Label, Select, Textarea } from '@/components/ui/input'
import { useToast } from '@/components/toast'
import { Alert, Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/misc'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ApiError, createAnalysis, startDemo } from '@/lib/api'
import { EXAMPLE_KEYWORD, EXAMPLE_TEXT } from '@/lib/example'
import {
  countWords,
  emptyForm,
  MAX_META,
  MAX_TITLE,
  MAX_WORDS,
  MIN_WORDS,
  toRequest,
  validateForm,
  type FormValues,
} from '@/lib/validate'
import { cn } from '@/lib/utils'

const COUNTRIES: [string, string][] = [
  ['us', 'United States'],
  ['gb', 'United Kingdom'],
  ['in', 'India'],
  ['ca', 'Canada'],
  ['au', 'Australia'],
  ['de', 'Germany'],
  ['fr', 'France'],
  ['es', 'Spain'],
  ['br', 'Brazil'],
  ['sg', 'Singapore'],
  ['ae', 'United Arab Emirates'],
]

function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null
  return (
    <p id={id} className="mt-1.5 text-sm text-destructive">
      {message}
    </p>
  )
}

export default function AnalyzerPage() {
  const navigate = useNavigate()
  const [form, setForm] = useState<FormValues>(emptyForm)
  const [submitted, setSubmitted] = useState(false)
  const [optionalOpen, setOptionalOpen] = useState(false)

  useEffect(() => {
    document.title = 'Seoul · SEO Content Optimizer'
  }, [])

  const errors = validateForm(form)
  const shown = submitted ? errors : {}
  const words = countWords(form.text)
  const set = <K extends keyof FormValues>(k: K, v: FormValues[K]) =>
    setForm((f) => ({ ...f, [k]: v }))

  const toast = useToast()
  const mutation = useMutation({
    mutationFn: createAnalysis,
    onSuccess: (res) => navigate(`/analysis/${res.analysis_id}`),
  })
  const demo = useMutation({
    mutationFn: startDemo,
    onSuccess: (res) => navigate(`/analysis/${res.analysis_id}`),
    onError: (e: Error) => toast.error(e.message || 'The demo is unavailable right now.'),
  })

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    setSubmitted(true)
    if (Object.keys(errors).length > 0) return
    mutation.mutate(toRequest(form))
  }

  function loadExample() {
    setForm({ ...emptyForm, keyword: EXAMPLE_KEYWORD, text: EXAMPLE_TEXT, mode: 'text' })
    setSubmitted(false)
  }

  const apiError = mutation.error instanceof ApiError ? mutation.error : null
  const retryMinutes = apiError?.retryAfter ? Math.ceil(apiError.retryAfter / 60) : null
  const errorText = apiError
    ? apiError.status === 429 && retryMinutes
      ? `${apiError.message.replace(/\s*Try again later\.?\s*$/i, '')} You can try again in about ${retryMinutes} minute${retryMinutes > 1 ? 's' : ''}.`
      : apiError.message
    : ''

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-8 text-center">
        <h1 className="text-balance text-3xl font-semibold tracking-tight sm:text-5xl">
          See exactly what your draft is missing
        </h1>
        <p className="mx-auto mt-4 max-w-xl text-pretty text-muted-foreground sm:text-lg">
          Seoul reads the pages that already rank for your keyword, finds the topics and phrases
          you left out, and tells you what to add, with sources.
        </p>
        <ul className="mt-5 flex flex-wrap justify-center gap-x-6 gap-y-2 text-sm text-muted-foreground">
          <li className="flex items-center gap-1.5">
            <Search className="size-4 text-primary" aria-hidden="true" />
            Reads the top 10 results
          </li>
          <li className="flex items-center gap-1.5">
            <Sparkles className="size-4 text-primary" aria-hidden="true" />
            Finds gaps with RAG
          </li>
          <li className="flex items-center gap-1.5">
            <ShieldCheck className="size-4 text-primary" aria-hidden="true" />
            Cites every suggestion
          </li>
        </ul>
        <div className="mt-6 flex flex-col items-center gap-1.5">
          <Button type="button" variant="outline" onClick={() => demo.mutate()} disabled={demo.isPending}>
            {demo.isPending ? <Loader2 className="animate-spin" /> : <Play />} Try demo
          </Button>
          <p className="text-xs text-muted-foreground">
            See a finished analysis instantly. No keyword or API quota needed.
          </p>
        </div>
      </div>

      <Card className="p-5 sm:p-8">
        <form onSubmit={onSubmit} noValidate className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-[1fr_12rem]">
            <div>
              <Label htmlFor="keyword">Target keyword</Label>
              <Input
                id="keyword"
                className="mt-2"
                placeholder="e.g. best running shoes"
                value={form.keyword}
                onChange={(e) => set('keyword', e.target.value)}
                aria-invalid={!!shown.keyword}
                aria-describedby={shown.keyword ? 'keyword-error' : undefined}
                maxLength={120}
                autoComplete="off"
              />
              <FieldError id="keyword-error" message={shown.keyword} />
            </div>
            <div>
              <Label htmlFor="country">Search country</Label>
              <Select
                id="country"
                className="mt-2"
                value={form.country}
                onChange={(e) => set('country', e.target.value)}
              >
                {COUNTRIES.map(([code, name]) => (
                  <option key={code} value={code}>
                    {name}
                  </option>
                ))}
              </Select>
            </div>
          </div>

          <Tabs value={form.mode} onValueChange={(v) => set('mode', v as FormValues['mode'])}>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <TabsList aria-label="Draft source">
                <TabsTrigger value="text">
                  <FileText className="size-4" aria-hidden="true" />
                  Paste text
                </TabsTrigger>
                <TabsTrigger value="url">
                  <Link2 className="size-4" aria-hidden="true" />
                  From URL
                </TabsTrigger>
              </TabsList>
              <Button type="button" variant="ghost" size="sm" onClick={loadExample}>
                <Wand2 /> Try an example draft
              </Button>
            </div>

            <TabsContent value="text">
              <Label htmlFor="draft-text" className="sr-only">
                Your draft
              </Label>
              <Textarea
                id="draft-text"
                placeholder="Paste your article here…"
                value={form.text}
                onChange={(e) => set('text', e.target.value)}
                aria-invalid={!!shown.text}
                aria-describedby={cn('draft-count', shown.text && 'draft-error')}
                rows={10}
              />
              <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                <span>
                  Tip: start headings with <code className="rounded bg-muted px-1">#</code>,{' '}
                  <code className="rounded bg-muted px-1">##</code> or{' '}
                  <code className="rounded bg-muted px-1">###</code> so structure is scored.
                </span>
                <span
                  id="draft-count"
                  className={cn(
                    'tabular-nums',
                    words >= MIN_WORDS && words <= MAX_WORDS ? 'text-success' : '',
                  )}
                >
                  {words.toLocaleString()} words · min {MIN_WORDS}
                </span>
              </div>
              <FieldError id="draft-error" message={shown.text} />
            </TabsContent>

            <TabsContent value="url">
              <Label htmlFor="draft-url" className="sr-only">
                Draft URL
              </Label>
              <Input
                id="draft-url"
                type="url"
                inputMode="url"
                placeholder="https://yourdomain.com/your-article"
                value={form.url}
                onChange={(e) => set('url', e.target.value)}
                aria-invalid={!!shown.url}
                aria-describedby={cn('url-help', shown.url && 'url-error')}
              />
              <p id="url-help" className="mt-2 text-xs text-muted-foreground">
                We fetch the public page and read its title, meta description and headings
                automatically. Private and internal addresses are blocked.
              </p>
              <FieldError id="url-error" message={shown.url} />
            </TabsContent>
          </Tabs>

          {form.mode === 'text' && (
            <Collapsible open={optionalOpen} onOpenChange={setOptionalOpen}>
              <CollapsibleTrigger className="flex items-center gap-1.5 text-sm font-medium text-primary hover:underline">
                <ChevronDown
                  className={cn('size-4 transition-transform', !optionalOpen && '-rotate-90')}
                  aria-hidden="true"
                />
                Add title tag &amp; meta description (optional)
              </CollapsibleTrigger>
              <CollapsibleContent className="mt-4 space-y-4">
                <div>
                  <div className="flex items-center justify-between">
                    <Label htmlFor="title">Title tag</Label>
                    <CharCounter value={form.title.length} max={MAX_TITLE} />
                  </div>
                  <Input
                    id="title"
                    className="mt-2"
                    value={form.title}
                    onChange={(e) => set('title', e.target.value)}
                    aria-invalid={!!shown.title}
                  />
                  <FieldError id="title-error" message={shown.title} />
                </div>
                <div>
                  <div className="flex items-center justify-between">
                    <Label htmlFor="meta">Meta description</Label>
                    <CharCounter value={form.meta.length} max={MAX_META} />
                  </div>
                  <Textarea
                    id="meta"
                    className="mt-2 min-h-[84px]"
                    rows={3}
                    value={form.meta}
                    onChange={(e) => set('meta', e.target.value)}
                    aria-invalid={!!shown.meta}
                  />
                  <FieldError id="meta-error" message={shown.meta} />
                </div>
                <p className="text-xs text-muted-foreground">
                  Providing these lets the placement score check your keyword in them and compare
                  your title with our suggestion.
                </p>
              </CollapsibleContent>
            </Collapsible>
          )}

          {apiError && (
            <Alert variant="destructive">
              <p>{errorText}</p>
            </Alert>
          )}
          {mutation.error && !apiError && (
            <Alert variant="destructive">
              <p>Something went wrong. Please try again.</p>
            </Alert>
          )}

          <Button type="submit" size="lg" className="w-full" disabled={mutation.isPending}>
            {mutation.isPending ? (
              <>
                <Loader2 className="animate-spin" /> Starting…
              </>
            ) : (
              <>
                <Search /> Analyze my draft
              </>
            )}
          </Button>
        </form>
      </Card>
    </div>
  )
}
