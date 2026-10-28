import { Footer, Nav } from './components/Landing'
import LectureApp from './components/LectureApp'

export default function Home() {
  return (
    <div className="story-site">
      <a href="#story-main" className="story-skip">
        Skip to content
      </a>
      <Nav />
      <LectureApp />
      <Footer />
    </div>
  )
}
