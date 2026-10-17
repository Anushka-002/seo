import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { CitedText, CopyButton } from '@/components/common'
import { KeyphraseTable } from '@/components/KeyphraseTable'
import { LlmNotice, ResultsView } from '@/components/ResultsView'
import { OutlineList, outlineToMarkdown } from '@/components/OutlineSection'
import { ProgressStepper } from '@/components/ProgressStepper'
import { ScoreGauge } from '@/components/ScoreGauge'
import { TitleMeta } from '@/components/TitleMeta'
import { TooltipProvider } from '@/components/ui/tooltip'
import { activeStepIndex, STEPS } from '@/lib/stages'
import type { ProgressEvent, Source } from '@/lib/types'
import { noLlmResult, renderApp, strongResult, weakResult } from '@/test/utils'

const sources: Source[] = [
  { n: 1, url: 'https://www.runnerlab.test/post', title: 'Runner Lab guide', rank: 1 },
  { n: 2, url: 'https://milesmag.test/x', title: 'Miles Mag', rank: 2 },
]

describe('ScoreGauge', () => {
  it.each([
    [12.3, 'Weak'],
    [55, 'Needs work'],
    [70, 'Good'],
    [91, 'Excellent'],
  ])('describes %s as %s for assistive tech', (score, label) => {
    render(<ScoreGauge score={score} />)
    expect(screen.getByRole('img')).toHaveAccessibleName(`SEO score ${score} out of 100: ${label}`)
  })
})

describe('CitedText', () => {
  it('turns known [n] markers into links to the source page and leaves unknown ones as text', () => {
    render(
      <TooltipProvider>
        <p>
          <CitedText
            text="Add a section [1] and expand it [2]. Odd marker [9]."
            sources={sources}
          />
        </p>
      </TooltipProvider>,
    )
    const link1 = screen.getByRole('link', { name: 'Source 1: runnerlab.test' })
    expect(link1).toHaveAttribute('href', 'https://www.runnerlab.test/post')
    expect(link1).toHaveAttribute('rel', 'noopener noreferrer')
    expect(link1).toHaveAttribute('target', '_blank')
    expect(screen.getByRole('link', { name: 'Source 2: milesmag.test' })).toBeInTheDocument()
    expect(screen.getAllByRole('link')).toHaveLength(2)
    expect(screen.getByText('[9]')).toBeInTheDocument() // unknown source: plain text, not a link
  })
  it('renders plain text when there are no markers', () => {
    render(
      <TooltipProvider>
        <CitedText text="Nothing to cite." sources={sources} />
      </TooltipProvider>,
    )
    expect(screen.getByText('Nothing to cite.')).toBeInTheDocument()
    expect(screen.queryByRole('link')).toBeNull()
  })
})

describe('CopyButton', () => {
  it('copies text and confirms', async () => {
    const user = userEvent.setup()
    const write = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue()
    render(<CopyButton text="hello" label="Copy title" />)
    await user.click(screen.getByRole('button', { name: /copy title/i }))
    expect(write).toHaveBeenCalledWith('hello')
    expect(await screen.findByText('Copied')).toBeInTheDocument()
  })
  it('reports failure when neither clipboard API nor fallback works', async () => {
    const user = userEvent.setup()
    vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValue(new Error('denied'))
    document.execCommand = vi.fn(() => false)
    render(<CopyButton text="x" />)
    await user.click(screen.getByRole('button'))
    expect(await screen.findByText('Copy failed')).toBeInTheDocument()
  })
})

const ev = (stage: ProgressEvent['stage'], progress: number, message = 'msg'): ProgressEvent => ({
  analysis_id: 'a',
  stage,
  status: 'running',
  message,
  progress,
  seq: 0,
  data: {},
})

