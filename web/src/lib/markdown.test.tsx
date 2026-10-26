import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { renderMarkdown } from "./markdown";

const html = (md: string) => renderToStaticMarkup(<>{renderMarkdown(md)}</>);

describe("renderMarkdown", () => {
  it("renders paragraphs with bold, italic and code", () => {
    expect(html("Do **3 × 10** at *easy* pace, then `Z2`.\n\nNext para")).toBe(
      "<p>Do <strong>3 × 10</strong> at <em>easy</em> pace, then <code>Z2</code>.</p><p>Next para</p>");
  });

  it("renders lists that follow a lead-in line", () => {
    expect(html("Plan:\n- Bench 4 × 6\n- Dips 3 × 10\n1. one\n2. two")).toBe(
      "<p>Plan:</p><ul><li>Bench 4 × 6</li><li>Dips 3 × 10</li></ul><ol><li>one</li><li>two</li></ol>");
  });

  it("renders headings and simple tables", () => {
    expect(html("### This week\n| Day | Session |\n|---|---|\n| Mon | Gym |")).toBe(
      '<h3>This week</h3><div class="table-wrap"><table class="table"><thead><tr><th>Day</th><th>Session</th></tr></thead>' +
      "<tbody><tr><td>Mon</td><td>Gym</td></tr></tbody></table></div>");
  });

  it("keeps raw HTML as text", () => {
    expect(html('<img src=x onerror="alert(1)"> **hi**')).toBe(
      "<p>&lt;img src=x onerror=&quot;alert(1)&quot;&gt; <strong>hi</strong></p>");
  });

  it("keeps line breaks inside a paragraph", () => {
    expect(html("line one\nline two")).toBe("<p>line one<br/>line two</p>");
  });

  it("survives a table that starts with its separator row and keeps rows that start with dashes", () => {
    expect(() => html("|---|---|\n| a | b |")).not.toThrow();
    expect(html("| Set | Note |\n|---|---|\n| -- | rest |")).toContain("<td>--</td>");
  });
});
