import ThemeToggle from '../../components/ThemeToggle'

export default function SettingsPage() {
  return (
    <section aria-labelledby="settings-heading" className="flex flex-col gap-6">
      <div>
        <p className="handwritten">your corner</p>
        <h2 id="settings-heading" className="text-4xl leading-tight">
          Settings
        </h2>
      </div>
      <div className="story-panel flex items-center justify-between gap-4 !p-5">
        <div>
          <p className="font-semibold">Light or dark</p>
          <p className="text-muted-foreground">The choice is saved in this browser.</p>
        </div>
        <ThemeToggle />
      </div>
    </section>
  )
}
