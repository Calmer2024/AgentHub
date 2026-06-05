import CodeMirror, { type ReactCodeMirrorRef } from "@uiw/react-codemirror";
import { javascript } from "@codemirror/lang-javascript";
import { html } from "@codemirror/lang-html";
import { css } from "@codemirror/lang-css";
import { json } from "@codemirror/lang-json";
import { markdown } from "@codemirror/lang-markdown";
import { python } from "@codemirror/lang-python";
import { oneDark } from "@codemirror/theme-one-dark";
import { type Extension } from "@codemirror/state";
import { EditorView, type ViewUpdate } from "@codemirror/view";
import { useMemo, type MutableRefObject } from "react";

interface Props {
  value: string;
  language: string;
  editorRef: MutableRefObject<ReactCodeMirrorRef | null>;
  onChange: (value: string) => void;
  onUpdate: (update: ViewUpdate) => void;
}

function languageExtensions(language: string): Extension[] {
  if (language === "tsx") return [javascript({ jsx: true, typescript: true })];
  if (language === "ts") return [javascript({ typescript: true })];
  if (language === "jsx") return [javascript({ jsx: true })];
  if (language === "js") return [javascript()];
  if (language === "html") return [html()];
  if (language === "css") return [css()];
  if (language === "json") return [json()];
  if (language === "markdown") return [markdown()];
  if (language === "python") return [python()];
  return [];
}

const editorTheme = EditorView.theme({
  "&": {
    height: "100%",
    backgroundColor: "#0d1117",
    color: "#d6deeb",
    fontSize: "12px",
  },
  "&.cm-focused": {
    outline: "none",
  },
  ".cm-scroller": {
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
    lineHeight: "24px",
  },
  ".cm-content": {
    minHeight: "100%",
    padding: "12px 0",
    caretColor: "#f0f6fc",
  },
  ".cm-line": {
    padding: "0 14px",
  },
  ".cm-gutters": {
    backgroundColor: "#0b1016",
    borderRight: "1px solid #30363d",
    color: "#6e7681",
  },
  ".cm-activeLine": {
    backgroundColor: "#162033",
  },
  ".cm-activeLineGutter": {
    backgroundColor: "#162033",
    color: "#c9d1d9",
  },
  ".cm-cursor": {
    borderLeftColor: "#f0f6fc",
  },
  ".cm-selectionBackground, &.cm-focused .cm-selectionBackground": {
    backgroundColor: "#264f78",
  },
  ".cm-searchMatch": {
    backgroundColor: "#9e6a03",
    outline: "1px solid #d29922",
  },
});

export function CodeMirrorFileEditor({
  value,
  language,
  editorRef,
  onChange,
  onUpdate,
}: Props) {
  const extensions = useMemo(() => [
    ...languageExtensions(language),
    oneDark,
    editorTheme,
  ], [language]);

  return (
    <CodeMirror
      ref={editorRef as MutableRefObject<ReactCodeMirrorRef>}
      value={value}
      height="100%"
      theme="dark"
      extensions={extensions}
      basicSetup={{
        lineNumbers: true,
        highlightActiveLine: true,
        highlightActiveLineGutter: true,
        foldGutter: true,
        bracketMatching: true,
        closeBrackets: true,
        autocompletion: true,
        searchKeymap: true,
      }}
      onChange={onChange}
      onUpdate={onUpdate}
      className="min-h-0 min-w-0 flex-1"
      aria-label="IDE 代码编辑器"
    />
  );
}
