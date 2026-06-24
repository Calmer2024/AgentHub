# AgentHub 项目目录与文件编辑器完整落地方案

## 1. 文档元信息

| 项目 | 内容 |
| --- | --- |
| 文档名称 | 项目目录与文件编辑器完整落地方案 |
| 存放位置 | `docs/scheme/project-file-explorer-editor-plan.md` |
| 目标读者 | 产品经理、UI/UX 设计师、前端工程师、后端工程师、测试工程师 |
| 产品范围 | 每个 Project 拥有独立文件资源管理器、文件预览、文件编辑、文件操作、变更感知、Agent 协作引用能力 |
| 交付口径 | 一次性交付完整闭环，不拆分版本、不拆分上线范围 |
| 当前依据 | Project-first workspace、消息级 Artifact、页面级弹窗、CodeMirror 文件编辑器、`agenthub-*` 设计 token、P1 本机与 P2 云端 workspace 双形态 |

## 2. 背景与定位

AgentHub 已经具备 Project-first 工作区模型、CLI Agent 读写 workspace、消息级 Artifact Card、文件快照编辑、预览与版本能力。现有能力偏向“Agent 输出后的产物查看与局部编辑”，用户只能从聊天消息或 Artifact 卡片进入某个文件或变更，缺少一个稳定的“项目文件工作台”。

本方案要把文件能力提升为 Project 的一级基础设施。用户进入任意 Project 后，除了与 Agent 对话，还应能直接理解当前项目目录结构、打开任意支持文件、预览可视内容、编辑文本文件、管理新增/删除/重命名/移动、查看 Agent 最近改动、把文件或代码片段引用回聊天，并在本机或云端 workspace 中保持相同的产品语义。

产品定位不是复制 VS Code，也不是恢复旧式右侧 Drawer。它应是嵌入 AgentHub IM 工作台的“轻量项目文件空间”：目录树负责理解与定位，编辑器负责小范围人工修正和引用，复杂生成与重构仍通过聊天和 Agent 完成。

## 3. 核心结论

1. 每个 Project 必须拥有一个独立文件资源管理器入口，入口与 Project 绑定，不与单个 Session 绑定。
2. 文件资源管理器采用页面级工作台弹窗或主工作区可切换面板，不放进聊天消息内部，也不重新引入常驻右侧 Drawer。
3. 文件编辑器继续基于 CodeMirror，沿用现有深色代码面板能力，但补齐标签页、脏状态、保存冲突、文件锁感知、快捷键、查找替换和代码引用闭环。
4. 文件预览根据类型分流：代码编辑、Markdown 渲染、HTML/IFrame 预览、图片/PDF/办公文件预览、二进制元信息页、超大文件只读摘要。
5. 所有文件操作必须经过 workspace 安全解析，禁止绝对路径、`../` 越界、系统保护目录、隐藏内部目录和未授权 cloud workspace 访问。
6. Agent 修改、用户编辑、构建预览、Artifact 版本链必须共享一个变更事实源。用户不应该分辨“这是聊天产物里的文件”还是“资源管理器里的文件”，二者应指向同一个 Project 相对路径。
7. 本功能一次性交付完整闭环，验收时必须同时覆盖前端 UI、后端 API、权限安全、实时刷新、异常状态、移动端降级、自动化测试和真实服务手工验证。

## 4. 现状约束与可复用资产

### 4.1 已有产品与技术事实

| 领域 | 当前事实 | 本方案处理 |
| --- | --- | --- |
| Project | Project 绑定 `workspacePath` 或 `workspaceId`，所有 Session 共享工作区 | 文件资源管理器挂在 Project 上 |
| Artifact | Artifact Card 绑定 `projectId`、`filePath`、`version`，支持页面级预览与编辑 | 文件入口与 Artifact 入口统一打开同一文件目标 |
| 文件接口 | 已有 `GET /projects/{id}/tree`、`GET /files?path=`、`PUT /files` | 扩展为完整文件系统 API |
| 编辑器 | 已有 `CodeMirrorFileEditor` 和 `FileEditorModal` | 升级为 Project File Workspace 内的多文件编辑器 |
| 样式 | `agenthub-*` CSS token，暗色优先，支持 light theme | 新组件必须复用 token，不引入新视觉系统 |
| 图标 | 项目已使用 `lucide-react` | 新按钮继续使用 lucide，保持图标族一致 |
| 壳层 | Local Desktop、SaaS Web、Mobile 多端能力矩阵 | 文件能力按 surface 做同语义降级 |

### 4.2 当前能力缺口

| 缺口 | 用户表现 | 必须补齐 |
| --- | --- | --- |
| 没有项目级文件入口 | 用户必须从 Artifact 或聊天记录里找文件 | Project 级文件工作台入口 |
| 树接口缺少元信息 | 无法区分语言、二进制、修改时间、忽略原因 | 文件节点扩展元数据 |
| 文件操作不完整 | 不能新建、删除、重命名、移动、复制、上传、下载 | 完整资源管理器操作 |
| 编辑冲突不可见 | Agent 同时修改时，用户可能覆盖新内容 | `etag`、`mtime`、冲突 Diff 与三选一处理 |
| 预览类型有限 | 图片、PDF、Markdown、二进制、超大文件体验不一致 | 统一预览矩阵 |
| 变更感知弱 | Agent 改了文件后树不会稳定刷新 | WebSocket/EventBus 广播与前端局部刷新 |
| 引用闭环不够强 | 文件树无法直接引用文件或选区给 Agent | 文件/代码片段引用回聊天输入框 |
| 安全和权限粒度不足 | SaaS 团队场景缺少角色差异 | read/write/delete/download/action 权限分层 |

