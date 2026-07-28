import type { Metadata } from "next";
import "./globals.css";
import { Nav } from "@/components/ui";

export const metadata: Metadata = {
  title: "设计灵感资产库",
  description: "素材进入、AI拆解、多模态检索与案例选择",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>
        <Nav />
        <main className="mx-auto max-w-[1440px] px-6 py-8 lg:px-10">{children}</main>
        <footer className="border-t border-line bg-white py-8 text-center text-xs text-gray-400">
          设计灵感资产库 · 第一阶段
        </footer>
      </body>
    </html>
  );
}
