import { Check, X } from 'lucide-react'
import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Progress } from '@/components/ui/misc'
import type { Keyphrase } from '@/lib/types'

type Filter = 'all' | 'missing' | 'used'

export function KeyphraseTable({
  phrases,
  totalPages,
}: {
  phrases: Keyphrase[]
  totalPages: number
}) {
  const [filter, setFilter] = useState<Filter>('all')
  const missing = phrases.filter((p) => !p.in_draft).length
  const rows = phrases.filter((p) =>
    filter === 'all' ? true : filter === 'missing' ? !p.in_draft : p.in_draft,
  )

  if (phrases.length === 0) {
    return (
      <Card className="p-6 text-sm text-muted-foreground">
        No phrases were shared by enough competitor pages to compare.
      </Card>
    )
  }
  const options: { id: Filter; label: string }[] = [
    { id: 'all', label: `All (${phrases.length})` },
    { id: 'missing', label: `Missing (${missing})` },
    { id: 'used', label: `Used (${phrases.length - missing})` },
  ]
  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b p-4">
        <p className="text-sm text-muted-foreground">
          Phrases that many top pages use.{' '}
          <span className="font-medium text-foreground">{missing}</span> missing from your draft.
        </p>
        <div
          role="group"
          aria-label="Filter phrases"
          className="inline-flex rounded-lg bg-muted p-1"
        >
          {options.map((o) => (
            <Button
              key={o.id}
              type="button"
              size="sm"
              variant={filter === o.id ? 'default' : 'ghost'}
              aria-pressed={filter === o.id}
              onClick={() => setFilter(o.id)}
              className="h-7"
            >
              {o.label}
            </Button>
          ))}
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">Competitor phrases and whether your draft uses them</caption>
          <thead>
            <tr className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground">
              <th scope="col" className="px-4 py-2.5 font-medium">
                Phrase
              </th>
              <th scope="col" className="px-4 py-2.5 font-medium">
                Used by top pages
              </th>
              <th scope="col" className="px-4 py-2.5 text-right font-medium">
                Your draft
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.phrase} className="border-b last:border-0">
                <td className="px-4 py-2.5 font-medium">{p.phrase}</td>
                <td className="px-4 py-2.5">
                  <div className="flex min-w-[9rem] items-center gap-3">
                    <Progress
                      value={p.page_share * 100}
                      label={`${p.phrase} used by ${p.pages} pages`}
                      className="h-1.5 w-24"
                    />
                    <span className="text-xs tabular-nums text-muted-foreground">
                      {p.pages}/{totalPages}
                    </span>
                  </div>
                </td>
                <td className="px-4 py-2.5 text-right">
                  {p.in_draft ? (
                    <Badge variant="success">
                      <Check aria-hidden="true" />
                      Used
                    </Badge>
                  ) : (
                    <Badge variant="destructive">
                      <X aria-hidden="true" />
                      Missing
                    </Badge>
                  )}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={3} className="px-4 py-6 text-center text-muted-foreground">
                  Nothing to show for this filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
