import { useRef, useState } from "react";

interface Props {
  content: string;
  loading?: boolean;
  error?: string | null;
  onPreview: (
    selection: string,
    instruction: string,
    editType: "replace" | "insert_after" | "insert_before" | "delete",
  ) => void;
}

export function CodeSelector({ content, loading = false, error = null, onPreview }: Props) {
  const textRef = useRef<HTMLTextAreaElement | null>(null);
  const [selection, setSelection] = useState("");
  const [instruction, setInstruction] = useState("");
  const [editType, setEditType] = useState<"replace" | "insert_after" | "insert_before" | "delete">("replace");

  const captureSelection = () => {
    const el = textRef.current;
    if (!el) return;
    const selected = content.slice(el.selectionStart, el.selectionEnd);
    setSelection(selected);
  };

  const canSubmit = selection.trim().length > 0 && instruction.trim().length > 0 && !loading;

  return (
    <div className="rounded-lg border border-slate-200 bg-white overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-3 py-2">
        <div className="text-xs font-medium text-slate-700">在线编辑</div>
        <div className="text-xs text-slate-500">已选 {selection.length} 字符</div>
      </div>
      <div className="grid gap-3 p-3">
        <textarea
          ref={textRef}
          value={content}
          readOnly
          onMouseUp={captureSelection}
          onKeyUp={captureSelection}
          className="h-44 resize-none rounded-md border border-slate-200 bg-slate-950 px-3 py-2 font-mono text-xs leading-5 text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
          spellCheck={false}
        />
        <div className="grid gap-2 md:grid-cols-[160px_1fr_auto]">
          <select
            value={editType}
            onChange={(event) => setEditType(event.target.value as typeof editType)}
            className="rounded-md border border-slate-200 bg-white px-2 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="replace">替换</option>
            <option value="insert_after">后插入</option>
            <option value="insert_before">前插入</option>
            <option value="delete">删除</option>
          </select>
          <input
            value={instruction}
            onChange={(event) => setInstruction(event.target.value)}
            placeholder="描述修改意图"
            className="min-w-0 rounded-md border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            type="button"
            disabled={!canSubmit}
            onClick={() => onPreview(selection, instruction, editType)}
            className="rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            生成 Diff
          </button>
        </div>
        {error && <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">{error}</div>}
      </div>
    </div>
  );
}
