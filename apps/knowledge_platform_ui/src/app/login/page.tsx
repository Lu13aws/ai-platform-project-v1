'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Loader2, Eye, EyeOff } from 'lucide-react'
import { platformLogin, platformSignUp, platformConfirmSignUp } from '@/lib/platform-auth'

type Step = 'login' | 'register' | 'verify'

export default function LoginPage() {
  const router = useRouter()
  const [step, setStep] = useState<Step>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function clearError() { setError(null) }

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true); clearError()
    try {
      await platformLogin(email, password)
      router.replace('/dashboard')
    } catch (err) {
      setError(String(err).replace('Error: ', ''))
    } finally {
      setLoading(false)
    }
  }

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true); clearError()
    try {
      await platformSignUp(email, password)
      setStep('verify')
    } catch (err) {
      setError(String(err).replace('Error: ', ''))
    } finally {
      setLoading(false)
    }
  }

  async function handleVerify(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true); clearError()
    try {
      await platformConfirmSignUp(email, code)
      // Auto-login after verification
      await platformLogin(email, password)
      router.replace('/dashboard')
    } catch (err) {
      setError(String(err).replace('Error: ', ''))
    } finally {
      setLoading(false)
    }
  }

  const emailPwFields = (
    <>
      <div>
        <label className="block text-xs text-slate-500 mb-1.5">Email</label>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@company.com"
          required
          disabled={loading}
          className="w-full px-3 py-2.5 bg-slate-900 border border-slate-700 rounded-lg text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-600 transition-colors"
        />
      </div>
      <div>
        <label className="block text-xs text-slate-500 mb-1.5">Password</label>
        <div className="relative">
          <input
            type={showPw ? 'text' : 'password'}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            required
            disabled={loading}
            className="w-full px-3 py-2.5 pr-10 bg-slate-900 border border-slate-700 rounded-lg text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-600 transition-colors"
          />
          <button type="button" onClick={() => setShowPw(!showPw)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300">
            {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        </div>
      </div>
    </>
  )

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center px-4">
      <div className="w-full max-w-sm">

        {/* Branding */}
        <div className="mb-8 text-center">
          <p className="text-xs font-semibold tracking-widest text-slate-500 uppercase mb-1">
            AI Knowledge Platform
          </p>
          <h1 className="text-2xl font-semibold text-slate-100">
            {step === 'login' && 'Sign in'}
            {step === 'register' && 'Create account'}
            {step === 'verify' && 'Verify your email'}
          </h1>
          {step === 'login' && (
            <p className="text-sm text-slate-500 mt-2">
              Access technology radar, competitor intelligence, and AI chat.
            </p>
          )}
          {step === 'register' && (
            <p className="text-sm text-slate-500 mt-2">
              Free access. A verification code will be sent to your email.
            </p>
          )}
          {step === 'verify' && (
            <p className="text-sm text-slate-500 mt-2">
              Enter the code sent to <span className="text-slate-300">{email}</span>
            </p>
          )}
        </div>

        {/* Login form */}
        {step === 'login' && (
          <form onSubmit={handleLogin} className="space-y-4">
            {emailPwFields}
            {error && <ErrorBox msg={error} />}
            <button type="submit" disabled={loading || !email || !password}
              className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 disabled:text-slate-600 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2">
              {loading && <Loader2 size={14} className="animate-spin" />}
              {loading ? 'Signing in…' : 'Sign in'}
            </button>
            <p className="text-xs text-center text-slate-500 pt-1">
              No account?{' '}
              <button type="button" onClick={() => { setStep('register'); clearError() }}
                className="text-blue-400 hover:text-blue-300 underline">
                Create one
              </button>
            </p>
          </form>
        )}

        {/* Register form */}
        {step === 'register' && (
          <form onSubmit={handleRegister} className="space-y-4">
            {emailPwFields}
            <p className="text-xs text-slate-600">
              Min. 8 characters, must include uppercase, lowercase, and a number.
            </p>
            {error && <ErrorBox msg={error} />}
            <button type="submit" disabled={loading || !email || !password}
              className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 disabled:text-slate-600 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2">
              {loading && <Loader2 size={14} className="animate-spin" />}
              {loading ? 'Creating account…' : 'Create account'}
            </button>
            <p className="text-xs text-center text-slate-500 pt-1">
              Already have an account?{' '}
              <button type="button" onClick={() => { setStep('login'); clearError() }}
                className="text-blue-400 hover:text-blue-300 underline">
                Sign in
              </button>
            </p>
          </form>
        )}

        {/* Verify form */}
        {step === 'verify' && (
          <form onSubmit={handleVerify} className="space-y-4">
            <div>
              <label className="block text-xs text-slate-500 mb-1.5">Verification code</label>
              <input
                type="text"
                value={code}
                onChange={(e) => setCode(e.target.value.trim())}
                placeholder="123456"
                maxLength={6}
                required
                disabled={loading}
                className="w-full px-3 py-2.5 bg-slate-900 border border-slate-700 rounded-lg text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-600 transition-colors tracking-widest text-center"
              />
            </div>
            {error && <ErrorBox msg={error} />}
            <button type="submit" disabled={loading || code.length < 6}
              className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 disabled:text-slate-600 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2">
              {loading && <Loader2 size={14} className="animate-spin" />}
              {loading ? 'Verifying…' : 'Verify and sign in'}
            </button>
          </form>
        )}
      </div>
    </div>
  )
}

function ErrorBox({ msg }: { msg: string }) {
  return (
    <p className="text-xs text-red-400 bg-red-950/30 border border-red-900/50 rounded px-3 py-2">
      {msg}
    </p>
  )
}
