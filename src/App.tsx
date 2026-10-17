import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { lazy, Suspense } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Layout } from '@/components/Layout'
import { ToastProvider } from '@/components/toast'
import { TooltipProvider } from '@/components/ui/tooltip'
import AnalyzerPage from '@/pages/AnalyzerPage'
import NotFoundPage from '@/pages/NotFoundPage'

// Results pull in the charting library; load them only when needed.
const AnalysisPage = lazy(() => import('@/pages/AnalysisPage'))
const DashboardPage = lazy(() => import('@/pages/DashboardPage'))
const HowItWorksPage = lazy(() => import('@/pages/HowItWorksPage'))

export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { refetchOnWindowFocus: false, staleTime: 5_000 } },
  })
}

export function AppRoutes() {
  return (
    <Suspense
      fallback={<p className="py-16 text-center text-sm text-muted-foreground">Loading…</p>}
    >
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<AnalyzerPage />} />
          <Route path="analysis/:id" element={<AnalysisPage />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="how-it-works" element={<HowItWorksPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </Suspense>
  )
}

export default function App() {
  const client = makeQueryClient()
  return (
    <QueryClientProvider client={client}>
      <TooltipProvider delayDuration={150}>
        <ToastProvider>
          <BrowserRouter>
            <AppRoutes />
          </BrowserRouter>
        </ToastProvider>
      </TooltipProvider>
    </QueryClientProvider>
  )
}
