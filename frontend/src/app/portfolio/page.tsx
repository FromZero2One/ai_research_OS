"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useWatchlists, useHoldings } from "@/lib/api";

export default function PortfolioPage() {
  const queryClient = useQueryClient();
  const { data: watchlists, isLoading: wlLoading } = useWatchlists();
  const refreshWLs = () => queryClient.invalidateQueries({ queryKey: [] });
  const { data: holdings, isLoading: hdLoading } = useHoldings();

  const [showNewWL, setShowNewWL] = useState(false);
  const [wlName, setWlName] = useState("");
  const [wlDesc, setWlDesc] = useState("");
  const [wlTicker, setWlTicker] = useState("");

  const [showNewHD, setShowNewHD] = useState(false);
  const [hdTicker, setHdTicker] = useState("");
  const [hdShares, setHdShares] = useState("");
  const [hdCost, setHdCost] = useState("");

  const [msg, setMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const showMsg = (type: "success" | "error", text: string) => {
    setMsg({ type, text });
    setTimeout(() => setMsg(null), 4000);
  };

  const handleCreateWatchlist = async () => {
    if (!wlName.trim()) return;
    try {
      const resp = await fetch("/api/portfolio/watchlists", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: wlName, description: wlDesc }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      const wl = await resp.json();

      if (wlTicker.trim()) {
        await fetch("/api/portfolio/watchlists", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ watchlist_id: wl.id, ticker: wlTicker.toUpperCase() }),
        });
      }
      setShowNewWL(false);
      setWlName("");
      setWlDesc("");
      setWlTicker("");
      showMsg("success", `自选列表 "${wlName}" 创建成功`);
    } catch (e: any) {
      showMsg("error", e.message || "创建失败");
    }
  };

  const handleCreateHolding = async () => {
    if (!hdTicker.trim() || !hdShares) return;
    try {
      const resp = await fetch("/api/portfolio/holdings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticker: hdTicker.toUpperCase(),
          shares: parseFloat(hdShares),
          avg_cost_basis: hdCost ? parseFloat(hdCost) : null,
        }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      setShowNewHD(false);
      setHdTicker("");
      setHdShares("");
      setHdCost("");
      showMsg("success", `持仓 ${hdTicker.toUpperCase()} 添加成功`);
    } catch (e: any) {
      showMsg("error", e.message || "添加失败");
    }
  };

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-[#e8eaed]">💼 投资组合</h1>
        <p className="text-[#9aa0a6] text-sm mt-1">自选列表 · 持仓 · 研究日志</p>
      </div>

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

      <div className="grid grid-cols-2 gap-6">
        {/* ── Watchlists ── */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold text-[#e8eaed]">自选列表</h2>
            <button
              onClick={() => setShowNewWL(!showNewWL)}
              className="px-3 py-1.5 rounded-lg bg-[#4f8cff] text-white text-xs font-medium hover:bg-[#3a7bf5]"
            >
              + 新建
            </button>
          </div>

          {showNewWL && (
            <div className="mb-3 p-4 rounded-xl bg-[#232736] border border-[#2d3140] space-y-2">
              <input
                placeholder="列表名称"
                value={wlName}
                onChange={(e) => setWlName(e.target.value)}
                className="w-full p-2 rounded bg-[#1a1d28] border border-[#2d3140] text-[#e8eaed] text-sm"
              />
              <input
                placeholder="描述（可选）"
                value={wlDesc}
                onChange={(e) => setWlDesc(e.target.value)}
                className="w-full p-2 rounded bg-[#1a1d28] border border-[#2d3140] text-[#e8eaed] text-sm"
              />
              <input
                placeholder="添加股票代码（可选）"
                value={wlTicker}
                onChange={(e) => setWlTicker(e.target.value)}
                className="w-full p-2 rounded bg-[#1a1d28] border border-[#2d3140] text-[#e8eaed] text-sm"
              />
              <button
                onClick={handleCreateWatchlist}
                disabled={!wlName.trim()}
                className="px-3 py-1.5 rounded bg-[#34d399] text-black text-xs font-medium disabled:opacity-50"
              >
                创建
              </button>
            </div>
          )}

          {wlLoading ? (
            <div className="p-6 rounded-xl bg-[#1a1d28] border border-[#2d3140] text-center text-sm text-[#9aa0a6]">加载中...</div>
          ) : !watchlists || watchlists.length === 0 ? (
            <div className="p-6 rounded-xl bg-[#1a1d28] border border-[#2d3140] text-center text-sm text-[#9aa0a6]">暂无自选列表</div>
          ) : (
            <div className="space-y-3">
              {watchlists.map((wl: any) => (
                <WatchlistCard key={wl.id} wl={wl} onMsg={showMsg} onRefresh={refreshWLs} />
              ))}
            </div>
          )}
        </div>

        {/* ── Holdings ── */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold text-[#e8eaed]">持仓</h2>
            <button
              onClick={() => setShowNewHD(!showNewHD)}
              className="px-3 py-1.5 rounded-lg bg-[#4f8cff] text-white text-xs font-medium hover:bg-[#3a7bf5]"
            >
              + 添加
            </button>
          </div>

          {showNewHD && (
            <div className="mb-3 p-4 rounded-xl bg-[#232736] border border-[#2d3140] space-y-2">
              <input
                placeholder="股票代码"
                value={hdTicker}
                onChange={(e) => setHdTicker(e.target.value)}
                className="w-full p-2 rounded bg-[#1a1d28] border border-[#2d3140] text-[#e8eaed] text-sm"
              />
              <input
                placeholder="持股数量"
                type="number"
                value={hdShares}
                onChange={(e) => setHdShares(e.target.value)}
                className="w-full p-2 rounded bg-[#1a1d28] border border-[#2d3140] text-[#e8eaed] text-sm"
              />
              <input
                placeholder="平均成本（可选）"
                type="number"
                value={hdCost}
                onChange={(e) => setHdCost(e.target.value)}
                className="w-full p-2 rounded bg-[#1a1d28] border border-[#2d3140] text-[#e8eaed] text-sm"
              />
              <button
                onClick={handleCreateHolding}
                disabled={!hdTicker.trim() || !hdShares}
                className="px-3 py-1.5 rounded bg-[#34d399] text-black text-xs font-medium disabled:opacity-50"
              >
                添加
              </button>
            </div>
          )}

          {hdLoading ? (
            <div className="p-6 rounded-xl bg-[#1a1d28] border border-[#2d3140] text-center text-sm text-[#9aa0a6]">加载中...</div>
          ) : !holdings || holdings.length === 0 ? (
            <div className="p-6 rounded-xl bg-[#1a1d28] border border-[#2d3140] text-center text-sm text-[#9aa0a6]">暂无持仓</div>
          ) : (
            <div className="space-y-3">
              {holdings.map((h: any) => (
                <div key={h.id} className="p-4 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-lg text-[#e8eaed]">{h.ticker}</span>
                    <span className="text-sm text-[#9aa0a6]">{h.shares} 股</span>
                  </div>
                  {h.avg_cost_basis && (
                    <div className="text-sm text-[#9aa0a6] mt-1">成本: ¥{h.avg_cost_basis.toFixed(2)}</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Journal */}
      <div>
        <h2 className="text-lg font-semibold text-[#e8eaed] mb-3">研究日志</h2>
        <div className="p-6 rounded-xl bg-[#1a1d28] border border-[#2d3140] text-center text-sm text-[#9aa0a6]">
          日志将显示在此处。通过研究流程自动记录。
        </div>
      </div>
    {/* Journal */}
      <div>
        <h2 className="text-lg font-semibold text-[#e8eaed] mb-3">研究日志</h2>
        <div className="p-6 rounded-xl bg-[#1a1d28] border border-[#2d3140] text-center text-sm text-[#9aa0a6]">
          日志将显示在此处。通过研究流程自动记录。
        </div>
      </div>
    </div>
  );
}

function WatchlistCard({ wl, onMsg, onRefresh }: { wl: any; onMsg: (t: "success" | "error", s: string) => void; onRefresh: () => void }) {
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState(false);
  const [ticker, setTicker] = useState("");
  const [editName, setEditName] = useState(wl.name);
  const [editDesc, setEditDesc] = useState(wl.description || "");

  const handleAdd = async () => {
    if (!ticker.trim()) return;
    try {
      const resp = await fetch(`/api/portfolio/watchlists/${wl.id}/items`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker: ticker.toUpperCase() }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      setTicker("");
      setAdding(false);
      onRefresh();
      onMsg("success", `${ticker.toUpperCase()} 已添加到 "${wl.name}"`);
    } catch (e: any) {
      onMsg("error", e.message || "添加股票失败");
    }
  };

  const handleSaveEdit = async () => {
    if (!editName.trim()) return;
    try {
      const resp = await fetch(`/api/portfolio/watchlists/${wl.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: editName, description: editDesc || null }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      setEditing(false);
      onRefresh();
      onMsg("success", `列表已更新`);
    } catch (e: any) {
      onMsg("error", e.message || "更新失败");
    }
  };

  const handleDelete = async () => {
    if (!confirm(`确定删除自选列表 "${wl.name}"？`)) return;
    try {
      await fetch(`/api/portfolio/watchlists/${wl.id}`, { method: "DELETE" });
      onRefresh();
      onMsg("success", `自选列表 "${wl.name}" 已删除`);
    } catch (e: any) {
      onMsg("error", e.message || "删除失败");
    }
  };

  return (
    <div className="p-4 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
      <div className="flex items-center justify-between">
        {editing ? (
          <div className="flex-1 space-y-2">
            <input value={editName} onChange={(e) => setEditName(e.target.value)} className="w-full p-1.5 rounded bg-[#1a1d28] border border-[#2d3140] text-[#e8eaed] text-sm" />
            <input value={editDesc} onChange={(e) => setEditDesc(e.target.value)} placeholder="描述" className="w-full p-1.5 rounded bg-[#1a1d28] border border-[#2d3140] text-[#e8eaed] text-sm" />
            <div className="flex gap-2">
              <button onClick={handleSaveEdit} className="px-2 py-1 rounded bg-[#34d399] text-black text-xs font-medium">保存</button>
              <button onClick={() => setEditing(false)} className="px-2 py-1 rounded bg-[#2d3140] text-[#9aa0a6] text-xs">取消</button>
            </div>
          </div>
        ) : (
          <div className="flex-1">
            <div className="font-medium text-[#e8eaed]">{wl.name}</div>
            {wl.description && <div className="text-sm text-[#9aa0a6] mt-1">{wl.description}</div>}
          </div>
        )}
        {!editing && (
          <div className="flex gap-1 ml-2">
            <button onClick={() => { setEditName(wl.name); setEditDesc(wl.description || ""); setEditing(true); }} className="text-[#9aa0a6] hover:text-[#4f8cff] text-xs">编辑</button>
            <button onClick={handleDelete} className="text-[#9aa0a6] hover:text-[#f87171] text-xs">删除</button>
          </div>
        )}
      </div>
      {wl.items?.length > 0 && (
        <div className="flex gap-2 mt-2 flex-wrap">
          {wl.items.map((item: any) => (
            <span key={item.id} className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-[#232736] text-[#4f8cff] border border-[#2d3140]">
              {item.ticker}
              <button
                onClick={async () => {
                  try {
                    await fetch(`/api/portfolio/watchlists/items/${item.id}`, { method: "DELETE" });
                    onRefresh();
                    onMsg("success", `${item.ticker} 已从 "${wl.name}" 移除`);
                  } catch (e: any) {
                    onMsg("error", e.message || "删除失败");
                  }
                }}
                className="text-[#9aa0a6] hover:text-[#f87171] leading-none"
              >×</button>
            </span>
          ))}
        </div>
      )}
      {adding ? (
        <div className="mt-3 flex gap-2">
          <input
            placeholder="股票代码"
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAdd()}
            className="flex-1 p-1.5 rounded bg-[#1a1d28] border border-[#2d3140] text-[#e8eaed] text-xs"
          />
          <button onClick={handleAdd} className="px-2 py-1 rounded bg-[#34d399] text-black text-xs font-medium">确认</button>
          <button onClick={() => { setAdding(false); setTicker(""); }} className="px-2 py-1 rounded bg-[#2d3140] text-[#9aa0a6] text-xs">取消</button>
        </div>
      ) : (
        <button onClick={() => setAdding(true)} className="mt-2 text-xs text-[#4f8cff] hover:text-[#6ba3ff]">+ 添加股票</button>
      )}
    </div>
  );
}