## 5. 产品目标

### 5.1 用户目标

1. 我可以在当前 Project 中看到完整、可信、可筛选的文件结构。
2. 我可以快速打开文件，知道它能编辑、只能预览，还是因为过大或二进制无法打开。
3. 我可以编辑小范围代码、Markdown、JSON、配置文件，并清楚知道是否已保存。
4. 我可以把某个文件、某段代码、某次变更直接交给 Agent 继续处理。
5. 我可以看到 Agent 最近改了哪些文件，并从文件树跳到 Diff、预览和聊天上下文。
6. 我可以在本机和云端 workspace 下获得一致的文件操作语义。
7. 我不会误删项目目录外的文件，也不会因为多人或 Agent 并发修改而悄悄覆盖内容。

### 5.2 产品成功指标

| 指标 | 目标 |
| --- | --- |
| 文件入口使用率 | 有 Artifact 的 Project 中，文件工作台打开率不低于 Artifact Card 打开率的 60% |
| 文件定位效率 | 从打开 Project 到打开目标文件的中位耗时低于 8 秒 |
| 编辑闭环成功率 | 用户打开文件、修改、保存、刷新仍正确的比例达到 99% |
| 冲突误覆盖率 | 因并发修改导致的静默覆盖为 0 |
| Agent 引用转化 | 文件或代码片段引用后成功发送给 Agent 的比例不低于 90% |
| 资源管理器错误可解释率 | 文件过大、权限不足、二进制不可编辑等错误均有明确可操作提示 |

## 6. 一次性交付范围

本功能上线时必须同时具备以下能力。任何缺项都不视为完整落地。

### 6.1 项目级文件资源管理器

| 能力 | 要求 |
| --- | --- |
| 树形浏览 | 展示目录、文件、展开折叠、懒加载子目录、空目录占位 |
| 快速筛选 | 支持文件名模糊搜索、路径搜索、扩展名筛选、最近修改筛选 |
| 文件状态 | 展示新增、修改、删除、未保存、冲突、Agent 正在改动、只读状态 |
| 文件操作 | 新建文件、新建目录、重命名、移动、复制路径、复制相对路径、删除、下载、上传 |
| 多选操作 | 多文件删除、下载为 zip、复制路径、移动到目录 |
| 忽略目录 | `.agenthub`、`.git`、`node_modules`、缓存目录默认隐藏，可在设置中显示“被忽略项摘要” |
| 排序 | 默认目录在前、文件在后，按名称排序；支持按最近修改和类型排序 |
| 面包屑 | 当前打开目录显示面包屑，可快速回到上级 |
| 右键菜单 | 桌面端支持上下文菜单，移动端转为长按或更多菜单 |
| 刷新 | 支持手动刷新和 Agent/系统变更后的自动局部刷新 |

### 6.2 文件打开与预览

| 文件类型 | 默认行为 | 关键细节 |
| --- | --- | --- |
| `.ts`、`.tsx`、`.js`、`.jsx`、`.css`、`.html`、`.json`、`.py`、`.md` | CodeMirror 编辑 | 自动识别语言，显示行列、字符数、编码、文件大小 |
| Markdown | 编辑和渲染双栏 | 支持同步滚动、标题锚点、GFM 表格 |
| HTML | 源码编辑和 IFrame 预览 | 支持工作区静态预览 URL，失败回退 `srcDoc` |
| 图片 | 图片预览 | 支持缩放、适配、打开原文件、下载 |
| PDF | 内嵌阅读 | 支持打开新标签页和下载 |
| Word、PPT、Excel | 元信息预览与下载 | 若已有渲染产物则直接复用；没有渲染产物时，本次必须提供清晰兜底 |
| 二进制 | 只读元信息页 | 展示类型、大小、修改时间、下载按钮，不允许文本编辑 |
| 超大文本 | 只读分块预览 | 不整文件读入编辑器，支持下载和让 Agent 分析 |
| 未知类型 | 安全只读 | 默认不执行，不内联危险脚本 |

### 6.3 文件编辑器

| 能力 | 要求 |
| --- | --- |
| 多标签页 | 支持同时打开多个文件，标签显示文件名、路径 tooltip、脏状态点 |
| 保存 | `Ctrl/Cmd + S` 保存当前文件，保存成功 toast，保存失败内联错误 |
| 自动保存策略 | 默认不自动保存，提供 Project 偏好设置。开启后仅对文本文件生效 |
| 查找替换 | 当前文件内查找、替换、大小写匹配、正则开关 |
| 格式化入口 | 对 JSON、Markdown、HTML、CSS 提供前端安全格式化；代码语言格式化交给 Agent |
| 只读模式 | 权限不足、二进制、超大文件、构建输出目录可只读打开 |
| 冲突处理 | 远端或 Agent 修改后，保存前弹出冲突比较，支持保留我的、使用工作区、手动合并 |
| 代码引用 | 选中代码后可“添加到对话”，携带 `projectId`、`filePath`、`startLine`、`endLine`、内容快照 |
| 文件引用 | 文件头部可一键“引用文件给 Agent”，不必选中文本 |
| Diff 入口 | 文件头部显示“查看最近变更”，打开同路径 Diff |
| 关闭保护 | 未保存文件关闭工作台或切换 Project 前必须确认 |

### 6.4 文件操作闭环

