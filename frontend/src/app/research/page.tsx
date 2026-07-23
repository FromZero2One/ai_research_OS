"use client";

import { useState } from "react";
import Link from "next/link";
import { useResearchSessions, useCreateResearch, useCompanies } from "@/lib/api";

const STATUS_OPTIONS = ["all", "draft", "researching", "reviewing", "completed"];

export default function ResearchPage() {
  const [status, setStatus] = useState("all");
  const { data: sessions, isLoading } = useResearchSessions(status === "all" ? undefined : status);
  const createResearch = useCreateResearch();
  const { data: companiesData } = useCompanies();

  const [showNew, setShowNew] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newQuestion, setNewQuestion] = useState("");
  const [newCompanyId, setNewCompanyId] = useState("");

  const handleCreate = async () => {
    if (!newTitle.trim() || !newQuestion.trim()) return;
    const body: Record<string, any> = { title: newTitle, question: newQuestion };
    if (newCompanyId) body.company_id = newCompanyId;
    await createResearch.mutateAsync(body);
    setShowNew(false);
    setNewTitle("");
    setNewQuestion("");
    setNewCompanyId("");
  };

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#e8eaed]">🔬 研究中心</h1>
          <p className="text-[#9aa0a6] text-sm mt-1">问题 → 证据 → 报告 → 决策</p>
        </div>
        <button
          onClick={() => setShowNew(!showNew)}
          className="px-4 py-2 rounded-lg bg-[#4f8cff] text-white text-sm font-medium hover:bg-[#3a7bf5] transition-colors"
        >
          + 新建研究
        </button>
      </div>

      {/* New Research Form */}
      {showNew && (
        <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140] space-y-3">
          <input
            type="text"
            placeholder="研究标题..."
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            className="w-full p-2.5 rounded-lg bg-[#232736] border border-[#2d3140] text-[#e8eaed] placeholder-[#9aa0a6] focus:outline-none focus:border-[#4f8cff]"
          />
          <textarea
            placeholder="你要研究什么问题？..."
            value={newQuestion}
            onChange={(e) => setNewQuestion(e.target.value)}
            rows={3}
            className="w-full p-2.5 rounded-lg bg-[#232736] border border-[#2d3140] text-[#e8eaed] placeholder-[#9aa0a6] focus:outline-none focus:border-[#4f8cff]"
          />
          <select
            value={newCompanyId}
            onChange={(e) => setNewCompanyId(e.target.value)}
            className="w-full p-2.5 rounded-lg bg-[#232736] border border-[#2d3140] text-[#e8eaed] text-sm focus:outline-none focus:border-[#4f8cff]"
          >
            <option value="">不关联公司（可选）</option>
            {(companiesData?.items || []).map((c) => (
              <option key={c.id} value={c.id}>{c.ticker} — {c.name}</option>
            ))}
          </select>
          <div className="flex gap-2">
            <button
              onClick={handleCreate}
              disabled={!newTitle.trim() || !newQuestion.trim() || createResearch.isPending}
              className="px-4 py-2 rounded-lg bg-[#4f8cff] text-white text-sm font-medium hover:bg-[#3a7bf5] disabled:opacity-50"
            >
              {createResearch.isPending ? "创建中..." : "开始研究"}
            </button>
            <button onClick={() => setShowNew(false)} className="px-4 py-2 rounded-lg text-sm text-[#9aa0a6] hover:text-[#e8eaed]">
              取消
            </button>
          </div>
        </div>
      )}

      {/* Status Filter */}
      <div className="flex gap-2">
        {STATUS_OPTIONS.map((s) => (
          <button
            key={s}
            onClick={() => setStatus(s)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              status === s
                ? "bg-[#4f8cff]/10 text-[#4f8cff] border border-[#4f8cff]/30"
                : "text-[#9aa0a6] hover:text-[#e8eaed] border border-transparent"
            }`}
          >
            {s.charAt(0).toUpperCase() + s.slice(1)}
          </button>
        ))}
      </div>

      {/* Sessions List */}
      {isLoading ? (
        <div className="text-center text-[#9aa0a6] py-12">加载中...</div>
      ) : !sessions || sessions.length === 0 ? (
        <div className="p-12 rounded-xl bg-[#1a1d28] border border-[#2d3140] text-center">
          <div className="text-3xl mb-3">🔬</div>
          <div className="text-[#e8eaed] font-medium">还没有研究会话</div>
          <div className="text-[#9aa0a6] text-sm mt-1">提出一个研究问题开始分析</div>
        </div>
      ) : (
        <div className="space-y-3">
          {sessions.map((session) => (
            <Link
              key={session.id}
              href={`/research/${session.id}`}
              className="block p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140] hover:border-[#4f8cff]/30 transition-colors"
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="font-medium text-[#e8eaed] text-lg">{session.title}</div>
                  <div className="text-sm text-[#9aa0a6] mt-1 line-clamp-2">{session.question}</div>
                  {session.thesis && (
                    <div className="text-sm text-[#9aa0a6] mt-2 italic line-clamp-1">论点: {session.thesis}</div>
                  )}
                </div>
                <div className="flex items-center gap-3 ml-4">
                  {session.decision && (
                    <span className={`px-2 py-1 rounded text-xs font-medium ${
                      session.decision === "buy" ? "bg-[#34d399]/10 text-[#34d399]" :
                      session.decision === "sell" ? "bg-[#f87171]/10 text-[#f87171]" :
                      "bg-[#fbbf24]/10 text-[#fbbf24]"
                    }`}>
                      {session.decision.toUpperCase()}
                    </span>
                  )}
                  <span className={`px-2 py-1 rounded text-xs font-medium ${
                    session.status === "completed" ? "bg-[#34d399]/10 text-[#34d399]" :
                    session.status === "researching" ? "bg-[#fbbf24]/10 text-[#fbbf24]" :
                    session.status === "draft" ? "bg-[#9aa0a6]/10 text-[#9aa0a6]" :
                    "bg-[#4f8cff]/10 text-[#4f8cff]"
                  }`}>
                    {session.status}
                  </span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
