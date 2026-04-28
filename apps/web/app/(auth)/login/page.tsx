"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiEmailLogin, AuthError } from "@/lib/auth/auth-client";
import { setInMemoryToken, setStoredAppMode } from "@/lib/auth/session";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = searchParams.get("next") ?? "/";
  const invite = searchParams.get("invite");

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const result = await apiEmailLogin({ email, password });
      setInMemoryToken(result.access_token, result.expires_at);
      setStoredAppMode("designer");
      router.push(invite ? `/invites/${invite}` : next);
    } catch (err) {
      setError(err instanceof AuthError ? "邮箱或密码错误，请重试" : "登录失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div className="space-y-1.5">
        <label htmlFor="email" className="block text-label font-medium text-charcoal-warm tracking-wide uppercase">
          邮箱地址
        </label>
        <Input
          id="email"
          type="email"
          autoComplete="email"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
      </div>

      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <label htmlFor="password" className="block text-label font-medium text-charcoal-warm tracking-wide uppercase">
            密码
          </label>
        </div>
        <Input
          id="password"
          type="password"
          autoComplete="current-password"
          placeholder="••••••••"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </div>

      {error && (
        <div className="rounded-comfortable border border-error-crimson/20 bg-error-crimson/5 px-4 py-3">
          <p className="text-body-sm text-error-crimson">{error}</p>
        </div>
      )}

      <Button
        type="submit"
        className="w-full h-10 text-body font-medium"
        disabled={loading}
      >
        {loading ? (
          <span className="flex items-center gap-2">
            <span className="h-4 w-4 rounded-full border-2 border-ivory/30 border-t-ivory animate-spin" />
            登录中…
          </span>
        ) : (
          "登录"
        )}
      </Button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <div className="min-h-screen bg-parchment flex flex-col items-center justify-center p-6">

      {/* Brand */}
      <div className="mb-10 text-center">
        <div className="inline-flex items-baseline gap-2 mb-3">
          <span className="font-serif text-[1.6rem] font-[500] leading-none text-near-black">Cognitrix</span>
          <span className="text-stone-gray text-body-sm">识枢</span>
        </div>
        <h1 className="font-serif text-heading text-near-black">欢迎回来</h1>
        <p className="mt-2 text-olive-gray text-body">登录以继续使用 AI 数据分析</p>
      </div>

      {/* Card */}
      <div className="w-full max-w-sm bg-ivory rounded-very border border-border-cream shadow-whisper px-8 py-9">
        <Suspense fallback={
          <div className="space-y-5 animate-pulse">
            <div className="h-9 bg-warm-sand rounded-generous" />
            <div className="h-9 bg-warm-sand rounded-generous" />
            <div className="h-10 bg-warm-sand rounded-comfortable" />
          </div>
        }>
          <LoginForm />
        </Suspense>
      </div>

      {/* Footer */}
      <p className="mt-6 text-stone-gray text-body-sm text-center">
        还没有账号？{" "}
        <a
          href="/register"
          className="text-terracotta hover:text-terracotta-light underline underline-offset-2 transition-colors"
        >
          立即注册
        </a>
      </p>

      {/* Divider decoration */}
      <div className="mt-16 flex items-center gap-3 text-stone-gray">
        <div className="h-px w-12 bg-border-warm" />
        <span className="text-label tracking-widest uppercase">Cognitrix · 识枢</span>
        <div className="h-px w-12 bg-border-warm" />
      </div>
    </div>
  );
}
