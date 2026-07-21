"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuickResearch, subscribeResearchStream, type ResearchProgress } from "@/lib/api";

const STEP_LABELS: Record<string, string> = {
  starting: "准备开始...",
  planning: "AI 正在生成研究计划...",
  searching: "正在搜索知识库和市场数据...",
  generating: "AI 正在生成研究报告...",
  completed: "研究完成！",
  error: "研究出错",
};

export default function QuickResearchPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialTicker = searchParams.get("ticker") || "";

  const [ticker, setTicker] = useState(initialTicker);
  const [question, setQuestion] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [progress, setProgress] = useState<ResearchProgress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<(() => void) | null>(null);

  const quickResearch = useQuickResearch();

  // Cleanup SSE on unmount
  useEffect(() => {
    return () => abortRef.current?.();
  }, []);

  const handleStart = useCallback(async () => {
    if (!ticker.trim() || !question.trim()) return;

    setError(null);
    setProgress(null);

    try {
      const result = await quickResearch.mutateAsync({
        ticker: ticker.toUpperCase(),
        question: question.trim(),
      });

      setSessionId(result.session_id);

      // Subscribe to SSE stream
      const cleanup = subscribeResearchStream(
        result.session_id,
        (p) => setProgress(p),
        (p) => {
          setProgress(p);
        },
        (err) => setError(err),
      );
      abortRef.current = cleanup;
    } catch (e) {
      setError(e instanceof Error ? e.message : "启动研究失败");
    }
  }, [ticker, question, quickResearch]);

  const progressPct = progress
    ? progress.step === "completed" ? 100
      : progress.step === "generating" ? 75
      : progress.step === "searching" ? 50
      : progress.step === "planning" ? 25
      : 0
    : 0;

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[#e8eaed]">一键研究</h1>
        <p className="text-sm text-[#9aa0a6] mt-1">输入公司和问题，AI 自动完成研究</p>
      </div>

      {!sessionId ? (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-[#e8eaed] mb-1.5">
              公司代码
            </label>
            <input
              type="text"
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              placeholder="例如：NVDA、TSLA、AAPL"
              className="w-full px-3 py-2 rounded-lg bg-[#232736] border border-[#2d3140] text-[#e8eaed] placeholder-[#6b7280] focus:outline-none focus:border-[#4f8cff]"
              maxLength={16}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-[#e8eaed] mb-1.5">
              研究问题
              <span className="text-xs text-[#9aa0a6] ml-2">({question.length}/1000，至少 10 字)</span>
            </label>
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="例如：未来两年的增长逻辑是什么？"
              className="w-full px-3 py-2 rounded-lg bg-[#232736] border border-[#2d3140] text-[#e8eaed] placeholder-[#6b7280] focus:outline-none focus:border-[#4f8cff] min-h-[100px]"
              maxLength={1000}
            />
          </div>

          {error && (
            <div className="p-3 rounded-lg bg-[#f87171]/10 border border-[#f87171]/20 text-sm text-[#f87171]">
              {error}
            </div>
          )}

          <button
            onClick={handleStart}
            disabled={!ticker.trim() || !question.trim() || quickResearch.isPending}
            className="w-full py-2.5 rounded-lg bg-[#4f8cff] text-white font-medium hover:bg-[#3b78e0] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {quickResearch.isPending ? "启动中..." : "🚀 开始研究"}
          </button>
        </div>
      ) : (
        <div className="p-6 rounded-xl bg-[#1a1d28] border border-[#2d3140] space-y-4">
          {/* Progress indicator */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-[#e8eaed]">
                {progress ? STEP_LABELS[progress.step] || progress.message : "正在启动..."}
              </span>
              <span className="text-[#9aa0a6]">{progressPct}%</span>
            </div>
            <div className="h-2 rounded-full bg-[#2d3140] overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  progress?.step === "completed" ? "bg-[#34d399]" :
                  progress?.step === "error" ? "bg-[#f87171]" :
                  "bg-[#4f8cff]"
                }`}
                style={{ width: `${progressPct}%` }}
              />
            </div>
          </div>

          {/* Step messages */}
          <div className="space-y-2 text-sm">
            {["starting", "planning", "searching", "generating", "completed"].map((step) => {
              const current = progress?.step || "starting";
              const isActive = step === current;
              const isDone = ["completed", "error"].includes(current) ||
                (["planning", "searching", "generating", "completed"].indexOf(step) <
                 ["planning", "searching", "generating", "completed"].indexOf(current));

              return (
                <div key={step} className="flex items-center gap-2">
                  {isDone || (isActive && current === "completed") ? (
                    <span className="text-[#34d399]">✅</span>
                  ) : isActive ? (
                    <span className="text-[#4f8cff] animate-pulse">⏳</span>
                  ) : (
                    <span className="text-[#2d3140]">⬜</span>
                  )}
                  <span className={
                    isDone ? "text-[#34d399]" :
                    isActive ? "text-[#e8eaed]" :
                    "text-[#4a4d59]"
                  }>
                    {STEP_LABELS[step]}
                  </span>
                </div>
              );
            })}
          </div>

          {/* Error */}
          {progress?.step === "error" && progress?.error && (
            <div className="p-3 rounded-lg bg-[#f87171]/10 border border-[#f87171]/20 text-sm text-[#f87171]">
              {progress.error}
            </div>
          )}

          {/* Actions when done */}
          {progress?.step === "completed" && sessionId && (
            <div className="flex gap-3 pt-2">
              <Link
                href={`/research/${sessionId}`}
                className="flex-1 py-2.5 rounded-lg bg-[#4f8cff] text-white text-center font-medium hover:bg-[#3b78e0] transition-colors"
              >
                📖 查看研究报告
              </Link>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
