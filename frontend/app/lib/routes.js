// Where the Back button of each page goes. A FIXED parent, never history.back(): the button can not loop through the history.
// Returns { href, label } or null (no Back button, e.g. on the home page).
//   /app/job/[id] (also example-strang), /app/new, /app/how, /app/settings  ->  /app/library
//   /app/library                                                            ->  /
export function parentRoute(pathname) {
  if (pathname === '/app/library') return { href: '/', label: 'Home' }
  if (pathname === '/app/new' || pathname === '/app/how' || pathname === '/app/settings' || pathname.startsWith('/app/job/')) {
    return { href: '/app/library', label: 'Library' }
  }
  return null
}
