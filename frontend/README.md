# AI Research OS — Frontend

Vue 3 前端。完整使用手册见根目录 [`USAGE.md`](../USAGE.md)。

## 技术栈

- **框架**: Vue 3.5 + Vite + TypeScript
- **UI**: Element Plus + `@element-plus/icons-vue`
- **数据**: TanStack Vue Query（`@tanstack/vue-query`）+ Pinia
- **图表**: ECharts + vue-echarts（Screener 页内引用）
- **其他**: marked + dompurify（Markdown 渲染）、vue-router

## 目录结构

```
src/
├── main.ts            # 应用入口
├── App.vue            # 根组件
├── router/            # Vue Router 路由（5 条，懒加载）
├── views/             # 页面视图（4 个）
├── components/        # 共享组件
├── stores/api.ts      # 数据层：fetch + TanStack Query 泛型 hooks
├── types/             # OpenAPI 生成类型（`npm run gen` 后生成 api.ts，默认空）
└── styles/            # 全局样式
```

## 启动

```bash
cd frontend
npm install            # legacy-peer-deps 由 frontend/.npmrc 固化
npm run dev            # http://localhost:5173
```

- vite 代理：`/api` → `http://localhost:8000/api/v1`（`VITE_API_PROXY_TARGET` 可覆盖）
- 类型检查：`npx vue-tsc --noEmit`（或 `npm run build` 内部先跑 `vue-tsc -b`；当前零错误）
- 构建：`npm run build`

## 视图与路由

| 路由 | 视图 | 说明 |
|------|------|------|
| `/` | — | 重定向到 `/screener` |
| `/screener` | Screener | 智能选股（首页，价值推荐清单视图） |
| `/market` | Market | 市场中心 |
| `/documents` | Documents | 文档中心 |
| `/system` | System | 系统/调度状态 |

> 2026-11-24 瘦身：Dashboard、Research×4、Portfolio、AICenter 视图已删除。
> 2026-11-25 二次瘦身：Knowledge 视图已删除（知识库保留为 Screener 事实检查的证据来源与后端 API）；Screener 页收缩为价值推荐清单视图（PresetManager、ReportCharts 组件随预设只读化与报告改造删除）。
> 2026-11-25 三次简化：Screener 明细弹窗的「自选」按钮随 `POST /runs/{id}/watchlist` 端点删除一并移除；报告视图对齐三段结构。
> 2026-11-26 六次简化：Companies/CompanyDetail 公司页与 Sidebar/路由/命令面板入口已删除（公司中心退役）；Screener 明细删「置信度」列。

## 数据层（stores/api.ts）

统一封装：`useList / useGet / useCreate / useUpdate / useDelete` 泛型 hooks，基于 TanStack Query，自动处理缓存失效与 422 校验错误格式化。视图不直接 `fetch`。

## 共享组件

| 组件 | 用途 |
|------|------|
| `StockSearch.vue` | 股票搜索下拉（v-model, 300ms 防抖, 键盘导航） |
| `StockChart.vue` | ECharts K 线图（MA5/MA20/成交量/dataZoom） |
| `CommandPalette.vue` | ⌘K 全局命令面板 |
| `Sidebar.vue` | 侧边栏导航 |

## 类型生成（已移除）

前端使用 `stores/api.ts` 手写接口；OpenAPI 类型生成管线已随七次简化删除（openapi.json 过时且无消费方，2026-11-26）。

## 后端文档

后端开发文档见 [`backend/README.md`](../backend/README.md)。
