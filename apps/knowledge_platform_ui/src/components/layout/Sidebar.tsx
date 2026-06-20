'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  LayoutDashboard,
  MessageSquare,
  FileText,
  Bot,
  Cpu,
} from 'lucide-react'

const NAV = [
  { href: '/dashboard', label: 'Dashboard',    icon: LayoutDashboard },
  { href: '/chat',      label: 'AI Chat',       icon: MessageSquare   },
  { href: '/reports',   label: 'Reports',       icon: FileText        },
  { href: '/agents',    label: 'Agents',        icon: Bot             },
  { href: '/skills',    label: 'Skills Hub',    icon: Cpu             },
]

export default function Sidebar() {
  const pathname = usePathname()

  return (
    <aside className="w-56 shrink-0 bg-slate-900 border-r border-slate-800 flex flex-col">
      {/* Logo */}
      <div className="px-4 py-5 border-b border-slate-800">
        <span className="text-xs font-semibold tracking-widest text-slate-500 uppercase">
          AI Knowledge Platform
        </span>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-4 space-y-0.5 px-2">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-colors ${
                active
                  ? 'bg-blue-600/20 text-blue-400 font-medium'
                  : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
              }`}
            >
              <Icon size={16} />
              {label}
            </Link>
          )
        })}
      </nav>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-slate-800">
        <p className="text-xs text-slate-600">Phase 6 — Local MVP</p>
      </div>
    </aside>
  )
}
