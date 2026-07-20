"use client";

import { useState, useRef, useCallback } from "react";
import { useDocuments, useUploadDocument } from "@/lib/api";

const DOC_TYPES = ["all", "pdf", "markdown", "text", "report", "transcript"];

export default function DocumentsPage() {
  const [docType, setDocType] = useState("all");
  const [isDragOver, setIsDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data, isLoading } = useDocuments(docType === "all" ? undefined : docType);
  const uploadDoc = useUploadDocument();

  const handleFile = useCallback(async (file: File) => {
    const maxSize = 50 * 1024 * 1024;
    if (file.size > maxSize) {
      setUploadMsg({ type: "error", text: `文件过大 (${(file.size / 1024 / 1024).toFixed(1)}MB)，最大 50MB` });
      return;
    }
    setUploading(true);
    setUploadMsg(null);
    try {
      const result = await uploadDoc.mutateAsync(file);
      setUploadMsg({
        type: "success",
        text: `"${result.title}" 上传成功 — ${result.chunk_count} 个切片，${result.is_indexed ? "已索引" : "索引中"}`,
      });
    } catch (e: any) {
      setUploadMsg({ type: "error", text: e.message || "上传失败" });
    } finally {
      setUploading(false);
    }
  }, [uploadDoc]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  }, [handleFile]);

  const handleSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }, [handleFile]);

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-[#e8eaed]">📄 文档中心</h1>
        <p className="text-[#9aa0a6] text-sm mt-1">
          导入 → 解析 → 分块 → 嵌入 → 索引 — 完整知识处理管道
        </p>
      </div>

      {/* Upload Zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`p-8 rounded-xl border-2 border-dashed text-center cursor-pointer transition-all ${
          isDragOver
            ? "bg-[#4f8cff]/5 border-[#4f8cff]"
            : uploading
            ? "bg-[#1a1d28] border-[#fbbf24]"
            : "bg-[#1a1d28] border-[#2d3140] hover:border-[#4f8cff]/30"
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.md,.txt,.html,.htm"
          className="hidden"
          onChange={handleSelect}
        />
        {uploading ? (
          <div>
            <div className="text-3xl mb-2 animate-pulse">⏳</div>
            <div className="text-[#e8eaed] font-medium">上传中...</div>
            <div className="text-sm text-[#9aa0a6] mt-1">正在解析并索引文档</div>
          </div>
        ) : (
          <div>
            <div className="text-3xl mb-2">📤</div>
            <div className="text-[#e8eaed] font-medium">点击或拖拽文件到此处上传</div>
            <div className="text-sm text-[#9aa0a6] mt-1">
              PDF · Markdown · TXT · HTML — 最大 50MB
            </div>
          </div>
        )}
      </div>

      {/* Upload Message */}
      {uploadMsg && (
        <div className={`p-4 rounded-xl text-sm ${
          uploadMsg.type === "success"
            ? "bg-[#34d399]/10 text-[#34d399] border border-[#34d399]/20"
            : "bg-[#f87171]/10 text-[#f87171] border border-[#f87171]/20"
        }`}>
          {uploadMsg.text}
        </div>
      )}

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
        <div className="text-center text-[#9aa0a6] py-12">加载中...</div>
      ) : !data || data.items.length === 0 ? (
        <div className="p-12 rounded-xl bg-[#1a1d28] border border-[#2d3140] text-center">
          <div className="text-3xl mb-3">📄</div>
          <div className="text-[#e8eaed] font-medium">暂无文档</div>
          <div className="text-[#9aa0a6] text-sm mt-1">上传第一个 PDF 或研究报告</div>
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
                <div className="text-xs text-[#9aa0a6] mt-1 space-x-2">
                  <span>{doc.doc_type}</span>
                  <span>·</span>
                  <span>{doc.chunk_count || 0} 切片</span>
                  {doc.source && (
                    <>
                      <span>·</span>
                      <span>{doc.source}</span>
                    </>
                  )}
                </div>
              </div>
              <span className={`px-2 py-1 rounded text-xs font-medium ${
                doc.is_indexed
                  ? "bg-[#34d399]/10 text-[#34d399]"
                  : "bg-[#fbbf24]/10 text-[#fbbf24]"
              }`}>
                {doc.is_indexed ? "已索引" : "待处理"}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
