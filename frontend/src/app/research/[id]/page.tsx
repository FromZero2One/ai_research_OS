"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useResearchSession } from "@/lib/api";

export default function ResearchDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data: session, isLoading } = useResearchSession(id);

  if (isLoading) return <div className="text-[#9aa0a6] py-12 text-center">Loading...</div>;
  if (!session) return <div className="text-[#f87171] py-12 text-center">Session not found</div>;

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <Link href="/research" className="text-sm text-[#4f8cff] hover:underline">← Research</Link>
        <h1 className="text-2xl font-bold text-[#e8eaed] mt-2">{session.title}</h1>
        <div className="flex items-center gap-3 mt-2">
          <span className={`px-2 py-0.5 rounded text-xs font-medium ${
            session.status === "completed" ? "bg-[#34d399]/10 text-[#34d399]" :
            session.status === "researching" ? "bg-[#fbbf24]/10 text-[#fbbf24]" :
            "bg-[#9aa0a6]/10 text-[#9aa0a6]"
          }`}>
            {session.status}
          </span>
          {session.decision && (
            <span className={`px-2 py-0.5 rounded text-xs font-medium ${
              session.decision === "buy" ? "bg-[#34d399]/10 text-[#34d399]" :
              session.decision === "sell" ? "bg-[#f87171]/10 text-[#f87171]" :
              "bg-[#fbbf24]/10 text-[#fbbf24]"
            }`}>
              {session.decision.toUpperCase()}
            </span>
          )}
          {session.confidence && (
            <span className="text-sm text-[#9aa0a6]">Confidence: {Math.round(session.confidence * 100)}%</span>
          )}
        </div>
      </div>

      {/* Question */}
      <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
        <div className="text-sm text-[#9aa0a6] mb-2">Research Question</div>
        <p className="text-[#e8eaed] text-lg leading-relaxed">{session.question}</p>
      </div>

      {/* Context */}
      {session.context && (
        <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
          <div className="text-sm text-[#9aa0a6] mb-2">Context</div>
          <p className="text-[#e8eaed] leading-relaxed">{session.context}</p>
        </div>
      )}

      {/* Evidences */}
      <div>
        <h2 className="text-lg font-semibold text-[#e8eaed] mb-3">Evidence ({session.evidences?.length || 0})</h2>
        {session.evidences?.length === 0 ? (
          <div className="p-4 rounded-xl bg-[#1a1d28] border border-[#2d3140] text-sm text-[#9aa0a6]">
            No evidence collected yet.
          </div>
        ) : (
          <div className="space-y-3">
            {session.evidences?.map((ev: any) => (
              <div key={ev.id} className="p-4 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
                <div className="flex items-center gap-2 mb-2">
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                    ev.evidence_type === "supporting" ? "bg-[#34d399]/10 text-[#34d399]" :
                    ev.evidence_type === "opposing" ? "bg-[#f87171]/10 text-[#f87171]" :
                    "bg-[#9aa0a6]/10 text-[#9aa0a6]"
                  }`}>
                    {ev.evidence_type}
                  </span>
                  <span className="text-xs text-[#9aa0a6]">{ev.source_type}</span>
                  {ev.relevance_score && (
                    <span className="text-xs text-[#9aa0a6]">Score: {ev.relevance_score.toFixed(2)}</span>
                  )}
                </div>
                <p className="text-sm text-[#e8eaed] line-clamp-3">{ev.content}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Thesis */}
      {session.thesis && (
        <div className="p-5 rounded-xl bg-[#1a1d28] border-l-4 border-[#4f8cff]">
          <div className="text-sm text-[#9aa0a6] mb-2">Investment Thesis</div>
          <p className="text-[#e8eaed] leading-relaxed">{session.thesis}</p>
        </div>
      )}

      {/* Reports */}
      {session.reports?.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold text-[#e8eaed] mb-3">Reports</h2>
          <div className="space-y-2">
            {session.reports.map((r: any) => (
              <div key={r.id} className="p-4 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
                <div className="font-medium text-[#e8eaed]">{r.title}</div>
                <div className="text-xs text-[#9aa0a6] mt-1">v{r.version} · {r.format}{r.is_final && " · Final"}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
