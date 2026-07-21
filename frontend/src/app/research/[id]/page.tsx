"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useResearchSession, useGeneratePlan, useAutoGatherEvidence, useGenerateReport, useFinalizeResearch, useSessionTimeline, useReportDiff } from "@/lib/api";

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    draft: "bg-[#9aa0a6]/10 text-[#9aa0a6]",
    researching: "bg-[#fbbf24]/10 text-[#fbbf24]",
    reviewing: "bg-[#4f8cff]/10 text-[#4f8cff]",
    completed: "bg-[#34d399]/10 text-[#34d399]",
    archived: "bg-[#6b7280]/10 text-[#6b7280]",
  };
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${colors[status] || colors.draft}`}>
      {status}
    </span>
  );
}

function DecisionBadge({ decision }: { decision: string }) {
  const colors: Record<string, string> = {
    buy: "bg-[#34d399]/10 text-[#34d399]",
    sell: "bg-[#f87171]/10 text-[#f87171]",
    hold: "bg-[#fbbf24]/10 text-[#fbbf24]",
    watch: "bg-[#4f8cff]/10 text-[#4f8cff]",
    pass: "bg-[#9aa0a6]/10 text-[#9aa0a6]",
  };
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${colors[decision] || colors.pass}`}>
      {decision.toUpperCase()}
    </span>
  );
}

const EVIDENCE_TYPE_COLORS: Record<string, { bg: string; border: string; label: string; icon: string }> = {
  supporting: { bg: "bg-[#34d399]/5", border: "border-[#34d399]/20", label: "支持", icon: "✅" },
  opposing: { bg: "bg-[#f87171]/5", border: "border-[#f87171]/20", label: "反对", icon: "⚠️" },
  neutral: { bg: "bg-[#9aa0a6]/5", border: "border-[#2d3140]", label: "中性", icon: "📊" },
};

const EVIDENCE_SOURCE_ICONS: Record<string, string> = {
  document: "📄",
  market_data: "📈",
  web: "🌐",
  ai_generated: "🤖",
  analyst_note: "📝",
};

