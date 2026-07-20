"use client";

import { useState, useEffect } from "react";

interface PromptTemplate {
  id: string;
  name: string;
  description: string | null;
  system_prompt: string | null;
  user_prompt_template: string | null;
  temperature: number | null;
  max_tokens: number | null;
  is_active: boolean;
}

export default function AICenterPage() {
  const [text, setText] = useState("");
  const [summary, setSummary] = useState("");
  const [loading, setLoading] = useState(false);
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [showNew, setShowNew] = useState(false);
  const [newTmpl, setNewTmpl] = useState({ name: "", description: "", system_prompt: "", user_prompt_template: "" });

  useEffect(() => {
    fetch("/api/ai/templates")
      .then((r) => r.json())
      .then(setTemplates)
      .catch(() => {});
  }, []);

  const handleSummarize = async () => {
    if (!text.trim()) return;
    setLoading(true);
    try {
      const resp = await fetch("/api/ai/summarize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, max_length: 300, format_: "paragraph" }),
      });
      const data = await resp.json();
      setSummary(data.content || data.error || "No response");
    } catch (e: any) {
      setSummary("Error: " + e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateTemplate = async () => {
    if (!newTmpl.name.trim()) return;
    try {
      const resp = await fetch("/api/ai/templates", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newTmpl),
      });
      if (resp.ok) {
        const created = await resp.json();
        setTemplates((prev) => [...prev, created]);
        setShowNew(false);
        setNewTmpl({ name: "", description: "", system_prompt: "", user_prompt_template: "" });
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleDeleteTemplate = async (id: string) => {
    try {
      await fetch(`/api/ai/templates/${id}`, { method: "DELETE" });
      setTemplates((prev) => prev.filter((t) => t.id !== id));
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-[#e8eaed]">⚡ AI 中心</h1>
        <p className="text-[#9aa0a6] text-sm mt-1">
          Prompt 管理 · LLM 编排 · 文本摘要 · 结构化提取
        </p>
      </div>

      {/* Capabilities Grid */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { icon: "📝", title: "Prompt 模板", desc: "管理可复用的 System + User Prompt，支持变量注入" },
          { icon: "🔄", title: "工作流", desc: "多步骤 LLM 管道（顺序执行，后续支持 LangGraph 有向图）" },
          { icon: "🔧", title: "结构提取", desc: "基于 JSON Schema 验证的结构化数据提取" },
        ].map((c) => (
          <div key={c.title} className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
            <div className="text-2xl mb-2">{c.icon}</div>
            <div className="font-medium text-[#e8eaed]">{c.title}</div>
            <div className="text-sm text-[#9aa0a6] mt-1">{c.desc}</div>
          </div>
        ))}
      </div>

      {/* ── Prompt Templates ── */}
      <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-[#e8eaed]">📝 Prompt 模板</h2>
          <button
            onClick={() => setShowNew(!showNew)}
            className="px-3 py-1.5 rounded-lg bg-[#4f8cff] text-white text-xs font-medium hover:bg-[#3a7bf5]"
          >
            + 新建
          </button>
        </div>

        {showNew && (
          <div className="mb-4 p-4 rounded-lg bg-[#232736] border border-[#2d3140] space-y-2">
            <input
              placeholder="模板名称"
              value={newTmpl.name}
              onChange={(e) => setNewTmpl({ ...newTmpl, name: e.target.value })}
              className="w-full p-2 rounded bg-[#1a1d28] border border-[#2d3140] text-[#e8eaed] text-sm"
            />
            <input
              placeholder="描述（可选）"
              value={newTmpl.description}
              onChange={(e) => setNewTmpl({ ...newTmpl, description: e.target.value })}
              className="w-full p-2 rounded bg-[#1a1d28] border border-[#2d3140] text-[#e8eaed] text-sm"
            />
            <textarea
              placeholder="System Prompt"
              value={newTmpl.system_prompt}
              onChange={(e) => setNewTmpl({ ...newTmpl, system_prompt: e.target.value })}
              rows={2}
              className="w-full p-2 rounded bg-[#1a1d28] border border-[#2d3140] text-[#e8eaed] text-sm"
            />
            <textarea
              placeholder="User Prompt 模板 (支持 {variable})"
              value={newTmpl.user_prompt_template}
              onChange={(e) => setNewTmpl({ ...newTmpl, user_prompt_template: e.target.value })}
              rows={2}
              className="w-full p-2 rounded bg-[#1a1d28] border border-[#2d3140] text-[#e8eaed] text-sm"
            />
            <button
              onClick={handleCreateTemplate}
              disabled={!newTmpl.name.trim()}
              className="px-3 py-1.5 rounded bg-[#34d399] text-black text-xs font-medium disabled:opacity-50"
            >
              保存
            </button>
          </div>
        )}

        {templates.length === 0 ? (
          <div className="text-sm text-[#9aa0a6]">暂无模板，点击"新建"创建</div>
        ) : (
          <div className="space-y-2">
            {templates.map((t) => (
              <div key={t.id} className="flex items-center justify-between p-3 rounded-lg bg-[#232736] border border-[#2d3140]">
                <div>
                  <div className="text-sm font-medium text-[#e8eaed]">{t.name}</div>
                  <div className="text-xs text-[#9aa0a6]">{t.description || "无描述"}</div>
                </div>
                <button
                  onClick={() => handleDeleteTemplate(t.id)}
                  className="text-xs text-[#f87171] hover:underline"
                >
                  删除
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Summarization Demo ── */}
      <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
        <h2 className="text-lg font-semibold text-[#e8eaed] mb-3">摘要功能演示</h2>
        <textarea
          placeholder="粘贴要摘要的文本..."
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={4}
          className="w-full p-3 rounded-lg bg-[#232736] border border-[#2d3140] text-[#e8eaed] placeholder-[#9aa0a6] focus:outline-none focus:border-[#4f8cff] text-sm"
        />
        <button
          onClick={handleSummarize}
          disabled={loading || !text.trim()}
          className="mt-3 px-5 py-2 rounded-lg bg-[#4f8cff] text-white text-sm font-medium hover:bg-[#3a7bf5] disabled:opacity-50"
        >
          {loading ? "摘要中..." : "生成摘要"}
        </button>
        {summary && (
          <div className="mt-4 p-4 rounded-lg bg-[#232736] border border-[#2d3140]">
            <div className="text-xs text-[#9aa0a6] mb-2">摘要结果</div>
            <p className="text-[#e8eaed] text-sm leading-relaxed whitespace-pre-wrap">{summary}</p>
          </div>
        )}
      </div>

      {/* Config */}
      <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140] text-sm">
        <h3 className="text-[#e8eaed] font-medium mb-2">配置信息</h3>
        <div className="space-y-1 text-[#9aa0a6]">
          <div>提供商: Ollama / OpenAI（在 .env 中设置 LLM_PROVIDER）</div>
          <div>当前模型: qwen3.5:latest</div>
          <div>API: POST /api/v1/ai/templates · POST /api/v1/ai/generate · POST /api/v1/ai/summarize</div>
        </div>
      </div>
    </div>
  );
}
