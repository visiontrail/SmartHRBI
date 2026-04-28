"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { getInMemoryToken } from "@/lib/auth/session";
import { acceptInvite } from "@/lib/workspace/collaboration";

export default function InviteAcceptPage() {
  const params = useParams();
  const router = useRouter();
  const token = typeof params.token === "string" ? params.token : Array.isArray(params.token) ? params.token[0] : "";
  const [status, setStatus] = useState<"loading" | "error" | "success">("loading");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!token) return;

    const sessionToken = getInMemoryToken();
    if (!sessionToken) {
      // Not logged in — redirect to register with invite
      router.replace(`/register?invite=${encodeURIComponent(token)}`);
      return;
    }

    acceptInvite(token)
      .then((result) => {
        setStatus("success");
        setTimeout(() => {
          router.push("/");
        }, 1500);
      })
      .catch((err: any) => {
        const code = err.code ?? "invite_failed";
        if (code === "invite_expired") {
          setMessage("邀请链接已过期，请联系工作空间所有者");
        } else if (code === "invite_revoked") {
          setMessage("邀请链接已被撤销");
        } else if (code === "invite_exhausted") {
          setMessage("邀请链接已超过使用次数");
        } else {
          setMessage("邀请链接无效");
        }
        setStatus("error");
      });
  }, [token, router]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="text-center space-y-4">
        {status === "loading" && <p className="text-muted-foreground">正在处理邀请...</p>}
        {status === "success" && <p className="text-green-600">已成功加入工作空间，正在跳转...</p>}
        {status === "error" && (
          <div className="space-y-2">
            <p className="text-destructive">{message}</p>
            <Link href="/" className="text-sm text-primary underline">返回首页</Link>
          </div>
        )}
      </div>
    </div>
  );
}
