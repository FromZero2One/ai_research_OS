"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { useCompanies, useStockSearch } from "@/lib/api";

export default function CompaniesPage() {
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("");
  const { data, isLoading } = useCompanies(query);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["companies"] });
  const [showNew, setShowNew] = useState(false);
  const [newName, setNewName] = useState("");
  const [newTicker, setNewTicker] = useState("");
  const [newExchange, setNewExchange] = useState("");
  const [newTags, setNewTags] = useState("");
  const [searchQ, setSearchQ] = useState("");
  const [showSearchDropdown, setShowSearchDropdown] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);
  const { data: searchData } = useStockSearch(searchQ);
  const searchResults = searchData?.results || [];

  // Close search dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setShowSearchDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  function handleSelectStock(symbol: string, name: string) {
    setNewTicker(symbol);
    setNewName(name);
    setSearchQ("");
    setShowSearchDropdown(false);
    // Auto-detect exchange
    if (symbol.startsWith("6")) setNewExchange("SSE");
    else if (symbol.match(/^\d/)) setNewExchange("SZSE");
    else if (symbol.match(/^0\d{4}HK/)) setNewExchange("HKEX");
    else setNewExchange("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editTicker, setEditTicker] = useState("");
  const [editSector, setEditSector] = useState("");
  const [editTags, setEditTags] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);
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
      const body = await resp.json();
      if (!resp.ok) {
        const detail = body?.detail || "";
        if (detail.includes("already exists") || detail.includes("Duplicate")) {
          showMsg("error", `❌ 股票代码 ${newTicker.toUpperCase()} 已存在`);
        } else {
          showMsg("error", typeof detail === "string" ? detail : "创建失败");
        }
        return;
      }
      setShowNew(false);
      setNewName("");
      setNewTicker("");
      setNewExchange("");
      setNewTags("");
      setSearchQ("");
      refresh();
      // Auto-trigger profile + financial fetch after creation
      fetch(`/api/market/profile/${newTicker}/ingest`, { method: "POST" }).catch(() => {});
      fetch(`/api/market/financials/${newTicker}/ingest`, { method: "POST" }).catch(() => {});
      showMsg("success", `${newName} 创建成功`);
    } catch (e: any) {
      showMsg("error", e.message || "创建失败");
    }
  };

  const startEdit = (company: any) => {
    setEditingId(company.id);
    setEditName(company.name || "");
    setEditTicker(company.ticker || "");
    setEditSector(company.sector || "");
    setEditTags((company.tags || []).map((t: any) => t.tag).join(", "));
  };

  const handleEdit = async () => {
    if (!editingId) return;
    try {
      const resp = await fetch(`/api/companies/${editingId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: editName,
          ticker: editTicker.toUpperCase(),
          sector: editSector,
          tags: editTags.split(",").map((t) => t.trim()).filter(Boolean),
        }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      setEditingId(null);
      refresh();
      showMsg("success", "更新成功");
    } catch (e: any) {
      showMsg("error", e.message || "更新失败");
    }
  };

  const handleDelete = async (id: string) => {
    try {
      const resp = await fetch(`/api/companies/${id}`, { method: "DELETE" });
      if (!resp.ok) throw new Error(await resp.text());
      setDeletingId(null);
      refresh();
      showMsg("success", "已删除");
    } catch (e: any) {
      showMsg("error", e.message || "删除失败");
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
          <div ref={searchRef} className="relative">
            <input
              placeholder="搜索股票代码或名称..."
              value={searchQ}
              onChange={(e) => { setSearchQ(e.target.value); setShowSearchDropdown(true); }}
              onFocus={() => setShowSearchDropdown(true)}
              className="w-full p-2 rounded bg-[#1a1d28] border border-[#2d3140] text-[#e8eaed] text-sm placeholder-[#9aa0a6] focus:outline-none focus:border-[#4f8cff]"
            />
            {showSearchDropdown && searchQ && (
              <div className="absolute z-10 mt-1 w-full rounded-lg bg-[#1a1d28] border border-[#2d3140] shadow-xl max-h-48 overflow-y-auto">
                {searchResults.length === 0 ? (
                  <div className="p-2 text-sm text-[#9aa0a6]">无匹配结果</div>
                ) : (
                  searchResults.map((r) => (
                    <button
                      key={r.symbol}
                      onClick={() => handleSelectStock(r.symbol, r.name)}
                      className="w-full flex items-center gap-3 px-3 py-2 text-sm text-left hover:bg-[#232736] transition-colors"
                    >
                      <span className="font-mono text-[#4f8cff]">{r.symbol}</span>
                      {r.name && <span className="text-[#e8eaed]">{r.name}</span>}
                    </button>
                  ))
                )}
              </div>
            )}
          </div>
          {newTicker && (
            <div className="flex items-center gap-2 px-2 py-1.5 rounded bg-[#1a1d28] text-sm">
              <span className="font-mono text-[#4f8cff]">{newTicker}</span>
              <span className="text-[#e8eaed]">{newName}</span>
              <button onClick={() => { setNewTicker(""); setNewName(""); }} className="ml-auto text-[#9aa0a6] hover:text-[#f87171]">✕</button>
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <select value={newExchange} onChange={(e) => setNewExchange(e.target.value)} className="p-2 rounded bg-[#1a1d28] border border-[#2d3140] text-[#e8eaed] text-sm">
              <option value="">选择交易所</option>
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
            <button onClick={() => { setShowNew(false); setSearchQ(""); setNewTicker(""); setNewName(""); }} className="px-3 py-1.5 rounded bg-[#2d3140] text-[#9aa0a6] text-xs">取消</button>
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
            <div
              key={company.id}
              className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140] transition-colors relative group"
            >
              {/* Edit / Delete buttons (top-right) */}
              {!editingId && (
                <div className="absolute top-3 right-3 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    onClick={() => startEdit(company)}
                    className="px-2 py-1 rounded text-xs bg-[#2d3140] text-[#9aa0a6] hover:text-[#e8eaed] hover:bg-[#3d4150]"
                  >
                    ✎ 编辑
                  </button>
                  <button
                    onClick={() => setDeletingId(company.id)}
                    className="px-2 py-1 rounded text-xs bg-[#2d1b1b] text-[#f87171] hover:bg-[#3d2525]"
                  >
                    🗑 删除
                  </button>
                </div>
              )}

              {/* Edit mode */}
              {editingId === company.id ? (
                <div className="space-y-3" onClick={(e) => e.stopPropagation()}>
                  <div className="grid grid-cols-2 gap-2">
                    <input value={editName} onChange={(e) => setEditName(e.target.value)} placeholder="名称" className="p-2 rounded bg-[#232736] border border-[#2d3140] text-[#e8eaed] text-sm" />
                    <input value={editTicker} onChange={(e) => setEditTicker(e.target.value)} placeholder="代码" className="p-2 rounded bg-[#232736] border border-[#2d3140] text-[#e8eaed] text-sm" />
                    <input value={editSector} onChange={(e) => setEditSector(e.target.value)} placeholder="行业" className="p-2 rounded bg-[#232736] border border-[#2d3140] text-[#e8eaed] text-sm" />
                    <input value={editTags} onChange={(e) => setEditTags(e.target.value)} placeholder="标签(逗号分隔)" className="p-2 rounded bg-[#232736] border border-[#2d3140] text-[#e8eaed] text-sm" />
                  </div>
                  <div className="flex gap-2">
                    <button onClick={handleEdit} className="px-3 py-1 rounded bg-[#4f8cff] text-white text-xs">保存</button>
                    <button onClick={() => setEditingId(null)} className="px-3 py-1 rounded bg-[#2d3140] text-[#9aa0a6] text-xs">取消</button>
                  </div>
                </div>
              ) : (
                /* View mode */
                <Link href={`/companies/${company.id}`} className="block">
                  <div className="flex items-start justify-between mb-2">
                    <div>
                      <span className="text-lg font-bold text-[#e8eaed]">{company.ticker}</span>
                      <span className="ml-2 text-[#9aa0a6]">{company.name}</span>
                    </div>
                  </div>
                  {company.sector && (
                    <div className="text-sm text-[#9aa0a6]">{company.sector}{company.industry ? ` · ${company.industry}` : ""}</div>
                  )}
                  <div className="flex gap-1.5 mt-3 flex-wrap">
                    {company.tags.map((t) => (
                      <span key={t.id} className="px-2 py-0.5 rounded text-xs bg-[#232736] text-[#9aa0a6]">{t.tag}</span>
                    ))}
                  </div>
                </Link>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Delete confirmation dialog */}
      {deletingId && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setDeletingId(null)}>
          <div className="p-6 rounded-xl bg-[#1a1d28] border border-[#2d3140] max-w-sm w-full mx-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-bold text-[#e8eaed] mb-2">确认删除</h3>
            <p className="text-sm text-[#9aa0a6] mb-4">删除后不可恢复，确定要删除这家公司吗？</p>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setDeletingId(null)} className="px-3 py-1.5 rounded bg-[#2d3140] text-[#9aa0a6] text-sm">取消</button>
              <button onClick={() => handleDelete(deletingId)} className="px-3 py-1.5 rounded bg-[#f87171] text-white text-sm">确认删除</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
