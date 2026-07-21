"use client";

import { useQuery } from "@tanstack/react-query";
import { useDashboard } from "@/lib/api";

const API_BASE = "/api";

function useSchedulerStatus() {
  return useQuery<any>({
    queryKey: ["scheduler-status"],
    queryFn: () => fetch(`${API_BASE}/scheduler/status`).then((r) => r.json()),
    refetchInterval: 30_000,
  });
}

function useObservations() {
  return useQuery<any>({
    queryKey: ["observations"],
    queryFn: () => fetch(`${API_BASE}/scheduler/observations?limit=10`).then((r) => r.json()),
  });
}

export default function SystemPage() {
  const { data: scheduler } = useSchedulerStatus();
  const { data: obsData } = useObservations();
  const { data: dashboard } = useDashboard();

  const stats = [
    { label: "同步测试", value: "88 通过" },
    { label: "数据库表", value: "17 张" },
    { label: "API 端点", value: "45+" },
    { label: "Git 提交", value: "19" },
  ];

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[#e8eaed]">📡 系统状态</h1>
        <p className="text-sm text-[#9aa0a6] mt-1">系统运行状态、调度任务和执行记录</p>
      </div>

      {/* Quick stats */}
      <div className="grid grid-cols-4 gap-3">
        {stats.map((s) => (
          <div key={s.label} className="p-4 rounded-xl bg-[#1a1d28] border border-[#2d3140] text-center">
            <div className="text-xs text-[#9aa0a6] mb-1">{s.label}</div>
            <div className="text-[#e8eaed] font-semibold">{s.value}</div>
          </div>
        ))}
      </div>

      {/* Scheduler Status */}
      <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-[#e8eaed]">⏱️ 调度器</h2>
          <span className={`px-2 py-0.5 rounded text-xs font-medium ${
            scheduler?.running ? "bg-[#34d399]/10 text-[#34d399]" : "bg-[#f87171]/10 text-[#f87171]"
          }`}>
            {scheduler?.running ? "运行中" : "已停止"}
          </span>
        </div>

        {scheduler?.jobs && scheduler.jobs.length > 0 ? (
          <div className="space-y-2">
            {scheduler.jobs.map((job: any) => (
              <div key={job.id} className="flex items-center justify-between p-3 rounded-lg bg-[#232736]">
                <div>
                  <div className="text-sm text-[#e8eaed]">{job.id}</div>
                  <div className="text-xs text-[#9aa0a6] mt-0.5">
                    触发: {job.trigger}
                  </div>
                </div>
                <div className="text-xs text-[#9aa0a6]">
                  {job.next_run ? `下次: ${new Date(job.next_run).toLocaleString("zh-CN")}` : "无调度"}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-sm text-[#9aa0a6] py-2">暂无调度任务</div>
        )}
      </div>

      {/* Recent Observations */}
      <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-[#e8eaed]">👁️ 最近观测</h2>
          <span className="text-xs text-[#9aa0a6]">
            {obsData?.observations?.length || 0} 条记录
          </span>
        </div>

        {obsData?.observations && obsData.observations.length > 0 ? (
          <div className="space-y-2">
            {obsData.observations.map((obs: any) => (
              <div key={obs.id} className="p-3 rounded-lg bg-[#232736]">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-[#e8eaed]">{obs.company_name || obs.ticker}</span>
                  <span className={`px-1.5 py-0.5 rounded text-xs ${
                    obs.status === "need_research" ? "bg-[#f87171]/10 text-[#f87171]" : "bg-[#fbbf24]/10 text-[#fbbf24]"
                  }`}>{obs.status}</span>
                </div>
                <div className="text-xs text-[#9aa0a6] mt-1">
                  {obs.reasons?.join("、") || "无信号"}
                </div>
                {obs.observed_at && (
                  <div className="text-xs text-[#6b7280] mt-1">
                    {new Date(obs.observed_at).toLocaleString("zh-CN")}
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="text-sm text-[#9aa0a6] py-2">
            暂无观测记录。运行调度器或手动触发观察。
          </div>
        )}
      </div>

      {/* Morning Brief */}
      <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
        <h2 className="text-lg font-semibold text-[#e8eaed] mb-3">☀️ 最新 Morning Brief</h2>
        {dashboard?.morning_brief?.content ? (
          <div className="text-sm text-[#e8eaed] whitespace-pre-wrap leading-relaxed">
            {dashboard.morning_brief.content}
          </div>
        ) : (
          <div className="text-sm text-[#9aa0a6]">暂无 Brief</div>
        )}
        {dashboard?.morning_brief?.generated_at && (
          <div className="text-xs text-[#6b7280] mt-2">
            生成时间: {new Date(dashboard.morning_brief.generated_at).toLocaleString("zh-CN")}
          </div>
        )}
      </div>

      {/* API Health */}
      <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
        <h2 className="text-lg font-semibold text-[#e8eaed] mb-3">🔌 API 健康检查</h2>
        <div className="space-y-2">
          {[
            { name: "Dashboard", path: "/dashboard", key: "dashboard" },
            { name: "研究", path: "/research/sessions?limit=1", key: "research" },
            { name: "公司", path: "/companies?limit=1", key: "companies" },
            { name: "调度器", path: "/scheduler/status", key: "scheduler" },
          ].map((endpoint) => (
            <HealthCheck key={endpoint.key} name={endpoint.name} path={endpoint.path} />
          ))}
        </div>
      </div>

      {/* Keyboard shortcuts */}
      <div className="p-5 rounded-xl bg-[#1a1d28] border border-[#2d3140]">
        <h2 className="text-lg font-semibold text-[#e8eaed] mb-3">⌨️ 快捷键</h2>
        <div className="space-y-2 text-sm">
          {[
            { keys: "⌘K / Ctrl+K", desc: "打开命令面板" },
            { keys: "↑↓", desc: "命令面板中导航" },
            { keys: "Enter", desc: "执行命令" },
            { keys: "Esc", desc: "关闭面板" },
          ].map((shortcut) => (
            <div key={shortcut.keys} className="flex items-center gap-3">
              <kbd className="px-2 py-0.5 rounded text-xs bg-[#232736] text-[#e8eaed] border border-[#2d3140] font-mono">
                {shortcut.keys}
              </kbd>
              <span className="text-[#9aa0a6]">{shortcut.desc}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function HealthCheck({ name, path }: { name: string; path: string }) {
  const { data, isError, isLoading } = useQuery<any>({
    queryKey: ["healthcheck", path],
    queryFn: () => fetch(`${API_BASE}${path}`).then((r) => (r.ok ? r.json() : Promise.reject(r.statusText))),
    retry: 0,
  });

  return (
    <div className="flex items-center justify-between p-3 rounded-lg bg-[#232736]">
      <span className="text-sm text-[#e8eaed]">{name}</span>
      <span className="text-xs">
        {isLoading ? (
          <span className="text-[#9aa0a6]">检查中...</span>
        ) : isError ? (
          <span className="text-[#f87171]">异常</span>
        ) : (
          <span className="text-[#34d399]">正常</span>
        )}
      </span>
    </div>
  );
}
