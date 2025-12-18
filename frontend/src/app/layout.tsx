import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "VideoSieve - AI 视频转录工具",
  description: "基于 AI 的视频转录、优化、翻译与摘要生成工具",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body className={inter.className}>
        <div className="min-h-screen bg-background">
          <header className="border-b">
            <div className="container mx-auto px-4 py-4">
              <h1 className="text-2xl font-bold">VideoSieve</h1>
              <p className="text-sm text-muted-foreground">
                AI 视频转录、优化与摘要生成
              </p>
            </div>
          </header>
          <main className="container mx-auto px-4 py-8">
            {children}
          </main>
          <footer className="border-t mt-auto">
            <div className="container mx-auto px-4 py-4 text-center text-sm text-muted-foreground">
              Made with ❤️ by VideoSieve Team
            </div>
          </footer>
        </div>
      </body>
    </html>
  );
}
