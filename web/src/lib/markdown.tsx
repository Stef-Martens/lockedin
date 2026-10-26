import type { ReactNode } from "react";

// The small slice of markdown the coach writes. Everything becomes React text, so raw HTML stays inert.
const INLINE = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/g;

function inline(text: string): ReactNode[] {
  return text.split(INLINE).filter(Boolean).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) return <code key={i}>{part.slice(1, -1)}</code>;
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) return <em key={i}>{part.slice(1, -1)}</em>;
    return part;
  });
}

type Kind = "p" | "ul" | "ol" | "table";
const kindOf = (line: string): Kind =>
  /^\s*[-*•] /.test(line) ? "ul" : /^\s*\d+[.)] /.test(line) ? "ol" : /^\s*\|/.test(line) ? "table" : "p";
const cells = (row: string) => row.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());

function block(kind: Kind, lines: string[], key: number): ReactNode {
  if (kind === "ul" || kind === "ol") {
    const items = lines.map((l, i) => <li key={i}>{inline(l.replace(/^\s*([-*•]|\d+[.)]) /, ""))}</li>);
    return kind === "ul" ? <ul key={key}>{items}</ul> : <ol key={key}>{items}</ol>;
  }
  if (kind === "table") {
    // The separator row (|---|---|) is the second line, or the first if the header went missing.
    const isSeparator = (row: string[]) => row.every((c) => /^:?-+:?$/.test(c));
    const rows = lines.map(cells).filter((r, i) => i > 1 || !isSeparator(r));
    const [head, ...body] = rows;
    if (!head) return null;
    return (
      <div key={key} className="table-wrap">
        <table className="table">
          <thead><tr>{head.map((c, i) => <th key={i}>{inline(c)}</th>)}</tr></thead>
          <tbody>{body.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{inline(c)}</td>)}</tr>)}</tbody>
        </table>
      </div>
    );
  }
  return <p key={key}>{lines.flatMap((l, i) => (i ? [<br key={`b${i}`} />, ...inline(l)] : inline(l)))}</p>;
}

export function renderMarkdown(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  let kind: Kind | null = null;
  let lines: string[] = [];
  const flush = () => {
    if (kind && lines.length) out.push(block(kind, lines, out.length));
    kind = null;
    lines = [];
  };
  for (const line of text.split("\n")) {
    const heading = /^#{1,4} (.*)/.exec(line.trim());
    if (!line.trim()) flush();
    else if (heading) {
      flush();
      out.push(<h3 key={out.length}>{inline(heading[1])}</h3>);
    } else {
      const k = kindOf(line);
      if (k !== kind) flush();
      kind = k;
      lines.push(line);
    }
  }
  flush();
  return out;
}