| 操作 | 交互要求 | 后端要求 |
| --- | --- | --- |
| 新建文件 | 当前目录内输入文件名，支持带子路径 | 创建空文件，自动打开编辑器 |
| 新建目录 | 输入目录名，创建后自动展开父目录 | 创建目录并广播变更 |
| 重命名 | 行内输入或菜单弹窗，保留扩展名提醒 | 原子 rename，路径冲突返回 409 |
| 移动 | 拖拽到目录或使用“移动到”弹窗 | 校验目标路径，不允许移动到自身子目录 |
| 删除 | 明确确认，显示文件数量和路径 | 进入回收策略或直接删除，必须有审计日志 |
| 上传 | 支持单文件和多文件，目录上传按浏览器能力降级 | 限制大小、类型、总量，返回逐项结果 |
| 下载 | 文件直接下载，目录或多选 zip 下载 | 使用流式 zip，不能加载整个大目录到内存 |
| 复制路径 | 复制 Project 相对路径 | 不暴露本机绝对路径给云端用户 |

删除策略：本机桌面版优先移动到 `.agenthub/trash` 并记录原路径，提供 24 小时内恢复入口；云端版进入 workspace trash 元数据区。若运行环境无法提供回收能力，删除确认文案必须明确“不可撤销”。

### 6.5 变更、版本与 Artifact 联动

| 场景 | 期望行为 |
| --- | --- |
| Agent 修改文件 | 文件树对应节点出现短暂高亮和状态标记，最近变更面板追加记录 |
| 用户保存文件 | 发布 `workspace.file_changed`，聊天输入可引用本次保存 |
| Artifact 指向文件 | 从 Artifact Card、文件树、审批卡打开同一路径时，使用同一编辑器和预览能力 |
| 文件树 Artifact | `file_tree` Artifact 中的文件行点击后打开真实文件，不只是预览变更摘要 |
| 恢复 Artifact 版本 | 如写回 workspace，文件树刷新，打开文件内容同步 |
| Snapshot Diff | 最近变更面板可基于 snapshot 展示 changed files，支持打开单文件 diff |
| 构建输出 | 构建产物目录默认只读，可预览、下载，不建议直接编辑 |

### 6.6 Chat 与 Agent 协作闭环

文件资源管理器不是独立工具，它必须和 AgentHub 的聊天范式咬合。

| 用户动作 | 聊天上下文结果 |
| --- | --- |
| 引用文件 | 输入框上方出现文件引用胶囊，发送时携带路径和文件元数据 |
| 引用选区 | 输入框上方出现代码引用胶囊，包含行号和内容快照 |
| 引用目录 | 携带目录路径和可见文件摘要，不自动注入全部内容 |
| 对文件发起任务 | 可从文件菜单选择“让 Agent 修改此文件”，自动聚焦聊天输入 |
| 对变更发起任务 | 可从最近变更中选择“解释这次修改”或“继续优化” |
| Agent 正在写文件 | 编辑器显示非阻塞提示，保存时进入冲突保护 |
| 任务完成 | 若有文件改动，文件树、最近变更、Artifact Card 一起刷新 |

发送给 Agent 的引用结构必须稳定，不能只拼文本。推荐扩展现有 `CodeReference`，并新增 `FileReference`：

```ts
interface FileReference {
  projectId: string;
  path: string;
  type: "file" | "directory";
  title: string;
  language?: string | null;
  size?: number;
  hash?: string;
  selected?: {
    startLine: number;
    endLine: number;
    content: string;
  } | null;
}
```

## 7. 信息架构与入口设计

### 7.1 主入口

文件工作台入口必须出现在 Project 上下文内，建议保留两个入口：

1. 左侧 Project 区当前项目行的文件图标按钮，tooltip 为“打开项目文件”。
2. 聊天区顶部当前 Project 标题旁的文件按钮，作为高频入口。

移动端入口放在会话标题栏的更多菜单中，打开全屏文件工作台。

### 7.2 工作台层级

```text
Project
  文件工作台
    顶部工具栏
    左侧文件资源管理器
    中部编辑/预览区
    右侧检查器
    底部状态栏
```

右侧检查器不是常驻 Drawer，而是文件工作台内部的信息区。它可折叠，负责显示文件详情、最近变更、引用信息、预览设置和 Agent 操作。

### 7.3 布局规格

| 区域 | 桌面端尺寸 | 作用 |
| --- | --- | --- |
| 顶部工具栏 | 高 48px 到 56px | 搜索、刷新、新建、上传、视图切换、关闭 |
| 文件树 | 宽 260px 到 320px，可拖拽调整 | 目录浏览和文件操作 |
| 编辑/预览区 | 自适应 | 多标签编辑器、预览器、Diff |
| 检查器 | 宽 280px，可折叠 | 元信息、变更、Agent 动作 |
| 状态栏 | 高 28px 到 32px | 路径、语言、行列、保存状态、权限 |

桌面端工作台默认是页面级 modal，最大宽度接近视口，建议 `h-[92dvh]`、`w-[min(1440px,96vw)]`。小屏和移动端使用全屏，不要在小视口中强行保留三列。

