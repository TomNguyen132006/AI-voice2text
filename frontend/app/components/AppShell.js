'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'
import BackLink from './BackLink'

const icon = { 'aria-hidden': true, viewBox: '0 0 24 24', width: 20, height: 20, fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }

const ITEMS = [
  {
    href: '/app/library',
    label: 'Library',
    icon: (
      <svg {...icon}>
        <path d="M4 5v14M9 5v14M14 6l4 13M4 19h5" />
      </svg>
    ),
  },
  {
    href: '/app/new',
    label: 'New lecture',
    icon: (
      <svg {...icon}>
        <path d="M12 5v14M5 12h14" />
      </svg>
    ),
  },
  {
    href: '/app/how',
    label: 'How it works',
    icon: (
      <svg {...icon}>
        <circle cx="12" cy="12" r="9" />
        <path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 .9-1 1.7M12 17h.01" />
      </svg>
    ),
  },
  {
    href: '/app/settings',
    label: 'Settings',
    icon: (
      <svg {...icon}>
        <path d="M4 7h10M18 7h2M4 17h2M10 17h10" />
        <circle cx="16" cy="7" r="2" />
        <circle cx="8" cy="17" r="2" />
      </svg>
    ),
  },
]

function Logo({ onClick }) {
  return (
    <Link href="/" className="story-logo" onClick={onClick} aria-label="Lecturesque home">
      <span aria-hidden="true" />
      Lecturesque
    </Link>
  )
}

// The app: a sidebar on a computer, a top bar with a drawer on a phone. No account, no login.
export default function AppShell({ children }) {
  const pathname = usePathname()
  const [open, setOpen] = useState(false)
  const menuButton = useRef(null)
  const drawer = useRef(null)

  // A job page belongs to the library. The page name is the one h1 of each page (for screen readers).
  const isJob = pathname.startsWith('/app/job')
  const active = isJob ? ITEMS[0] : ITEMS.find((item) => pathname.startsWith(item.href))
  const pageTitle = isJob ? 'Lecture notes' : active?.label || 'Lecturesque'

  function close() {
    setOpen(false)
    menuButton.current?.focus()
  }

  // Escape closes the drawer; Tab stays inside it while it is open (it covers the page on a phone).
  useEffect(() => {
    if (!open) return
    drawer.current?.querySelector('a')?.focus()
    function onKey(event) {
      if (event.key === 'Escape') {
        setOpen(false)
        menuButton.current?.focus()
      }
      if (event.key === 'Tab' && drawer.current) {
        const items = drawer.current.querySelectorAll('a, button')
        const first = items[0]
        const last = items[items.length - 1]
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault()
          last.focus()
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault()
          first.focus()
        }
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])

  return (
    <div className="story-site shell">
      <a href="#story-main" className="story-skip">
        Skip to content
      </a>
      <header className="shell-top">
        <div className="shell-top-left">
          <BackLink pathname={pathname} />
          <Logo />
        </div>
        <button
          ref={menuButton}
          type="button"
          className="theme-toggle"
          aria-label={open ? 'Close the menu' : 'Open the menu'}
          aria-expanded={open}
          aria-controls="shell-drawer"
          onClick={() => setOpen((value) => !value)}
        >
          <svg {...icon}>{open ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}</svg>
        </button>
      </header>
      {open && <div className="shell-scrim" onClick={close} aria-hidden="true" />}
      <aside id="shell-drawer" ref={drawer} className="shell-side" data-open={open}>
        <div className="shell-brand">
          <Logo onClick={() => setOpen(false)} />
        </div>
        <nav aria-label="App" className="shell-nav">
          {ITEMS.map((item) => (
            <Link key={item.href} href={item.href} aria-current={item === active ? 'page' : undefined} onClick={() => setOpen(false)}>
              {item.icon}
              {item.label}
            </Link>
          ))}
        </nav>
        <p className="shell-note">No account. Your list of lectures stays in this browser.</p>
      </aside>
      <main id="story-main" tabIndex={-1} className="shell-main">
        <div className="shell-content">
          <BackLink pathname={pathname} className="shell-back-desktop" />
          <h1 className="sr-only">{pageTitle}</h1>
          {children}
        </div>
      </main>
    </div>
  )
}