export default function ResearchDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data: session, isLoading } = useResearchSession(id);
  const { data: timeline } = useSessionTimeline(id);

  const generatePlan = useGeneratePlan();
  const gatherEvidence = useAutoGatherEvidence();
  const generateReport = useGenerateReport();
  const finalize = useFinalizeResearch();

  const [showFinalize, setShowFinalize] = useState(false);
  const [thesis, setThesis] = useState("");
  const [decision, setDecision] = useState("buy");
  const [confidence, setConfidence] = useState(0.7);
  const [expandedReport, setExpandedReport] = useState<string | null>(null);
  const [diffVersion, setDiffVersion] = useState<number | null>(null);
  const [showTimeline, setShowTimeline] = useState(false);

  if (isLoading) return <div className="text-[#9aa0a6] py-12 text-center">加载中...</div>;
  if (!session) return <div className="text-[#f87171] py-12 text-center">研究会话不存在</div>;

  const plan = session.plan;
  const isCompleted = session.status === "completed";
  const hasPlan = !!plan;

  const supporting = (session.evidences || []).filter((e: any) => e.evidence_type === "supporting");
  const opposing = (session.evidences || []).filter((e: any) => e.evidence_type === "opposing");
  const neutral = (session.evidences || []).filter((e: any) => e.evidence_type === "neutral");

  const reportVersions = (session.reports || []).map((r: any) => r.version).filter((v: number) => v > 1);

  const handleFinalize = async () => {
    if (!thesis.trim()) return;
    await finalize.mutateAsync({
      sessionId: id,
      thesis: thesis.trim(),
      decision,
      confidence,
    });
    setShowFinalize(false);
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <Link href="/research" className="text-sm text-[#4f8cff] hover:underline">← 研究中心</Link>
        <h1 className="text-2xl font-bold text-[#e8eaed] mt-2">{session.title}</h1>
        <div className="flex items-center gap-3 mt-2">
          <StatusBadge status={session.status} />
          {session.decision && <DecisionBadge decision={session.decision} />}
          {session.confidence != null && (
            <span className="text-sm text-[#9aa0a6]">置信度: {Math.round(session.confidence * 100)}%</span>
          )}
        </div>
      </div>

      {/* Question */}
      <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
        <div className="text-sm text-[#9aa0a6] mb-2">研究问题</div>
        <p className="text-[#e8eaed] text-lg leading-relaxed">{session.question}</p>
      </div>

      {/* Actions */}
      {!isCompleted && (
        <div className="flex flex-wrap gap-3">
          {!hasPlan && (
            <button onClick={() => generatePlan.mutateAsync(id)} disabled={generatePlan.isPending}
              className="px-4 py-2 rounded-lg bg-[#4f8cff] text-white text-sm font-medium hover:bg-[#3a7bf5] disabled:opacity-50 transition-colors">
              {generatePlan.isPending ? "生成中..." : "🎯 生成研究计划"}
            </button>
          )}
          <button onClick={() => gatherEvidence.mutateAsync(id)} disabled={gatherEvidence.isPending}
            className="px-4 py-2 rounded-lg bg-[#232736] border border-[#2d3140] text-[#e8eaed] text-sm font-medium hover:border-[#4f8cff]/40 disabled:opacity-50 transition-colors">
            {gatherEvidence.isPending ? "收集中..." : "📚 收集证据"}
          </button>
          <button onClick={() => generateReport.mutateAsync({ sessionId: id, isFinal: false })} disabled={generateReport.isPending}
            className="px-4 py-2 rounded-lg bg-[#232736] border border-[#2d3140] text-[#e8eaed] text-sm font-medium hover:border-[#4f8cff]/40 disabled:opacity-50 transition-colors">
            {generateReport.isPending ? "生成中..." : "📝 生成报告"}
          </button>
          <button onClick={() => setShowTimeline(!showTimeline)}
            className="px-4 py-2 rounded-lg bg-[#232736] border border-[#2d3140] text-[#e8eaed] text-sm font-medium hover:border-[#4f8cff]/40 transition-colors">
            {showTimeline ? "隐藏时间线" : "📋 查看时间线"}
          </button>
        </div>
      )}

      {/* Timeline panel */}
      {showTimeline && timeline && (
        <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
          <h2 className="text-lg font-semibold text-[#e8eaed] mb-3">📋 研究时间线</h2>
          <div className="space-y-2">
            {timeline.events.map((event, i) => (
              <div key={i} className="flex items-start gap-3 text-sm">
                <span className="text-[#9aa0a6] shrink-0 w-16 text-xs">
                  {event.date ? new Date(event.date).toLocaleDateString("zh-CN") : ""}
                </span>
                <span className="text-[#e8eaed]">{event.detail}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Plan */}
      {hasPlan && (
        <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140] border-l-4 border-l-[#4f8cff]">
          <h2 className="text-lg font-semibold text-[#e8eaed] mb-3">📋 研究计划</h2>
          <div className="mb-3">
            <div className="text-sm text-[#9aa0a6] mb-1">目标</div>
            <p className="text-[#e8eaed] text-sm">{plan.research_goal}</p>
          </div>
          {plan.sub_questions.length > 0 && (
            <div className="mb-3">
              <div className="text-sm text-[#9aa0a6] mb-1">子问题</div>
              <ul className="space-y-1">
                {plan.sub_questions.map((q: string, i: number) => (
                  <li key={i} className="text-sm text-[#e8eaed] flex gap-2">
                    <span className="text-[#4f8cff] shrink-0">{i + 1}.</span>
                    <span>{q}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            {plan.analysis_dimensions?.map((d: string, i: number) => (
              <span key={i} className="px-2 py-1 rounded bg-[#232736] text-xs text-[#9aa0a6] border border-[#2d3140]">{d}</span>
            ))}
          </div>
        </div>
      )}

      {/* Evidence Viewer (enhanced) */}
      <div>
        <h2 className="text-lg font-semibold text-[#e8eaed] mb-3">
          证据
          <span className="text-sm font-normal text-[#9aa0a6] ml-2">
            ({supporting.length} 支持 · {opposing.length} 反对 · {neutral.length} 中性)
          </span>
        </h2>

        {session.evidences?.length === 0 ? (
          <div className="p-6 rounded-xl bg-[#1a1d28] border border-[#2d3140] text-center">
            <div className="text-sm text-[#9aa0a6]">尚未收集证据，点击上方"收集证据"按钮</div>
          </div>
        ) : (
          <div className="space-y-3">
            {opposing.length > 0 && (
              <div>
                <div className="text-sm text-[#f87171] font-medium mb-2">⚠️ 反对证据</div>
                {opposing.map((ev: any) => <EvidenceCard key={ev.id} evidence={ev} />)}
              </div>
            )}
            {supporting.length > 0 && (
              <div>
                <div className="text-sm text-[#34d399] font-medium mb-2">✅ 支持证据</div>
                {supporting.map((ev: any) => <EvidenceCard key={ev.id} evidence={ev} />)}
              </div>
            )}
            {neutral.length > 0 && (
              <div>
                <div className="text-sm text-[#9aa0a6] font-medium mb-2">📊 中性数据</div>
                {neutral.map((ev: any) => <EvidenceCard key={ev.id} evidence={ev} />)}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Reports with Diff */}
      {session.reports?.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold text-[#e8eaed] mb-3">
            研究报告
            <span className="text-sm font-normal text-[#9aa0a6] ml-2">({session.reports.length} 个版本)</span>
          </h2>
          <div className="space-y-3">
            {session.reports.map((r: any) => (
              <div key={r.id} className="rounded-xl bg-[#1a1d28] border border-[#2d3140] overflow-hidden">
                <button
                  onClick={() => {
                    setExpandedReport(expandedReport === r.id ? null : r.id);
                    setDiffVersion(null);
                  }}
                  className="w-full flex items-center justify-between p-4 hover:bg-[#232736] transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <span className="text-[#e8eaed] font-medium">{r.title}</span>
                    <span className="text-xs text-[#9aa0a6]">v{r.version}</span>
                    {r.is_final && <span className="px-1.5 py-0.5 rounded text-xs bg-[#34d399]/10 text-[#34d399]">终稿</span>}
                  </div>
                  <span className="text-[#9aa0a6] text-sm">{expandedReport === r.id ? "收起 ▲" : "展开 ▼"}</span>
                </button>
                {expandedReport === r.id && (
                  <div className="px-4 pb-4 space-y-2">
                    {/* Diff button for multi-version reports */}
                    {r.version > 1 && (
                      <div className="flex gap-2">
                        <button
                          onClick={(e) => { e.stopPropagation(); setDiffVersion(diffVersion === r.version ? null : r.version - 1); }}
                          className="px-3 py-1.5 rounded-lg bg-[#232736] border border-[#2d3140] text-xs text-[#e8eaed] hover:border-[#4f8cff]/40 transition-colors"
                        >
                          {diffVersion === r.version ? "隐藏对比" : `📊 对比 v{r.version - 1}`}
                        </button>
                      </div>
                    )}
                    {diffVersion === r.version && (
                      <DiffView reportId={r.id} fromVersion={r.version - 1} />
                    )}
                    <div className="p-4 rounded-lg bg-[#0d1117] text-sm text-[#e8eaed] leading-relaxed whitespace-pre-wrap font-mono max-h-[600px] overflow-y-auto">
                      {r.content}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Thesis */}
      {session.thesis && (
        <div className="p-5 rounded-xl bg-[#1a1d28] border-l-4 border-[#4f8cff]">
          <div className="text-sm text-[#9aa0a6] mb-2">投资论点</div>
          <p className="text-[#e8eaed] leading-relaxed">{session.thesis}</p>
        </div>
      )}

      {/* Finalize */}
      {!isCompleted && (
        <div className="border-t border-[#2d3140] pt-6">
          {!showFinalize ? (
            <button onClick={() => setShowFinalize(true)}
              className="px-4 py-2 rounded-lg bg-[#34d399]/10 text-[#34d399] text-sm font-medium border border-[#34d399]/20 hover:bg-[#34d399]/20 transition-colors">
              🏁 完结研究
            </button>
          ) : (
            <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140] space-y-3">
              <h3 className="text-[#e8eaed] font-medium">完结研究</h3>
              <textarea
                placeholder="输入投资论点..."
                value={thesis} onChange={(e) => setThesis(e.target.value)}
                rows={3}
                className="w-full p-2.5 rounded-lg bg-[#232736] border border-[#2d3140] text-[#e8eaed] placeholder-[#9aa0a6] focus:outline-none focus:border-[#4f8cff] text-sm"
              />
              <div className="flex gap-3">
                <select value={decision} onChange={(e) => setDecision(e.target.value)}
                  className="p-2 rounded-lg bg-[#232736] border border-[#2d3140] text-[#e8eaed] text-sm">
                  <option value="buy">买入</option>
                  <option value="sell">卖出</option>
                  <option value="hold">持有</option>
                  <option value="watch">关注</option>
                  <option value="pass">跳过</option>
                </select>
                <div className="flex items-center gap-2">
                  <span className="text-sm text-[#9aa0a6]">置信度:</span>
                  <input type="range" min={0} max={100} value={Math.round(confidence * 100)}
                    onChange={(e) => setConfidence(Number(e.target.value) / 100)} className="w-24" />
                  <span className="text-sm text-[#e8eaed] w-8">{Math.round(confidence * 100)}%</span>
                </div>
              </div>
              <div className="flex gap-2">
                <button onClick={handleFinalize} disabled={!thesis.trim() || finalize.isPending}
                  className="px-4 py-2 rounded-lg bg-[#34d399] text-black text-sm font-medium hover:bg-[#2bc088] disabled:opacity-50 transition-colors">
                  {finalize.isPending ? "提交中..." : "确认完结"}
                </button>
                <button onClick={() => setShowFinalize(false)}
                  className="px-4 py-2 rounded-lg text-sm text-[#9aa0a6] hover:text-[#e8eaed]">取消</button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Enhanced Evidence Card ───────────────────────────────────────────

function EvidenceCard({ evidence }: { evidence: any }) {
  const [expanded, setExpanded] = useState(false);
  const colors = EVIDENCE_TYPE_COLORS[evidence.evidence_type] || EVIDENCE_TYPE_COLORS.neutral;
  const sourceIcon = EVIDENCE_SOURCE_ICONS[evidence.source_type] || "📄";

  return (
    <div className={`p-4 rounded-xl bg-[#1a1d28] border ${colors.border} ${colors.bg}`}>
      <div className="flex items-center gap-2 mb-2">
        <span>{sourceIcon}</span>
        <span className="text-xs px-1.5 py-0.5 rounded bg-[#232736] text-[#9aa0a6]">{evidence.source_type}</span>
        {evidence.source_title && (
          <span className="text-xs text-[#9aa0a6] truncate max-w-[200px]" title={evidence.source_title}>
            {evidence.source_title}
          </span>
        )}
        {evidence.relevance_score != null && (
          <span className="text-xs text-[#9aa0a6] ml-auto">
            可信度: <span className={evidence.relevance_score >= 0.7 ? "text-[#34d399]" : evidence.relevance_score >= 0.4 ? "text-[#fbbf24]" : "text-[#f87171]"}>{Math.round(evidence.relevance_score * 100)}%</span>
          </span>
        )}
        <button onClick={() => setExpanded(!expanded)} className="text-xs text-[#4f8cff] hover:underline shrink-0">
          {expanded ? "收起" : "展开"}
        </button>
      </div>
      <p className={`text-sm text-[#e8eaed] leading-relaxed ${expanded ? "" : "line-clamp-3"}`}>
        {evidence.content}
      </p>
      {evidence.source_id && (
        <div className="mt-2 text-xs text-[#4f8cff]">
          来源: {evidence.source_id}
        </div>
      )}
    </div>
  );
}

// ── Diff View ────────────────────────────────────────────────────────

function DiffView({ reportId, fromVersion }: { reportId: string; fromVersion: number }) {
  const { data, isLoading } = useReportDiff(reportId, fromVersion);

  if (isLoading) return <div className="text-xs text-[#9aa0a6] py-2">加载对比...</div>;
  if (!data) return null;

  return (
    <div className="rounded-lg bg-[#0d1117] border border-[#2d3140] overflow-hidden">
      <div className="flex items-center justify-between px-3 py-2 bg-[#232736] border-b border-[#2d3140]">
        <span className="text-xs text-[#9aa0a6]">
          对比 v{data.from_version} → v{data.to_version}
        </span>
        <span className="text-xs text-[#9aa0a6]">
          <span className="text-[#34d399]">+{data.stats.additions}</span>
          {" / "}
          <span className="text-[#f87171]">-{data.stats.deletions}</span>
        </span>
      </div>
      <div className="p-3 text-xs font-mono leading-relaxed max-h-[400px] overflow-y-auto whitespace-pre-wrap">
        {data.diff.split("\n").map((line, i) => {
          if (line.startsWith("+") && !line.startsWith("+++")) {
            return <div key={i} className="bg-[#34d399]/10 text-[#34d399]">{line}</div>;
          }
          if (line.startsWith("-") && !line.startsWith("---")) {
            return <div key={i} className="bg-[#f87171]/10 text-[#f87171]">{line}</div>;
          }
          if (line.startsWith("@@")) {
            return <div key={i} className="bg-[#4f8cff]/10 text-[#4f8cff]">{line}</div>;
          }
          return <div key={i} className="text-[#9aa0a6]">{line}</div>;
        })}
      </div>
    </div>
  );
}
