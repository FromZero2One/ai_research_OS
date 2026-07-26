"use client";

import { useState } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { useDashboard } from "@/lib/api";

const QUICK_ACTIONS = [
  { label: "快速研究", href: "/research/quick", icon: "⚡", desc: "一键 AI 研究" },
  { label: "研究中心", href: "/research", icon: "🔬", desc: "查看研究会话" },
  { label: "公司", href: "/companies", icon: "🏢", desc: "管理关注公司" },
  { label: "行情", href: "/market", icon: "📊", desc: "市场行情与 K 线" },
  { label: "上传文档", href: "/documents", icon: "📄", desc: "添加报告或纪要" },
];

const STATUS_LABEL: Record<string, { label: string; color: string }> = {
  normal: { label: "正常", color: "bg-[#34d399]/10 text-[#34d399]" },
  attention: { label: "关注", color: "bg-[#fbbf24]/10 text-[#fbbf24]" },
  need_research: { label: "需研究", color: "bg-[#f87171]/10 text-[#f87171]" },
};

export default function DashboardPage() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useDashboard();
  const [generating, setGenerating] = useState(false);

  const handleGenerateBrief = async () => {
    setGenerating(true);
    try {
      await fetch("/api/dashboard/generate-brief", { method: "POST" });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    } catch {
      // ignore
    }
    setGenerating(false);
  };

  const brief = data?.morning_brief;
  const watchlist = data?.watchlist || [];
  const reminders = data?.research_reminders || [];
  const recentResearch = data?.recent_research || [];
  const marketOverview = data?.market_overview || [];
  const hasBrief = brief?.content;
  const today = new Date().toLocaleDateString("zh-CN", {
    weekday: "long", year: "numeric", month: "long", day: "numeric",
  });

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#e8eaed]">☀️ Daily Workspace</h1>
          <p className="text-sm text-[#9aa0a6] mt-1">{today}</p>
        </div>
        <div className="flex items-center gap-2 text-sm text-[#9aa0a6]">
          <span className="w-2 h-2 rounded-full bg-[#34d399]"></span>
          系统运行中
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20 text-[#9aa0a6]">加载中...</div>
      ) : (
        <>
          {/* Quick Actions */}
          <div className="grid grid-cols-5 gap-3">
            {QUICK_ACTIONS.map((action) => (
              <Link key={action.label} href={action.href}
                className="p-4 rounded-xl bg-[#1a1d28] border border-[#2d3140] hover:border-[#4f8cff]/40 transition-all group text-center">
                <div className="text-2xl mb-1">{action.icon}</div>
                <div className="font-medium text-sm text-[#e8eaed] group-hover:text-[#4f8cff] transition-colors">{action.label}</div>
                <div className="text-xs text-[#9aa0a6] mt-0.5">{action.desc}</div>
              </Link>
            ))}
          </div>

          {/* Top Row: Morning Brief + Market Overview */}
          <div className="grid grid-cols-3 gap-6">
            {/* Morning Brief */}
            <div className="col-span-2 p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-lg font-semibold text-[#e8eaed]">📋 晨间简报</h2>
                <div className="flex items-center gap-2">
                  {brief?.generated_at && (
                    <span className="text-xs text-[#9aa0a6]">
                      {new Date(brief.generated_at).toLocaleString("zh-CN")}
                    </span>
                  )}
                  <button onClick={handleGenerateBrief} disabled={generating}
                    className="px-2 py-1 rounded text-xs bg-[#2d3140] text-[#9aa0a6] hover:text-[#e8eaed] disabled:opacity-50 transition-colors">
                    {generating ? "生成中..." : "🔄 生成"}
                  </button>
                </div>
              </div>
              {hasBrief ? (
                <div className="text-sm text-[#e8eaed] whitespace-pre-wrap leading-relaxed max-h-96 overflow-y-auto">
                  {brief.content}
                </div>
              ) : (
                <div className="text-sm text-[#9aa0a6] py-4 text-center">
                  暂无简报。点击「生成」或系统将在工作日 6am 自动生成。
                </div>
              )}
            </div>

            {/* Research Reminders */}
            <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
              <h2 className="text-lg font-semibold text-[#e8eaed] mb-3">⏰ 研究提醒</h2>
              {reminders.length > 0 ? (
                <div className="space-y-3">
                  {reminders.slice(0, 5).map((r) => (
                    <div key={r.ticker} className="p-3 rounded-lg bg-[#232736]">
                      <div className="flex items-center justify-between">
                        <span className="font-medium text-sm text-[#e8eaed]">{r.company_name}</span>
                        <span className="text-xs text-[#f87171]">{r.days_since_research} 天</span>
                      </div>
                      <Link href={`/research/quick?ticker=${r.ticker}`}
                        className="text-xs text-[#4f8cff] hover:underline mt-1 inline-block">
                        开始研究 →
                      </Link>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-sm text-[#9aa0a6] py-4 text-center">
                  没有待处理的研究提醒。
                </div>
              )}
            </div>
          </div>

          {/* Market Overview */}
          {marketOverview.length > 0 && (
            <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-lg font-semibold text-[#e8eaed]">📈 行情概览</h2>
                <Link href="/market" className="text-sm text-[#4f8cff] hover:underline">
                  详细 →
                </Link>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-[#9aa0a6] border-b border-[#2d3140]">
                      <th className="text-left py-2 pr-4 font-medium">公司</th>
                      <th className="text-right py-2 pr-4 font-medium">最新价</th>
                      <th className="text-right py-2 pr-4 font-medium">涨跌幅</th>
                      <th className="text-left py-2 font-medium">行业</th>
                    </tr>
                  </thead>
                  <tbody>
                    {marketOverview.map((item) => (
                      <tr key={item.ticker} className="border-b border-[#2d3140]/50 hover:bg-[#232736] transition-colors">
                        <td className="py-3 pr-4">
                          <Link href={`/companies/${item.ticker}`}
                            className="font-medium text-[#e8eaed] hover:text-[#4f8cff]">
                            {item.company_name}
                          </Link>
                          <div className="text-xs text-[#9aa0a6]">{item.ticker}</div>
                        </td>
                        <td className="py-3 pr-4 text-right text-[#e8eaed]">
                          {item.latest_price?.toFixed(2) ?? "-"}
                        </td>
                        <td className="py-3 pr-4 text-right">
                          {item.change_pct !== null ? (
                            <span className={item.change_pct >= 0 ? "text-[#34d399]" : "text-[#f87171]"}>
                              {item.change_pct >= 0 ? "+" : ""}{item.change_pct}%
                            </span>
                          ) : (
                            <span className="text-[#9aa0a6]">-</span>
                          )}
                        </td>
                        <td className="py-3 text-[#9aa0a6]">{item.sector || "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Watchlist */}
          {watchlist.length > 0 && (
            <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-lg font-semibold text-[#e8eaed]">👁️ 关注列表</h2>
                <Link href="/portfolio" className="text-sm text-[#4f8cff] hover:underline">
                  管理 →
                </Link>
              </div>
              {watchlist.map((wl) => (
                <div key={wl.watchlist_id}>
                  {wl.items.length === 0 ? (
                    <div className="text-sm text-[#9aa0a6] py-2">关注列表为空</div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-[#9aa0a6] border-b border-[#2d3140]">
                            <th className="text-left py-2 pr-4 font-medium">公司</th>
                            <th className="text-right py-2 pr-4 font-medium">价格</th>
                            <th className="text-right py-2 pr-4 font-medium">涨跌</th>
                            <th className="text-center py-2 pr-4 font-medium">状态</th>
                            <th className="text-left py-2 font-medium">观点</th>
                          </tr>
                        </thead>
                        <tbody>
                          {wl.items.map((item) => (
                            <tr key={item.id} className="border-b border-[#2d3140]/50 hover:bg-[#232736] transition-colors">
                              <td className="py-3 pr-4">
                                <Link href={`/companies/${item.ticker}`}
                                  className="font-medium text-[#e8eaed] hover:text-[#4f8cff]">{item.company_name}
                                </Link>
                                <div className="text-xs text-[#9aa0a6]">{item.ticker}</div>
                              </td>
                              <td className="py-3 pr-4 text-right text-[#e8eaed]">
                                {item.latest_price?.toFixed(2) ?? "-"}
                              </td>
                              <td className="py-3 pr-4 text-right">
                                {item.price_change !== null ? (
                                  <span className={item.price_change >= 0 ? "text-[#34d399]" : "text-[#f87171]"}>
                                    {item.price_change >= 0 ? "+" : ""}{item.price_change}%
                                  </span>
                                ) : (
                                  <span className="text-[#9aa0a6]">-</span>
                                )}
                              </td>
                              <td className="py-3 pr-4 text-center">
                                <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${STATUS_LABEL[item.status]?.color || ""}`}>
                                  {STATUS_LABEL[item.status]?.label || item.status}
                                </span>
                              </td>
                              <td className="py-3 text-[#9aa0a6] max-w-[200px] truncate">
                                {item.thesis ?? "-"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Recent Research */}
          {recentResearch.length > 0 && (
            <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-lg font-semibold text-[#e8eaed]">📋 最近研究</h2>
                <Link href="/research" className="text-sm text-[#4f8cff] hover:underline">
                  查看全部 →
                </Link>
              </div>
              <div className="space-y-2">
                {recentResearch.map((s) => (
                  <Link key={s.id} href={`/research/${s.id}`}
                    className="block p-3 rounded-lg bg-[#232736] hover:bg-[#2d3140] transition-colors">
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="font-medium text-sm text-[#e8eaed]">{s.title}</div>
                        <div className="text-xs text-[#9aa0a6] mt-0.5 line-clamp-1">{s.question}</div>
                      </div>
                      <div className="flex items-center gap-2">
                        {s.thesis && <span className="text-xs text-[#34d399]">有观点</span>}
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                          s.status === "completed" ? "bg-[#34d399]/10 text-[#34d399]" :
                          s.status === "researching" ? "bg-[#fbbf24]/10 text-[#fbbf24]" :
                          "bg-[#9aa0a6]/10 text-[#9aa0a6]"
                        }`}>{s.status}</span>
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
