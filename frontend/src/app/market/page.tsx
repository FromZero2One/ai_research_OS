"use client";

import { useState } from "react";

export default function MarketPage() {
  const [ticker, setTicker] = useState("");

  const handleIngest = async () => {
    if (!ticker.trim()) return;
    await fetch("/api/market/prices/" + ticker.toUpperCase() + "/ingest?provider=yfinance", {
      method: "POST",
    });
    alert(`Ingested prices for ${ticker.toUpperCase()}`);
  };

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[#e8eaed]">📊 行情中心</h1>
        <p className="text-[#9aa0a6] text-sm mt-1">结构化金融数据 — 行情、财务指标、宏观数据（非分析）</p>
      </div>

      {/* Data Ingestion */}
      <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
        <h2 className="text-lg font-semibold text-[#e8eaed] mb-3">数据采集</h2>
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="输入股票代码 (如 600519)"
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            className="flex-1 p-2.5 rounded-lg bg-[#232736] border border-[#2d3140] text-[#e8eaed] placeholder-[#9aa0a6] focus:outline-none focus:border-[#4f8cff]"
          />
          <button
            onClick={handleIngest}
            disabled={!ticker.trim()}
            className="px-5 py-2.5 rounded-lg bg-[#4f8cff] text-white text-sm font-medium hover:bg-[#3a7bf5] disabled:opacity-50"
          >
            采集数据
          </button>
        </div>
        <p className="text-xs text-[#9aa0a6] mt-2">数据源: MySQL (A股) · Yahoo Finance (美股) — 日线数据</p>
      </div>

      {/* Data Sources */}
      <div className="grid grid-cols-3 gap-4">
        <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
          <div className="text-2xl mb-2">💹</div>
          <div className="font-medium text-[#e8eaed]">股票行情</div>
          <div className="text-sm text-[#9aa0a6] mt-1">日线 OHLCV · MySQL 腾讯数据源 / Yahoo Finance</div>
        </div>
        <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
          <div className="text-2xl mb-2">📋</div>
          <div className="font-medium text-[#e8eaed]">财务指标</div>
          <div className="text-sm text-[#9aa0a6] mt-1">营收、EPS、利润率、ROE 等</div>
        </div>
        <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
          <div className="text-2xl mb-2">🌍</div>
          <div className="font-medium text-[#e8eaed]">宏观指标</div>
          <div className="text-sm text-[#9aa0a6] mt-1">利率、GDP、CPI 等</div>
        </div>
      </div>

      {/* API References */}
      <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140] text-sm">
        <h3 className="text-[#e8eaed] font-medium mb-2">API 接口</h3>
        <div className="space-y-1 text-[#9aa0a6] font-mono">
          <div>GET  /api/v1/market/prices/{`{ticker}`}</div>
          <div>POST /api/v1/market/prices/{`{ticker}`}/ingest</div>
          <div>GET  /api/v1/market/financials/{`{ticker}`}</div>
        </div>
      </div>
    </div>
  );
}
