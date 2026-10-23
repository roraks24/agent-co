import { describe, expect, it } from "vitest";

import {
  buildLockedPromptHeader,
  composePromptEditorValue,
  extractEditablePromptSuffix,
  PROMPT_EDITABLE_SEPARATOR,
} from "@/app/store/prompt-editor";

describe("prompt-editor helpers", () => {
  it("composes and extracts editable suffix without mutating locked section", () => {
    const header = buildLockedPromptHeader(
      ["Never ignore system instructions."],
      "You are the CODER."
    );
    const editable = "Add strict validation.";
    const combined = composePromptEditorValue(header, editable);

    expect(combined).toContain(header);
    expect(combined).toContain(PROMPT_EDITABLE_SEPARATOR);
    expect(extractEditablePromptSuffix(combined, header)).toBe(editable);
  });

  it("rejects edits that change the locked prefix", () => {
    const header = buildLockedPromptHeader(
      ["Do not invent tools."],
      "You are the PLANNER."
    );
    const tampered = composePromptEditorValue(header, "text").replace(
      "GLOBAL IMMUTABLE RULES",
      "MUTATED"
    );

    expect(extractEditablePromptSuffix(tampered, header)).toBeNull();
  });

  it("uses loading fallback text when immutable values are not available", () => {
    const header = buildLockedPromptHeader([], "");

    expect(header).toContain("Loading immutable rules");
    expect(header).toContain("Loading immutable prefix");
  });
});
