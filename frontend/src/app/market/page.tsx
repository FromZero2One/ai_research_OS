"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useMarketPrices, useFinancialMetrics, useStockSearch } from "@/lib/api";
import StockChart from "@/components/StockChart";

const STORAGE_KEY = "market_quick_tickers";
const DEFAULT_TICKERS = ["000002", "600519", "1810", "300750", "NVDA", "TSLA"];

function loadTickers(): string[] {
  if (typeof window === "undefined") return DEFAULT_TICKERS;
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      const parsed = JSON.parse(saved);
      if (Array.isArray(parsed) && parsed.length > 0) return parsed;
    }
  } catch {}
  return DEFAULT_TICKERS;
}

function saveTickers(tickers: string[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(tickers));
  } catch {}
}

export default function MarketPage() {
  const [ticker, setTicker] = useState("000002");
  const [limit, setLimit] = useState(120);
  const [quickTickers, setQuickTickers] = useState<string[]>([]);
  const [editing, setEditing] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [showDropdown, setShowDropdown] = useState(false);
  const [tickerNames, setTickerNames] = useState<Record<string, string>>({});
  const [highlightIdx, setHighlightIdx] = useState(-1);
  const searchRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();
  const { data: priceData, isLoading } = useMarketPrices(ticker, limit);
  const { data: finData } = useFinancialMetrics(ticker);
  const { data: searchData } = useStockSearch(debouncedSearch);

  // Debounce search query (300ms)
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setDebouncedSearch(searchQuery);
    }, 300);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [searchQuery]);

  // Reset highlight when search results change
  useEffect(() => { setHighlightIdx(-1); }, [searchData]);

  // Load quick tickers on mount
  useEffect(() => {
    setQuickTickers(loadTickers());
  }, []);

  // When quick tickers load, pick first valid one
  useEffect(() => {
    if (quickTickers.length > 0 && !quickTickers.includes(ticker)) {
      setTicker(quickTickers[0]);
    }
  }, [quickTickers, ticker]);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  // Look up name when ticker changes
  useEffect(() => {
    if (!ticker || tickerNames[ticker]) return;
    // Search by exact ticker to get name
    fetch(`/api/v1/market/search?query=${encodeURIComponent(ticker)}&limit=5`)
      .then((r) => r.json())
      .then((d) => {
        const match = d.results?.find(
          (r: any) => r.symbol.toUpperCase() === ticker.toUpperCase()
        );
        if (match?.name) {
          setTickerNames((prev) => ({ ...prev, [ticker]: match.name }));
        }
      })
      .catch(() => {});
  }, [ticker, tickerNames]);

  function handleRemove(t: string) {
    const next = quickTickers.filter((x) => x !== t);
    setQuickTickers(next);
    saveTickers(next);
    if (ticker === t && next.length > 0) setTicker(next[0]);
  }

  function handleSelect(symbol: string, name?: string) {
    setTicker(symbol);
    setShowDropdown(false);
    setSearchQuery("");
    setDebouncedSearch("");
    if (name) setTickerNames((prev) => ({ ...prev, [symbol]: name }));
    if (!quickTickers.includes(symbol)) {
      const next = [...quickTickers, symbol];
      setQuickTickers(next);
      saveTickers(next);
    }
  }

  function handleReset() {
    setQuickTickers(DEFAULT_TICKERS);
    saveTickers(DEFAULT_TICKERS);
    setEditing(false);
  }

  const prices = priceData?.prices || [];
  const financials = finData?.metrics || [];
  const searchResults = searchData?.results || [];

  const activeName = tickerNames[ticker];
  const latestPrice = prices.length > 0 ? prices[prices.length - 1].close : null;
  const prevClose = prices.length > 1 ? prices[prices.length - 2].close : null;
  const change = latestPrice != null && prevClose != null ? latestPrice - prevClose : null;
  const changePct = change != null && prevClose != null ? (change / prevClose) * 100 : null;

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

      {/* Search + Quick Tickers */}
      <div className="space-y-3">
        {/* Search combobox */}
        <div ref={searchRef} className="relative">
          <input
            type="text"
            placeholder="搜索股票代码或名称..."
            value={searchQuery}
            onChange={(e) => { setSearchQuery(e.target.value); setShowDropdown(true); }}
            onFocus={() => setShowDropdown(true)}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setHighlightIdx((i) => Math.min(i + 1, searchResults.length - 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setHighlightIdx((i) => Math.max(i - 1, 0));
              } else if (e.key === "Enter" && searchResults.length > 0) {
                const idx = highlightIdx >= 0 ? highlightIdx : 0;
                const r = searchResults[idx];
                handleSelect(r.symbol, r.name);
              } else if (e.key === "Escape") {
                setShowDropdown(false);
              }
            }}
            className="w-full p-2.5 rounded-lg bg-[#1a1d28] border border-[#2d3140] text-[#e8eaed] text-sm placeholder-[#9aa0a6] focus:outline-none focus:border-[#4f8cff]"
          />
          {showDropdown && debouncedSearch && (
            <div className="absolute z-10 mt-1 w-full rounded-lg bg-[#1a1d28] border border-[#2d3140] shadow-xl max-h-64 overflow-y-auto">
              {searchResults.length === 0 ? (
                <div className="p-3 text-sm text-[#9aa0a6]">无匹配结果</div>
              ) : (
                searchResults.map((r, i) => (
                  <button
                    key={r.symbol}
                    onClick={() => handleSelect(r.symbol, r.name)}
                    onMouseEnter={() => setHighlightIdx(i)}
                    className={`w-full flex items-center gap-3 px-3 py-2.5 text-sm text-left transition-colors ${
                      i === highlightIdx ? "bg-[#232736]" : "hover:bg-[#232736]"
                    }`}
                  >
                    <span className="font-mono text-[#4f8cff]">{r.symbol}</span>
                    {r.name && <span className="text-[#e8eaed]">{r.name}</span>}
                  </button>
                ))
              )}
            </div>
          )}
        </div>

        {/* Quick ticker row */}
        <div className="flex flex-wrap gap-2 items-center">
          {quickTickers.map((t) => (
            <div key={t} className="relative group">
              <button
                onClick={() => !editing && setTicker(t)}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  ticker === t && !editing
                    ? "bg-[#4f8cff]/10 text-[#4f8cff] border border-[#4f8cff]/30"
                    : editing
                    ? "bg-[#2d1b1b] text-[#f87171] border border-[#f87171]/30"
                    : "bg-[#1a1d28] text-[#9aa0a6] border border-[#2d3140] hover:border-[#4f8cff]/30"
                }`}
              >
                {t}
              </button>
              {editing && (
                <button
                  onClick={() => handleRemove(t)}
                  className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-[#f87171] text-white text-[10px] leading-none flex items-center justify-center hover:bg-red-500 transition-colors"
                >
                  ×
                </button>
              )}
            </div>
          ))}
          <button
            onClick={() => { setEditing(!editing); }}
            className={`px-2 py-1.5 rounded-lg text-xs transition-colors ${
              editing
                ? "bg-[#4f8cff]/20 text-[#4f8cff] border border-[#4f8cff]/30"
                : "bg-[#1a1d28] text-[#9aa0a6] border border-[#2d3140] hover:border-[#4f8cff]/30"
            }`}
          >
            {editing ? "✓ 完成" : "✎ 编辑"}
          </button>
          {editing && (
            <button onClick={handleReset} className="px-2 py-1.5 rounded-lg text-[#9aa0a6] border border-[#2d3140] text-xs hover:text-[#e8eaed]">
              ↺ 重置
            </button>
          )}
        </div>
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

      {/* Price Info + Name */}
      {prices.length > 0 && (
        <div className="space-y-3">
          {/* Stock identity header */}
          <div className="flex items-baseline gap-3">
            <h2 className="text-xl font-bold text-[#e8eaed]">
              {activeName || ticker}
              {activeName && <span className="text-[#9aa0a6] text-base font-normal ml-2">{ticker}</span>}
            </h2>
            {change != null && (
              <span className={`text-lg font-semibold ${change >= 0 ? "text-[#34d399]" : "text-[#f87171]"}`}>
                {change >= 0 ? "+" : ""}{change.toFixed(2)} ({changePct?.toFixed(2)}%)
              </span>
            )}
          </div>
          <div className="grid grid-cols-4 gap-3">
            {[
              { label: "最新收盘", value: latestPrice, fmt: (v: number) => v.toFixed(2) },
              { label: "最高", value: Math.max(...prices.map((p) => p.high)), fmt: (v: number) => v.toFixed(2) },
              { label: "最低", value: Math.min(...prices.map((p) => p.low)), fmt: (v: number) => v.toFixed(2) },
              { label: "均价", value: prices.reduce((s, p) => s + p.close, 0) / prices.length, fmt: (v: number) => v.toFixed(2) },
            ].map((stat) => (
              <div key={stat.label} className="p-3 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
                <div className="text-xs text-[#9aa0a6]">{stat.label}</div>
                <div className="text-lg font-bold text-[#e8eaed] mt-0.5">{stat.value != null ? stat.fmt(stat.value) : "—"}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* K-line Chart */}
      <div className="p-4 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
        <div className="text-sm text-[#9aa0a6] mb-3">{ticker} · K 线图</div>
        {isLoading ? (
          <div className="flex items-center justify-center h-64 text-[#9aa0a6]">加载中...</div>
        ) : prices.length === 0 ? (
          <div className="flex items-center justify-center h-64 text-[#9aa0a6]">
            暂无数据 — 请尝试点公司页的「↻ 刷新」拉取行情
          </div>
        ) : (
          <StockChart prices={prices} height={420} showVolume={true} />
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
