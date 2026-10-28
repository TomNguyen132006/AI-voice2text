import localFont from 'next/font/local'

// The same four families as the Narrator project, all licensed under the SIL Open Font License (the OFL texts are in public/fonts).
export const headlineFont = localFont({
  src: '../public/fonts/gloock-400.woff2',
  variable: '--font-story-heading',
  weight: '400',
  display: 'swap',
})
export const bodyFont = localFont({
  src: [
    { path: '../public/fonts/instrument-sans-400.woff2', weight: '400' },
    { path: '../public/fonts/instrument-sans-500.woff2', weight: '500' },
    { path: '../public/fonts/instrument-sans-600.woff2', weight: '600' },
    { path: '../public/fonts/instrument-sans-700.woff2', weight: '700' },
  ],
  variable: '--font-story-body',
  display: 'swap',
})
// Tiny handwritten labels only.
export const noteFont = localFont({
  src: '../public/fonts/caveat-600.woff2',
  variable: '--font-story-note',
  weight: '600',
  display: 'swap',
  preload: false,
})
// Uppercase labels.
export const labelFont = localFont({
  src: '../public/fonts/dm-mono-500.woff2',
  variable: '--font-story-label',
  weight: '500',
  display: 'swap',
  preload: false,
})