describe('ProgressStepper', () => {
  it('marks earlier steps complete, the current one active, later ones pending', () => {
    render(<ProgressStepper event={ev('indexing', 50, 'Chunking and embedding')} />)
    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(STEPS.length)
    expect(items[0]).toHaveTextContent('(complete)')
    expect(items[1]).toHaveTextContent('(complete)')
    expect(items[2]).toHaveAttribute('aria-current', 'step')
    expect(items[2]).toHaveTextContent('(in progress)')
    expect(items[3]).not.toHaveAttribute('aria-current')
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '50')
    expect(screen.getByText('Chunking and embedding')).toBeInTheDocument()
  })
  it('shows a queued message before any step starts', () => {
    render(<ProgressStepper event={null} />)
    expect(screen.getByText(/waiting for a free analysis slot/i)).toBeInTheDocument()
    expect(screen.queryByRole('listitem', { current: 'step' })).toBeNull()
  })
  it('falls back to the polled stage when no stream events arrived', () => {
    render(<ProgressStepper event={null} fallbackStage="analyzing" />)
    expect(screen.getAllByRole('listitem')[3]).toHaveAttribute('aria-current', 'step')
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '65')
  })
  it('flags the failing step', () => {
    render(<ProgressStepper event={null} fallbackStage="scraping" failed />)
    expect(screen.getAllByRole('listitem')[1]).toHaveTextContent('(failed)')
  })
  it('maps stages to step indexes', () => {
    expect(activeStepIndex('queued')).toBe(-1)
    expect(activeStepIndex('searching')).toBe(0)
    expect(activeStepIndex('generating')).toBe(4)
    expect(activeStepIndex('done')).toBe(STEPS.length)
  })
})

describe('KeyphraseTable', () => {
  const phrases = [
    { phrase: 'midsole foam', pages: 5, page_share: 1, in_draft: true },
    { phrase: 'gait analysis', pages: 4, page_share: 0.8, in_draft: true },
    { phrase: 'stack height', pages: 4, page_share: 0.8, in_draft: false },
    { phrase: 'heel counter', pages: 3, page_share: 0.6, in_draft: false },
    { phrase: 'carbon plate', pages: 2, page_share: 0.4, in_draft: false },
  ]
  it('filters between all, missing and used phrases', async () => {
    const user = userEvent.setup()
    render(<KeyphraseTable phrases={phrases} totalPages={5} />)
    expect(screen.getAllByRole('row')).toHaveLength(6) // header + 5
    await user.click(screen.getByRole('button', { name: /missing \(3\)/i }))
    expect(screen.getAllByRole('row')).toHaveLength(4)
    expect(screen.queryByText('midsole foam')).toBeNull()
    expect(screen.getByRole('button', { name: /missing/i })).toHaveAttribute('aria-pressed', 'true')
    await user.click(screen.getByRole('button', { name: /used \(2\)/i }))
    expect(screen.getAllByRole('row')).toHaveLength(3)
    expect(screen.getByText('midsole foam')).toBeInTheDocument()
  })
  it('shows an empty-state row when a filter matches nothing', async () => {
    const user = userEvent.setup()
    render(<KeyphraseTable phrases={weakResult.keyphrases} totalPages={5} />)
    // the weak sample draft uses none of the competitor phrases
    await user.click(screen.getByRole('button', { name: /used \(0\)/i }))
    expect(screen.getByText(/nothing to show for this filter/i)).toBeInTheDocument()
  })
  it('handles an empty list', () => {
    render(<KeyphraseTable phrases={[]} totalPages={5} />)
    expect(screen.getByText(/no phrases were shared/i)).toBeInTheDocument()
  })
})

describe('TitleMeta', () => {
  it('shows current vs suggested with counters and keyword flags', () => {
    render(
      <TitleMeta
        currentTitle="Shoes"
        currentMeta="All about shoes"
        suggestions={weakResult.suggestions}
      />,
    )
    const s = weakResult.suggestions!
    expect(screen.getAllByText('Shoes').length).toBeGreaterThan(0)
    expect(screen.getAllByLabelText(`${s.title.length} of 60 characters`)).not.toHaveLength(0)
    expect(screen.getAllByText('Has keyword')).toHaveLength(2)
    expect(screen.getByRole('button', { name: /copy title/i })).toBeInTheDocument()
  })
  it('flags an over-long current title and handles missing inputs/suggestions', () => {
    const long = 'x'.repeat(75)
    render(<TitleMeta currentTitle={long} currentMeta={null} suggestions={null} />)
    expect(screen.getByLabelText('75 of 60 characters, over the limit')).toBeInTheDocument()
    expect(screen.getByText(/no meta description provided/i)).toBeInTheDocument()
    expect(screen.getByText(/not available for this analysis/i)).toBeInTheDocument()
  })
  it('explains when nothing was provided', () => {
    render(<TitleMeta currentTitle={null} currentMeta={null} suggestions={null} />)
    expect(screen.getByText(/did not provide a title or meta description/i)).toBeInTheDocument()
  })
})

describe('OutlineList', () => {
  it('indents H3s and exports Markdown', () => {
    const items = weakResult.suggestions!.outline
    expect(
      outlineToMarkdown([
        { level: 2, heading: 'A', notes: '' },
        { level: 3, heading: 'B', notes: '' },
      ]),
    ).toBe('## A\n\n### B')
    render(<OutlineList items={items} />)
    expect(screen.getAllByRole('listitem')).toHaveLength(items.length)
    expect(screen.getByRole('button', { name: /copy outline as markdown/i })).toBeInTheDocument()
  })
})

