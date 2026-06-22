'use client'

import { useEffect, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { Loader2 } from 'lucide-react'
import Sidebar from './Sidebar'
import { getPlatformAuth, platformLogout, type PlatformAuth } from '@/lib/platform-auth'

const PUBLIC_PATHS = ['/login']

// trailingSlash: true makes /login -> /login/ — normalize before comparing
function isPublicPath(path: string): boolean {
  const normalized = path.endsWith('/') && path !== '/' ? path.slice(0, -1) : path
  return PUBLIC_PATHS.includes(normalized)
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const [auth, setAuth] = useState<PlatformAuth | null | undefined>(undefined)

  useEffect(() => {
    const stored = getPlatformAuth()
    setAuth(stored)
    if (!stored && !isPublicPath(pathname)) {
      router.replace('/login')
    }
  }, [pathname, router])

  // Login page: full-screen, no sidebar
  if (isPublicPath(pathname)) {
    return <div className="w-full">{children}</div>
  }

  // Auth not checked yet — show spinner
  if (auth === undefined) {
    return (
      <div className="flex items-center justify-center w-full h-full">
        <Loader2 size={20} className="animate-spin text-slate-500" />
      </div>
    )
  }

  // Not authenticated — redirect in progress
  if (!auth) {
    return (
      <div className="flex items-center justify-center w-full h-full">
        <Loader2 size={20} className="animate-spin text-slate-500" />
      </div>
    )
  }

  function handleLogout() {
    platformLogout()
    setAuth(null)
    router.replace('/login')
  }

  return (
    <>
      <Sidebar email={auth.email} onLogout={handleLogout} />
      <main className="flex-1 overflow-y-auto bg-slate-950">
        {children}
      </main>
    </>
  )
}