### 7.4 工作台视觉线框

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ 项目文件  /src/components        [搜索文件] [刷新] [+] [上传] [关闭]       │
├──────────────────────┬──────────────────────────────────────┬──────────────┤
│ 文件资源管理器        │ tabs: App.tsx  index.css  README.md   │ 文件详情      │
│                      ├──────────────────────────────────────┤              │
│ ▾ src                │ CodeMirror / Preview / Diff           │ 路径          │
│   ▾ components       │                                      │ 大小          │
│     ChatWindow.tsx   │                                      │ 最近修改      │
│     FileTree.tsx *   │                                      │ Agent 动作    │
│   api/client.ts      │                                      │ 最近变更      │
│ package.json         │                                      │              │
├──────────────────────┴──────────────────────────────────────┴──────────────┤
│ TSX  第 42 行，第 7 列  已修改  main workspace  Ctrl+S 保存                │
└────────────────────────────────────────────────────────────────────────────┘
```

## 8. UI 风格与组件设计

### 8.1 设计读法

本功能属于高频生产力工具界面，视觉密度高，动作反馈明确，审美应克制、清晰、贴近当前 AgentHub 桌面工作台。建议设计参数：

| 参数 | 建议 |
| --- | --- |
| 视觉变体 | 低到中，优先稳定布局，不做营销式构图 |
| 动效强度 | 低到中，仅用于状态反馈、展开折叠、保存成功、变更高亮 |
| 信息密度 | 高，文件树和编辑器需要支持长时间使用 |
| 主题 | 继续支持暗色和亮色，默认跟随现有主题 |
| 图标 | 继续使用 `lucide-react`，不混用图标族 |
| 圆角 | 遵循当前 `agenthub-card-radius`、`agenthub-panel-radius`，编辑器内部可使用 8px 到 12px 小圆角 |

### 8.2 设计 token 使用

新组件不得硬编码一套独立色板。应复用：

| 用途 | token |
| --- | --- |
| 背景 | `--ah-modal-bg`、`--ah-chat-bg`、`--ah-panel-bg` |
| 面板 | `--ah-card-bg`、`--ah-card-soft`、`--ah-panel-muted` |
| 边框 | `--ah-border`、`--ah-border-strong`、`--ah-border-hover` |
| 文字 | `--ah-text`、`--ah-text-strong`、`--ah-muted`、`--ah-faint` |
| 代码 | `--ah-code-bg`、`--ah-code-panel`、`--ah-code-header`、`--ah-code-text`、`--ah-code-border` |
| 状态 | `--ah-success`、`--ah-warning`、`--ah-danger`、`--ah-info` 及 soft token |
| 阴影 | `--ah-shadow` |

### 8.3 组件清单

| 组件 | 职责 |
| --- | --- |
| `ProjectFilesButton` | Project 文件入口按钮 |
| `ProjectFileWorkspaceModal` | 页面级文件工作台容器 |
| `ProjectFileToolbar` | 搜索、刷新、新建、上传、视图切换 |
| `ProjectFileTree` | 树渲染、懒加载、选中、展开、状态标记 |
| `ProjectFileTreeRow` | 文件行、图标、状态、右键菜单 |
| `ProjectFileContextMenu` | 文件/目录上下文操作 |
| `ProjectFileTabs` | 多文件 tab、脏状态、关闭保护 |
| `ProjectFileEditorPane` | CodeMirror 编辑器容器 |
| `ProjectFilePreviewPane` | Markdown、HTML、图片、PDF、二进制预览 |
| `ProjectFileDiffPane` | 单文件 Diff 与冲突比较 |
| `ProjectFileInspector` | 元信息、最近变更、引用、Agent 动作 |
| `ProjectFileStatusBar` | 路径、语言、行列、保存状态、权限 |
| `ProjectFileCommandDialog` | 新建、重命名、移动、删除等确认弹窗 |
| `ProjectFileUploadDialog` | 上传队列、进度、失败重试 |
| `ProjectFileConflictDialog` | 保存冲突解决 |

### 8.4 文件树视觉规则

1. 文件树使用紧凑列表，不使用大卡片。
2. 行高建议 30px 到 34px，目录行可略高。
3. 文件图标按类型区分，但颜色保持低饱和，不做彩虹文件树。
4. 当前选中文件使用 `agenthub-nav-active` 类似样式。
5. hover 显示更多按钮，不常驻过多操作图标。
6. 脏状态使用小圆点或文件名后 `*`，但状态点只表达真实状态。
7. Agent 刚修改的文件使用短暂淡入高亮，不持续闪烁。
8. 错误文件或冲突文件使用 warning/danger token，并在 inspector 说明原因。

### 8.5 编辑器视觉规则

1. CodeMirror 区域继续使用深色代码主题，即使外层为 light theme，也可保持代码暗色面板，以延续当前产品习惯。
2. 编辑器外壳不嵌套多层卡片，使用一层边框和 header 足够。
3. 标签页高度保持 36px 左右，按钮图标优先，文字只用于文件名。
4. 保存、关闭、引用、更多等动作使用图标按钮，并提供 `title` 和 `aria-label`。
5. 编辑器状态栏字体使用 monospace，显示信息保持一行，窄屏自动隐藏次要项。
6. 预览和编辑切换使用 segmented control，而不是普通文字按钮。

### 8.6 空、加载、错误状态

| 状态 | UI |
| --- | --- |
| 无 Project | 文件入口禁用，tooltip 提示“请先选择项目” |
| 空 workspace | 文件树显示新建文件、新建目录、上传入口 |
| 加载树 | 使用与文件行等高的 skeleton，不用大 spinner |
| 文件读取中 | 编辑区显示代码面板骨架 |
| 文件过大 | 显示大小、阈值、下载、让 Agent 分析按钮 |
| 权限不足 | 显示角色、缺少权限、申请或切换空间提示 |
| 路径不存在 | 提示文件可能已被 Agent 删除，提供刷新和查看最近变更 |
| 保存失败 | 编辑器顶部内联错误，toast 只作辅助 |
| 冲突 | 进入冲突 Dialog，不允许静默覆盖 |

## 9. 交互流程

### 9.1 打开文件工作台

1. 用户在当前 Project 点击文件入口。
2. 前端打开 `ProjectFileWorkspaceModal`。
3. 请求 Project 根目录树，展示 skeleton。
4. 若 Project 最近打开过文件，则恢复上次打开的 tabs、选中项和滚动位置。
5. 若无历史，则选中文件树根目录，编辑区展示空态和快捷动作。

### 9.2 打开文件

1. 用户点击文件树节点。
2. 前端先根据节点元信息判断预览策略。
3. 文本文件请求 `GET /files?path=`，携带 `etag` 和 `mtime`。
4. 成功后打开或激活 tab。
5. 编辑器显示内容、语言、行列、大小和保存状态。
6. 若文件不可编辑，进入只读预览，并在 inspector 说明原因。

### 9.3 保存文件

1. 用户修改内容，tab 和状态栏显示未保存。
2. 用户点击保存或按 `Ctrl/Cmd + S`。
3. 前端调用写入接口，携带 `baseEtag` 或 `baseMtime`。
4. 后端检查目标文件是否被其他 actor 修改。
5. 无冲突则写入文件，返回新 `etag`、`mtime`、`size`。
6. 前端清除脏状态，刷新节点元信息，发布 toast。
7. 有冲突则返回 409 和当前工作区内容摘要，前端打开冲突处理。

### 9.4 保存冲突处理

冲突弹窗必须包含三种操作：

| 操作 | 结果 |
| --- | --- |
| 保留我的内容 | 强制覆盖，后端记录 `force: true` 和审计日志 |
| 使用工作区内容 | 放弃本地未保存内容，编辑器刷新为最新内容 |
| 手动合并 | 打开三栏 Diff 或上下双栏，用户编辑合并后再次保存 |

默认焦点不能放在“强制覆盖”上，避免误操作。

### 9.5 新建文件

1. 用户在目录菜单点击新建文件。
2. 弹出小型命名浮层，默认聚焦输入框。
3. 输入支持 `src/foo.ts`，但必须校验非法字符和越界路径。
4. 创建成功后刷新父目录并打开新文件 tab。
5. 若文件已存在，展示 409 文案并保持输入。

### 9.6 删除文件

1. 用户点击删除或多选删除。
2. 弹窗展示路径列表、数量、是否可恢复。
3. 用户确认后调用删除接口。
4. 删除成功后关闭相关 tab，刷新父目录，最近变更记录新增删除项。
5. 若文件正在被 Agent 或其他用户编辑，提示风险，允许有权限用户继续确认。

### 9.7 引用文件给 Agent

1. 用户在文件树或编辑器头部点击“引用到对话”。
2. 文件工作台关闭或保持打开，根据用户偏好决定。
3. 聊天输入框上方出现引用胶囊。
4. 用户输入指令并发送。
5. 后端 prompt 注入文件引用结构，Agent 可读取真实 workspace 文件。
6. Agent 完成后，文件树刷新并显示新增变更。

### 9.8 Agent 修改后的刷新

1. 后端在 CLI Agent 执行前创建 workspace snapshot。
2. 执行后计算 changed files。
3. 发布 `workspace.file_changed` 和 `workspace.diff_ready`。
4. 前端收到事件后只刷新受影响目录和已打开文件元信息。
5. 若打开文件未修改，自动静默刷新内容。
6. 若打开文件有本地未保存改动，显示“工作区已有新版本”提示，保存时进入冲突处理。

## 10. 数据模型与 API 契约

### 10.1 文件节点模型

```ts
interface WorkspaceTreeNode {
  path: string;
  name: string;
  type: "file" | "dir";
  size: number;
  mtime: string;
  etag: string;
  mediaType?: string | null;
  extension?: string | null;
  language?: string | null;
  editable: boolean;
  previewable: boolean;
  readonlyReason?: string | null;
  ignored?: boolean;
  childrenLoaded?: boolean;
  hasChildren?: boolean;
  status?: "clean" | "modified" | "added" | "deleted" | "conflict" | "agent_running";
}
```

### 10.2 文件读取模型

```ts
interface WorkspaceFileRead {
  path: string;
  content: string;
  size: number;
  mtime: string;
  etag: string;
  mediaType: string;
  encoding: "utf-8" | "binary" | "unknown";
  editable: boolean;
  previewKind: "code" | "markdown" | "html" | "image" | "pdf" | "document" | "binary" | "large_text";
  readonlyReason?: string | null;
}
```

### 10.3 API 清单

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/projects/{projectId}/tree?subpath=&depth=&includeIgnored=` | 获取目录树 |
| GET | `/api/projects/{projectId}/files?path=` | 读取文件内容或元信息 |
| PUT | `/api/projects/{projectId}/files` | 保存文件内容 |
| POST | `/api/projects/{projectId}/files` | 新建文件 |
| POST | `/api/projects/{projectId}/directories` | 新建目录 |
| PATCH | `/api/projects/{projectId}/paths` | 重命名或移动文件/目录 |
| DELETE | `/api/projects/{projectId}/paths` | 删除文件/目录，支持批量 |
| POST | `/api/projects/{projectId}/uploads` | 上传文件 |
| GET | `/api/projects/{projectId}/download?path=` | 下载文件或目录 zip |
| GET | `/api/projects/{projectId}/search-files?q=&limit=` | 搜索文件名和路径 |
| GET | `/api/projects/{projectId}/file-diff?path=&baseRef=` | 获取单文件 Diff |
| POST | `/api/projects/{projectId}/file-reference` | 创建文件引用上下文，可选 |

