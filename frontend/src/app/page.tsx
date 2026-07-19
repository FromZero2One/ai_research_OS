"use client";

import Link from "next/link";
import { useResearchSessions } from "@/lib/api";

const QUICK_ACTIONS = [
  { label: "New Research", href: "/research", icon: "🔬", desc: "Start a new investment research session" },
  { label: "Upload Document", href: "/documents", icon: "📄", desc: "Add PDF, report, or transcript" },
  { label: "Search Knowledge", href: "/knowledge", icon: "🧠", desc: "Hybrid RAG search across all documents" },
  { label: "View Portfolio", href: "/portfolio", icon: "💼", desc: "Watchlists, holdings & journal" },
];

export default function HomePage() {
  const { data: sessions } = useResearchSessions();

  return (
    <div className="max-w-6xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-[#e8eaed]">Research Workspace</h1>
        <p className="text-[#9aa0a6] mt-1">
          Company → Knowledge → AI → Research → Portfolio
        </p>
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-4 gap-4">
        {QUICK_ACTIONS.map((action) => (
          <Link
            key={action.label}
            href={action.href}
            className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140] hover:border-[#4f8cff]/40 transition-all group"
          >
            <div className="text-2xl mb-2">{action.icon}</div>
            <div className="font-medium text-[#e8eaed] group-hover:text-[#4f8cff] transition-colors">
              {action.label}
            </div>
            <div className="text-sm text-[#9aa0a6] mt-1">{action.desc}</div>
          </Link>
        ))}
      </div>

      {/* Recent Research */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-[#e8eaed]">Recent Research</h2>
          <Link href="/research" className="text-sm text-[#4f8cff] hover:underline">
            View all →
          </Link>
        </div>

        <div className="space-y-2">
          {!sessions || sessions.length === 0 ? (
            <div className="p-8 rounded-xl bg-[#1a1d28] border border-[#2d3140] text-center text-[#9aa0a6]">
              No research sessions yet. Start your first one!
            </div>
          ) : (
            sessions.slice(0, 5).map((session) => (
              <Link
                key={session.id}
                href={`/research/${session.id}`}
                className="block p-4 rounded-xl bg-[#1a1d28] border border-[#2d3140] hover:border-[#4f8cff]/30 transition-colors"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-medium text-[#e8eaed]">{session.title}</div>
                    <div className="text-sm text-[#9aa0a6] mt-1 line-clamp-1">{session.question}</div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={`px-2 py-1 rounded text-xs font-medium ${
                      session.status === "completed" ? "bg-[#34d399]/10 text-[#34d399]" :
                      session.status === "researching" ? "bg-[#fbbf24]/10 text-[#fbbf24]" :
                      "bg-[#9aa0a6]/10 text-[#9aa0a6]"
                    }`}>
                      {session.status}
                    </span>
                  </div>
                </div>
              </Link>
            ))
          )}
        </div>
      </div>

      {/* System status */}
      <div className="p-4 rounded-xl bg-[#1a1d28] border border-[#2d3140] flex items-center justify-between text-sm">
        <span className="text-[#9aa0a6]">System Status</span>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-[#34d399]"></span>
          <span className="text-[#e8eaed]">All systems operational</span>
        </div>
      </div>
    </div>
  );
}
