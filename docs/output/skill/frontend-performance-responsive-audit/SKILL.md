---
name: frontend-performance-responsive-audit
description: Audits and optimizes frontend component structure, interaction responsiveness, popover/list rendering, and adaptive workspace layouts. Use when a user asks to inspect frontend UI performance, reduce slow component switching/rendering, fix unreasonable nesting, or ensure layouts adapt across desktop/tablet/mobile screens.
---

# Frontend Performance Responsive Audit

## Quick Start

Use this loop:

1. Read project rules first, especially git/deploy restrictions.
2. Identify frontend entry points, shells, and layout owner components.
3. Search for repeated portals, per-row menus, hidden-but-rendered panels, large mapped children, unstable refs, and missing flex overflow constraints.
4. Make narrow changes that preserve the current product direction.
5. Verify relevant frontend build modes.

```bash
rg -n "createPortal|FloatingMenu|map\\(|useMemo|useCallback|@media|overflow|min-width|min-height" frontend/src
npm run build:saas
npm run build:mobile
npm run build:local
git diff --check
```

## Audit Checklist

Component structure:

- Replace per-row portal/menu components with one shared active menu anchored to the active row button.
- Lazily render large collapsed children; delay unmount when a close animation must finish.
- Memoize visible/grouped/sorted lists that are switched frequently or expensive to derive.
- Avoid callbacks depending on large mutable objects; use refs for read-only cache checks.
- Keep dropdowns, context menus, and command UI in a high-z portal layer.
- Prefer in-place rename/delete/archive operations for list workflows.

Layout foundations:

- Add `min-width: 0` and `min-height: 0` at flex/grid workspace boundaries.
- Give scroll ownership to specific containers with `overflow-y: auto`.
- Keep shell, activity zone, workspace outer gap, and page root on the same theme background token.
- Give split panes deterministic width and `max-width`; on narrow screens, overlay secondary panes instead of squeezing primary work.
- Use borders and color layers for workbench surfaces; avoid heavy shadows and nested cards in core layout.

## Patterns

Single active menu:

```tsx
const [menuOpen, setMenuOpen] = useState<string | null>(null);
const buttonRefs = useRef<Record<string, HTMLButtonElement | null>>({});
const activeItem = useMemo(() => items.find((item) => item.id === menuOpen) ?? null, [items, menuOpen]);

<FloatingMenu open={Boolean(activeItem)} anchorElement={activeItem ? buttonRefs.current[activeItem.id] : null}>
  {activeItem && <MenuContent item={activeItem} />}
</FloatingMenu>
```

Animated lazy collapse:

```tsx
useEffect(() => {
  setRenderedIds((value) => new Set([...value, ...expandedIds]));
  const timeout = window.setTimeout(() => {
    setRenderedIds((value) => new Set([...value].filter((id) => expandedIds.has(id))));
  }, 230);
  return () => window.clearTimeout(timeout);
}, [expandedIds]);
```

Workbench baseline:

```css
.workbench-shell { min-width: 0; overflow: hidden; isolation: isolate; }
.workspace-main,
.workspace-frame,
.workspace-primary { min-width: 0; min-height: 0; }
.workspace-main { flex: 1 1 auto; overflow: hidden; }
.workspace-frame { position: relative; overflow: hidden; contain: layout paint; }
@media (max-width: 1023px) {
  .workspace-frame .secondary-pane {
    position: absolute;
    inset-block: 0;
    right: 0;
    z-index: 34;
    width: min(100%, 560px);
    max-width: 100%;
  }
}
```

## Delivery Checklist

- `git diff --check` has no whitespace errors.
- Relevant frontend builds pass.
- No unauthorized git commit, push, deploy, or destructive revert was performed.
- Final response lists touched files, verification, and residual risk such as existing large bundle chunks.
