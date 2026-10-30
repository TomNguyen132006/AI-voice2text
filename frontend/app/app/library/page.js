import { existsSync } from 'node:fs'
import { join } from 'node:path'
import LibraryView from '../../components/LibraryView'

// An optional photo for the hero: drop frontend/public/hero-library.jpg in place and it is used (checked when the page is built).
// Without the file the hero is made of CSS only.
export default function LibraryPage() {
  const photo = existsSync(join(process.cwd(), 'public', 'hero-library.jpg'))
  return <LibraryView photo={photo} />
}
