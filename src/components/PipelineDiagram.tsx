import { motion, useReducedMotion } from 'framer-motion'
import {
  ArrowRight,
  ChevronDown,
  Database,
  FileText,
  Gauge,
  Layers,
  Search,
  Sparkles,
  type LucideIcon,
} from 'lucide-react'
import { Card } from '@/components/ui/card'

interface Node {
  name: string
  title: string
  detail: string
  icon: LucideIcon
}

// Mirrors the named nodes of the LangGraph pipeline in backend/app/services/pipeline.py.
export const PIPELINE: Node[] = [
  {
    name: 'fetch_serp',
    title: 'Search',
    detail: 'Top 10 Google results plus related searches, via Serper (DuckDuckGo fallback).',
    icon: Search,
  },
  {
    name: 'scrape_pages',
    title: 'Read',
    detail: 'Pages fetched in parallel with timeouts; clean text and H1–H3 headings extracted.',
    icon: FileText,
  },
  {
    name: 'build_index',
    title: 'Index',
    detail: 'About 300-token chunks with overlap, embedded locally and stored in a vector index.',
    icon: Layers,
  },
  {
    name: 'analyze_draft',
    title: 'Compare & score',
    detail:
      'Competitor chunks are clustered into subtopics; your draft is compared to each. The 0–100 score is computed here by fixed rules, not by an LLM.',
    icon: Gauge,
  },
  {
    name: 'generate_recommendations',
    title: 'Recommend',
    detail:
      'For each gap, the 3 closest competitor passages are retrieved and the LLM writes advice grounded only in them, with [n] citations.',
    icon: Sparkles,
  },
  {
    name: 'finalize',
    title: 'Save',
    detail: 'The result is stored so the dashboard can show history and trends.',
    icon: Database,
  },
]

export function PipelineDiagram() {
  const reduced = useReducedMotion()
  return (
    <ol className="grid gap-3 md:grid-cols-3" aria-label="Analysis pipeline">
      {PIPELINE.map((n, i) => (
        <motion.li
          key={n.name}
          initial={reduced ? false : { opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: reduced ? 0 : i * 0.06, duration: 0.3 }}
          className="relative"
        >
          <Card className="h-full p-5">
            <div className="flex items-center gap-3">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
                <n.icon className="size-5" aria-hidden="true" />
              </span>
              <div>
                <p className="text-xs text-muted-foreground">Step {i + 1}</p>
                <h3 className="font-semibold leading-tight">{n.title}</h3>
              </div>
            </div>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{n.detail}</p>
            <code className="mt-3 inline-block rounded bg-muted px-1.5 py-0.5 text-xs">{n.name}</code>
          </Card>
          {i < PIPELINE.length - 1 && (
            <>
              <ChevronDown
                className="mx-auto mt-2 size-5 text-muted-foreground md:hidden"
                aria-hidden="true"
              />
              {(i + 1) % 3 !== 0 && (
                <ArrowRight
                  className="absolute -right-[1.15rem] top-1/2 hidden size-5 -translate-y-1/2 text-muted-foreground md:block"
                  aria-hidden="true"
                />
              )}
            </>
          )}
        </motion.li>
      ))}
    </ol>
  )
}
