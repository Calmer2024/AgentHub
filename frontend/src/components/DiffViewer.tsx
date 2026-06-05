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
  if (type === "add") return "bg-emerald-500/[0.13] text-emerald-100";
  if (type === "remove") return "bg-rose-500/[0.14] text-rose-100";
  if (type === "hunk") return "bg-[#122d4a] text-[#8fc7ff]";
  if (type === "file") return "bg-[#202a35] text-[#d2d8e0]";
  return "bg-[#111820] text-[#c8d1dc]";
}

function gutterClasses(type: DiffLineType) {
  if (type === "add") return "text-emerald-300/75";
  if (type === "remove") return "text-rose-300/75";
  if (type === "hunk") return "text-[#8fc7ff]/80";
  return "text-[#6f7b88]";
}

export function DiffViewer({ diff, compact = false, title }: Props) {
  if (!diff) {
    return (
      <div className="overflow-hidden rounded-md border border-[#30363d] bg-[#0d1117]">
        <div className="px-3 py-4 text-xs text-[#8b949e]">选择两个版本查看差异</div>
      </div>
    );
  }

  const rows = parseUnifiedDiff(buildUnifiedText(diff));
  const additions = rows.filter((row) => row.type === "add").length;
  const removals = rows.filter((row) => row.type === "remove").length;
  const visibleRows = compact ? rows.slice(0, 18) : rows;
  const hiddenRows = rows.length - visibleRows.length;

  return (
    <div className="overflow-hidden rounded-md border border-[#30363d] bg-[#0d1117] text-xs shadow-[0_18px_45px_rgba(0,0,0,0.24)]">
      <div className="flex items-center justify-between gap-3 border-b border-[#30363d] bg-[#161b22] px-3 py-2">
        <div className="min-w-0 font-medium text-[#c9d1d9]">
          {title ?? `v${diff.fromVersion} → v${diff.toVersion}`}
        </div>
        <div className="flex shrink-0 items-center gap-2 font-mono text-[11px]">
          <span className="text-emerald-300">+{additions}</span>
          <span className="text-rose-300">-{removals}</span>
        </div>
      </div>
      <div className={compact ? "max-h-64 overflow-hidden" : "max-h-[68vh] overflow-auto"}>
        <table className="w-full border-collapse font-mono text-[11px] leading-5">
          <tbody>
            {visibleRows.map((row, index) => (
              <tr key={`${index}:${row.text}`} className={lineClasses(row.type)}>
                <td className={`w-10 select-none border-r border-[#30363d] px-2 text-right ${gutterClasses(row.type)}`}>
                  {row.oldLine ?? ""}
                </td>
                <td className={`w-10 select-none border-r border-[#30363d] px-2 text-right ${gutterClasses(row.type)}`}>
                  {row.newLine ?? ""}
                </td>
                <td className="w-6 select-none px-2 text-center text-[#8b949e]">
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
          <div className="border-t border-[#30363d] bg-[#161b22] px-3 py-2 font-mono text-[11px] text-[#8b949e]">
            还有 {hiddenRows} 行，点击打开完整 diff
          </div>
        )}
      </div>
    </div>
  );
}
