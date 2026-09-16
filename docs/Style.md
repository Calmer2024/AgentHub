# AgentHub 组件样式规范

本规范约束 AgentHub 桌面端和 Web 端的基础交互组件。新增组件应优先复用本文指定的语义类与公共组件，不在业务组件中重新拼装另一套 hover、输入框或菜单视觉。

## 1. 按钮

### 1.1 工具按钮

- 工具栏、标题栏和卡片操作区统一使用纯图标按钮，不在按钮内部并排展示说明文字。
- 可访问名称必须通过 `aria-label` 提供，鼠标提示通过 `title` 提供。
- 默认无边框、透明背景；hover 使用侧边栏“对话”“好友”按钮相同的纯色背景 `--ah-activity-hover`。
- 选中状态使用 `--ah-activity-selected`，不增加边框、描边、外发光或位移动画。
- 推荐尺寸为 `32 × 32` 或 `36 × 36`，圆角根据所在区域使用 `rounded-lg` 或 `rounded-full`。
- 统一使用 `.agenthub-icon-button`；选中时附加 `.agenthub-file-entry-active`。

```tsx
<button
  type="button"
  className="agenthub-icon-button inline-flex h-9 w-9 items-center justify-center rounded-full"
  aria-label="搜索"
  title="搜索"
>
  <Search size={15} />
</button>
```

提交、确认、危险操作等必须表达明确业务含义的按钮可以保留文字，但 hover 仍不得产生边框、外发光或位移动画。

## 2. 搜索框与筛选器

- 搜索框在默认、hover、focus 和输入状态下均不显示 border、ring 或阴影。
- 背景使用 `--ah-activity-subtle`；hover/focus 使用 `--ah-activity-hover`。
- 搜索图标位于左侧，输入文本区域保持透明。
- 搜索框统一使用 `.agenthub-search-field`。
- 紧邻搜索框的筛选触发器使用相同表面，统一使用 `.agenthub-filter-trigger`。
- 禁止在业务界面直接使用原生 `<select>` 作为可见筛选控件。

```tsx
<div className="relative">
  <Search className="agenthub-muted pointer-events-none absolute left-3 top-1/2 -translate-y-1/2" />
  <input className="agenthub-search-field h-9 rounded-lg pl-9 pr-3 outline-none" />
</div>
```

## 3. 下拉菜单

- 下拉菜单以消息“更多”菜单为唯一视觉基准。
- 菜单浮层统一使用 `.agenthub-menu` 和 `.agenthub-popover`，无边框，使用菜单背景和统一阴影。
- 菜单项使用纯色 hover、无 border，圆角为 `rounded-xl`，标准内边距为 `px-3 py-2`。
- 选择类控件统一使用 `MenuSelect`；搜索筛选场景传入 `variant="filter"`。
- 菜单应由 `FloatingMenu` 渲染到 portal，以统一处理视口边缘、滚动和层级。

```tsx
<MenuSelect
  value={level}
  options={levelOptions}
  onChange={setLevel}
  ariaLabel="日志级别"
  variant="filter"
/>
```
