"use client";

import { useQuery, useMutation, useQueryClient, type UseQueryOptions } from "@tanstack/react-query";

const API_BASE = "/api";

async function fetchApi<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `API error: ${res.status}`);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ── Generic hooks ──────────────────────────────────────────────────

export function useList<T>(
  key: string[],
  url: string,
  opts?: Partial<UseQueryOptions<T>>
) {
  return useQuery<T>({
    queryKey: key,
    queryFn: () => fetchApi<T>(url),
    ...opts,
  });
}

export function useGet<T>(
  key: string[],
  url: string,
  opts?: Partial<UseQueryOptions<T>>
) {
  return useQuery<T>({
    queryKey: key,
    queryFn: () => fetchApi<T>(url),
    enabled: !!url,
    ...opts,
  });
}

export function useCreate<TResult, TBody = any>(url: string, invalidateKeys?: string[][]) {
  const qc = useQueryClient();
  return useMutation<TResult, Error, TBody>({
    mutationFn: (body) =>
      fetchApi<TResult>(url, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      invalidateKeys?.forEach((key) => qc.invalidateQueries({ queryKey: key }));
    },
  });
}

export function useUpdate<TResult, TBody = any>(url: string, invalidateKeys?: string[][]) {
  const qc = useQueryClient();
  return useMutation<TResult, Error, TBody>({
    mutationFn: (body) =>
      fetchApi<TResult>(url, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      invalidateKeys?.forEach((key) => qc.invalidateQueries({ queryKey: key }));
    },
  });
}

export function useDelete(invalidateKeys?: string[][]) {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (url) => fetchApi<void>(url, { method: "DELETE" }),
    onSuccess: () => {
      invalidateKeys?.forEach((key) => qc.invalidateQueries({ queryKey: key }));
    },
  });
}

// ── Companies ──────────────────────────────────────────────────────

export interface Company {
  id: string;
  ticker: string;
  name: string;
  description: string | null;
  sector: string | null;
  industry: string | null;
  headquarters: string | null;
  website: string | null;
  is_active: boolean;
  tags: { id: string; tag: string }[];
  created_at: string;
}

export function useCompanies(query?: string) {
  const params = query ? `?query=${encodeURIComponent(query)}` : "";
  return useList<{ items: Company[]; total: number }>(
    ["companies", query || ""],
    `/companies${params}`
  );
}

export function useCompany(id: string) {
  return useGet<Company>(["company", id], `/companies/${id}`);
}

export function useCreateCompany() {
  return useCreate<Company>("/companies", [["companies"]]);
}

// ── Research ───────────────────────────────────────────────────────

export interface ResearchPlan {
  research_goal: string;
  sub_questions: string[];
  analysis_dimensions: string[];
  data_requirements: string[];
  suggested_sources: string[];
}

export interface ResearchSession {
  id: string;
  title: string;
  question: string;
  context: string | null;
  company_id: string | null;
  status: string;
  thesis: string | null;
  decision: string | null;
  confidence: number | null;
  plan: ResearchPlan | null;
  created_at: string;
}

export interface ResearchSessionDetail extends ResearchSession {
  evidences: any[];
  reports: any[];
}

export function useResearchSessions(status?: string) {
  const params = status ? `?status=${status}` : "";
  return useList<ResearchSession[]>(
    ["research", status || "all"],
    `/research/sessions${params}`
  );
}

export function useResearchSession(id: string) {
  return useGet<ResearchSessionDetail>(
    ["research", id],
    `/research/sessions/${id}`
  );
}

export function useCreateResearch() {
  return useCreate<ResearchSession>("/research/sessions", [["research"]]);
}

export function useGeneratePlan() {
  const qc = useQueryClient();
  return useMutation<any, Error, string>({
    mutationFn: (sessionId) =>
      fetchApi(`/research/sessions/${sessionId}/plan`, { method: "POST" }),
    onSuccess: (_, sessionId) => {
      qc.invalidateQueries({ queryKey: ["research", sessionId] });
    },
  });
}

export function useAutoGatherEvidence() {
  const qc = useQueryClient();
  return useMutation<any, Error, string>({
    mutationFn: (sessionId) =>
      fetchApi(`/research/sessions/${sessionId}/auto-gather?use_plan=true`, { method: "POST" }),
    onSuccess: (_, sessionId) => {
      qc.invalidateQueries({ queryKey: ["research", sessionId] });
    },
  });
}

export function useGenerateReport() {
  const qc = useQueryClient();
  return useMutation<any, Error, { sessionId: string; isFinal: boolean }>({
    mutationFn: ({ sessionId, isFinal }) =>
      fetchApi(`/research/sessions/${sessionId}/generate-report?is_final=${isFinal}`, { method: "POST" }),
    onSuccess: (_, { sessionId }) => {
      qc.invalidateQueries({ queryKey: ["research", sessionId] });
    },
  });
}

export function useFinalizeResearch() {
  const qc = useQueryClient();
  return useMutation<any, Error, { sessionId: string; thesis: string; decision: string; confidence: number }>({
    mutationFn: ({ sessionId, thesis, decision, confidence }) =>
      fetchApi(`/research/sessions/${sessionId}/finalize?thesis=${encodeURIComponent(thesis)}&decision=${decision}&confidence=${confidence}`, { method: "POST" }),
    onSuccess: (_, { sessionId }) => {
      qc.invalidateQueries({ queryKey: ["research", sessionId] });
    },
  });
}

// ── Documents ──────────────────────────────────────────────────────

export interface Document {
  id: string;
  title: string;
  doc_type: string;
  source: string | null;
  company_id: string | null;
  is_indexed: boolean;
  chunk_count: number | null;
  created_at: string;
}

export function useDocuments(docType?: string) {
  const params = docType ? `?doc_type=${docType}` : "";
  return useList<{ items: Document[]; total: number }>(
    ["documents", docType || "all"],
    `/documents${params}`
  );
}

export function useUploadDocument() {
  const qc = useQueryClient();
  return useMutation<any, Error, File>({
    mutationFn: async (file) => {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("title", file.name.replace(/\.[^/.]+$/, ""));
      const res = await fetch(`${API_BASE}/documents/upload`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Upload failed");
      }
      return res.json();
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}

// ── Knowledge (Search) ─────────────────────────────────────────────

export interface SearchResult {
  content: string;
  score: number;
  document_id: string;
  title: string;
  doc_type: string;
}

export async function searchKnowledge(
  query: string,
  topK: number = 10
): Promise<{ query: string; count: number; results: SearchResult[] }> {
  return fetchApi(
    `/knowledge/search?query=${encodeURIComponent(query)}&top_k=${topK}`
  );
}

// ── Portfolio ──────────────────────────────────────────────────────

export function useWatchlists() {
  return useList<any[]>([], "/portfolio/watchlists");
}

export function useHoldings() {
  return useList<any[]>(["holdings"], "/portfolio/holdings");
}
