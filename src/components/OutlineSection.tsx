import { CopyButton } from '@/components/common'
import { Card } from '@/components/ui/card'
import type { OutlineItem } from '@/lib/types'
import { cn } from '@/lib/utils'

export function outlineToMarkdown(items: OutlineItem[]): string {
  return items.map((i) => `${'#'.repeat(i.level)} ${i.heading}`).join('\n\n')
}

export function OutlineList({ items }: { items: OutlineItem[] }) {
  return (
    <Card className="p-5">
      <ol className="space-y-3">
        {items.map((item, i) => (
          <li key={`${i}-${item.heading}`} className={cn('flex gap-3', item.level === 3 && 'ml-7')}>
            <span
              className="mt-0.5 shrink-0 rounded bg-accent px-1.5 py-0.5 text-[0.65rem] font-semibold text-accent-foreground"
              aria-label={`Heading level ${item.level}`}
            >
              H{item.level}
            </span>
            <div className="min-w-0">
              <p className="font-medium leading-snug">{item.heading}</p>
              {item.notes && <p className="mt-0.5 text-sm text-muted-foreground">{item.notes}</p>}
            </div>
          </li>
        ))}
      </ol>
      <div className="mt-5 border-t pt-4">
        <CopyButton text={outlineToMarkdown(items)} label="Copy outline as Markdown" />
      </div>
    </Card>
  )
}
