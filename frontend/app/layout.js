import './globals.css'
import './story.css'
import { bodyFont, headlineFont, labelFont, noteFont } from './fonts'

export const metadata = {
  title: 'Lecturesque: your lecture, turned into notes you can check',
  description: 'Turn a lecture transcript into study notes, slides and a timestamped transcript. Every note shows its source.',
}

// Runs before the first paint: use the saved theme, else the system setting (no flash of the wrong theme).
const THEME_SCRIPT = `try{var t=localStorage.getItem('theme');if(t==='dark'||(!t&&window.matchMedia('(prefers-color-scheme: dark)').matches))document.documentElement.classList.add('dark')}catch(e){}`

export default function RootLayout({ children }) {
  return (
    <html lang="en" suppressHydrationWarning className={`${headlineFont.variable} ${bodyFont.variable} ${noteFont.variable} ${labelFont.variable} antialiased`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>{children}</body>
    </html>
  )
}
