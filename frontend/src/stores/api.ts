import { useQuery, useMutation, useQueryClient, type UseQueryOptions } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

const API_BASE = '/api'

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({ detail: res.statusText }))
    if (res.status === 422 && Array.isArray(errorBody.detail)) {
      const messages = errorBody.detail.map((e: any) => {
        const field = e.loc?.filter((s: string) => s !== 'body').join('.') || ''
        return field ? `${field}: ${e.msg}` : e.msg
      })
      throw new Error(messages.join('; '))
    }
    throw new Error(errorBody.detail || `API error: ${res.status}`)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

// ── Generic hooks ──
export function useList<T>(key: string[], url: string, opts?: Partial<UseQueryOptions<T>>) {
  return useQuery<T>({ queryKey: key, queryFn: () => fetchApi<T>(url), ...opts })
}

export function useGet<T>(key: MaybeRefOrGetter<string[]>, url: MaybeRefOrGetter<string>, opts?: Partial<UseQueryOptions<T>>) {
  return useQuery<T>({
    queryKey: computed(() => toValue(key)),
    queryFn: () => fetchApi<T>(toValue(url)),
    enabled: computed(() => !!toValue(url)),
    ...opts,
  })
}

export function useCreate<TResult, TBody = any>(url: string, invalidateKeys?: string[][]) {
  const qc = useQueryClient()
  return useMutation<TResult, Error, TBody>({
    mutationFn: (body) => fetchApi<TResult>(url, { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: () => { invalidateKeys?.forEach((key) => qc.invalidateQueries({ queryKey: key })) },
  })
}

export function useUpdate<TResult, TBody = any>(url: string, invalidateKeys?: string[][]) {
  const qc = useQueryClient()
  return useMutation<TResult, Error, TBody>({
    mutationFn: (body) => fetchApi<TResult>(url, { method: 'PATCH', body: JSON.stringify(body) }),
    onSuccess: () => { invalidateKeys?.forEach((key) => qc.invalidateQueries({ queryKey: key })) },
  })
}

export function useDelete(invalidateKeys?: string[][]) {
  const qc = useQueryClient()
  return useMutation<void, Error, string>({
    mutationFn: (url) => fetchApi<void>(url, { method: 'DELETE' }),
    onSuccess: () => { invalidateKeys?.forEach((key) => qc.invalidateQueries({ queryKey: key })) },
  })
}

// ── Companies ──
export interface Company {
  id: string; ticker: string; name: string
  description: string | null; sector: string | null; industry: string | null
  headquarters: string | null; website: string | null; is_active: boolean
  tags: { id: string; tag: string }[]; created_at: string
}

export function useCompanies(query?: MaybeRefOrGetter<string>) {
  return useQuery<{ items: Company[]; total: number }>({
    queryKey: computed(() => ['companies', toValue(query) || 'all']),
    queryFn: () => {
      const q = toValue(query)
      return fetchApi(q ? `/companies?query=${encodeURIComponent(q)}` : '/companies')
    },
  })
}

export function useCompany(id: string) {
  return useGet<Company>(['company', id], `/companies/${id}`)
}

export function useCreateCompany() {
  return useCreate<Company>('/companies', [['companies']])
}

export function useUpdateCompany(id: MaybeRefOrGetter<string | null>) {
  const qc = useQueryClient()
  return useMutation<Company, Error, Record<string, unknown>>({
    mutationFn: (data) => fetchApi(`/companies/${toValue(id) ?? ''}`, { method: 'PATCH', body: JSON.stringify(data) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['company', id] })
      qc.invalidateQueries({ queryKey: ['companies'] })
    },
  })
}

export function useDeleteCompany() {
  const qc = useQueryClient()
  return useMutation<void, Error, string>({
    mutationFn: (id) => fetchApi(`/companies/${id}`, { method: 'DELETE' }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['companies'] }) },
  })
}

// ── Research ──
export interface ResearchPlan {
  research_goal: string; sub_questions: string[]; analysis_dimensions: string[]
  data_requirements: string[]; suggested_sources: string[]
}

export interface ResearchSession {
  id: string; title: string; question: string; context: string | null
  company_id: string | null; status: string; thesis: string | null
  decision: string | null; confidence: number | null; plan: ResearchPlan | null; created_at: string
}

