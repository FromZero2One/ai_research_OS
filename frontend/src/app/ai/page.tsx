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
  const [editId, setEditId] = useState<string | null>(null);
  const [editTmpl, setEditTmpl] = useState({ name: "", description: "", system_prompt: "", user_prompt_template: "" });
  const [execId, setExecId] = useState<string | null>(null);
  const [execVars, setExecVars] = useState("");
  const [execResult, setExecResult] = useState("");
  const [execLoading, setExecLoading] = useState(false);

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

  const handleUpdateTemplate = async (id: string) => {
    try {
      const resp = await fetch(`/api/ai/templates/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(editTmpl),
      });
      if (resp.ok) {
        const updated = await resp.json();
        setTemplates((prev) => prev.map((t) => (t.id === id ? updated : t)));
        setEditId(null);
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

  const handleExecute = async (id: string) => {
    setExecLoading(true);
    setExecResult("");
    try {
      const variables: Record<string, string> = {};
      execVars.split("\n").filter(Boolean).forEach((line) => {
        const idx = line.indexOf("=");
        if (idx > 0) variables[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
      });
      const resp = await fetch("/api/ai/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt_name: id, variables }),
      });
      const data = await resp.json();
      setExecResult(data.content || data.error || "No response");
    } catch (e: any) {
      setExecResult("Error: " + e.message);
    } finally {
      setExecLoading(false);
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
              <div key={t.id}>
                {editId === t.id ? (
                  <div className="p-4 rounded-lg bg-[#232736] border border-[#2d3140] space-y-2">
                    <input value={editTmpl.name} onChange={(e) => setEditTmpl({ ...editTmpl, name: e.target.value })}
                      className="w-full p-2 rounded bg-[#1a1d28] border border-[#2d3140] text-[#e8eaed] text-sm" placeholder="名称" />
                    <input value={editTmpl.description} onChange={(e) => setEditTmpl({ ...editTmpl, description: e.target.value })}
                      className="w-full p-2 rounded bg-[#1a1d28] border border-[#2d3140] text-[#e8eaed] text-sm" placeholder="描述" />
                    <textarea value={editTmpl.system_prompt} onChange={(e) => setEditTmpl({ ...editTmpl, system_prompt: e.target.value })}
                      rows={2} className="w-full p-2 rounded bg-[#1a1d28] border border-[#2d3140] text-[#e8eaed] text-sm" placeholder="System Prompt" />
                    <textarea value={editTmpl.user_prompt_template} onChange={(e) => setEditTmpl({ ...editTmpl, user_prompt_template: e.target.value })}
                      rows={2} className="w-full p-2 rounded bg-[#1a1d28] border border-[#2d3140] text-[#e8eaed] text-sm" placeholder="User Prompt" />
                    <div className="flex gap-2">
                      <button onClick={() => handleUpdateTemplate(t.id)} className="px-3 py-1.5 rounded bg-[#34d399] text-black text-xs font-medium">保存</button>
                      <button onClick={() => setEditId(null)} className="px-3 py-1.5 rounded bg-[#2d3140] text-[#9aa0a6] text-xs">取消</button>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-center justify-between p-3 rounded-lg bg-[#232736] border border-[#2d3140]">
                    <div>
                      <div className="text-sm font-medium text-[#e8eaed]">{t.name}</div>
                      <div className="text-xs text-[#9aa0a6]">{t.description || "无描述"}</div>
                    </div>
                    <div className="flex gap-2 items-center">
                      <button onClick={() => { setEditId(t.id); setEditTmpl({ name: t.name || "", description: t.description || "", system_prompt: t.system_prompt || "", user_prompt_template: t.user_prompt_template || "" }); }}
                        className="text-xs text-[#4f8cff] hover:underline">编辑</button>
                      <button onClick={() => { setExecId(t.id); setExecVars(""); setExecResult(""); }}
                        className="text-xs text-[#34d399] hover:underline">执行</button>
                      <button onClick={() => handleDeleteTemplate(t.id)} className="text-xs text-[#f87171] hover:underline">删除</button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Execute Dialog */}
        {execId && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setExecId(null)}>
            <div className="w-full max-w-lg p-6 rounded-xl bg-[#1a1d28] border border-[#2d3140] space-y-3" onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center justify-between">
                <h3 className="text-[#e8eaed] font-medium">执行模板</h3>
                <button onClick={() => setExecId(null)} className="text-[#9aa0a6] hover:text-[#e8eaed] text-lg leading-none">✕</button>
              </div>
              <textarea placeholder="每行一个变量，格式 key=value&#10;例如:&#10;company=工商银行&#10;topic=估值分析" value={execVars} onChange={(e) => setExecVars(e.target.value)}
                rows={4} className="w-full p-2 rounded bg-[#232736] border border-[#2d3140] text-[#e8eaed] text-sm" />
              <button onClick={() => handleExecute(execId)} disabled={execLoading}
                className="w-full px-4 py-2 rounded-lg bg-[#4f8cff] text-white text-sm font-medium disabled:opacity-50">
                {execLoading ? "执行中..." : "执行"}
              </button>
              {execResult && (
                <div className="p-3 rounded-lg bg-[#232736] border border-[#2d3140] max-h-60 overflow-auto">
                  <div className="text-xs text-[#9aa0a6] mb-1">结果</div>
                  <p className="text-[#e8eaed] text-sm whitespace-pre-wrap">{execResult}</p>
                </div>
              )}
              <button onClick={() => setExecId(null)} className="w-full px-4 py-2 rounded-lg bg-[#2d3140] text-[#9aa0a6] text-sm">关闭</button>
            </div>
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
