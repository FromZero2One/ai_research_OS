"use client";

import { useState } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { useCompanies } from "@/lib/api";

export default function CompaniesPage() {
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("");
  const { data, isLoading } = useCompanies(query);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["companies"] });
  const [showNew, setShowNew] = useState(false);
  const [newName, setNewName] = useState("");
  const [newTicker, setNewTicker] = useState("");
  const [newExchange, setNewExchange] = useState("SSE");
  const [newTags, setNewTags] = useState("");
  const [msg, setMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const showMsg = (type: "success" | "error", text: string) => {
    setMsg({ type, text });
    setTimeout(() => setMsg(null), 4000);
  };

  const handleCreate = async () => {
    if (!newName.trim() || !newTicker.trim()) return;
    try {
      const resp = await fetch("/api/companies", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newName,
          ticker: newTicker.toUpperCase(),
          exchange: newExchange,
          tags: newTags.split(",").map((t) => t.trim()).filter(Boolean),
        }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      setShowNew(false);
      setNewName("");
      setNewTicker("");
      setNewExchange("SSE");
      setNewTags("");
      refresh();
      showMsg("success", `${newName} 创建成功`);
    } catch (e: any) {
      showMsg("error", e.message || "创建失败");
    }
  };

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Message */}
      {msg && (
        <div className={`p-3 rounded-xl text-sm ${
          msg.type === "success"
            ? "bg-[#34d399]/10 text-[#34d399] border border-[#34d399]/20"
            : "bg-[#f87171]/10 text-[#f87171] border border-[#f87171]/20"
        }`}>
          {msg.text}
        </div>
      )}

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#e8eaed]">🏢 公司中心</h1>
          <p className="text-[#9aa0a6] text-sm mt-1">公司档案、行业分类与研究对象</p>
        </div>
        <button
          onClick={() => setShowNew(!showNew)}
          className="px-3 py-1.5 rounded-lg bg-[#4f8cff] text-white text-xs font-medium hover:bg-[#3a7bf5]"
        >
          + 新建
        </button>
      </div>

      {showNew && (
        <div className="p-5 rounded-xl bg-[#232736] border border-[#2d3140] space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <input placeholder="公司名称 *" value={newName} onChange={(e) => setNewName(e.target.value)} className="p-2 rounded bg-[#1a1d28] border border-[#2d3140] text-[#e8eaed] text-sm" />
            <input placeholder="股票代码 *" value={newTicker} onChange={(e) => setNewTicker(e.target.value)} className="p-2 rounded bg-[#1a1d28] border border-[#2d3140] text-[#e8eaed] text-sm" />
            <select value={newExchange} onChange={(e) => setNewExchange(e.target.value)} className="p-2 rounded bg-[#1a1d28] border border-[#2d3140] text-[#e8eaed] text-sm">
              <option value="SSE">SSE 上交所</option>
              <option value="SZSE">SZSE 深交所</option>
              <option value="NASDAQ">NASDAQ 纳斯达克</option>
              <option value="NYSE">NYSE 纽交所</option>
              <option value="HKEX">HKEX 港交所</option>
            </select>
            <input placeholder="标签(逗号分隔)" value={newTags} onChange={(e) => setNewTags(e.target.value)} className="p-2 rounded bg-[#1a1d28] border border-[#2d3140] text-[#e8eaed] text-sm" />
          </div>
          <div className="flex gap-2">
            <button onClick={handleCreate} disabled={!newName.trim() || !newTicker.trim()} className="px-3 py-1.5 rounded bg-[#34d399] text-black text-xs font-medium disabled:opacity-50">创建</button>
            <button onClick={() => setShowNew(false)} className="px-3 py-1.5 rounded bg-[#2d3140] text-[#9aa0a6] text-xs">取消</button>
          </div>
        </div>
      )}

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
