import type { ArtifactDiff } from "../types";

interface Props {
  diff: ArtifactDiff | null;
  compact?: boolean;
  title?: string;
}

type DiffLineType = "context" | "add" | "remove" | "hunk" | "file";

interface DiffLine {
  type: DiffLineType;
  text: string;
  oldLine: number | null;
  newLine: number | null;
}

function classifyLine(text: string): DiffLineType {
  if (text.startsWith("@@")) return "hunk";
  if (text.startsWith("+++") || text.startsWith("---") || text.startsWith("diff --git")) return "file";
  if (text.startsWith("+")) return "add";
  if (text.startsWith("-")) return "remove";
  return "context";
}

function parseHunkStart(text: string): { oldLine: number; newLine: number } | null {
  const match = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(text);
  if (!match) return null;
  return {
    oldLine: Number(match[1]),
    newLine: Number(match[2]),
  };
}

function buildUnifiedText(diff: ArtifactDiff): string {
  if (diff.diff.trim()) return diff.diff;

  const oldLines = diff.oldContent.split("\n");
  const newLines = diff.newContent.split("\n");
  const rows = [`@@ -1,${oldLines.length} +1,${newLines.length} @@`];
  oldLines.forEach((line) => rows.push(`-${line}`));
  newLines.forEach((line) => rows.push(`+${line}`));
  return rows.join("\n");
}

function parseUnifiedDiff(text: string): DiffLine[] {
  let oldLine = 1;
  let newLine = 1;

  return text.split("\n").map((line) => {
    const type = classifyLine(line);
    const hunk = type === "hunk" ? parseHunkStart(line) : null;
    if (hunk) {
      oldLine = hunk.oldLine;
      newLine = hunk.newLine;
      return { type, text: line, oldLine: null, newLine: null };
    }
    if (type === "file") {
      return { type, text: line, oldLine: null, newLine: null };
    }
    if (type === "add") {
      const row = { type, text: line, oldLine: null, newLine };
      newLine += 1;
      return row;
    }
    if (type === "remove") {
      const row = { type, text: line, oldLine, newLine: null };
      oldLine += 1;
      return row;
    }
    const row = { type, text: line, oldLine, newLine };
    oldLine += 1;
    newLine += 1;
    return row;
  });
}

function lineClasses(type: DiffLineType) {
  if (type === "add") return "bg-[color:var(--ah-diff-add-bg)] text-[color:var(--ah-diff-add-text)]";
  if (type === "remove") return "bg-[color:var(--ah-diff-remove-bg)] text-[color:var(--ah-diff-remove-text)]";
  if (type === "hunk") return "bg-[color:var(--ah-diff-hunk-bg)] text-[color:var(--ah-text-strong)]";
  if (type === "file") return "bg-[color:var(--ah-code-header)] text-[color:var(--ah-code-text)]";
  return "bg-[color:var(--ah-code-panel)] text-[color:var(--ah-code-text)]";
}

function gutterClasses(type: DiffLineType) {
  if (type === "add") return "text-[color:var(--ah-success)]";
  if (type === "remove") return "text-[color:var(--ah-danger)]";
  if (type === "hunk") return "text-[color:var(--ah-text-strong)]";
  return "text-[color:var(--ah-code-muted)]";
}

export function DiffViewer({ diff, compact = false, title }: Props) {
  if (!diff) {
    return (
      <div className="agenthub-code-surface min-w-0 max-w-full overflow-hidden rounded-2xl border">
        <div className="px-3 py-4 text-xs text-[color:var(--ah-code-muted)]">选择两个版本查看差异</div>
      </div>
    );
  }

  const rows = parseUnifiedDiff(buildUnifiedText(diff));
  const additions = rows.filter((row) => row.type === "add").length;
  const removals = rows.filter((row) => row.type === "remove").length;
  const visibleRows = compact ? rows.slice(0, 18) : rows;
  const hiddenRows = rows.length - visibleRows.length;

  return (
    <div className="agenthub-code-surface min-w-0 max-w-full overflow-hidden rounded-2xl border text-xs shadow-[0_18px_45px_rgba(0,0,0,0.18)]">
      <div className="agenthub-code-header flex min-w-0 items-center justify-between gap-3 border-b px-3 py-2">
        <div className="min-w-0 truncate font-medium">
          {title ?? `v${diff.fromVersion} → v${diff.toVersion}`}
        </div>
        <div className="flex shrink-0 items-center gap-2 font-mono text-[11px]">
          <span className="text-[color:var(--ah-success)]">+{additions}</span>
          <span className="text-[color:var(--ah-danger)]">-{removals}</span>
        </div>
      </div>
      <div className={compact ? "max-h-64 overflow-hidden" : "max-h-[68vh] overflow-auto"}>
        <table className="w-full border-collapse font-mono text-[11px] leading-5">
          <tbody>
            {visibleRows.map((row, index) => (
              <tr key={`${index}:${row.text}`} className={lineClasses(row.type)}>
                <td className={`w-10 select-none border-r px-2 text-right ${gutterClasses(row.type)}`} style={{ borderColor: "var(--ah-code-border)" }}>
                  {row.oldLine ?? ""}
                </td>
                <td className={`w-10 select-none border-r px-2 text-right ${gutterClasses(row.type)}`} style={{ borderColor: "var(--ah-code-border)" }}>
                  {row.newLine ?? ""}
                </td>
                <td className="w-6 select-none px-2 text-center text-[color:var(--ah-code-muted)]">
                  {row.type === "add" ? "+" : row.type === "remove" ? "-" : " "}
                </td>
                <td className="min-w-0 whitespace-pre-wrap break-words py-0.5 pr-3">
                  {row.type === "add" || row.type === "remove" ? row.text.slice(1) : row.text}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {hiddenRows > 0 && (
          <div className="agenthub-code-header border-t px-3 py-2 font-mono text-[11px]">
            还有 {hiddenRows} 行，点击打开完整差异
          </div>
        )}
      </div>
    </div>
  );
}
