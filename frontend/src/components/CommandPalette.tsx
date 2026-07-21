"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

interface Command {
  id: string;
  label: string;
  description: string;
  icon: string;
  action: () => void;
  keywords: string[];
}

export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  // Toggle on Cmd+K / Ctrl+K
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  // Focus input when opened
  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 50);
      setQuery("");
      setSelectedIndex(0);
    }
  }, [open]);

  const commands: Command[] = [
    {
      id: "quick-research",
      label: "快速研究",
      description: "一键发起 AI 研究",
      icon: "⚡",
      action: () => router.push("/research/quick"),
      keywords: ["研究", "分析", "快速", "research", "quick"],
    },
    {
      id: "research",
      label: "研究中心",
      description: "查看所有研究会话",
      icon: "🔬",
      action: () => router.push("/research"),
      keywords: ["研究", "会话", "research", "session"],
    },
    {
      id: "timeline",
      label: "研究时间线",
      description: "按公司查看研究历史",
      icon: "📋",
      action: () => router.push("/research/timeline"),
      keywords: ["时间线", "历史", "timeline", "history"],
    },
    {
      id: "dashboard",
      label: "工作台",
      description: "每日投资工作台",
      icon: "🏠",
      action: () => router.push("/"),
      keywords: ["首页", "工作台", "home", "dashboard"],
    },
    {
      id: "companies",
      label: "公司",
      description: "浏览所有公司",
      icon: "🏢",
      action: () => router.push("/companies"),
      keywords: ["公司", "企业", "company", "ticker"],
    },
    {
      id: "documents",
      label: "上传文档",
      description: "上传 PDF、报告或会议纪要",
      icon: "📄",
      action: () => router.push("/documents"),
      keywords: ["文档", "上传", "pdf", "document", "upload"],
    },
    {
      id: "knowledge",
      label: "知识库搜索",
      description: "混合 RAG 搜索全部文档",
      icon: "🧠",
      action: () => router.push("/knowledge"),
      keywords: ["知识库", "搜索", "rag", "knowledge", "search"],
    },
    {
      id: "market",
      label: "行情",
      description: "市场行情与 K 线",
      icon: "📊",
      action: () => router.push("/market"),
      keywords: ["行情", "市场", "k线", "market", "stock"],
    },
    {
      id: "ai",
      label: "AI 中心",
      description: "Prompt 模板与 AI 工具",
      icon: "⚡",
      action: () => router.push("/ai"),
      keywords: ["ai", "prompt", "模板", "生成"],
    },
    {
      id: "portfolio",
      label: "投资组合",
      description: "自选列表、持仓与研究日志",
      icon: "💼",
      action: () => router.push("/portfolio"),
      keywords: ["组合", "持仓", "自选", "portfolio", "holding"],
    },
    {
      id: "scheduler",
      label: "系统状态",
      description: "调度器状态与执行记录",
      icon: "📡",
      action: () => router.push("/system"),
      keywords: ["系统", "状态", "调度", "scheduler", "status"],
    },
  ];

  const filtered = query.trim()
    ? commands.filter((cmd) => {
        const q = query.toLowerCase();
        return (
          cmd.label.toLowerCase().includes(q) ||
          cmd.description.toLowerCase().includes(q) ||
          cmd.keywords.some((k) => k.toLowerCase().includes(q))
        );
      })
    : commands;

  // Clamp selection
  useEffect(() => {
    if (selectedIndex >= filtered.length) {
      setSelectedIndex(Math.max(0, filtered.length - 1));
    }
  }, [filtered.length, selectedIndex]);

  const execute = useCallback(
    (cmd: Command) => {
      setOpen(false);
      cmd.action();
    },
    [],
  );

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && filtered[selectedIndex]) {
      e.preventDefault();
      execute(filtered[selectedIndex]);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60" onClick={() => setOpen(false)} />

      {/* Modal */}
      <div className="relative w-full max-w-lg bg-[#1a1d28] border border-[#2d3140] rounded-xl shadow-2xl overflow-hidden">
        {/* Search input */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-[#2d3140]">
          <span className="text-[#9aa0a6] text-lg">🔍</span>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setSelectedIndex(0)}
            onKeyDown={handleKeyDown}
            placeholder="搜索命令..."
            className="flex-1 bg-transparent text-[#e8eaed] placeholder-[#6b7280] focus:outline-none text-sm"
          />
          <kbd className="px-1.5 py-0.5 rounded text-xs bg-[#232736] text-[#9aa0a6] border border-[#2d3140]">
            ESC
          </kbd>
        </div>

        {/* Results */}
        <div className="max-h-80 overflow-y-auto p-2">
          {filtered.length === 0 ? (
            <div className="p-4 text-center text-sm text-[#9aa0a6]">
              没有匹配的命令
            </div>
          ) : (
            <div className="space-y-0.5">
              {filtered.map((cmd, i) => (
                <button
                  key={cmd.id}
                  onClick={() => execute(cmd)}
                  onMouseEnter={() => setSelectedIndex(i)}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-colors ${
                    i === selectedIndex
                      ? "bg-[#4f8cff]/10 text-[#e8eaed]"
                      : "text-[#9aa0a6] hover:bg-[#232736]"
                  }`}
                >
                  <span className="text-lg">{cmd.icon}</span>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium">{cmd.label}</div>
                    <div className="text-xs opacity-70 truncate">{cmd.description}</div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Footer hint */}
        <div className="px-4 py-2 border-t border-[#2d3140] flex items-center gap-3 text-xs text-[#6b7280]">
          <span>↑↓ 导航</span>
          <span>↵ 确认</span>
          <span className="ml-auto">⌘K 切换</span>
        </div>
      </div>
    </div>
  );
}
