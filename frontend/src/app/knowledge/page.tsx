"use client";

import { useState } from "react";
import { searchKnowledge, type SearchResult } from "@/lib/api";

const DOC_TYPES = [
  { value: "", label: "全部" },
  { value: "pdf", label: "PDF" },
  { value: "markdown", label: "Markdown" },
  { value: "text", label: "TXT" },
  { value: "report", label: "报告" },
];

function ScoreBar({ score }: { score: number }) {
  const pct = Math.min(score * 100, 100);
  const color = score > 0.7 ? "#34d399" : score > 0.4 ? "#fbbf24" : "#9aa0a6";
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 rounded-full bg-[#2d3140] overflow-hidden">
        <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
      <span className="text-xs" style={{ color }}>{score.toFixed(3)}</span>
    </div>
  );
}

export default function KnowledgePage() {
  const [query, setQuery] = useState("");
  const [docType, setDocType] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);

  const handleSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const data = await searchKnowledge(query, 10, docType || undefined);
      setResults(data.results);
      setSearched(true);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-[#e8eaed]">🧠 知识库</h1>
        <p className="text-[#9aa0a6] text-sm mt-1">
          混合检索 RAG — 稠密向量 + BM25 + BGE Reranker 重排序
        </p>
      </div>

      {/* Search Bar */}
      <div className="flex gap-2">
        <input
          type="text"
          placeholder="搜索知识库..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          className="flex-1 p-3 rounded-xl bg-[#1a1d28] border border-[#2d3140] text-[#e8eaed] placeholder-[#9aa0a6] focus:outline-none focus:border-[#4f8cff]"
        />
        <button
          onClick={handleSearch}
          disabled={loading || !query.trim()}
          className="px-6 py-3 rounded-xl bg-[#4f8cff] text-white font-medium hover:bg-[#3a7bf5] disabled:opacity-50 transition-colors"
        >
          {loading ? "搜索中..." : "搜索"}
        </button>
      </div>

      {/* Doc Type Filter */}
      <div className="flex gap-2 flex-wrap">
        {DOC_TYPES.map((t) => (
          <button
            key={t.value}
            onClick={() => setDocType(t.value)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              docType === t.value
                ? "bg-[#4f8cff]/10 text-[#4f8cff] border border-[#4f8cff]/30"
                : "text-[#9aa0a6] hover:text-[#e8eaed] border border-transparent"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Results */}
      {loading ? (
        <div className="text-center text-[#9aa0a6] py-12">
          <div className="text-2xl mb-2 animate-pulse">🔍</div>
          混合检索中...
        </div>
      ) : results.length > 0 ? (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-[#9aa0a6]">找到 {results.length} 条结果</span>
            {searched && (
              <button
                onClick={() => { setResults([]); setSearched(false); setQuery(""); }}
                className="text-xs text-[#4f8cff] hover:underline"
              >
                清除
              </button>
            )}
          </div>
          {results.map((r, i) => (
            <div
              key={i}
              className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140] hover:border-[#4f8cff]/20 transition-colors"
            >
              {/* Header */}
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="px-1.5 py-0.5 rounded text-xs font-medium bg-[#232736] text-[#9aa0a6] border border-[#2d3140] shrink-0">
                    {r.doc_type}
                  </span>
                  <span className="text-sm font-medium text-[#e8eaed] truncate">{r.title}</span>
                </div>
                <ScoreBar score={r.score} />
              </div>

              {/* Content preview */}
              <p className={`text-sm text-[#9aa0a6] leading-relaxed ${expandedIdx === i ? "" : "line-clamp-3"}`}>
                {r.content}
              </p>

              {/* Expand / Source info */}
              <div className="flex items-center gap-3 mt-2">
                <button
                  onClick={() => setExpandedIdx(expandedIdx === i ? null : i)}
                  className="text-xs text-[#4f8cff] hover:underline"
                >
                  {expandedIdx === i ? "收起" : "展开全部"}
                </button>
                <span className="text-xs text-[#6b7280]">文档ID: {r.document_id.slice(0, 8)}...</span>
              </div>
            </div>
          ))}
        </div>
      ) : searched ? (
        <div className="p-12 rounded-xl bg-[#1a1d28] border border-[#2d3140] text-center">
          <div className="text-3xl mb-3">🔍</div>
          <div className="text-[#e8eaed] font-medium">未找到结果</div>
          <div className="text-[#9aa0a6] text-sm mt-1 max-w-md mx-auto">
            知识库中还没有匹配的内容。上传文档后会自动索引到 Qdrant。
          </div>
        </div>
      ) : (
        <div className="p-12 rounded-xl bg-[#1a1d28] border border-[#2d3140] text-center">
          <div className="text-3xl mb-3">🧠</div>
          <div className="text-[#e8eaed] font-medium">搜索全部已索引文档</div>
          <div className="text-[#9aa0a6] text-sm mt-1">
            稠密 + 稀疏混合检索 → RRF 融合 → BGE Reranker 重排序
          </div>
        </div>
      )}
    </div>
  );
}
