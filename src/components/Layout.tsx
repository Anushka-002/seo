import { Link, NavLink, Outlet } from 'react-router-dom'
import { ThemeToggle } from '@/components/ThemeToggle'
import { cn } from '@/lib/utils'

const LINKS: [string, string][] = [
  ['/', 'Analyze'],
  ['/dashboard', 'Dashboard'],
  ['/how-it-works', 'How it works'],
]

export function SeoulLogo({ className }: { className?: string }) {
  return (
    <div className={cn('relative flex size-6 items-center justify-center', className)}>
      <svg viewBox="0 0 100 100" className="size-full text-primary" aria-hidden="true">
        <circle
          cx="50"
          cy="50"
          r="40"
          stroke="currentColor"
          strokeWidth="18"
          fill="none"
          strokeDasharray="251.2"
          strokeDashoffset="60"
        />
        <circle cx="50" cy="50" r="22" fill="currentColor" />
      </svg>
    </div>
  )
}

export function Layout() {
  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-card focus:px-3 focus:py-2 focus:shadow"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-40 border-b border-border/60 bg-background/80 backdrop-blur-md print:hidden">
        <div className="container flex h-14 items-center justify-between gap-2">
          <Link to="/" className="flex items-center gap-2.5 font-bold tracking-tight text-foreground">
            <SeoulLogo />
            <span className="text-lg">Seoul</span>
          </Link>
          <div className="flex items-center gap-1">
            <nav aria-label="Main" className="flex items-center gap-0.5 text-sm">
              {LINKS.map(([to, label]) => (
                <NavLink
                  key={to}
                  to={to}
                  end={to === '/'}
                  className={({ isActive }) =>
                    cn(
                      'whitespace-nowrap rounded-md px-2.5 py-1.5 font-medium transition-colors hover:bg-accent hover:text-accent-foreground sm:px-3',
                      isActive ? 'bg-accent font-semibold text-accent-foreground' : 'text-muted-foreground',
                    )
                  }
                >
                  {label}
                </NavLink>
              ))}
            </nav>
            <ThemeToggle />
          </div>
        </div>
      </header>
      <main id="main" className="container flex-1 py-8 sm:py-12">
        <Outlet />
      </main>
      <footer className="border-t py-6 text-center text-xs text-muted-foreground print:hidden">
        Seoul compares your draft with the pages that already rank. Scores are heuristic
        guidance, not a ranking guarantee.
      </footer>
    </div>
  )
}
