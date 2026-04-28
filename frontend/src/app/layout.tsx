import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Enterprise RAG Agent",
  description: "Advanced Agentic Coding Assistant",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`dark ${inter.variable}`} suppressHydrationWarning>
      <body className="h-screen overflow-hidden antialiased bg-zinc-950 text-zinc-50 font-sans" suppressHydrationWarning>
        {children}
      </body>
    </html>
  );
}