现有接口可以兼容保留，但新前端应使用扩展后的契约。老的 `WorkspaceFile` 类型需要扩展 `mtime`、`etag`、`mediaType`、`editable` 等字段。

### 10.4 保存接口请求

```json
{
  "path": "src/App.tsx",
  "content": "...",
  "baseEtag": "sha256:abc",
  "baseMtime": "2026-06-23T21:00:00+08:00",
  "force": false
}
```

### 10.5 保存接口响应

```json
{
  "path": "src/App.tsx",
  "content": "...",
  "size": 1234,
  "mtime": "2026-06-23T21:10:00+08:00",
  "etag": "sha256:def",
  "changed": true
}
```

### 10.6 冲突响应

```json
{
  "detail": "file changed since read",
  "code": "WORKSPACE_FILE_CONFLICT",
  "path": "src/App.tsx",
  "baseEtag": "sha256:abc",
  "currentEtag": "sha256:def",
  "currentContent": "...",
  "currentMtime": "2026-06-23T21:09:00+08:00"
}
```

### 10.7 批量删除请求

```json
{
  "paths": ["src/old.ts", "tmp"],
  "useTrash": true
}
```

### 10.8 路径移动请求

```json
{
  "fromPath": "src/old.ts",
  "toPath": "src/new.ts",
  "overwrite": false
}
```

