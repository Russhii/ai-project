import Editor, { type OnMount } from "@monaco-editor/react";
import { useEffect, useRef } from "react";
import type { Sym } from "../api";

const LANG: Record<string, string> = { py: "python", js: "javascript", ts: "typescript", json: "json", md: "markdown", yml: "yaml", yaml: "yaml", html: "html", css: "css", sql: "sql", sh: "shell", toml: "ini" };

export default function CodePane({ path, content, selected }: { path: string; content: string; selected: Sym | null }) {
  const editorRef = useRef<Parameters<OnMount>[0] | null>(null);
  const decoRef = useRef<{ clear: () => void } | null>(null);

  const highlight = () => {
    const ed = editorRef.current;
    if (!ed) return;
    decoRef.current?.clear();
    decoRef.current = null;
    if (selected && selected.file_path === path) {
      decoRef.current = ed.createDecorationsCollection([{
        range: { startLineNumber: selected.start_line, startColumn: 1, endLineNumber: selected.end_line, endColumn: 1 },
        options: { isWholeLine: true, className: "sym-highlight" },
      }]);
      ed.revealLineInCenter(selected.start_line);
    }
  };
  useEffect(highlight, [selected, path, content]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Editor
      height="100%"
      theme="vs"
      language={LANG[path.split(".").pop() ?? ""] ?? "plaintext"}
      path={path}
      value={content}
      onMount={(ed) => { editorRef.current = ed; highlight(); }}
      options={{ readOnly: true, minimap: { enabled: false }, fontSize: 13, fontFamily: "JetBrains Mono, monospace", scrollBeyondLastLine: false, padding: { top: 12 }, renderLineHighlight: "none" }}
    />
  );
}
