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
    const errorBody = await res.json().catch(() => ({ detail: res.statusText }));
    // Format validation errors (422) into readable message
    if (res.status === 422 && Array.isArray(errorBody.detail)) {
      const messages = errorBody.detail.map((e: any) => {
        const field = e.loc?.filter((s: string) => s !== "body").join(".") || "";
        return field ? `${field}: ${e.msg}` : e.msg;
      });
      throw new Error(messages.join("; "));
    }
    throw new Error(errorBody.detail || `API error: ${res.status}`);
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

// ── Market ─────────────────────────────────────────────────────────

export interface PricePoint {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface MarketPricesResponse {
  ticker: string;
  count: number;
  prices: PricePoint[];
}

export function useMarketPrices(ticker: string, limit: number = 120) {
  return useGet<MarketPricesResponse>(
    ["market", ticker],
    ticker ? `/market/prices/${ticker}?limit=${limit}` : "",
  );
}

export interface FinancialMetricPoint {
  fiscal_year: number;
  fiscal_period: string;
  metric_name: string;
  metric_value: number;
}

export function useFinancialMetrics(ticker: string) {
  return useGet<{ ticker: string; count: number; metrics: FinancialMetricPoint[] }>(
    ["financials", ticker],
    ticker ? `/market/financials/${ticker}` : "",
  );
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
  topK: number = 10,
  docType?: string
): Promise<{ query: string; count: number; results: SearchResult[] }> {
  let url = `/knowledge/search?query=${encodeURIComponent(query)}&top_k=${topK}`;
  if (docType) url += `&doc_type=${encodeURIComponent(docType)}`;
  return fetchApi(url);
}

// ── Portfolio ──────────────────────────────────────────────────────

export function useWatchlists() {
  return useList<any[]>([], "/portfolio/watchlists");
}

export function useHoldings() {
  return useList<any[]>(["holdings"], "/portfolio/holdings");
}

// ── Dashboard ─────────────────────────────────────────────────────

export interface DashboardBrief {
  content: string;
  generated_at: string | null;
}

export interface DashboardWatchlistItem {
  id: string;
  ticker: string;
  company_name: string;
  sector: string | null;
  priority: number;
  target_price: number | null;
  reason: string | null;
  latest_price: number | null;
  price_date: string | null;
  price_change: number | null;
  status: "normal" | "attention" | "need_research";
  thesis: string | null;
  last_research_at: string | null;
  days_since_research: number | null;
}

export interface DashboardWatchlist {
  watchlist_id: string;
  watchlist_name: string;
  items: DashboardWatchlistItem[];
}

export interface DashboardReminder {
  ticker: string;
  company_name: string;
  days_since_research: number;
  reasons: string[];
  priority: number;
}

export interface DashboardRecentResearch {
  id: string;
  title: string;
  question: string;
  status: string;
  thesis: string | null;
  created_at: string;
}

export interface DashboardData {
  morning_brief: DashboardBrief | null;
  watchlist: DashboardWatchlist[];
  research_reminders: DashboardReminder[];
  recent_research: DashboardRecentResearch[];
}

export function useDashboard() {
  return useGet<DashboardData>(["dashboard"], "/dashboard");
}

// ── Quick Research ────────────────────────────────────────────────

export interface QuickResearchRequest {
  ticker: string;
  question: string;
  title?: string;
}

export interface QuickResearchResponse {
  session_id: string;
  status: string;
}

export interface ResearchProgress {
  step: string;
  message: string;
  status: string;
  session_id: string;
  report_id?: string;
  error?: string;
}

export function useQuickResearch() {
  const qc = useQueryClient();
  return useMutation<QuickResearchResponse, Error, QuickResearchRequest>({
    mutationFn: (data) =>
      fetchApi("/research/quick", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["research"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function subscribeResearchStream(
  sessionId: string,
  onProgress: (progress: ResearchProgress) => void,
  onComplete: (progress: ResearchProgress) => void,
  onError: (error: string) => void,
): () => void {
  const eventSource = new EventSource(`/api/research/quick/${sessionId}/stream`);

  eventSource.addEventListener("progress", (event) => {
    try {
      const data = JSON.parse(event.data) as ResearchProgress;
      onProgress(data);
    } catch { /* ignore parse errors */ }
  });

  eventSource.addEventListener("complete", (event) => {
    try {
      const data = JSON.parse(event.data) as ResearchProgress;
      onComplete(data);
    } catch { /* ignore */ }
    eventSource.close();
  });

  eventSource.addEventListener("error", (event) => {
    onError("SSE connection error");
    eventSource.close();
  });

  return () => eventSource.close();
}

// ── Research Timeline ───────────────────────────────────────────

export interface TimelineEvent {
  type: string;
  date: string;
  session_id?: string;
  session_title?: string;
  report_id?: string;
  version?: number;
  is_final?: boolean;
  thesis?: string | null;
  decision?: string | null;
  confidence?: number | null;
  detail: string;
  status?: string;
}

export interface TimelineData {
  ticker: string;
  company_name: string | null;
  events: TimelineEvent[];
}

export function useTimeline(ticker: string) {
  return useGet<TimelineData>(
    ["timeline", ticker],
    ticker ? `/research/timeline?ticker=${encodeURIComponent(ticker)}` : "",
  );
}

export interface DiffData {
  report_id: string;
  session_id: string;
  from_version: number;
  to_version: number;
  diff: string;
  stats: {
    additions: number;
    deletions: number;
    context_lines: number;
  };
}

export function useReportDiff(reportId: string, otherVersion: number) {
  return useGet<DiffData>(
    ["report-diff", reportId, String(otherVersion)],
    reportId ? `/research/reports/${reportId}/diff?other_version=${otherVersion}` : "",
  );
}

export interface SessionTimelineData {
  session_id: string;
  session_title: string;
  status: string;
  thesis: string | null;
  decision: string | null;
  events: TimelineEvent[];
}

export function useSessionTimeline(sessionId: string) {
  return useGet<SessionTimelineData>(
    ["session-timeline", sessionId],
    sessionId ? `/research/sessions/${sessionId}/timeline` : "",
  );
}

// ── Thesis Panel ─────────────────────────────────────────────────

export interface ThesisData {
  ticker: string;
  company_name: string;
  thesis: string | null;
  decision: string | null;
  confidence: number | null;
  source_session_id: string | null;
  updated_at: string | null;
}

export interface WorkspaceData {
  ticker: string;
  company_name: string;
  company_id: string;
  thesis: ThesisData | null;
  recent_research: {
    id: string;
    title: string;
    status: string;
    decision: string | null;
    thesis: string | null;
    created_at: string | null;
  }[];
  evidence_summary: {
    supporting: number;
    opposing: number;
    neutral: number;
  };
}

export function useCompanyThesis(ticker: string) {
  return useGet<ThesisData>(
    ["thesis", ticker],
    ticker ? `/companies/by-ticker/${encodeURIComponent(ticker)}/thesis` : "",
  );
}

export function useUpdateThesis() {
  const qc = useQueryClient();
  return useMutation<any, Error, { ticker: string; thesis: string; decision?: string; confidence?: number }>({
    mutationFn: ({ ticker, thesis, decision, confidence }) =>
      fetchApi(`/companies/by-ticker/${encodeURIComponent(ticker)}/thesis`, {
        method: "POST",
        body: JSON.stringify({ thesis, decision, confidence }),
      }),
    onSuccess: (_, { ticker }) => {
      qc.invalidateQueries({ queryKey: ["thesis", ticker] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function useCompanyWorkspace(ticker: string) {
  return useGet<WorkspaceData>(
    ["workspace", ticker],
    ticker ? `/companies/by-ticker/${encodeURIComponent(ticker)}/workspace` : "",
  );
}
