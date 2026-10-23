export const PROMPT_EDITABLE_SEPARATOR =
  "\n\n===== USER EDITABLE (ONLY THIS PART IS SENT) =====\n";

export function buildLockedPromptHeader(
  immutableRules: string[],
  immutablePrefix: string
): string {
  const rulesText = immutableRules.length
    ? immutableRules.map((rule) => `- ${rule}`).join("\n")
    : "- Loading immutable rules from backend policy...";
  const prefixText =
    immutablePrefix.trim().length > 0
      ? immutablePrefix
      : "Loading immutable prefix from /api/prompts...";

  return [
    "GLOBAL IMMUTABLE RULES (READ-ONLY):",
    rulesText,
    "",
    "NODE IMMUTABLE PREFIX (READ-ONLY):",
    prefixText,
  ].join("\n");
}

export function composePromptEditorValue(
  lockedHeader: string,
  editableSuffix: string
): string {
  return `${lockedHeader}${PROMPT_EDITABLE_SEPARATOR}${editableSuffix}`;
}

export function extractEditablePromptSuffix(
  nextValue: string,
  lockedHeader: string
): string | null {
  const requiredPrefix = `${lockedHeader}${PROMPT_EDITABLE_SEPARATOR}`;
  if (!nextValue.startsWith(requiredPrefix)) {
    return null;
  }
  return nextValue.slice(requiredPrefix.length);
}
