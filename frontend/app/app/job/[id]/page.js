import { Suspense } from 'react'
import JobView from '../../../components/JobView'

// The id is read in the client component (useParams): the job is asked from the browser, so nothing here is cached.
export default function JobPage() {
  return (
    <Suspense fallback={null}>
      <JobView />
    </Suspense>
  )
}
