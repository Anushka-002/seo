import { Check, X } from 'lucide-react'
import { CharCounter, CopyButton } from '@/components/common'
import { Alert } from '@/components/ui/misc'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import type { SeoSuggestions } from '@/lib/types'

export const TITLE_MAX = 60
export const META_MAX = 155

function SerpPreview({ title, description }: { title: string | null; description: string | null }) {
  return (
    <div className="rounded-lg border bg-card p-4" aria-label="Search result preview">
      <p className="truncate text-xs text-[#188038] dark:text-[#81c995]">
        yourdomain.com › your-page
      </p>
      <p className="mt-1 line-clamp-2 text-lg leading-snug text-[#1a0dab] dark:text-[#8ab4f8]">
        {title || <span className="italic text-muted-foreground">No title provided</span>}
      </p>
      <p className="mt-1 line-clamp-3 text-sm leading-relaxed text-muted-foreground">
        {description || <span className="italic">No meta description provided</span>}
      </p>
    </div>
  )
}

function KeywordFlag({ ok, label }: { ok: boolean; label: string }) {
  return ok ? (
    <Badge variant="success">
      <Check aria-hidden="true" />
      {label}
    </Badge>
  ) : (
    <Badge variant="warning">
      <X aria-hidden="true" />
      {label}
    </Badge>
  )
}

export function TitleMeta({
  currentTitle,
  currentMeta,
  suggestions,
}: {
  currentTitle: string | null
  currentMeta: string | null
  suggestions: SeoSuggestions | null
}) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="space-y-4 p-5">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Your current
        </h3>
        <SerpPreview title={currentTitle} description={currentMeta} />
        <dl className="space-y-2 text-sm">
          <div className="flex items-center justify-between">
            <dt>Title length</dt>
            <dd>
              <CharCounter value={currentTitle?.length ?? 0} max={TITLE_MAX} />
            </dd>
          </div>
          <div className="flex items-center justify-between">
            <dt>Description length</dt>
            <dd>
              <CharCounter value={currentMeta?.length ?? 0} max={META_MAX} />
            </dd>
          </div>
        </dl>
        {!currentTitle && !currentMeta && (
          <p className="text-xs text-muted-foreground">
            You did not provide a title or meta description, so they were not scored. Add them next
            time for a fuller placement check.
          </p>
        )}
      </Card>

      <Card className="space-y-4 border-primary/30 p-5">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-primary">Suggested</h3>
        {suggestions ? (
          <>
            <SerpPreview title={suggestions.title} description={suggestions.meta_description} />
            <div className="space-y-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">Title</span>
                <CharCounter value={suggestions.title.length} max={TITLE_MAX} />
                <KeywordFlag ok={suggestions.title_has_keyword} label="Has keyword" />
                <CopyButton text={suggestions.title} label="Copy title" className="ml-auto" />
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">Description</span>
                <CharCounter value={suggestions.meta_description.length} max={META_MAX} />
                <KeywordFlag ok={suggestions.meta_has_keyword} label="Has keyword" />
                <CopyButton
                  text={suggestions.meta_description}
                  label="Copy description"
                  className="ml-auto"
                />
              </div>
            </div>
          </>
        ) : (
          <Alert variant="info">
            <p>AI-written title and description suggestions are not available for this analysis.</p>
          </Alert>
        )}
      </Card>
    </div>
  )
}
