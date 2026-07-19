"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useCompany, useResearchSessions } from "@/lib/api";

export default function CompanyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data: company, isLoading } = useCompany(id);
  const { data: sessions } = useResearchSessions();

  if (isLoading) return <div className="text-[#9aa0a6] py-12 text-center">Loading...</div>;
  if (!company) return <div className="text-[#f87171] py-12 text-center">Company not found</div>;

  const relatedSessions = sessions?.filter((s) => s.company_id === id) || [];

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <Link href="/companies" className="text-sm text-[#4f8cff] hover:underline">← 公司列表</Link>
        <div className="flex items-center gap-4 mt-3">
          <h1 className="text-3xl font-bold text-[#e8eaed]">{company.ticker}</h1>
          <span className="text-xl text-[#9aa0a6]">· {company.name}</span>
        </div>
      </div>

      {/* Info Grid */}
      <div className="grid grid-cols-2 gap-4">
        {company.sector && (
          <div className="p-4 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
            <div className="text-sm text-[#9aa0a6]">行业板块</div>
            <div className="text-[#e8eaed] font-medium mt-1">{company.sector}</div>
          </div>
        )}
        {company.industry && (
          <div className="p-4 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
            <div className="text-sm text-[#9aa0a6]">细分行业</div>
            <div className="text-[#e8eaed] font-medium mt-1">{company.industry}</div>
          </div>
        )}
        {company.headquarters && (
          <div className="p-4 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
            <div className="text-sm text-[#9aa0a6]">总部</div>
            <div className="text-[#e8eaed] font-medium mt-1">{company.headquarters}</div>
          </div>
        )}
        {company.website && (
          <div className="p-4 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
            <div className="text-sm text-[#9aa0a6]">网站</div>
            <div className="text-[#4f8cff] font-medium mt-1">
              <a href={`https://${company.website}`} target="_blank" rel="noopener noreferrer">{company.website}</a>
            </div>
          </div>
        )}
      </div>

      {/* Description */}
      {company.description && (
        <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
          <div className="text-sm text-[#9aa0a6] mb-2">公司简介</div>
          <p className="text-[#e8eaed] leading-relaxed">{company.description}</p>
        </div>
      )}

      {/* Tags */}
      {company.tags.length > 0 && (
        <div>
          <div className="text-sm text-[#9aa0a6] mb-2">标签</div>
          <div className="flex gap-2 flex-wrap">
            {company.tags.map((t) => (
              <span key={t.id} className="px-3 py-1 rounded-lg text-sm bg-[#232736] text-[#9aa0a6] border border-[#2d3140]">
                {t.tag}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Related Research */}
      <div>
        <h2 className="text-lg font-semibold text-[#e8eaed] mb-3">相关研究</h2>
        {relatedSessions.length === 0 ? (
          <div className="p-4 rounded-xl bg-[#1a1d28] border border-[#2d3140] text-sm text-[#9aa0a6]">
            暂无此公司的研究会话。
          </div>
        ) : (
          <div className="space-y-2">
            {relatedSessions.map((s) => (
              <Link
                key={s.id}
                href={`/research/${s.id}`}
                className="block p-4 rounded-xl bg-[#1a1d28] border border-[#2d3140] hover:border-[#4f8cff]/30 transition-colors"
              >
                <div className="font-medium text-[#e8eaed]">{s.title}</div>
                <div className="text-sm text-[#9aa0a6] mt-1">{s.question.slice(0, 200)}...</div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