export interface ResearchSessionDetail extends ResearchSession {
  evidences: any[]; reports: any[]
}

export function useResearchSessions(status?: string) {
  const params = status ? `?status=${status}` : ''
  return useList<ResearchSession[]>(['research', status || 'all'], `/research/sessions${params}`)
}

export function useResearchSession(id: string) {
  return useGet<ResearchSessionDetail>(['research', id], `/research/sessions/${id}`)
}

export function useCreateResearch() {
  return useCreate<ResearchSession>('/research/sessions', [['research']])
}

export function useGeneratePlan() {
  const qc = useQueryClient()
  return useMutation<any, Error, string>({
    mutationFn: (sessionId) => fetchApi(`/research/sessions/${sessionId}/plan`, { method: 'POST' }),
    onSuccess: (_, sessionId) => { qc.invalidateQueries({ queryKey: ['research', sessionId] }) },
  })
}

export function useAutoGatherEvidence() {
  const qc = useQueryClient()
  return useMutation<any, Error, string>({
    mutationFn: (sessionId) => fetchApi(`/research/sessions/${sessionId}/auto-gather?use_plan=true`, { method: 'POST' }),
    onSuccess: (_, sessionId) => { qc.invalidateQueries({ queryKey: ['research', sessionId] }) },
  })
}

export function useGenerateReport() {
  const qc = useQueryClient()
  return useMutation<any, Error, { sessionId: string; isFinal: boolean }>({
    mutationFn: ({ sessionId, isFinal }) => fetchApi(
      `/research/sessions/${sessionId}/generate-report`,
      { method: 'POST', body: JSON.stringify({ is_final: isFinal }) },
    ),
    onSuccess: (_, { sessionId }) => { qc.invalidateQueries({ queryKey: ['research', sessionId] }) },
  })
}

export function useFinalizeResearch() {
  const qc = useQueryClient()
  return useMutation<any, Error, { sessionId: string; thesis: string; decision: string; confidence: number }>({
    mutationFn: ({ sessionId, thesis, decision, confidence }) =>
      fetchApi(
        `/research/sessions/${sessionId}/finalize`,
        { method: 'POST', body: JSON.stringify({ thesis, decision, confidence }) },
      ),
    onSuccess: (_, { sessionId }) => { qc.invalidateQueries({ queryKey: ['research', sessionId] }) },
  })
}

// ── Documents ──
export interface Document {
  id: string; title: string; doc_type: string; source: string | null
  company_id: string | null; is_indexed: boolean; chunk_count: number | null; created_at: string
}

export function useDocuments(docType?: string) {
  const params = docType ? `?doc_type=${docType}` : ''
  return useList<{ items: Document[]; total: number }>(['documents', docType || 'all'], `/documents${params}`)
}

export function useUploadDocument() {
  const qc = useQueryClient()
  return useMutation<{
    id: string; title: string; doc_type: string
    chunk_count: number; is_indexed: boolean; status: string; message: string
  }, Error, { file: File; companyId?: string | null }>({
    mutationFn: async ({ file, companyId }) => {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('title', file.name.replace(/\.[^/.]+$/, ''))
      if (companyId) formData.append('company_id', companyId)
      const res = await fetch(`${API_BASE}/documents/upload`, { method: 'POST', body: formData })
      if (!res.ok) { const err = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(err.detail || 'Upload failed') }
      return res.json()
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['documents'] }) },
  })
}

export interface DocumentIndexingStatus {
  id: string; is_indexed: boolean; chunk_count: number | null
  step: string; message: string; error?: string | null
}

export function useDocumentStatus(id: MaybeRefOrGetter<string | null>) {
  return useGet<DocumentIndexingStatus>(
    computed(() => ['document-status', toValue(id) || '']),
    computed(() => (toValue(id) ? `/documents/${toValue(id)}/status` : '')),
    { refetchInterval: 2000 },
  )
}

