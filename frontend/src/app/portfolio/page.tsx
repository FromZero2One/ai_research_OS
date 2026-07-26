"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useWatchlists, useHoldings } from "@/lib/api";

export default function PortfolioPage() {
  const queryClient = useQueryClient();
  const { data: watchlists, isLoading: wlLoading } = useWatchlists();
  const refresh = () => queryClient.invalidateQueries({ queryKey: [] });
  const { data: holdings, isLoading: hdLoading } = useHoldings();

  const [showNewHD, setShowNewHD] = useState(false);
  const [hdTicker, setHdTicker] = useState("");
  const [hdShares, setHdShares] = useState("");
  const [hdCost, setHdCost] = useState("");

  const [msg, setMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const showMsg = (type: "success" | "error", text: string) => {
    setMsg({ type, text });
    setTimeout(() => setMsg(null), 4000);
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

  // Find the first watchlist that has items (or the first one overall)
  const activeWL = Array.isArray(watchlists) ? watchlists.find((w: any) => w.items?.length > 0) || watchlists[0] : null;

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-[#e8eaed]">💼 投资组合</h1>
        <p className="text-[#9aa0a6] text-sm mt-1">自选列表 · 持仓</p>
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
        {/* ── Watchlist ── */}
        <div>
          <h2 className="text-lg font-semibold text-[#e8eaed] mb-3">自选列表</h2>
          {wlLoading ? (
            <div className="p-6 rounded-xl bg-[#1a1d28] border border-[#2d3140] text-center text-sm text-[#9aa0a6]">加载中...</div>
          ) : activeWL ? (
            <WatchlistCard key={activeWL.id} wl={activeWL} onMsg={showMsg} onRefresh={refresh} />
          ) : (
            <div className="p-6 rounded-xl bg-[#1a1d28] border border-[#2d3140] text-center text-sm text-[#9aa0a6]">暂无自选列表</div>
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
              <input placeholder="股票代码" value={hdTicker} onChange={(e) => setHdTicker(e.target.value)} className="w-full p-2 rounded bg-[#1a1d28] border border-[#2d3140] text-[#e8eaed] text-sm" />
              <input placeholder="持股数量" type="number" value={hdShares} onChange={(e) => setHdShares(e.target.value)} className="w-full p-2 rounded bg-[#1a1d28] border border-[#2d3140] text-[#e8eaed] text-sm" />
              <input placeholder="平均成本（可选）" type="number" value={hdCost} onChange={(e) => setHdCost(e.target.value)} className="w-full p-2 rounded bg-[#1a1d28] border border-[#2d3140] text-[#e8eaed] text-sm" />
              <button onClick={handleCreateHolding} disabled={!hdTicker.trim() || !hdShares} className="px-3 py-1.5 rounded bg-[#34d399] text-black text-xs font-medium disabled:opacity-50">添加</button>
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
    </div>
  );
}

function WatchlistCard({ wl, onMsg, onRefresh }: { wl: any; onMsg: (t: "success" | "error", s: string) => void; onRefresh: () => void }) {
  const [adding, setAdding] = useState(false);
  const [ticker, setTicker] = useState("");

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
      onMsg("success", `${ticker.toUpperCase()} 已添加`);
    } catch (e: any) {
      onMsg("error", e.message || "添加股票失败");
    }
  };

  const handleRemove = async (itemId: string, ticker: string) => {
    try {
      const resp = await fetch(`/api/portfolio/watchlists/items/${itemId}`, { method: "DELETE" });
      if (!resp.ok) throw new Error(await resp.text());
      onRefresh();
      onMsg("success", `${ticker} 已移除`);
    } catch (e: any) {
      onMsg("error", e.message || "移除失败");
    }
  };

  return (
    <div className="p-4 rounded-xl bg-[#1a1d28] border border-[#2d3140] space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs text-[#9aa0a6]">{wl.items?.length || 0} 只关注股票</span>
        <button onClick={() => setAdding(!adding)}
          className="px-2 py-1 rounded text-xs bg-[#4f8cff] text-white hover:bg-[#3a7bf5]">
          + 添加股票
        </button>
      </div>

      {adding && (
        <div className="flex gap-2">
          <input
            placeholder="输入股票代码"
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            onKeyDown={(e) => { if (e.key === "Enter") handleAdd(); }}
            className="flex-1 p-2 rounded bg-[#232736] border border-[#2d3140] text-[#e8eaed] text-sm placeholder-[#6b7280]"
          />
          <button onClick={handleAdd} disabled={!ticker.trim()}
            className="px-3 py-1 rounded bg-[#34d399] text-black text-xs font-medium disabled:opacity-50">
            添加
          </button>
        </div>
      )}

      {wl.items?.length > 0 ? (
        <div className="space-y-1.5">
          {wl.items.map((item: any) => (
            <div key={item.id} className="flex items-center justify-between p-2 rounded bg-[#232736] group">
              <span className="text-sm text-[#e8eaed] font-mono">{item.ticker}</span>
              <button onClick={() => handleRemove(item.id, item.ticker)}
                className="text-xs text-[#f87171] opacity-0 group-hover:opacity-100 transition-opacity">
                ✕ 移除
              </button>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-sm text-[#9aa0a6] text-center py-2">点击「添加股票」开始关注</div>
      )}
    </div>
  );
}
