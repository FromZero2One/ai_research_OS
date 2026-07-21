"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { clsx } from "clsx";

const NAV_ITEMS = [
  {
    label: "工作台",
    href: "/",
    icon: "🏠",
  },
  {
    label: "快速研究",
    href: "/research/quick",
    icon: "⚡",
  },
  {
    label: "研究中心",
    href: "/research",
    icon: "🔬",
  },
  {
    label: "研究时间线",
    href: "/research/timeline",
    icon: "📋",
  },
  {
    label: "公司",
    href: "/companies",
    icon: "🏢",
  },
  {
    label: "文档",
    href: "/documents",
    icon: "📄",
  },
  {
    label: "知识库",
    href: "/knowledge",
    icon: "🧠",
  },
  {
    label: "行情",
    href: "/market",
    icon: "📊",
  },
  {
    label: "AI 中心",
    href: "/ai",
    icon: "⚡",
  },
  {
    label: "投资组合",
    href: "/portfolio",
    icon: "💼",
  },
  {
    label: "系统状态",
    href: "/system",
    icon: "📡",
  },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 h-screen bg-[#1a1d28] border-r border-[#2d3140] flex flex-col">
      <div className="p-5 border-b border-[#2d3140]">
        <Link href="/" className="flex items-center gap-2">
          <span className="text-xl">🧠</span>
          <span className="font-semibold text-[#e8eaed] text-lg">AI 投研系统</span>
        </Link>
      </div>

      <nav className="flex-1 p-3 space-y-1">
        {NAV_ITEMS.map((item) => {
          const active = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={clsx(
                "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors",
                active
                  ? "bg-[#4f8cff]/10 text-[#4f8cff]"
                  : "text-[#9aa0a6] hover:bg-[#232736] hover:text-[#e8eaed]"
              )}
            >
              <span className="text-base">{item.icon}</span>
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="p-4 border-t border-[#2d3140]">
        <div className="text-xs text-[#9aa0a6]">v0.1.0 · 研究优先</div>
      </div>
    </aside>
  );
}
