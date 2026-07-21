"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useCompany, useDocuments, useResearchSessions, useMarketPrices, useFinancialMetrics, useCompanyWorkspace, useUpdateThesis } from "@/lib/api";
import StockChart from "@/components/StockChart";

function TabBar({ tabs, active, onChange }: { tabs: string[]; active: string; onChange: (t: string) => void }) {
  return (
    <div className="flex gap-1 border-b border-[#2d3140] mb-4 overflow-x-auto">
      {tabs.map((tab) => (
        <button
          key={tab}
          onClick={() => onChange(tab)}
          className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-[1px] whitespace-nowrap ${
            active === tab
              ? "text-[#4f8cff] border-[#4f8cff]"
              : "text-[#9aa0a6] border-transparent hover:text-[#e8eaed]"
          }`}
        >
          {tab}
        </button>
      ))}
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="p-4 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
      <div className="text-xs text-[#9aa0a6] mb-1">{label}</div>
      <div className="text-[#e8eaed] font-medium truncate">{value || "—"}</div>
    </div>
  );
}

function MiniBar({ data, color }: { data: { fiscal_year: number; fiscal_period: string; metric_value: number }[]; color: string }) {
  const maxVal = Math.max(...data.map((d) => d.metric_value));
  const num = (v: number) => {
    if (v > 1e9) return `$${(v / 1e9).toFixed(1)}B`;
    if (v > 1e6) return `$${(v / 1e6).toFixed(1)}M`;
    return `$${v.toFixed(0)}`;
  };
  return (
    <div className="space-y-1.5">
      {data.slice(-8).map((d, i) => (
        <div key={i} className="flex items-center gap-2 text-xs">
          <span className="text-[#9aa0a6] w-14 shrink-0">{d.fiscal_period}</span>
          <div className="flex-1 h-4 rounded bg-[#232736] overflow-hidden">
            <div className="h-full rounded" style={{ width: `${(d.metric_value / maxVal) * 100}%`, backgroundColor: color }} />
          </div>
          <span className="text-[#e8eaed] w-20 text-right font-mono">{num(d.metric_value)}</span>
        </div>
      ))}
    </div>
  );
}

export default function CompanyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data: company, isLoading } = useCompany(id);
  const { data: docsData } = useDocuments();
  const { data: sessions } = useResearchSessions();
  const [activeTab, setActiveTab] = useState("概览");
  const [chartTicker, setChartTicker] = useState<string | null>(null);
  const { data: priceData } = useMarketPrices(chartTicker || "", 260);
  const { data: finData } = useFinancialMetrics(chartTicker || "");

  // Workspace data for thesis + timeline
  const ticker = company?.ticker || "";
  const { data: workspace } = useCompanyWorkspace(ticker);
  const updateThesis = useUpdateThesis();

  // Thesis edit state
  const [editingThesis, setEditingThesis] = useState(false);
  const [thesisText, setThesisText] = useState("");
  const [thesisDecision, setThesisDecision] = useState("watch");
  const [thesisConfidence, setThesisConfidence] = useState(0.6);

  if (company && !chartTicker) setChartTicker(company.ticker);

  const prices = priceData?.prices || [];
  const financials = finData?.metrics || [];
  const revenueData = financials.filter((m) => m.metric_name === "revenue").reverse();
  const incomeData = financials.filter((m) => m.metric_name === "net_income").reverse();

  if (isLoading) return <div className="text-[#9aa0a6] py-12 text-center">加载中...</div>;
  if (!company) return <div className="text-[#f87171] py-12 text-center">公司未找到</div>;

  const relatedSessions = sessions?.filter((s) => s.company_id === id) || [];
  const relatedDocs = docsData?.items?.filter((d: any) => d.company_id === id) || [];

  const handleSaveThesis = async () => {
    if (!thesisText.trim()) return;
    await updateThesis.mutateAsync({
      ticker: company.ticker,
      thesis: thesisText.trim(),
      decision: thesisDecision,
      confidence: thesisConfidence,
    });
    setEditingThesis(false);
  };

  const currentThesis = workspace?.thesis;
  const evidenceCounts = workspace?.evidence_summary || { supporting: 0, opposing: 0, neutral: 0 };

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <Link href="/companies" className="text-sm text-[#4f8cff] hover:underline">← 公司列表</Link>
        <div className="flex items-center gap-4 mt-3">
          <div>
            <h1 className="text-3xl font-bold text-[#e8eaed]">{company.ticker}</h1>
            <p className="text-lg text-[#9aa0a6] mt-0.5">{company.name}</p>
          </div>
          <div className="ml-auto flex items-center gap-2">
            {/* Thesis indicator */}
            {currentThesis?.thesis && (
              <span className="px-2 py-1 rounded text-xs bg-[#4f8cff]/10 text-[#4f8cff] border border-[#4f8cff]/20">
                有观点
              </span>
            )}
            <Link
              href={`/research/quick?ticker=${company.ticker}`}
              className="px-4 py-2 rounded-lg bg-[#4f8cff] text-white text-sm font-medium hover:bg-[#3a7bf5] transition-colors shrink-0"
            >
              ⚡ 快速研究
            </Link>
          </div>
        </div>
      </div>

      {/* Tags */}
      {company.tags.length > 0 && (
        <div className="flex gap-1.5 flex-wrap">
          {company.tags.map((t: { id: string; tag: string }) => (
            <span key={t.id} className="px-2.5 py-1 rounded-lg text-xs bg-[#232736] text-[#9aa0a6] border border-[#2d3140]">{t.tag}</span>
          ))}
        </div>
      )}

      {/* Thesis Summary Bar */}
      {currentThesis?.thesis && !editingThesis && (
        <div className="p-4 rounded-xl bg-[#1a1d28] border border-[#2d3140] border-l-4 border-l-[#4f8cff]">
          <div className="flex items-center justify-between">
            <div className="flex-1 min-w-0">
              <div className="text-xs text-[#9aa0a6] mb-1">当前观点</div>
              <p className="text-sm text-[#e8eaed] line-clamp-2">{currentThesis.thesis}</p>
            </div>
            <div className="flex items-center gap-3 ml-4 shrink-0">
              {currentThesis.decision && (
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                  currentThesis.decision === "buy" ? "bg-[#34d399]/10 text-[#34d399]" :
                  currentThesis.decision === "sell" ? "bg-[#f87171]/10 text-[#f87171]" :
                  "bg-[#fbbf24]/10 text-[#fbbf24]"
                }`}>{currentThesis.decision.toUpperCase()}</span>
              )}
              {currentThesis.confidence != null && (
                <span className="text-xs text-[#9aa0a6]">{Math.round(currentThesis.confidence * 100)}%</span>
              )}
              <button onClick={() => { setThesisText(currentThesis.thesis || ""); setEditingThesis(true); }}
                className="text-xs text-[#4f8cff] hover:underline">编辑</button>
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <TabBar tabs={["概览", "投资观点", "财务数据", "研究", "文档"]} active={activeTab} onChange={setActiveTab} />

      {/* ══════ Overview Tab ══════ */}
      {activeTab === "概览" && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard label="行业板块" value={company.sector} />
            <StatCard label="细分行业" value={company.industry} />
            <StatCard label="总部" value={company.headquarters} />
            <StatCard label="网站" value={company.website || "—"} />
          </div>
          {company.description && (
            <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
              <div className="text-sm text-[#9aa0a6] mb-2">公司简介</div>
              <p className="text-[#e8eaed] leading-relaxed text-sm">{company.description}</p>
            </div>
          )}
          {/* Evidence Summary */}
          {(evidenceCounts.supporting > 0 || evidenceCounts.opposing > 0) && (
            <div className="p-4 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
              <div className="text-sm text-[#9aa0a6] mb-2">证据总览</div>
              <div className="flex gap-4 text-sm">
                <span className="text-[#34d399]">✅ {evidenceCounts.supporting} 支持</span>
                <span className="text-[#f87171]">⚠️ {evidenceCounts.opposing} 反对</span>
                <span className="text-[#9aa0a6]">📊 {evidenceCounts.neutral} 中性</span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ══════ Thesis Tab ══════ */}
      {activeTab === "投资观点" && (
        <div className="space-y-6">
          {/* Current Thesis */}
          <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
            <h2 className="text-lg font-semibold text-[#e8eaed] mb-3">🎯 当前观点</h2>
            {editingThesis ? (
              <div className="space-y-3">
                <textarea
                  value={thesisText}
                  onChange={(e) => setThesisText(e.target.value)}
                  rows={4}
                  placeholder="输入投资观点..."
                  className="w-full p-2.5 rounded-lg bg-[#232736] border border-[#2d3140] text-[#e8eaed] placeholder-[#9aa0a6] focus:outline-none focus:border-[#4f8cff] text-sm"
                />
                <div className="flex gap-3">
                  <select value={thesisDecision} onChange={(e) => setThesisDecision(e.target.value)}
                    className="p-2 rounded-lg bg-[#232736] border border-[#2d3140] text-[#e8eaed] text-sm">
                    <option value="buy">买入</option>
                    <option value="sell">卖出</option>
                    <option value="hold">持有</option>
                    <option value="watch">关注</option>
                    <option value="pass">跳过</option>
                  </select>
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-[#9aa0a6]">置信度:</span>
                    <input type="range" min={0} max={100} value={Math.round(thesisConfidence * 100)}
                      onChange={(e) => setThesisConfidence(Number(e.target.value) / 100)} className="w-24" />
                    <span className="text-sm text-[#e8eaed] w-8">{Math.round(thesisConfidence * 100)}%</span>
                  </div>
                </div>
                <div className="flex gap-2">
                  <button onClick={handleSaveThesis} disabled={!thesisText.trim() || updateThesis.isPending}
                    className="px-4 py-2 rounded-lg bg-[#34d399] text-black text-sm font-medium hover:bg-[#2bc088] disabled:opacity-50 transition-colors">
                    {updateThesis.isPending ? "保存中..." : "保存观点"}
                  </button>
                  <button onClick={() => setEditingThesis(false)}
                    className="px-4 py-2 rounded-lg text-sm text-[#9aa0a6] hover:text-[#e8eaed]">取消</button>
                </div>
              </div>
            ) : currentThesis?.thesis ? (
              <div>
                <p className="text-[#e8eaed] leading-relaxed">{currentThesis.thesis}</p>
                <div className="flex items-center gap-3 mt-3">
                  {currentThesis.decision && (
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                      currentThesis.decision === "buy" ? "bg-[#34d399]/10 text-[#34d399]" :
                      currentThesis.decision === "sell" ? "bg-[#f87171]/10 text-[#f87171]" :
                      "bg-[#fbbf24]/10 text-[#fbbf24]"
                    }`}>{currentThesis.decision.toUpperCase()}</span>
                  )}
                  {currentThesis.confidence != null && (
                    <span className="text-sm text-[#9aa0a6]">置信度: {Math.round(currentThesis.confidence * 100)}%</span>
                  )}
                  {currentThesis.updated_at && (
                    <span className="text-xs text-[#9aa0a6]">更新于 {new Date(currentThesis.updated_at).toLocaleDateString("zh-CN")}</span>
                  )}
                  <button onClick={() => { setThesisText(currentThesis.thesis || ""); setThesisDecision(currentThesis.decision || "watch"); setThesisConfidence(currentThesis.confidence || 0.6); setEditingThesis(true); }}
                    className="ml-auto text-xs text-[#4f8cff] hover:underline">编辑</button>
                </div>
              </div>
            ) : (
              <div className="text-center py-6">
                <div className="text-sm text-[#9aa0a6] mb-3">还没有投资观点</div>
                <button onClick={() => { setThesisText(""); setEditingThesis(true); }}
                  className="px-4 py-2 rounded-lg bg-[#4f8cff] text-white text-sm font-medium hover:bg-[#3a7bf5] transition-colors">
                  ✏️ 创建观点
                </button>
              </div>
            )}
          </div>

          {/* Evidence Summary */}
          {(evidenceCounts.supporting > 0 || evidenceCounts.opposing > 0) && (
            <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
              <h2 className="text-lg font-semibold text-[#e8eaed] mb-3">📊 证据统计</h2>
              <div className="grid grid-cols-3 gap-4">
                <div className="p-4 rounded-lg bg-[#34d399]/5 border border-[#34d399]/20 text-center">
                  <div className="text-2xl font-bold text-[#34d399]">{evidenceCounts.supporting}</div>
                  <div className="text-xs text-[#9aa0a6] mt-1">支持</div>
                </div>
                <div className="p-4 rounded-lg bg-[#f87171]/5 border border-[#f87171]/20 text-center">
                  <div className="text-2xl font-bold text-[#f87171]">{evidenceCounts.opposing}</div>
                  <div className="text-xs text-[#9aa0a6] mt-1">反对</div>
                </div>
                <div className="p-4 rounded-lg bg-[#9aa0a6]/5 border border-[#2d3140] text-center">
                  <div className="text-2xl font-bold text-[#9aa0a6]">{evidenceCounts.neutral}</div>
                  <div className="text-xs text-[#9aa0a6] mt-1">中性</div>
                </div>
              </div>
            </div>
          )}

          {/* Recent Timeline */}
          {workspace?.recent_research && workspace.recent_research.length > 0 && (
            <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
              <h2 className="text-lg font-semibold text-[#e8eaed] mb-3">📋 近期研究</h2>
              <div className="space-y-2">
                {workspace.recent_research.map((s: any) => (
                  <Link key={s.id} href={`/research/${s.id}`}
                    className="flex items-center justify-between p-3 rounded-lg bg-[#232736] hover:bg-[#2d3140] transition-colors">
                    <div>
                      <div className="text-sm text-[#e8eaed]">{s.title}</div>
                      <div className="text-xs text-[#9aa0a6] mt-0.5">
                        {s.created_at ? new Date(s.created_at).toLocaleDateString("zh-CN") : ""}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {s.decision && <span className="text-xs text-[#34d399]">{s.decision.toUpperCase()}</span>}
                      <span className="text-xs text-[#9aa0a6]">{s.status}</span>
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ══════ Financials Tab ══════ */}
      {activeTab === "财务数据" && (
        <div className="space-y-6">
          <div className="p-4 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
            <div className="text-sm text-[#9aa0a6] mb-3">{company.ticker} · 股价走势</div>
            <StockChart prices={prices} height={350} />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {revenueData.length > 0 && (
              <div className="p-4 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
                <div className="text-sm text-[#9aa0a6] mb-3">营收趋势</div>
                <MiniBar data={revenueData} color="#4f8cff" />
              </div>
            )}
            {incomeData.length > 0 && (
              <div className="p-4 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
                <div className="text-sm text-[#9aa0a6] mb-3">净利润趋势</div>
                <MiniBar data={incomeData} color="#34d399" />
              </div>
            )}
          </div>
        </div>
      )}

      {/* ══════ Research Tab ══════ */}
      {activeTab === "研究" && (
        <div>
          {relatedSessions.length === 0 ? (
            <div className="p-8 rounded-xl bg-[#1a1d28] border border-[#2d3140] text-center">
              <div className="text-3xl mb-3">🔬</div>
              <div className="text-[#e8eaed] font-medium">暂无研究</div>
              <div className="text-sm text-[#9aa0a6] mt-1">创建第一个研究会话</div>
              <Link href={`/research/quick?ticker=${company.ticker}`}
                className="inline-block mt-3 px-4 py-2 rounded-lg bg-[#4f8cff] text-white text-sm font-medium hover:bg-[#3a7bf5]">
                ⚡ 快速研究
              </Link>
            </div>
          ) : (
            <div className="space-y-3">
              {relatedSessions.map((s: any) => (
                <Link key={s.id} href={`/research/${s.id}`}
                  className="block p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140] hover:border-[#4f8cff]/30 transition-colors">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-medium text-[#e8eaed]">{s.title}</div>
                      <div className="text-sm text-[#9aa0a6] mt-1 line-clamp-1">{s.question}</div>
                    </div>
                    <div className="flex items-center gap-2 ml-3">
                      {s.decision && (
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                          s.decision === "buy" ? "bg-[#34d399]/10 text-[#34d399]" :
                          s.decision === "sell" ? "bg-[#f87171]/10 text-[#f87171]" :
                          "bg-[#fbbf24]/10 text-[#fbbf24]"
                        }`}>{s.decision.toUpperCase()}</span>
                      )}
                      <span className="px-2 py-0.5 rounded text-xs bg-[#9aa0a6]/10 text-[#9aa0a6]">{s.status}</span>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ══════ Documents Tab ══════ */}
      {activeTab === "文档" && (
        <div>
          {relatedDocs.length === 0 ? (
            <div className="p-8 rounded-xl bg-[#1a1d28] border border-[#2d3140] text-center">
              <div className="text-3xl mb-3">📄</div>
              <div className="text-[#e8eaed] font-medium">暂无文档</div>
              <div className="text-sm text-[#9aa0a6] mt-1">上传相关财报或报告</div>
              <Link href="/documents"
                className="inline-block mt-3 px-4 py-2 rounded-lg bg-[#4f8cff] text-white text-sm font-medium hover:bg-[#3a7bf5]">
                + 上传文档
              </Link>
            </div>
          ) : (
            <div className="space-y-2">
              {relatedDocs.map((doc: any) => (
                <div key={doc.id} className="p-4 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
                  <div className="font-medium text-[#e8eaed]">{doc.title}</div>
                  <div className="text-xs text-[#9aa0a6] mt-1">
                    {doc.doc_type} · {doc.is_indexed ? "已索引" : "未索引"}
                    {doc.chunk_count != null && ` · ${doc.chunk_count} 切片`}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
