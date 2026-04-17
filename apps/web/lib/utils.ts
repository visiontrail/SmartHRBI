import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import { DEFAULT_LOCALE, type Locale } from "@/lib/i18n/dictionary";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function generateId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `id-${Math.random().toString(36).slice(2)}-${Date.now()}`;
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function formatRelativeTime(date: Date, locale: Locale = DEFAULT_LOCALE): string {
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);
  const formatter = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });

  if (minutes < 1) return locale === "zh-CN" ? "刚刚" : "just now";
  if (minutes < 60) return formatter.format(-minutes, "minute");
  if (hours < 24) return formatter.format(-hours, "hour");
  if (days < 7) return formatter.format(-days, "day");
  return date.toLocaleDateString(locale);
}

export function truncate(str: string, length: number): string {
  if (str.length <= length) return str;
  return str.slice(0, length) + "…";
}
