"use client";

import { useState } from "react";

export default function AICenterPage() {
  const [text, setText] = useState("");
  const [summary, setSummary] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSummarize = async () => {
    if (!text.trim()) return;
    setLoading(true);
    try {
      const resp = await fetch("/api/ai/summarize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, max_length: 300, format: "paragraph" }),
      });
      const data = await resp.json();
      setSummary(data.content);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[#e8eaed]">⚡ AI Center</h1>
        <p className="text-[#9aa0a6] text-sm mt-1">
          Prompt management · LLM orchestration · Summarization · Extraction
        </p>
      </div>

      {/* Capabilities Grid */}
      <div className="grid grid-cols-3 gap-4">
        <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
          <div className="text-2xl mb-2">📝</div>
          <div className="font-medium text-[#e8eaed]">Prompt Templates</div>
          <div className="text-sm text-[#9aa0a6] mt-1">Manage reusable system + user prompts with variable injection</div>
        </div>
        <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
          <div className="text-2xl mb-2">🔄</div>
          <div className="font-medium text-[#e8eaed]">Workflows</div>
          <div className="text-sm text-[#9aa0a6] mt-1">Multi-step LLM pipelines (sequential, later DAG via LangGraph)</div>
        </div>
        <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
          <div className="text-2xl mb-2">🔧</div>
          <div className="font-medium text-[#e8eaed]">Extraction</div>
          <div className="text-sm text-[#9aa0a6] mt-1">Structured data extraction with JSON schema validation</div>
        </div>
      </div>

      {/* Summarization Demo */}
      <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
        <h2 className="text-lg font-semibold text-[#e8eaed] mb-3">Summarization Demo</h2>
        <textarea
          placeholder="Paste text to summarize..."
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={5}
          className="w-full p-3 rounded-lg bg-[#232736] border border-[#2d3140] text-[#e8eaed] placeholder-[#9aa0a6] focus:outline-none focus:border-[#4f8cff]"
        />
        <button
          onClick={handleSummarize}
          disabled={loading || !text.trim()}
          className="mt-3 px-5 py-2.5 rounded-lg bg-[#4f8cff] text-white text-sm font-medium hover:bg-[#3a7bf5] disabled:opacity-50"
        >
          {loading ? "Summarizing..." : "Summarize"}
        </button>
        {summary && (
          <div className="mt-4 p-4 rounded-lg bg-[#232736] border border-[#2d3140]">
            <div className="text-xs text-[#9aa0a6] mb-2">Summary</div>
            <p className="text-[#e8eaed] text-sm leading-relaxed">{summary}</p>
          </div>
        )}
      </div>

      {/* Config */}
      <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140] text-sm">
        <h3 className="text-[#e8eaed] font-medium mb-2">Configuration</h3>
        <div className="space-y-1 text-[#9aa0a6]">
          <div>Provider: Ollama (llama3.1:70b) / OpenAI (gpt-4o)</div>
          <div>Set LLM_PROVIDER and API keys in .env</div>
        </div>
      </div>
    </div>
  );
}
