import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Steel-Compass V2",
  description: "景观结构方案快算与专业计算 Beta",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