export function useUpdateDocumentCompany() {
  const qc = useQueryClient()
  return useMutation<unknown, Error, { id: string; companyId: string | null }>({
    mutationFn: ({ id, companyId }) =>
      fetchApi(`/documents/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ company_id: companyId }),
      }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['documents'] }) },
  })
}

// ── Market ──
export interface PricePoint { date: string; open: number; high: number; low: number; close: number; volume: number }
export interface MarketPricesResponse { ticker: string; count: number; prices: PricePoint[] }
export interface FinancialMetricPoint { fiscal_year: number; fiscal_period: string; metric_name: string; metric_value: number }
export interface StockSearchResult { symbol: string; name: string }

export function useMarketPrices(ticker: MaybeRefOrGetter<string>, limit: number = 120) {
  return useGet<MarketPricesResponse>(
    computed(() => ['market', toValue(ticker)]),
    computed(() => (toValue(ticker) ? `/market/prices/${toValue(ticker)}?limit=${limit}` : '')),
  )
}

export function useFinancialMetrics(ticker: MaybeRefOrGetter<string>) {
  return useGet<{ ticker: string; count: number; metrics: FinancialMetricPoint[] }>(
    computed(() => ['financials', toValue(ticker)]),
    computed(() => (toValue(ticker) ? `/market/financials/${toValue(ticker)}` : '')),
  )
}

export function useStockSearch(query: MaybeRefOrGetter<string>) {
  return useQuery<{ query: string; count: number; results: StockSearchResult[] }>({
    queryKey: ['stock-search', query],
    queryFn: () => { const q = toValue(query); return fetchApi(`/market/search?query=${encodeURIComponent(q)}&limit=10`) },
    enabled: () => !!toValue(query),
  })
}

export function useIngestPrices() {
  const qc = useQueryClient()
  return useMutation<unknown, Error, string>({
    mutationFn: (ticker) => fetchApi(`/market/prices/${ticker}/ingest`, { method: 'POST' }),
    onSuccess: (_, ticker) => { qc.invalidateQueries({ queryKey: ['market', ticker] }) },
  })
}

export function useIngestFinancials() {
  const qc = useQueryClient()
  return useMutation<unknown, Error, string>({
    mutationFn: (ticker) => fetchApi(`/market/financials/${ticker}/ingest`, { method: 'POST' }),
    onSuccess: (_, ticker) => { qc.invalidateQueries({ queryKey: ['financials', ticker] }) },
  })
}

export function useIngestProfile() {
  const qc = useQueryClient()
  return useMutation<unknown, Error, string>({
    mutationFn: (ticker) => fetchApi(`/market/profile/${ticker}/ingest`, { method: 'POST' }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['companies'] }) },
  })
}

// ── Knowledge ──
export interface SearchResult {
  content: string; score: number; document_id: string; title: string; doc_type: string
  snippet?: string; highlights?: string[]
}

export async function searchKnowledge(query: string, topK: number = 10, docType?: string): Promise<{ query: string; count: number; results: SearchResult[] }> {
  let url = `/knowledge/search?query=${encodeURIComponent(query)}&top_k=${topK}`
  if (docType) url += `&doc_type=${encodeURIComponent(docType)}`
  return fetchApi(url)
}

export interface AskSource {
  title: string; chunk_index: number; score: number
  document_id: string; content: string
}

export function useAskKnowledge() {
  return useMutation<{ answer: string; sources: AskSource[]; model?: string }, Error, {
    question: string; top_k?: number; provider?: 'default' | 'ollama'; model?: string | null
  }>({
    mutationFn: (body) => fetchApi('/knowledge/ask', { method: 'POST', body: JSON.stringify(body) }),
  })
}

export function useLlmModels() {
  return useGet<{ default: { provider: string; model: string }; ollama: string[] }>(
    ['llm-models'],
    '/knowledge/llm/models',
  )
}

// ── Portfolio ──
export function useWatchlists() { return useList<any[]>(['watchlists'], '/portfolio/watchlists') }
export function useHoldings() { return useList<any[]>(['holdings'], '/portfolio/holdings') }

export function useAddHolding() {
  const qc = useQueryClient()
  return useMutation<unknown, Error, { ticker: string; shares: number; avg_cost_basis: number | null }>({
    mutationFn: (body) => fetchApi('/portfolio/holdings', { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['holdings'] }) },
  })
}

export function useAddWatchlistItem(watchlistId: MaybeRefOrGetter<string>) {
  const qc = useQueryClient()
  return useMutation<unknown, Error, { ticker: string }>({
    mutationFn: (body) => fetchApi(`/portfolio/watchlists/${toValue(watchlistId)}/items`, { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['watchlists'] }) },
  })
}

export function useRemoveWatchlistItem() {
  const qc = useQueryClient()
  return useMutation<unknown, Error, string>({
    mutationFn: (itemId) => fetchApi(`/portfolio/watchlists/items/${itemId}`, { method: 'DELETE' }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['watchlists'] }) },
  })
}

// ── Dashboard ──
export interface DashboardBrief { content: string; generated_at: string | null }
export interface DashboardWatchlistItem {
  id: string; ticker: string; company_name: string; sector: string | null
  priority: number; target_price: number | null; reason: string | null
  latest_price: number | null; price_date: string | null; price_change: number | null
  status: 'normal' | 'attention' | 'need_research'; thesis: string | null
  last_research_at: string | null; days_since_research: number | null
}
export interface DashboardWatchlist { watchlist_id: string; watchlist_name: string; items: DashboardWatchlistItem[] }
export interface DashboardReminder { ticker: string; company_name: string; days_since_research: number; reasons: string[]; priority: number }
export interface DashboardRecentResearch { id: string; title: string; question: string; status: string; thesis: string | null; created_at: string }
export interface DashboardMarketItem {
  ticker: string; company_name: string; sector: string | null; latest_price: number | null; change_pct: number | null
}
export interface DashboardData {
  morning_brief: DashboardBrief | null; watchlist: DashboardWatchlist[]
  research_reminders: DashboardReminder[]; recent_research: DashboardRecentResearch[]
  market_overview?: DashboardMarketItem[]
}
export function useDashboard() { return useGet<DashboardData>(['dashboard'], '/dashboard') }

export function useGenerateBrief() {
  const qc = useQueryClient()
  return useMutation<unknown, Error, void>({
    mutationFn: () => fetchApi('/dashboard/generate-brief', { method: 'POST' }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['dashboard'] }) },
  })
}

// ── System ──
export function useSchedulerStatus() {
  return useQuery<{ running?: boolean; jobs?: any[] }>({
    queryKey: ['scheduler-status'],
    queryFn: () => fetchApi('/scheduler/status'),
    refetchInterval: 30_000,
  })
}

export function useObservations(limit = 10) {
  return useGet<{ observations: any[] }>(['observations'], `/scheduler/observations?limit=${limit}`)
}

export function useHealth(path: string) {
  return useQuery<unknown>({
    queryKey: ['health', path],
    queryFn: () => fetchApi(path),
    retry: 0,
  })
}

// ── AI Center ──
export interface PromptTemplate {
  id: string; name: string; description: string | null
  system_prompt: string | null; user_prompt_template: string | null
  temperature: number | null; max_tokens: number | null; is_active: boolean
}

export function useListTemplates() {
  return useList<PromptTemplate[]>(['ai-templates'], '/ai/templates')
}

export function useCreateTemplate() {
  const qc = useQueryClient()
  return useMutation<PromptTemplate, Error, Record<string, unknown>>({
    mutationFn: (body) => fetchApi('/ai/templates', { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['ai-templates'] }) },
  })
}

export function useUpdateTemplate(id: MaybeRefOrGetter<string | null>) {
  const qc = useQueryClient()
  return useMutation<PromptTemplate, Error, Record<string, unknown>>({
    mutationFn: (body) => fetchApi(`/ai/templates/${toValue(id) ?? ''}`, { method: 'PATCH', body: JSON.stringify(body) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['ai-templates'] }) },
  })
}

export function useDeleteTemplate() {
  const qc = useQueryClient()
  return useMutation<unknown, Error, string>({
    mutationFn: (id) => fetchApi(`/ai/templates/${id}`, { method: 'DELETE' }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['ai-templates'] }) },
  })
}

export function useExecuteTemplate() {
  return useMutation<{ content: string; model: string; error?: string }, Error, { prompt_name: string; variables: Record<string, string> }>({
    mutationFn: (body) => fetchApi('/ai/generate', { method: 'POST', body: JSON.stringify(body) }),
  })
}

export function useSummarize() {
  return useMutation<{ content: string; error?: string }, Error, { text: string; max_length: number; format_: string }>({
    mutationFn: (body) => fetchApi('/ai/summarize', { method: 'POST', body: JSON.stringify(body) }),
  })
}

// ── Quick Research ──
export interface QuickResearchRequest { ticker: string; question: string; title?: string }
export interface QuickResearchResponse { session_id: string; status: string }
export interface ResearchProgress { step: string; message: string; status: string; session_id: string; report_id?: string; error?: string }

export function useQuickResearch() {
  const qc = useQueryClient()
  return useMutation<QuickResearchResponse, Error, QuickResearchRequest>({
    mutationFn: (data) => fetchApi('/research/quick', { method: 'POST', body: JSON.stringify(data) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['research'] }); qc.invalidateQueries({ queryKey: ['dashboard'] }) },
  })
}

export function subscribeResearchStream(
  sessionId: string,
  onProgress: (progress: ResearchProgress) => void,
  onComplete: (progress: ResearchProgress) => void,
  onError: (error: string) => void,
): () => void {
  const eventSource = new EventSource(`/api/research/quick/${sessionId}/stream`)
  eventSource.addEventListener('progress', (event) => { try { onProgress(JSON.parse(event.data)) } catch {} })
  eventSource.addEventListener('complete', (event) => { try { onComplete(JSON.parse(event.data)) } catch {}; eventSource.close() })
  eventSource.addEventListener('error', () => { onError('SSE connection error'); eventSource.close() })
  return () => eventSource.close()
}

// ── Research Timeline ──
export interface TimelineEvent {
  type: string; date: string; session_id?: string; session_title?: string
  report_id?: string; version?: number; is_final?: boolean
  thesis?: string | null; decision?: string | null; confidence?: number | null
  detail: string; status?: string
}
export interface TimelineData { ticker: string; company_name: string | null; events: TimelineEvent[] }
export interface DiffData {
  report_id: string; session_id: string; from_version: number; to_version: number
  diff: string; stats: { additions: number; deletions: number; context_lines: number }
}
export interface SessionTimelineData { session_id: string; session_title: string; status: string; thesis: string | null; decision: string | null; events: TimelineEvent[] }

export function useTimeline(ticker: string) {
  return useGet<TimelineData>(['timeline', ticker], ticker ? `/research/timeline?ticker=${encodeURIComponent(ticker)}` : '')
}

export function useReportDiff(reportId: string, otherVersion: number) {
  return useGet<DiffData>(['report-diff', reportId, String(otherVersion)], reportId ? `/research/reports/${reportId}/diff?other_version=${otherVersion}` : '')
}

export function useSessionTimeline(sessionId: string) {
  return useGet<SessionTimelineData>(['session-timeline', sessionId], sessionId ? `/research/sessions/${sessionId}/timeline` : '')
}

// ── Thesis Panel ──
export interface ThesisData {
  ticker: string; company_name: string; thesis: string | null; decision: string | null
  confidence: number | null; source_session_id: string | null; updated_at: string | null
  structured_thesis?: { bull_case: string[]; bear_case: string[]; key_drivers: string[]; risks: string[] } | null
}
export interface WorkspaceData {
  ticker: string; company_name: string; company_id: string; thesis: ThesisData | null
  recent_research: { id: string; title: string; status: string; decision: string | null; thesis: string | null; created_at: string | null }[]
  evidence_summary: { supporting: number; opposing: number; neutral: number }
}

export function useCompanyThesis(ticker: MaybeRefOrGetter<string>) {
  return useGet<ThesisData>(
    computed(() => ['thesis', toValue(ticker)]),
    computed(() => (toValue(ticker) ? `/companies/by-ticker/${encodeURIComponent(toValue(ticker))}/thesis` : '')),
  )
}

export function useUpdateThesis() {
  const qc = useQueryClient()
  return useMutation<any, Error, { ticker: string; thesis: string; decision?: string; confidence?: number }>({
    mutationFn: ({ ticker, thesis, decision, confidence }) => fetchApi(`/companies/by-ticker/${encodeURIComponent(ticker)}/thesis`, { method: 'POST', body: JSON.stringify({ thesis, decision, confidence }) }),
    onSuccess: (_, { ticker }) => { qc.invalidateQueries({ queryKey: ['thesis', ticker] }); qc.invalidateQueries({ queryKey: ['dashboard'] }) },
  })
}

export function useCompanyWorkspace(ticker: MaybeRefOrGetter<string>) {
  return useGet<WorkspaceData>(
    computed(() => ['workspace', toValue(ticker)]),
    computed(() => (toValue(ticker) ? `/companies/by-ticker/${encodeURIComponent(toValue(ticker))}/workspace` : '')),
  )
}
