"use client";

import { useState } from "react";
import { searchKnowledge, type SearchResult } from "@/lib/api";

export default function KnowledgePage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  const handleSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const data = await searchKnowledge(query);
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
      <div>
        <h1 className="text-2xl font-bold text-[#e8eaed]">🧠 知识库</h1>
        <p className="text-[#9aa0a6] text-sm mt-1">
          混合检索 RAG — 稠密向量 + 稀疏 BM25 倒数排序融合
        </p>
      </div>

      {/* Search */}
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

      {/* Results */}
      {loading ? (
        <div className="text-center text-[#9aa0a6] py-12">混合检索中...</div>
      ) : results.length > 0 ? (
        <div className="space-y-3">
          <div className="text-sm text-[#9aa0a6]">找到 {results.length} 条结果</div>
          {results.map((r, i) => (
            <div
              key={i}
              className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140] hover:border-[#4f8cff]/20 transition-colors"
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-[#9aa0a6]">
                    [{r.doc_type}]
                  </span>
                  <span className="text-sm font-medium text-[#e8eaed]">{r.title}</span>
                </div>
                <span className="text-xs text-[#4f8cff]">
                  得分: {r.score.toFixed(3)}
                </span>
              </div>
              <p className="text-sm text-[#9aa0a6] leading-relaxed">{r.content}</p>
            </div>
          ))}
        </div>
      ) : searched ? (
        <div className="p-12 rounded-xl bg-[#1a1d28] border border-[#2d3140] text-center">
          <div className="text-3xl mb-3">🔍</div>
          <div className="text-[#e8eaed] font-medium">未找到结果</div>
          <div className="text-[#9aa0a6] text-sm mt-1">换个关键词试试</div>
        </div>
      ) : (
        <div className="p-12 rounded-xl bg-[#1a1d28] border border-[#2d3140] text-center">
          <div className="text-3xl mb-3">🧠</div>
          <div className="text-[#e8eaed] font-medium">搜索全部已索引文档</div>
          <div className="text-[#9aa0a6] text-sm mt-1">稠密 + 稀疏混合检索，RRF 融合排序</div>
        </div>
      )}
    </div>
  );
}
