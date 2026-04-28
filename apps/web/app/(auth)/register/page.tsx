"use client";

import { Suspense, useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiRegister, AuthError } from "@/lib/auth/auth-client";
import { setInMemoryToken, setStoredAppMode } from "@/lib/auth/session";

type JobOption = { id: number; code: string; label_zh: string; label_en: string };

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

function RegisterForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = searchParams.get("next") ?? "/";
  const invite = searchParams.get("invite");

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [jobId, setJobId] = useState<number | "">("");
  const [jobs, setJobs] = useState<JobOption[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE_URL}/jobs`)
      .then((r) => r.json())
      .then((data) => setJobs(data.jobs ?? []))
      .catch(() => {});
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!jobId) { setError("请选择您的岗位"); return; }
    if (password.length < 8) { setError("密码至少 8 位"); return; }
    setLoading(true);
    try {
      const result = await apiRegister({
        email,
        password,
        display_name: displayName,
        job_id: Number(jobId),
      });
      setInMemoryToken(result.access_token, result.expires_at);
      setStoredAppMode("designer");
      router.push(invite ? `/invites/${invite}` : next);
    } catch (err) {
      if (err instanceof AuthError) {
        if (err.code === "email_taken") setError("该邮箱已被注册");
        else if (err.code === "password_too_short") setError("密码长度不足");
        else setError(err.message || "注册失败，请重试");
      } else {
        setError("注册失败，请稍后重试");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div className="space-y-1.5">
        <label htmlFor="displayName" className="block text-label font-medium text-charcoal-warm tracking-wide uppercase">
          姓名
        </label>
        <Input
          id="displayName"
          type="text"
          autoComplete="name"
          placeholder="您的姓名"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          required
        />
      </div>

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
        <label htmlFor="password" className="block text-label font-medium text-charcoal-warm tracking-wide uppercase">
          密码
        </label>
        <Input
          id="password"
          type="password"
          autoComplete="new-password"
          placeholder="至少 8 位"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          minLength={8}
        />
      </div>

      <div className="space-y-1.5">
        <label htmlFor="job" className="block text-label font-medium text-charcoal-warm tracking-wide uppercase">
          岗位
        </label>
        <select
          id="job"
          className="flex h-9 w-full rounded-generous border border-border-cream bg-ivory px-3 py-1 text-body-sm text-near-black shadow-ring-border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-blue focus-visible:border-focus-blue placeholder:text-stone-gray"
          value={jobId}
          onChange={(e) => setJobId(e.target.value ? Number(e.target.value) : "")}
          required
        >
          <option value="" className="text-stone-gray">请选择您的岗位</option>
          {jobs.map((j) => (
            <option key={j.id} value={j.id}>
              {j.label_zh}
            </option>
          ))}
        </select>
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
            注册中…
          </span>
        ) : (
          "创建账号"
        )}
      </Button>
    </form>
  );
}

export default function RegisterPage() {
  return (
    <div className="min-h-screen bg-parchment flex flex-col items-center justify-center p-6">

      {/* Brand */}
      <div className="mb-10 text-center">
        <div className="inline-flex items-baseline gap-2 mb-3">
          <span className="font-serif text-[1.6rem] font-[500] leading-none text-near-black">Cognitrix</span>
          <span className="text-stone-gray text-body-sm">识枢</span>
        </div>
        <h1 className="font-serif text-heading text-near-black">创建账号</h1>
        <p className="mt-2 text-olive-gray text-body">开始使用 AI 驱动的数据分析</p>
      </div>

      {/* Card */}
      <div className="w-full max-w-sm bg-ivory rounded-very border border-border-cream shadow-whisper px-8 py-9">
        <Suspense fallback={
          <div className="space-y-5 animate-pulse">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-9 bg-warm-sand rounded-generous" />
            ))}
            <div className="h-10 bg-warm-sand rounded-comfortable" />
          </div>
        }>
          <RegisterForm />
        </Suspense>
      </div>

      {/* Footer */}
      <p className="mt-6 text-stone-gray text-body-sm text-center">
        已有账号？{" "}
        <a
          href="/login"
          className="text-terracotta hover:text-terracotta-light underline underline-offset-2 transition-colors"
        >
          立即登录
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