describe('LlmNotice', () => {
  it('is silent when ok, informative when skipped, a warning when partial/failed', () => {
    const { rerender, container } = render(<LlmNotice status="ok" message="" />)
    expect(container).toBeEmptyDOMElement()
    rerender(<LlmNotice status="skipped" message="" />)
    expect(screen.getByRole('alert')).toHaveTextContent(/turned off on this server/i)
    rerender(<LlmNotice status="partial" message="Rate limit reached." />)
    expect(screen.getByRole('alert')).toHaveTextContent(
      /some ai suggestions are missing\. rate limit reached/i,
    )
    rerender(<LlmNotice status="failed" message="Key rejected." />)
    expect(screen.getByRole('alert')).toHaveTextContent(/could not be generated\. key rejected/i)
  })
})

describe('ResultsView (real backend output)', () => {
  it('renders the weak draft: score, six gap cards with cited advice, evidence, and all sections', async () => {
    const user = userEvent.setup()
    renderApp(<ResultsView result={weakResult} />)
    expect(screen.getByRole('img', { name: /SEO score 12.3 out of 100: Weak/ })).toBeInTheDocument()

    const gaps = weakResult.topics.filter((t) => t.is_gap)
    expect(gaps).toHaveLength(6)
    for (const g of gaps)
      expect(screen.getByRole('heading', { name: g.label, level: 3 })).toBeInTheDocument()

    // every recommendation shows at least one working citation link to a competitor page
    const sourceUrls = new Set(weakResult.sources.map((s) => s.url))
    const cites = screen.getAllByRole('link', { name: /^Source \d+:/ })
    expect(cites.length).toBeGreaterThanOrEqual(gaps.length)
    cites.forEach((a) => expect(sourceUrls.has(a.getAttribute('href')!)).toBe(true))

    // evidence of the first (high priority) gap is open by default; the next is collapsed
    expect(screen.getAllByText(/What competitors wrote \(3 passages\)/)).toHaveLength(gaps.length)
    const firstRec = weakResult.recommendations[0]
    const excerpt = new RegExp(firstRec.evidence[0].excerpt.slice(0, 30))
    expect(screen.getAllByText(excerpt)[0]).toBeVisible()
    const badges = () => screen.getAllByText(/^Source \d+$/).length
    const openBefore = badges()
    expect(openBefore).toBe(firstRec.evidence.length) // only the first card is expanded
    await user.click(screen.getAllByText(/What competitors wrote/)[1])
    expect(badges()).toBeGreaterThan(openBefore)

    for (const heading of [
      'Content gaps',
      'Keyword & phrase coverage',
      'Title, meta description & placement',
      'Suggested outline',
      'How you compare',
    ]) {
      expect(screen.getByRole('heading', { name: heading, level: 2 })).toBeInTheDocument()
    }
    expect(
      screen.getByRole('heading', { level: 1, name: /your draft for “best running shoes”/i }),
    ).toBeInTheDocument()
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
    expect(screen.getByRole('navigation', { name: 'On this page' })).toBeInTheDocument()
    const table = screen.getByRole('table', { name: /top-ranking pages compared/i })
    expect(within(table).getByText('Your draft')).toBeInTheDocument() // comparison table row
    expect(within(table).getAllByRole('row')).toHaveLength(1 + 1 + weakResult.competitors.length)
    expect(screen.queryByText(/turned off on this server/)).toBeNull()
  })

  it('celebrates a strong draft with no gaps and still lists covered topics', () => {
    renderApp(<ResultsView result={strongResult} />)
    expect(screen.getByText(/no major content gaps/i)).toBeInTheDocument()
    expect(screen.getByText(/topics you already cover \(\d+\)/i)).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /Excellent|Good/ })).toBeInTheDocument()
  })

  it('degrades gracefully without AI: template notes, notice, no suggested rewrite', () => {
    renderApp(<ResultsView result={noLlmResult} />)
    expect(screen.getByText(/turned off on this server/i)).toBeInTheDocument()
    expect(screen.getAllByText(/ai-written advice was unavailable/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/outline is not available/i)).toBeInTheDocument()
    expect(
      within(screen.getByRole('region', { name: /title, meta description/i })).getByText(
        /not available for this analysis/i,
      ),
    ).toBeInTheDocument()
  })
})
