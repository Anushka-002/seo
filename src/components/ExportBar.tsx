import { Download, FileDown } from 'lucide-react'
import { useMemo } from 'react'
import { CopyButton } from '@/components/common'
import { useToast } from '@/components/toast'
import { Button } from '@/components/ui/button'
import { downloadText, reportFilename } from '@/lib/download'
import { buildMarkdownReport } from '@/lib/exportMarkdown'
import type { AnalysisResult } from '@/lib/types'

/** Copy / download Markdown, or print to PDF (the browser's "Save as PDF"). */
export function ExportBar({ result }: { result: AnalysisResult }) {
  const toast = useToast()
  const markdown = useMemo(() => buildMarkdownReport(result), [result])

  function saveMarkdown() {
    try {
      downloadText(`${reportFilename(result.keyword)}.md`, markdown)
      toast.success('Markdown report downloaded.')
    } catch {
      toast.error('Could not create the file. Try “Copy report” instead.')
    }
  }

  function savePdf() {
    const previous = document.title
    document.title = reportFilename(result.keyword) // becomes the default PDF file name
    const restore = () => {
      document.title = previous
      window.removeEventListener('afterprint', restore)
    }
    window.addEventListener('afterprint', restore)
    try {
      window.print()
    } catch {
      restore()
      toast.error('Printing is not available in this browser. Use the Markdown export instead.')
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2 print:hidden" aria-label="Export report">
      <CopyButton text={markdown} label="Copy report" />
      <Button type="button" variant="outline" size="sm" onClick={saveMarkdown}>
        <Download /> Markdown
      </Button>
      <Button type="button" variant="outline" size="sm" onClick={savePdf}>
        <FileDown /> PDF
      </Button>
    </div>
  )
}
