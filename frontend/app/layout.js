import "./globals.css";

export const metadata = {
  title: "AI-voice2text",
  description: "Turn a lecture transcript into study notes, slides and a transcript, where every point has a source.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
