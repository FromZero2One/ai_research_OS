"use client";

import { useState } from "react";
import Link from "next/link";
import { useTimeline } from "@/lib/api";

const TYPE_ICONS: Record<string, string> = {
  session_created: "🆕",
  plan_generated: "🎯",
  report_generated: "📝",
  report_version: "📄",
  research_completed: "✅",
  status_change: "🔄",
};

const TYPE_LABELS: Record<string, string> = {
  session_created: "创建研究",
  plan_generated: "研究计划",
  report_generated: "报告生成",
  report_version: "报告版本",
  research_completed: "研究完结",
  status_change: "状态变更",
};

export default function TimelinePage() {
  const [ticker, setTicker] = useState("");
  const [searchTicker, setSearchTicker] = useState("");
  const { data, isLoading } = useTimeline(searchTicker);

  const handleSearch = () => {
    setSearchTicker(ticker.toUpperCase().trim());
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[#e8eaed]">研究时间线</h1>
        <p className="text-sm text-[#9aa0a6] mt-1">按公司查看所有研究活动的完整历史</p>
      </div>

      {/* Search */}
      <div className="flex gap-3">
        <input
          type="text"
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          placeholder="输入公司代码，如 NVDA"
          className="flex-1 px-3 py-2 rounded-lg bg-[#232736] border border-[#2d3140] text-[#e8eaed] placeholder-[#6b7280] focus:outline-none focus:border-[#4f8cff]"
        />
        <button
          onClick={handleSearch}
          disabled={!ticker.trim()}
          className="px-4 py-2 rounded-lg bg-[#4f8cff] text-white font-medium hover:bg-[#3b78e0] disabled:opacity-50 transition-colors"
        >
          查询
        </button>
      </div>

      {/* Timeline */}
      {searchTicker && (
        <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
          {isLoading ? (
            <div className="text-center py-8 text-[#9aa0a6]">加载中...</div>
          ) : !data || !data.company_name ? (
            <div className="text-center py-8 text-[#9aa0a6]">
              未找到公司「{searchTicker}」的研究记录
            </div>
          ) : data.events.length === 0 ? (
            <div className="text-center py-8 text-[#9aa0a6]">
              「{data.company_name}」暂无研究活动
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-[#e8eaed]">
                  {data.company_name}
                  <span className="text-sm font-normal text-[#9aa0a6] ml-2">({data.ticker})</span>
                </h2>
                <span className="text-xs text-[#9aa0a6]">{data.events.length} 条事件</span>
              </div>

              <div className="relative">
                {/* Timeline line */}
                <div className="absolute left-[15px] top-2 bottom-2 w-0.5 bg-[#2d3140]" />

                <div className="space-y-0">
                  {data.events.map((event, i) => (
                    <div key={`${event.date}-${i}`} className="relative flex gap-4 pb-4">
                      {/* Dot */}
                      <div className="relative z-10 shrink-0 mt-0.5">
                        <div className="w-8 h-8 rounded-full bg-[#232736] border-2 border-[#2d3140] flex items-center justify-center text-sm">
                          {TYPE_ICONS[event.type] || "📌"}
                        </div>
                      </div>

                      {/* Content */}
                      <div className="flex-1 min-w-0 pt-0.5">
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-[#9aa0a6]">
                            {event.date ? new Date(event.date).toLocaleDateString("zh-CN") : ""}
                          </span>
                          <span className="text-xs px-1.5 py-0.5 rounded bg-[#232736] text-[#9aa0a6]">
                            {TYPE_LABELS[event.type] || event.type}
                          </span>
                        </div>
                        <div className="text-sm text-[#e8eaed] mt-1">{event.detail}</div>

                        {/* Action link */}
                        {event.session_id && (
                          <Link
                            href={`/research/${event.session_id}`}
                            className="text-xs text-[#4f8cff] hover:underline mt-1 inline-block"
                          >
                            查看研究 →
                          </Link>
                        )}

                        {/* Thesis/Decision */}
                        {event.thesis && (
                          <div className="mt-1 p-2 rounded bg-[#232736] text-xs text-[#9aa0a6]">
                            <span className="text-[#e8eaed]">观点:</span> {event.thesis?.slice(0, 120)}...
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
