"use client";

import { useState } from "react";
import { useMarketPrices, useFinancialMetrics } from "@/lib/api";
import StockChart from "@/components/StockChart";

const QUICK_TICKERS = ["NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "JPM", "BRK.B"];

export default function MarketPage() {
  const [ticker, setTicker] = useState("NVDA");
  const [limit, setLimit] = useState(120);
  const { data: priceData, isLoading } = useMarketPrices(ticker, limit);
  const { data: finData } = useFinancialMetrics(ticker);

  const prices = priceData?.prices || [];
  const financials = finData?.metrics || [];

  // Group financials by metric name
  const revenueData = financials.filter((m) => m.metric_name === "revenue").reverse();
  const incomeData = financials.filter((m) => m.metric_name === "net_income").reverse();
  const marginData = financials.filter((m) => m.metric_name === "operating_margin").reverse();

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-[#e8eaed]">📊 行情中心</h1>
        <p className="text-[#9aa0a6] text-sm mt-1">股票行情 · 财务指标 · 宏观数据</p>
      </div>

      {/* Ticker Selector */}
      <div className="flex flex-wrap gap-2 items-center">
        {QUICK_TICKERS.map((t) => (
          <button
            key={t}
            onClick={() => setTicker(t)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              ticker === t
                ? "bg-[#4f8cff]/10 text-[#4f8cff] border border-[#4f8cff]/30"
                : "bg-[#1a1d28] text-[#9aa0a6] border border-[#2d3140] hover:border-[#4f8cff]/30"
            }`}
          >
            {t}
          </button>
        ))}
        <input
          type="text"
          placeholder="自定义..."
          value={!QUICK_TICKERS.includes(ticker) ? ticker : ""}
          onKeyDown={(e) => {
            if (e.key === "Enter") setTicker((e.target as HTMLInputElement).value.toUpperCase());
          }}
          className="w-24 p-1.5 rounded-lg bg-[#1a1d28] border border-[#2d3140] text-[#e8eaed] text-sm placeholder-[#9aa0a6] focus:outline-none focus:border-[#4f8cff]"
        />
      </div>

      {/* Time Range */}
      <div className="flex gap-2">
        {[
          { label: "1月", days: 22 },
          { label: "3月", days: 66 },
          { label: "半年", days: 130 },
          { label: "1年", days: 260 },
          { label: "全部", days: 520 },
        ].map((r) => (
          <button
            key={r.label}
            onClick={() => setLimit(r.days)}
            className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
              limit === r.days
                ? "bg-[#232736] text-[#e8eaed] border border-[#2d3140]"
                : "text-[#9aa0a6] hover:text-[#e8eaed]"
            }`}
          >
            {r.label}
          </button>
        ))}
      </div>

      {/* Price Info */}
      {prices.length > 0 && (
        <div className="grid grid-cols-4 gap-3">
          {[
            { label: "最新收盘", value: prices[prices.length - 1].close, fmt: (v: number) => `$${v.toFixed(2)}` },
            { label: "最高", value: Math.max(...prices.map((p) => p.high)), fmt: (v: number) => `$${v.toFixed(2)}` },
            { label: "最低", value: Math.min(...prices.map((p) => p.low)), fmt: (v: number) => `$${v.toFixed(2)}` },
            { label: "均价", value: prices.reduce((s, p) => s + p.close, 0) / prices.length, fmt: (v: number) => `$${v.toFixed(2)}` },
          ].map((stat) => (
            <div key={stat.label} className="p-3 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
              <div className="text-xs text-[#9aa0a6]">{stat.label}</div>
              <div className="text-lg font-bold text-[#e8eaed] mt-0.5">{stat.fmt(stat.value)}</div>
            </div>
          ))}
        </div>
      )}

      {/* K-line Chart */}
      <div className="p-4 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
        <div className="text-sm text-[#9aa0a6] mb-3">{ticker} · K 线图</div>
        {isLoading ? (
          <div className="flex items-center justify-center h-64 text-[#9aa0a6]">加载中...</div>
        ) : (
          <StockChart prices={prices} height={420} />
        )}
      </div>

      {/* Financial Charts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {revenueData.length > 0 && (
          <FinancialChart data={revenueData} title="营收趋势" color="#4f8cff" />
        )}
        {incomeData.length > 0 && (
          <FinancialChart data={incomeData} title="净利润趋势" color="#34d399" />
        )}
        {marginData.length > 0 && (
          <FinancialChart data={marginData} title="运营利润率" color="#fbbf24" format="pct" />
        )}
      </div>
    </div>
  );
}

function FinancialChart({
  data,
  title,
  color,
  format = "num",
}: {
  data: { fiscal_year: number; fiscal_period: string; metric_value: number }[];
  title: string;
  color: string;
  format?: "num" | "pct";
}) {
  const labels = data.map((d) => `${d.fiscal_year} ${d.fiscal_period}`);
  const values = data.map((d) => d.metric_value);

  const formatVal = (v: number) => {
    if (format === "pct") return `${(v * 100).toFixed(1)}%`;
    if (v > 1e9) return `$${(v / 1e9).toFixed(1)}B`;
    if (v > 1e6) return `$${(v / 1e6).toFixed(1)}M`;
    return `$${v.toFixed(0)}`;
  };

  return (
    <div className="p-4 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
      <div className="text-sm text-[#9aa0a6] mb-3">{title}</div>
      <div className="space-y-1">
        {data.slice(-8).map((d, i) => (
          <div key={i} className="flex items-center gap-3 text-sm">
            <span className="text-[#9aa0a6] w-16 shrink-0">{d.fiscal_period}</span>
            <div className="flex-1 h-5 rounded bg-[#232736] overflow-hidden">
              <div
                className="h-full rounded transition-all"
                style={{
                  width: `${(d.metric_value / Math.max(...values)) * 100}%`,
                  backgroundColor: color,
                }}
              />
            </div>
            <span className="text-[#e8eaed] w-20 text-right font-mono text-xs">
              {formatVal(d.metric_value)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
