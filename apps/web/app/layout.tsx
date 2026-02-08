import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "VideoSieve Web",
  description: "VideoSieve Control Plane",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased min-h-screen bg-background">
        {children}
      </body>
    </html>
  );
}
