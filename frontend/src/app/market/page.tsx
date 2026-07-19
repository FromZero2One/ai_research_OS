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
        <h1 className="text-2xl font-bold text-[#e8eaed]">📊 Market Center</h1>
        <p className="text-[#9aa0a6] text-sm mt-1">Structured financial data — prices, financials, macros (not analysis)</p>
      </div>

      {/* Data Ingestion */}
      <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
        <h2 className="text-lg font-semibold text-[#e8eaed] mb-3">Data Ingestion</h2>
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="Enter ticker (e.g., AAPL)"
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            className="flex-1 p-2.5 rounded-lg bg-[#232736] border border-[#2d3140] text-[#e8eaed] placeholder-[#9aa0a6] focus:outline-none focus:border-[#4f8cff]"
          />
          <button
            onClick={handleIngest}
            disabled={!ticker.trim()}
            className="px-5 py-2.5 rounded-lg bg-[#4f8cff] text-white text-sm font-medium hover:bg-[#3a7bf5] disabled:opacity-50"
          >
            Ingest Prices
          </button>
        </div>
        <p className="text-xs text-[#9aa0a6] mt-2">Sources: Yahoo Finance (US) · AKShare (CN) — 1 year of daily data</p>
      </div>

      {/* Data Sources */}
      <div className="grid grid-cols-3 gap-4">
        <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
          <div className="text-2xl mb-2">💹</div>
          <div className="font-medium text-[#e8eaed]">Stock Prices</div>
          <div className="text-sm text-[#9aa0a6] mt-1">Daily OHLCV · Yahoo Finance / AKShare</div>
        </div>
        <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
          <div className="text-2xl mb-2">📋</div>
          <div className="font-medium text-[#e8eaed]">Financial Metrics</div>
          <div className="text-sm text-[#9aa0a6] mt-1">Revenue, EPS, margins, ratios</div>
        </div>
        <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
          <div className="text-2xl mb-2">🌍</div>
          <div className="font-medium text-[#e8eaed]">Macro Indicators</div>
          <div className="text-sm text-[#9aa0a6] mt-1">Interest rates, GDP, CPI</div>
        </div>
      </div>

      {/* API References */}
      <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140] text-sm">
        <h3 className="text-[#e8eaed] font-medium mb-2">API Endpoints</h3>
        <div className="space-y-1 text-[#9aa0a6] font-mono">
          <div>GET  /api/v1/market/prices/{`{ticker}`}</div>
          <div>POST /api/v1/market/prices/{`{ticker}`}/ingest</div>
          <div>GET  /api/v1/market/financials/{`{ticker}`}</div>
        </div>
      </div>
    </div>
  );
}
