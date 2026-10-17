import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Section } from '@/components/common'
import { PipelineDiagram } from '@/components/PipelineDiagram'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'

const WEIGHTS: [string, number, string][] = [
  ['Topic coverage', 30, 'How well your draft covers the subtopics the top pages share.'],
  ['Keyword & phrase coverage', 20, 'Phrases that appear across many top pages and are missing from yours.'],
  ['Keyword placement', 15, 'Your keyword in the title, H1, first 100 words and meta description.'],
  ['Structure & length', 15, 'Word count and heading count versus the competitor median.'],
  ['Search intent match', 10, 'Whether your draft serves the intent the results show (guide, comparison, shop…).'],
  ['Readability', 10, 'Flesch reading ease compared with the pages that rank.'],
]

export default function HowItWorksPage() {
  useEffect(() => {
    document.title = 'How it works · Seoul'
  }, [])
  return (
    <div className="space-y-12">
      <div className="max-w-2xl">
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">How Seoul works</h1>
        <p className="mt-3 text-muted-foreground sm:text-lg">
          Seoul uses retrieval-augmented generation (RAG) over the pages that already rank. Every
          suggestion is written from passages it actually retrieved, so you can click through to the
          source.
        </p>
      </div>

      <Section id="pipeline" title="The pipeline" description="Six named steps run in order as a LangGraph graph. Progress streams to your screen as each one starts.">
        <PipelineDiagram />
      </Section>

      <Section id="score" title="How the score is calculated" description="The score is deterministic: the same inputs give the same number. The AI only writes advice, never the score.">
        <Card className="divide-y">
          {WEIGHTS.map(([name, pts, why]) => (
            <div key={name} className="flex items-start gap-4 p-4">
              <span className="w-14 shrink-0 text-right text-2xl font-semibold tabular-nums text-primary">
                {pts}
              </span>
              <div>
                <h3 className="font-medium">{name}</h3>
                <p className="text-sm text-muted-foreground">{why}</p>
              </div>
            </div>
          ))}
        </Card>
      </Section>

      <Section id="limits" title="What to keep in mind">
        <ul className="max-w-2xl list-disc space-y-2 pl-5 text-sm text-muted-foreground">
          <li>Scores measure alignment with today’s top results. They do not guarantee rankings.</li>
          <li>Pages that block scraping are skipped; at least 4 competitor pages are needed.</li>
          <li>Your history is stored against an anonymous id in this browser, not an account.</li>
        </ul>
        <Button asChild className="mt-6">
          <Link to="/">Analyze a draft</Link>
        </Button>
      </Section>
    </div>
  )
}