### 10.9 事件契约

| 事件 | 触发时机 | Payload |
| --- | --- | --- |
| `workspace.tree_changed` | 新建、删除、移动、上传、Agent 批量改动后 | `projectId`、`changes`、`actor` |
| `workspace.file_changed` | 单文件内容写入后 | `projectId`、`path`、`change`、`etag`、`mtime` |
| `workspace.file_conflict` | 保存冲突被检测到 | `projectId`、`path`、`currentEtag` |
| `workspace.file_opened` | 用户打开文件，可用于审计 | `projectId`、`path`、`userId` |
| `workspace.diff_ready` | snapshot diff 完成 | `projectId`、`changedFiles`、`baseRef` |

前端实时刷新优先通过 WebSocket。若 WebSocket 不可用，工作台打开期间每 15 秒轻量轮询树版本号。

## 11. 权限、安全与审计

### 11.1 权限矩阵

| 角色或场景 | 浏览 | 预览 | 编辑 | 删除 | 下载 | 上传 |
| --- | --- | --- | --- | --- | --- | --- |
| 本机桌面用户 | 是 | 是 | 是 | 是 | 是 | 是 |
| SaaS owner/admin | 是 | 是 | 是 | 是 | 是 | 是 |
| SaaS member | 是 | 是 | 是 | 视团队策略 | 是 | 是 |
| SaaS viewer | 是 | 是 | 否 | 否 | 视团队策略 | 否 |
| 归档 Project | 是 | 是 | 否 | 否 | 是 | 否 |
| 构建输出目录 | 是 | 是 | 否 | 否 | 是 | 否 |

### 11.2 路径安全

后端必须统一使用 workspace provider 的安全解析能力：

1. 所有路径必须是 Project workspace 内相对路径。
2. 拒绝绝对路径、`~`、盘符路径、`../` 越界路径。
3. 拒绝访问 `.agenthub` 内部运行数据，除非专门的安全读取接口允许。
4. 默认隐藏 `.git`、`node_modules`、缓存目录和构建缓存。
5. 对 symlink 必须解析真实路径，真实路径若越界则拒绝。
6. 本机绝对路径只在 local shell 必要位置展示，SaaS 永不暴露宿主路径。

### 11.3 文件类型安全

1. HTML 预览使用 sandboxed iframe，默认不允许 top navigation。
2. 二进制文件不尝试按文本写回。
3. 上传文件执行大小限制、文件数量限制和可选 MIME allowlist。
4. 下载目录使用 zip streaming，避免内存爆炸。
5. 图片和 PDF 使用浏览器原生预览，不执行未知脚本。

### 11.4 审计

以下动作必须记录审计日志：

| 动作 | 记录字段 |
| --- | --- |
| 文件创建 | actor、projectId、path、size |
| 文件保存 | actor、projectId、path、oldEtag、newEtag |
| 强制覆盖 | actor、projectId、path、baseEtag、currentEtag |
| 重命名/移动 | actor、fromPath、toPath |
| 删除 | actor、paths、useTrash |
| 上传 | actor、paths、sizes |
| 下载 | actor、path、type |

本机桌面版也应至少写入应用级日志，便于问题追踪。

## 12. 前端状态设计

建议新增 `fileWorkspaceStore`，不要把文件状态塞入聊天 store。

```ts
interface FileWorkspaceState {
  open: boolean;
  projectId: string | null;
  tree: WorkspaceTreeNode[];
  expandedPaths: string[];
  selectedPath: string | null;
  tabs: FileTab[];
  activeTabId: string | null;
  searchQuery: string;
  filter: FileFilter;
  inspectorOpen: boolean;
  pendingOperation: FileOperation | null;
}
```

### 12.1 Tab 模型

```ts
interface FileTab {
  id: string;
  projectId: string;
  path: string;
  title: string;
  content: string | null;
  originalContent: string | null;
  etag: string | null;
  mtime: string | null;
  dirty: boolean;
  readonly: boolean;
  previewKind: WorkspaceFileRead["previewKind"];
  language?: string | null;
  cursor?: { line: number; column: number };
  error?: string | null;
}
```

