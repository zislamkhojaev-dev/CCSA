import { describe, expect, it } from "vitest";
import { highlightTranscriptParts } from "./highlightTranscript";

describe("highlightTranscriptParts", () => {
  it("keeps unsafe HTML as text nodes", () => {
    const parts = highlightTranscriptParts('<img src=x onerror=alert(1)> спасибо');
    expect(parts.some((p) => p.kind === "text" && p.value.includes("<img"))).toBe(true);
    expect(parts.some((p) => p.kind === "pos" && p.value.toLowerCase() === "спасибо")).toBe(true);
    expect(parts.every((p) => !p.value.includes("<span"))).toBe(true);
  });

  it("marks negative triggers", () => {
    const parts = highlightTranscriptParts("это плохо");
    expect(parts.some((p) => p.kind === "neg")).toBe(true);
  });
});
