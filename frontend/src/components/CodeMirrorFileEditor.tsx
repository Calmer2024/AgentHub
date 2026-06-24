import CodeMirror, { type ReactCodeMirrorRef } from "@uiw/react-codemirror";
import { javascript } from "@codemirror/lang-javascript";
import { html } from "@codemirror/lang-html";
import { css } from "@codemirror/lang-css";
import { json } from "@codemirror/lang-json";
import { markdown } from "@codemirror/lang-markdown";
import { python } from "@codemirror/lang-python";
import { type Extension } from "@codemirror/state";
import { EditorView, type ViewUpdate } from "@codemirror/view";
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { tags as t } from "@lezer/highlight";
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
    backgroundColor: "var(--ah-code-bg)",
    color: "var(--ah-code-text)",
    fontSize: "12px",
  },
  "&.cm-focused": {
    outline: "none",
  },
  ".cm-scroller": {
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
    lineHeight: "24px",
    overflow: "auto",
    scrollbarColor: "var(--ah-scrollbar-thumb) transparent",
    scrollbarWidth: "thin",
  },
  ".cm-scroller::-webkit-scrollbar": {
    width: "10px",
    height: "10px",
  },
  ".cm-scroller::-webkit-scrollbar-track": {
    background: "transparent",
  },
  ".cm-scroller::-webkit-scrollbar-thumb": {
    background: "var(--ah-scrollbar-thumb)",
    border: "3px solid transparent",
    borderRadius: "999px",
    backgroundClip: "padding-box",
  },
  ".cm-scroller::-webkit-scrollbar-thumb:hover": {
    background: "var(--ah-scrollbar-thumb-hover)",
    backgroundClip: "padding-box",
  },
  ".cm-content": {
    minWidth: "max-content",
    minHeight: "100%",
    padding: "12px 0",
    caretColor: "var(--ah-text-strong)",
  },
  ".cm-line": {
    padding: "0 14px",
  },
  ".cm-gutters": {
    backgroundColor: "var(--ah-code-panel)",
    borderRight: "1px solid var(--ah-code-border)",
    color: "var(--ah-code-muted)",
  },
  ".cm-activeLine": {
    backgroundColor: "color-mix(in srgb, var(--ah-accent-strong) 14%, transparent)",
  },
  ".cm-activeLineGutter": {
    backgroundColor: "color-mix(in srgb, var(--ah-accent-strong) 14%, transparent)",
    color: "var(--ah-text-strong)",
  },
  ".cm-cursor": {
    borderLeftColor: "var(--ah-text-strong)",
  },
  ".cm-selectionBackground, &.cm-focused .cm-selectionBackground": {
    backgroundColor: "color-mix(in srgb, var(--ah-info) 28%, transparent)",
  },
  ".cm-searchMatch": {
    backgroundColor: "color-mix(in srgb, var(--ah-warning) 30%, transparent)",
    outline: "1px solid color-mix(in srgb, var(--ah-warning) 64%, transparent)",
  },
});

const syntaxTheme = HighlightStyle.define([
  { tag: [t.keyword, t.operatorKeyword], color: "var(--ah-syntax-keyword)" },
  { tag: [t.name, t.deleted, t.character, t.macroName], color: "var(--ah-syntax-variable)" },
  { tag: [t.propertyName, t.attributeName], color: "var(--ah-syntax-property)" },
  { tag: [t.function(t.variableName), t.labelName], color: "var(--ah-syntax-function)" },
  { tag: [t.color, t.constant(t.name), t.standard(t.name)], color: "var(--ah-syntax-constant)" },
  { tag: [t.definition(t.name), t.separator], color: "var(--ah-code-text)" },
  { tag: [t.typeName, t.className], color: "var(--ah-syntax-type)" },
  { tag: [t.number, t.bool, t.null], color: "var(--ah-syntax-number)" },
  { tag: [t.string, t.special(t.string), t.regexp], color: "var(--ah-syntax-string)" },
  { tag: [t.comment, t.meta], color: "var(--ah-syntax-comment)" },
  { tag: [t.heading, t.strong], color: "var(--ah-syntax-heading)", fontWeight: "600" },
  { tag: [t.link], color: "var(--ah-info)", textDecoration: "underline" },
  { tag: [t.invalid], color: "var(--ah-danger)" },
]);

export function CodeMirrorFileEditor({
  value,
  language,
  editorRef,
  onChange,
  onUpdate,
}: Props) {
  const extensions = useMemo(() => [
    ...languageExtensions(language),
    syntaxHighlighting(syntaxTheme),
  ], [language]);

  return (
    <CodeMirror
      ref={editorRef as MutableRefObject<ReactCodeMirrorRef>}
      value={value}
      height="100%"
      theme={editorTheme}
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
