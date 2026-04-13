import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Providers } from "@/components/shared/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "SmartHRBI — AI Native HR & Project BI",
  description: "Conversational AI analytics for HR and project management. Ask questions, generate charts, compose reports.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en" className="antialiased">
      <body className="min-h-screen bg-parchment text-near-black font-sans">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
