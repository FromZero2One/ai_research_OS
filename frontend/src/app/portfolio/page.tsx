"use client";

import { useWatchlists, useHoldings } from "@/lib/api";

export default function PortfolioPage() {
  const { data: watchlists } = useWatchlists();
  const { data: holdings } = useHoldings();

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[#e8eaed]">💼 Portfolio Center</h1>
        <p className="text-[#9aa0a6] text-sm mt-1">Watchlists · Holdings · Research Journal</p>
      </div>

      <div className="grid grid-cols-2 gap-6">
        {/* Watchlists */}
        <div>
          <h2 className="text-lg font-semibold text-[#e8eaed] mb-3">Watchlists</h2>
          {!watchlists || watchlists.length === 0 ? (
            <div className="p-6 rounded-xl bg-[#1a1d28] border border-[#2d3140] text-center text-sm text-[#9aa0a6]">
              No watchlists yet. Create one via the API.
            </div>
          ) : (
            <div className="space-y-3">
              {watchlists.map((wl: any) => (
                <div key={wl.id} className="p-4 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
                  <div className="font-medium text-[#e8eaed]">{wl.name}</div>
                  {wl.description && (
                    <div className="text-sm text-[#9aa0a6] mt-1">{wl.description}</div>
                  )}
                  {wl.items && wl.items.length > 0 && (
                    <div className="flex gap-2 mt-2 flex-wrap">
                      {wl.items.map((item: any) => (
                        <span key={item.id} className="px-2 py-0.5 rounded text-xs bg-[#232736] text-[#4f8cff] border border-[#2d3140]">
                          {item.ticker}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Holdings */}
        <div>
          <h2 className="text-lg font-semibold text-[#e8eaed] mb-3">Holdings</h2>
          {!holdings || holdings.length === 0 ? (
            <div className="p-6 rounded-xl bg-[#1a1d28] border border-[#2d3140] text-center text-sm text-[#9aa0a6]">
              No holdings yet.
            </div>
          ) : (
            <div className="space-y-3">
              {holdings.map((h: any) => (
                <div key={h.id} className="p-4 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-lg text-[#e8eaed]">{h.ticker}</span>
                    <span className="text-sm text-[#9aa0a6]">{h.shares} shares</span>
                  </div>
                  {h.avg_cost_basis && (
                    <div className="text-sm text-[#9aa0a6] mt-1">
                      Avg Cost: ${h.avg_cost_basis.toFixed(2)}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Journal */}
      <div>
        <h2 className="text-lg font-semibold text-[#e8eaed] mb-3">Investment Journal</h2>
        <div className="p-6 rounded-xl bg-[#1a1d28] border border-[#2d3140] text-center text-sm text-[#9aa0a6]">
          Journal entries will appear here. POST /api/v1/portfolio/journal to create entries.
        </div>
      </div>

      {/* API Reference */}
      <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140] text-sm">
        <h3 className="text-[#e8eaed] font-medium mb-2">API Endpoints</h3>
        <div className="space-y-1 text-[#9aa0a6] font-mono">
          <div>GET/POST  /api/v1/portfolio/watchlists</div>
          <div>GET/POST  /api/v1/portfolio/holdings</div>
          <div>GET/POST  /api/v1/portfolio/journal</div>
        </div>
      </div>
    </div>
  );
}
