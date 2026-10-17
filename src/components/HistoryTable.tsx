import { ArrowDown, ArrowUp, ArrowUpDown, ExternalLink, Search, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/misc'
import { useToast } from '@/components/toast'
import { useDeleteAnalysis, useHistory } from '@/hooks/useDashboard'
import { formatDate, scoreBand } from '@/lib/format'
import type { SortKey, SortOrder } from '@/lib/types'

const PAGE = 10
const COLUMNS: [SortKey, string][] = [
  ['keyword', 'Keyword'],
  ['score', 'Score'],
  ['created_at', 'Date'],
]

export function HistoryTable() {
  const toast = useToast()
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')
  const [sort, setSort] = useState<SortKey>('created_at')
  const [order, setOrder] = useState<SortOrder>('desc')
  const [offset, setOffset] = useState(0)
  const [confirmId, setConfirmId] = useState<string | null>(null)

  useEffect(() => {
    const t = window.setTimeout(() => {
      setQ(search.trim())
      setOffset(0)
    }, 250)
    return () => window.clearTimeout(t)
  }, [search])

  const history = useHistory({ limit: PAGE, offset, q, sort, order })
  const remove = useDeleteAnalysis(
    () => {
      setConfirmId(null)
      toast.success('Analysis deleted.')
    },
    (m) => toast.error(m || 'Could not delete the analysis.'),
  )
  const data = history.data

  // Deleting the last row of a page would leave an empty page: step back.
  useEffect(() => {
    if (data && data.items.length === 0 && offset > 0) setOffset(Math.max(0, offset - PAGE))
  }, [data, offset])

  function toggleSort(key: SortKey) {
    if (key === sort) setOrder(order === 'asc' ? 'desc' : 'asc')
    else {
      setSort(key)
      setOrder(key === 'keyword' ? 'asc' : 'desc')
    }
    setOffset(0)
  }

  const ariaSort = (key: SortKey) =>
    key !== sort ? 'none' : order === 'asc' ? 'ascending' : 'descending'

  return (
    <div>
      <div className="relative mb-4 max-w-sm">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden="true"
        />
        <Input
          type="search"
          aria-label="Search history by keyword"
          placeholder="Search keywords…"
          className="pl-9"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {history.isError ? (
        <p role="alert" className="text-sm text-destructive">
          Could not load your history. {history.error.message}
        </p>
      ) : !data ? (
        <div className="space-y-2" aria-busy="true" aria-label="Loading history">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-11 w-full" />
          ))}
        </div>
      ) : data.items.length === 0 ? (
        <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
          {q ? `No analyses match “${q}”.` : 'No analyses yet.'}
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-left text-sm">
            <thead className="bg-muted/50 text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                {COLUMNS.map(([key, label]) => (
                  <th key={key} scope="col" aria-sort={ariaSort(key)} className="px-4 py-2.5">
                    <button
                      type="button"
                      onClick={() => toggleSort(key)}
                      className="inline-flex items-center gap-1 font-medium uppercase hover:text-foreground"
                    >
                      {label}
                      {key !== sort ? (
                        <ArrowUpDown className="size-3" aria-hidden="true" />
                      ) : order === 'asc' ? (
                        <ArrowUp className="size-3" aria-hidden="true" />
                      ) : (
                        <ArrowDown className="size-3" aria-hidden="true" />
                      )}
                    </button>
                  </th>
                ))}
                <th scope="col" className="px-4 py-2.5 text-right">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {data.items.map((row) => (
                <tr key={row.id} className="bg-card">
                  <td className="max-w-[16rem] truncate px-4 py-3 font-medium">{row.keyword}</td>
                  <td className="px-4 py-3 tabular-nums">
                    {row.status === 'done' && row.score !== null ? (
                      <span className="font-semibold">
                        {Math.round(row.score)}{' '}
                        <span className="text-xs font-normal text-muted-foreground">
                          {scoreBand(row.score).label}
                        </span>
                      </span>
                    ) : (
                      <Badge variant={row.status === 'failed' ? 'destructive' : 'secondary'}>
                        {row.status === 'failed' ? 'Failed' : 'In progress'}
                      </Badge>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-muted-foreground">
                    {formatDate(row.created_at)}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1">
                      <Button asChild variant="ghost" size="sm">
                        <Link to={`/analysis/${row.id}`} aria-label={`Open analysis for ${row.keyword}`}>
                          <ExternalLink /> Open
                        </Link>
                      </Button>
                      {confirmId === row.id ? (
                        <>
                          <Button
                            variant="destructive"
                            size="sm"
                            disabled={remove.isPending}
                            onClick={() => remove.mutate(row.id)}
                            aria-label={`Confirm delete ${row.keyword}`}
                          >
                            Confirm
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => setConfirmId(null)}>
                            Cancel
                          </Button>
                        </>
                      ) : (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setConfirmId(row.id)}
                          aria-label={`Delete analysis for ${row.keyword}`}
                        >
                          <Trash2 /> Delete
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && data.total > PAGE && (
        <div className="mt-3 flex items-center justify-between text-sm text-muted-foreground">
          <span>
            {offset + 1}–{Math.min(offset + PAGE, data.total)} of {data.total}
          </span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
              Previous
            </Button>
            <Button variant="outline" size="sm" disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