### 12.2 持久化偏好

按 Project 存储在 local storage 或用户偏好表：

| 偏好 | 默认 |
| --- | --- |
| 最近打开文件 | 最近 8 个 |
| 展开目录 | 保留 |
| inspector 是否展开 | 桌面端展开，移动端关闭 |
| 自动保存 | 关闭 |
| 显示隐藏文件 | 关闭 |
| 文件排序 | 名称 |

## 13. 后端服务设计

### 13.1 服务边界

建议新增 `WorkspaceFileService` 或扩展 `ProjectService` 中的文件职责，但要避免 ProjectService 继续膨胀。推荐结构：

```text
backend/app/services/
  workspace_file_service.py
  workspace_provider.py
  project_service.py
```

职责划分：

| 服务 | 职责 |
| --- | --- |
| `ProjectService` | Project 生命周期、workspace 绑定、Project 级授权 |
| `WorkspaceFileService` | 文件树、读写、操作、搜索、下载、上传、冲突检测 |
| `LocalWorkspaceProvider` | 本机路径安全解析和文件系统原语 |
| `CloudWorkspaceProvider` | 云端 workspace 映射、快照、导入恢复 |
| `FileChangeDetector` | snapshot、diff、changed files |

### 13.2 Provider 能力

Provider 层需要补齐：

| 方法 | 用途 |
| --- | --- |
| `list_tree(workspace_path, subpath, depth, include_ignored)` | 树和懒加载 |
| `stat_path(workspace_path, path)` | 元信息 |
| `read_text_file(workspace_path, path, range?)` | 文本读取 |
| `write_text_file(workspace_path, path, content, base_etag, force)` | 冲突安全写入 |
| `create_file(workspace_path, path)` | 新建文件 |
| `create_directory(workspace_path, path)` | 新建目录 |
| `move_path(workspace_path, from_path, to_path)` | 重命名和移动 |
| `delete_paths(workspace_path, paths, use_trash)` | 删除 |
| `search_paths(workspace_path, query, limit)` | 文件路径搜索 |
| `open_download_stream(workspace_path, path)` | 下载 |
| `save_upload(workspace_path, file, target_dir)` | 上传 |

### 13.3 大目录性能

1. 树接口默认只返回当前目录一层，`depth=1`。
2. 搜索接口使用受限遍历，跳过忽略目录，最多返回 200 条。
3. 文件树前端使用虚拟列表，避免一次渲染数千行。
4. 读取文件默认 10MB 阈值，超过后进入大文件预览或拒绝编辑。
5. 目录下载 zip 使用流式响应，限制单次最大文件数和总大小。

## 14. 与现有组件的融合

### 14.1 `FileEditorModal` 的处理

现有 `FileEditorModal` 可以作为底层编辑器能力来源，但不应直接承担项目文件工作台。建议：

1. 抽出 `CodeMirrorFileEditor` 继续复用。
2. 将 `FileEditorModal` 保留给 Artifact 简单编辑入口。
3. 新增 `ProjectFileWorkspaceModal`，内部复用 `CodeMirrorFileEditor`。
4. Artifact Card 点击编辑文件时，如果用户需要项目上下文，直接打开 `ProjectFileWorkspaceModal` 并定位到该文件。

### 14.2 `ArtifactCard` 的融合

Artifact Card 中的 `file_tree`、`code_diff`、`web_preview` 均应加上“在项目文件中打开”动作：

| Artifact 类型 | 行为 |
| --- | --- |
| `file_tree` | 打开文件工作台，展开相关路径，最近变更过滤为该 Artifact |
| `code_diff` | 打开 Diff Pane，关联真实文件 |
| `web_preview` | 打开预览 Pane，并可切换到源文件 |
| `document` | 若有 `filePath`，打开文件预览，否则保持 Artifact 预览 |

### 14.3 ProjectSidebar 的融合

Project 列表项右键菜单新增：

1. 打开项目文件。
2. 复制工作区路径，仅 local shell 显示。
3. 刷新文件索引。

Project 顶部区域可新增一个固定文件入口，但不要挤占“对话”和“添加 Agent”的主入口。

## 15. 响应式与多端适配

| Surface | 布局 |
| --- | --- |
| Desktop | 页面级大 modal，三列布局，支持拖拽调整文件树宽度 |
| SaaS Web | 同 Desktop，但权限和团队空间更严格 |
| Mobile | 全屏工作台，文件树、编辑器、检查器使用底部 tabs 切换 |

移动端不要求完整代码编辑舒适度，但必须可预览、搜索、引用、查看变更、处理审批关联文件。文本编辑可保留基本能力，复杂修改建议引导到 Agent。

## 16. 可访问性与键盘操作

### 16.1 键盘快捷键

| 快捷键 | 行为 |
| --- | --- |
| `Ctrl/Cmd + P` | 文件快速打开 |
| `Ctrl/Cmd + S` | 保存当前文件 |
| `Ctrl/Cmd + F` | 当前文件查找 |
| `Ctrl/Cmd + Shift + F` | 项目文件名和内容搜索入口，内容搜索可按能力开关 |
| `Ctrl/Cmd + W` | 关闭当前 tab |
| `Esc` | 关闭菜单、弹窗或退出搜索，不直接关闭有脏文件的工作台 |
| `Enter` | 打开选中文件或确认命名 |
| `Delete` | 删除选中项，必须弹确认 |

### 16.2 A11y 要求

