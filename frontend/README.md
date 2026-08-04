# AI Research OS — Frontend

Vue 3 前端。完整使用手册见根目录 [`USAGE.md`](../USAGE.md)。

## 技术栈

- **框架**: Vue 3.5 + Vite + TypeScript
- **UI**: Element Plus + `@element-plus/icons-vue`
- **数据**: TanStack Vue Query（`@tanstack/vue-query`）+ Pinia
- **图表**: ECharts + vue-echarts
- **其他**: marked + dompurify（Markdown 渲染）、vue-router

## 目录结构

```
src/
├── main.ts            # 应用入口
├── App.vue            # 根组件
├── router/            # Vue Router（13 条路由，懒加载）
├── views/             # 页面视图（13 个）
├── components/        # 共享组件
├── stores/api.ts      # 数据层：fetch + TanStack Query 泛型 hooks
├── types/             # 类型定义
└── styles/            # 全局样式
```

## 启动

```bash
cd frontend
npm install            # legacy-peer-deps 由 frontend/.npmrc 固化
npm run dev            # http://localhost:5173
```

- vite 代理：`/api` → `http://localhost:8000/api/v1`（`VITE_API_PROXY_TARGET` 可覆盖）
- 类型检查：`npm run typecheck`（vue-tsc，当前零错误）
- 构建：`npm run build`

## 视图与路由

| 路由 | 视图 | 说明 |
|------|------|------|
| `/` | Dashboard | 工作台聚合 |
| `/research` | ResearchList / ResearchQuick / ResearchTimeline / ResearchDetail | 研究中心 |
| `/companies` | Companies / CompanyDetail | 公司中心（自选已并入） |
| `/market` | Market | 市场中心 |
| `/documents` | Documents | 文档中心 |
| `/knowledge` | Knowledge | 知识中心 |
| `/ai` | AICenter | AI 中心 |
| `/portfolio` | Portfolio | 投资组合（持仓前端待 V2） |
| `/system` | System | 系统/调度状态 |

## 数据层（stores/api.ts）

统一封装：`useList / useGet / useCreate / useUpdate / useDelete` 泛型 hooks，基于 TanStack Query，自动处理缓存失效与 422 校验错误格式化。视图不直接 `fetch`。

## 共享组件

| 组件 | 用途 |
|------|------|
| `StockSearch.vue` | 股票搜索下拉（v-model, 300ms 防抖, 键盘导航） |
| `StockChart.vue` | ECharts K 线图（MA5/MA20/成交量/dataZoom） |
| `CommandPalette.vue` | ⌘K 全局命令面板 |
| `Sidebar.vue` | 侧边栏导航 |
| `FinancialBars.vue` | 财务指标条 |

## 类型生成（按需）

前端当前使用 `stores/api.ts` 手写接口；OpenAPI 类型生成管线保留为按需工具：

```bash
npm run gen            # 后端生成 openapi.json → src/types/api.ts
```

## 后端文档

后端开发文档见 [`backend/README.md`](../backend/README.md)。
