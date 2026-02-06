import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'FlexFlow - AI Physical Therapist',
  description: 'Real-time AI Physical Therapist powered by Gemini and LiveKit',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body suppressHydrationWarning>{children}</body>
    </html>
  )
}
