import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import Sidebar from '@/components/layout/Sidebar'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'AI Knowledge Platform',
  description: 'Corporate AI Knowledge Platform — Phase 6',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} bg-slate-950 text-slate-100 h-screen flex`}>
        <Sidebar />
        <main className="flex-1 overflow-y-auto bg-slate-950">
          {children}
        </main>
      </body>
    </html>
  )
}
