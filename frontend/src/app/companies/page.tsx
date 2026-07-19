"use client";

import { useState } from "react";
import Link from "next/link";
import { useCompanies } from "@/lib/api";

export default function CompaniesPage() {
  const [query, setQuery] = useState("");
  const { data, isLoading } = useCompanies(query);

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#e8eaed]">🏢 公司中心</h1>
          <p className="text-[#9aa0a6] text-sm mt-1">公司档案、行业分类与研究对象</p>
        </div>
      </div>

      {/* Search */}
      <div className="relative">
        <input
          type="text"
          placeholder="搜索公司名称或股票代码..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-full p-3 pl-10 rounded-xl bg-[#1a1d28] border border-[#2d3140] text-[#e8eaed] placeholder-[#9aa0a6] focus:outline-none focus:border-[#4f8cff]"
        />
        <span className="absolute left-3 top-3 text-[#9aa0a6]">🔍</span>
      </div>

      {/* Companies Grid */}
      {isLoading ? (
        <div className="text-center text-[#9aa0a6] py-12">加载中...</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {data?.items.map((company) => (
            <Link
              key={company.id}
              href={`/companies/${company.id}`}
              className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140] hover:border-[#4f8cff]/30 transition-colors"
            >
              <div className="flex items-start justify-between mb-2">
                <div>
                  <span className="text-lg font-bold text-[#e8eaed]">{company.ticker}</span>
                  <span className="ml-2 text-[#9aa0a6]">{company.name}</span>
                </div>
              </div>
              {company.sector && (
                <div className="text-sm text-[#9aa0a6]">{company.sector} · {company.industry}</div>
              )}
              <div className="flex gap-1.5 mt-3 flex-wrap">
                {company.tags.map((t) => (
                  <span key={t.id} className="px-2 py-0.5 rounded text-xs bg-[#232736] text-[#9aa0a6]">
                    {t.tag}
                  </span>
                ))}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
