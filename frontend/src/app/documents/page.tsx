"use client";

import { useState } from "react";
import { useDocuments } from "@/lib/api";

const DOC_TYPES = ["all", "pdf", "markdown", "text", "report", "transcript"];

export default function DocumentsPage() {
  const [docType, setDocType] = useState("all");
  const { data, isLoading } = useDocuments(docType === "all" ? undefined : docType);

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[#e8eaed]">📄 Document Center</h1>
        <p className="text-[#9aa0a6] text-sm mt-1">
          Ingest → Parse → Chunk → Embed → Index — the entire knowledge pipeline
        </p>
      </div>

      {/* Upload zone placeholder */}
      <div className="p-8 rounded-xl bg-[#1a1d28] border-2 border-dashed border-[#2d3140] text-center hover:border-[#4f8cff]/30 transition-colors cursor-pointer">
        <div className="text-3xl mb-2">📤</div>
        <div className="text-[#e8eaed] font-medium">Upload Document</div>
        <div className="text-sm text-[#9aa0a6] mt-1">PDF, Markdown, TXT, HTML — max 50MB</div>
        <p className="text-xs text-[#9aa0a6] mt-2">API: POST /api/v1/documents/upload</p>
      </div>

      {/* Type Filter */}
      <div className="flex gap-2">
        {DOC_TYPES.map((t) => (
          <button
            key={t}
            onClick={() => setDocType(t)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              docType === t
                ? "bg-[#4f8cff]/10 text-[#4f8cff] border border-[#4f8cff]/30"
                : "text-[#9aa0a6] hover:text-[#e8eaed] border border-transparent"
            }`}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {/* Documents List */}
      {isLoading ? (
        <div className="text-center text-[#9aa0a6] py-12">Loading...</div>
      ) : !data || data.items.length === 0 ? (
        <div className="p-12 rounded-xl bg-[#1a1d28] border border-[#2d3140] text-center">
          <div className="text-3xl mb-3">📄</div>
          <div className="text-[#e8eaed] font-medium">No documents yet</div>
          <div className="text-[#9aa0a6] text-sm mt-1">Upload your first PDF or research report</div>
        </div>
      ) : (
        <div className="space-y-2">
          {data.items.map((doc) => (
            <div
              key={doc.id}
              className="p-4 rounded-xl bg-[#1a1d28] border border-[#2d3140] flex items-center justify-between"
            >
              <div className="flex-1">
                <div className="font-medium text-[#e8eaed]">{doc.title}</div>
                <div className="text-xs text-[#9aa0a6] mt-1">
                  {doc.doc_type} · {doc.chunk_count || 0} chunks · {doc.source}
                </div>
              </div>
              <span className={`px-2 py-1 rounded text-xs font-medium ${
                doc.is_indexed
                  ? "bg-[#34d399]/10 text-[#34d399]"
                  : "bg-[#fbbf24]/10 text-[#fbbf24]"
              }`}>
                {doc.is_indexed ? "Indexed" : "Pending"}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
