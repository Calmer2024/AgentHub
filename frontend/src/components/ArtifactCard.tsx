import { useState } from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";

interface Artifact {
  id: string;
  type: string;
  title: string;
  content: string;
  status: string;
}

interface Props {
  artifact: Artifact;
}

export function ArtifactCard({ artifact }: Props) {
  const [fullscreen, setFullscreen] = useState(false);

  const card = (
    <div className="mt-2 border border-gray-200 rounded-xl overflow-hidden bg-white">
      <div className="flex items-center justify-between px-3 py-2 bg-gray-50 border-b border-gray-200">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-gray-700">
            {artifact.type === "code_diff" ? "代码" : artifact.type === "web_preview" ? "网页" : "文档"}
          </span>
          {artifact.status === "rendering" && <span className="w-2 h-2 bg-yellow-400 rounded-full animate-pulse" />}
          {artifact.status === "ready" && <span className="w-2 h-2 bg-green-500 rounded-full" />}
          {artifact.status === "error" && <span className="w-2 h-2 bg-red-500 rounded-full" />}
        </div>
        <button onClick={() => setFullscreen(true)} className="text-xs text-blue-600 hover:underline">全屏</button>
      </div>
      <div className="p-3 max-h-48 overflow-auto">
        {artifact.type === "code_diff" ? (
          <SyntaxHighlighter language="python" style={oneDark} customStyle={{ borderRadius: "0.5rem", fontSize: "0.75rem", margin: 0 }}>
            {artifact.content}
          </SyntaxHighlighter>
        ) : artifact.type === "web_preview" ? (
          <iframe srcDoc={artifact.content} sandbox="allow-scripts" className="w-full h-40 border-0 rounded" title="preview" />
        ) : (
          <pre className="text-xs whitespace-pre-wrap">{artifact.content}</pre>
        )}
      </div>
    </div>
  );

  return (
    <>
      {card}
      {fullscreen && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-8" onClick={() => setFullscreen(false)}>
          <div className="bg-white rounded-2xl w-full max-w-4xl max-h-[90vh] overflow-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-4 py-3 border-b">
              <h3 className="font-semibold">{artifact.title || "产物预览"}</h3>
              <button onClick={() => setFullscreen(false)} className="text-gray-400 hover:text-gray-600">x</button>
            </div>
            <div className="p-4">
              {artifact.type === "code_diff" ? (
                <SyntaxHighlighter language="python" style={oneDark} customStyle={{ borderRadius: "0.75rem" }}>
                  {artifact.content}
                </SyntaxHighlighter>
              ) : artifact.type === "web_preview" ? (
                <iframe srcDoc={artifact.content} sandbox="allow-scripts" className="w-full h-[75vh] border rounded-xl" />
              ) : (
                <pre className="whitespace-pre-wrap text-sm">{artifact.content}</pre>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