1. 文件树使用 `tree`、`treeitem`、`aria-expanded`。
2. tab 使用 `tablist`、`tab`、`tabpanel`。
3. 所有 icon button 必须有 `aria-label` 和 `title`。
4. 错误和保存状态使用 `aria-live="polite"`。
5. Modal 打开后焦点锁定在工作台内，关闭后回到触发按钮。
6. 颜色状态必须配合文字或图标，不只依赖颜色。

## 17. 测试与验收

### 17.1 自动化测试

| 层级 | 必测 |
| --- | --- |
| 后端单元 | 路径安全、读写、冲突、删除、移动、忽略目录、symlink 越界 |
| 后端 API | tree、read、write、create、delete、move、upload、download、权限 |
| 前端组件 | 文件树展开、搜索、tab 脏状态、保存、冲突弹窗、引用到聊天 |
| 前端集成 | Artifact 打开文件工作台、Agent 变更刷新、Project 切换关闭保护 |
| E2E | 创建 Project、创建文件、编辑保存、预览、引用给 Agent、Agent 修改后刷新 |

### 17.2 手工验收场景

1. 新建空白 Project，打开文件工作台，新建 `README.md`，编辑保存，Markdown 预览正确。
2. 选择已有 React 项目，搜索 `App.tsx`，打开编辑，保存后工作区文件真实变化。
3. 打开 HTML 文件，预览 Pane 渲染正确，静态资源路径不越界。
4. 上传图片，文件树刷新，图片预览可打开和下载。
5. 删除文件，相关 tab 自动关闭，最近变更出现删除记录。
6. Agent 修改当前打开文件，用户无本地改动时编辑器自动刷新。
7. Agent 修改当前打开文件，用户有本地改动时保存触发冲突弹窗。
8. 从文件选区添加到对话，发送后 Agent 能接收文件路径和行号上下文。
9. SaaS viewer 打开文件只能预览不能保存，删除和上传不可用。
10. `../secret.txt`、绝对路径、symlink 越界均被后端拒绝。
11. `node_modules` 不默认展示，大目录打开不卡顿。
12. 移动端可打开文件工作台、搜索文件、预览、引用，不发生布局溢出。

### 17.3 验收通过标准

| 分类 | 标准 |
| --- | --- |
| 功能完整 | 本文一次性交付范围全部可用 |
| 数据正确 | 文件操作真实写入对应 Project workspace，Artifact 与文件路径一致 |
| 安全 | 路径越界、权限越权、二进制误编辑均被阻断 |
| 体验 | 暗色和亮色主题可用，桌面和移动布局不溢出 |
| 性能 | 1000 文件项目树浏览可交互，搜索响应可接受，编辑器打开 1MB 文本不卡顿 |
| 冲突 | 并发修改不静默覆盖 |
| 测试 | 新增测试全部通过，现有 Artifact、Project、Chat 回归不破坏 |

## 18. 交付实施清单

本清单是一次性交付的工程执行顺序，不代表拆期上线。

1. 扩展后端文件 API 契约，补齐 tree 元信息、保存冲突、文件操作、上传下载。
2. 抽离 workspace 文件服务，统一 local/cloud 文件能力和权限校验。
3. 扩展前端 API client 与类型定义。
4. 新增 `fileWorkspaceStore`，管理树、tab、选中、搜索、脏状态。
5. 新增 Project 文件入口和 `ProjectFileWorkspaceModal`。
6. 实现文件树、上下文菜单、快速搜索、基础文件操作。
7. 实现多标签编辑器、预览矩阵、状态栏和 inspector。
8. 接入保存、冲突处理、Diff、最近变更。
9. 接入文件/选区引用到聊天输入框。
10. 接入 WebSocket/EventBus 变更刷新。
11. 融合 Artifact Card 和审批卡入口。
12. 完成权限、审计、移动端适配、可访问性和测试。
13. 运行真实服务验收，修复发现的问题后一次性交付。

## 19. 风险与应对

| 风险 | 影响 | 应对 |
| --- | --- | --- |
| 大目录卡顿 | 文件工作台不可用 | 懒加载、虚拟列表、忽略目录、搜索限制 |
| 并发覆盖 | 用户或 Agent 修改丢失 | `etag` 冲突检测和强制覆盖审计 |
| 路径越界 | 安全事故 | Provider 统一安全解析和 symlink 检查 |
| 文件类型误判 | 乱码或错误编辑 | MIME、扩展名、内容嗅探结合，二进制只读 |
| 与 Artifact 入口割裂 | 用户困惑 | 所有入口最终定位到同一 Project path |
| 移动端编辑困难 | 小屏体验差 | 移动端强调预览、搜索、引用，编辑保留基础能力 |
| 权限规则复杂 | SaaS 越权 | TenantGuard 前置授权，API 测试覆盖角色矩阵 |
| 现有 modal 层级冲突 | UI 遮挡或焦点丢失 | 统一 z-index 约定和焦点管理 |

## 20. 最终完成定义

本功能完成时，用户在任意 Project 内都可以完成以下闭环：

```text
打开项目文件
  -> 浏览和搜索目录
  -> 打开任意支持文件
  -> 预览或编辑
  -> 保存并处理冲突
  -> 查看最近变更或 Diff
  -> 将文件或代码片段引用给 Agent
  -> Agent 修改 workspace
  -> 文件树、编辑器、Artifact 和聊天上下文同步刷新
```

只有当上述闭环在本机桌面、SaaS Web 权限场景和移动端降级场景中都可验证，且文件安全、冲突保护、异常状态和测试全部通过，才视为项目目录与文件编辑器功能完整落地。
