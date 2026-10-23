import type { ActionExecutionRecord, AgentLogEvent, GoalPlan, VerificationResult } from "@/app/store/useAgentStore";

export interface ActivityItem {
  id: string;
  stepId?: string;
  toolName?: string;
  type: "plan" | "tool" | "verification" | "error" | "status";
  title: string;
  subtitle?: string;
  status: "running" | "success" | "failed" | "error";
  startedAt?: string;
  completedAt?: string;
  durationMs?: number;
  formattedDuration?: string;
  retryCount?: number;
  inputArgs?: Record<string, unknown>;
  toolResult?: unknown;
  error?: string | null;
  verificationOutcome?: string | null;
  verificationCriteria?: string[];
  raw?: unknown;
}

const SENSITIVE_KEY_REGEX = /(?:api[_-]?key|token|secret|password|auth(?:orization)?|credential|private[_-]?key)/i;
const SENSITIVE_VALUE_REGEX = /(?:gsk_[a-zA-Z0-9_-]{20,}|sk-[a-zA-Z0-9_-]{20,}|Bearer\s+[a-zA-Z0-9._-]{20,})/gi;

export function sanitizeValue(val: unknown): unknown {
  if (typeof val === "string") {
    return val.replace(SENSITIVE_VALUE_REGEX, "[REDACTED]");
  }
  if (Array.isArray(val)) {
    return val.map(sanitizeValue);
  }
  if (val && typeof val === "object") {
    return sanitizeInputArgs(val as Record<string, unknown>);
  }
  return val;
}

export function sanitizeInputArgs(
  args?: Record<string, unknown> | null
): Record<string, unknown> | undefined {
  if (!args || typeof args !== "object") return undefined;
  const sanitized: Record<string, unknown> = {};

  for (const [key, val] of Object.entries(args)) {
    if (SENSITIVE_KEY_REGEX.test(key)) {
      sanitized[key] = "[REDACTED]";
    } else {
      sanitized[key] = sanitizeValue(val);
    }
  }

  return sanitized;
}

export function formatDuration(durationMs?: number | null): string {
  if (durationMs === null || durationMs === undefined || durationMs < 0) return "";
  if (durationMs < 1000) {
    return `${Math.round(durationMs)} ms`;
  }
  const seconds = durationMs / 1000;
  return `${seconds < 10 ? seconds.toFixed(1) : Math.round(seconds)} s`;
}

function getFilename(pathStr?: unknown): string {
  if (typeof pathStr !== "string" || !pathStr.trim()) return "file";
  const normalized = pathStr.trim().replace(/\\/g, "/");
  const parts = normalized.split("/");
  return parts.filter(Boolean).pop() || normalized;
}

function truncateString(str: string, maxLen = 40): string {
  if (!str) return "";
  return str.length > maxLen ? `${str.slice(0, maxLen - 3)}...` : str;
}

export function formatToolAction(
  toolName: string,
  args?: Record<string, unknown>,
  status: "running" | "success" | "failed" | "error" = "success",
  retryCount = 0
): { title: string; subtitle?: string } {
  const isRunning = status === "running";
  const isFailed = status === "failed" || status === "error";

  switch (toolName) {
    case "write_file": {
      const filename = getFilename(args?.path || args?.file_path);
      const retryPrefix = retryCount > 0 ? `Retrying ${filename} (attempt ${retryCount + 1})` : null;

      if (isRunning) {
        return {
          title: retryPrefix || `Writing ${filename}`,
          subtitle: args?.path ? String(args.path) : undefined,
        };
      }
      if (isFailed) {
        return {
          title: `Writing ${filename} · Failed`,
          subtitle: args?.path ? String(args.path) : undefined,
        };
      }
      return {
        title: `Wrote ${filename}`,
        subtitle: args?.path ? String(args.path) : undefined,
      };
    }

    case "read_file": {
      const filename = getFilename(args?.path || args?.file_path);
      if (isRunning) return { title: `Reading ${filename}`, subtitle: args?.path ? String(args.path) : undefined };
      if (isFailed) return { title: `Reading ${filename} · Failed` };
      return { title: `Read ${filename}`, subtitle: args?.path ? String(args.path) : undefined };
    }

    case "list_files":
    case "list_directory": {
      const dir = typeof args?.path === "string" && args.path ? args.path : "";
      if (dir && dir !== "." && dir !== "/") {
        const dirName = getFilename(dir);
        if (isRunning) return { title: `Inspecting ${dirName} directory` };
        if (isFailed) return { title: `Inspecting ${dirName} directory · Failed` };
        return { title: `Inspected ${dirName} directory` };
      }
      if (isRunning) return { title: "Inspecting workspace files" };
      if (isFailed) return { title: "Inspecting workspace files · Failed" };
      return { title: "Inspected workspace files" };
    }

    case "web_search": {
      const query = typeof args?.query === "string" ? args.query : (typeof args?.q === "string" ? args.q : "");
      const shortQuery = truncateString(query, 36);
      const queryText = shortQuery ? ` for "${shortQuery}"` : "";
      if (isRunning) return { title: `Searching web${queryText}` };
      if (isFailed) return { title: `Searching web${queryText} · Failed` };
      return { title: `Searched web${queryText}` };
    }

    case "fetch_url_content": {
      const url = typeof args?.url === "string" ? args.url : "";
      let host = url;
      try {
        if (url.startsWith("http")) {
          const parsed = new URL(url);
          host = parsed.hostname + (parsed.pathname !== "/" ? truncateString(parsed.pathname, 20) : "");
        }
      } catch {
        host = truncateString(url, 30);
      }
      const hostText = host ? ` ${host}` : "";
      if (isRunning) return { title: `Fetching${hostText}` };
      if (isFailed) return { title: `Fetching${hostText} · Failed` };
      return { title: `Fetched${hostText}` };
    }

    case "get_github_repo_metadata": {
      const repo = typeof args?.repo === "string" ? args.repo : (typeof args?.repository === "string" ? args.repository : "");
      const repoText = repo ? ` ${repo}` : "";
      if (isRunning) return { title: `Inspecting GitHub repo${repoText}` };
      if (isFailed) return { title: `Inspecting GitHub repo${repoText} · Failed` };
      return { title: `Inspected GitHub repo${repoText}` };
    }

    case "run_command":
    case "execute_command":
    case "bash": {
      const cmd = typeof args?.command === "string" ? args.command : (typeof args?.cmd === "string" ? args.cmd : "");
      const shortCmd = truncateString(cmd, 32);
      const cmdText = shortCmd ? ` ${shortCmd}` : "";
      if (isRunning) return { title: `Running${cmdText}` };
      if (isFailed) return { title: `Command failed:${cmdText}` };
      return { title: `Ran${cmdText}` };
    }

    default: {
      const cleanName = toolName.replace(/_/g, " ").trim();
      const capitalized = cleanName.charAt(0).toUpperCase() + cleanName.slice(1);
      if (isRunning) return { title: `Running ${cleanName}` };
      if (isFailed) return { title: `${capitalized} · Failed` };
      return { title: `Ran ${cleanName}` };
    }
  }
}

export function buildActivityFeed(params: {
  logs: AgentLogEvent[];
  executionRecords: ActionExecutionRecord[];
  executionPlan: GoalPlan | null;
  verification: VerificationResult | null;
  objectiveStatus: string | null;
  isGenerating: boolean;
  activeNodeId: string | null;
}): ActivityItem[] {
  const {
    logs,
    executionRecords,
    executionPlan,
    verification,
    objectiveStatus,
    isGenerating,
    activeNodeId,
  } = params;

  const activities: ActivityItem[] = [];
  const processedKeys = new Set<string>();

  // 1. Planning Activity
  const hasPlannerStarted = logs.some((l) => l.event === "on_node_start" && l.node === "planner") || isGenerating;
  if (executionPlan) {
    const stepCount = executionPlan.steps?.length || 0;
    activities.push({
      id: "planning-established",
      type: "plan",
      title: `Plan created · ${stepCount} steps`,
      subtitle: executionPlan.objective ? truncateString(executionPlan.objective, 60) : undefined,
      status: "success",
      inputArgs: executionPlan.objective
        ? { objective: executionPlan.objective, task_type: executionPlan.task_type }
        : undefined,
      toolResult: executionPlan.steps,
      attemptCount: 1,
    });
  } else if (hasPlannerStarted && activeNodeId === "planner" && isGenerating) {
    activities.push({
      id: "planning-in-progress",
      type: "plan",
      title: "Planning objective",
      status: "running",
      attemptCount: 1,
    });
  }

  // 2. Completed / Recorded Tool Actions from executionRecords (primary source of truth)
  for (let i = 0; i < executionRecords.length; i += 1) {
    const rec = executionRecords[i];
    const stepId = rec.step_id || `step-${i + 1}`;
    const retryCount = rec.retry_count || 0;
    const key = `${stepId}-${rec.tool_name}-attempt-${retryCount}`;
    processedKeys.add(key);

    const isRecSuccess = rec.status === "success";
    const status: ActivityItem["status"] = isRecSuccess ? "success" : "failed";
    const formatted = formatToolAction(rec.tool_name, rec.tool_args, status, retryCount);

    const durText = formatDuration(rec.duration_ms);
    const fullTitle = isRecSuccess && durText ? `${formatted.title} · ${durText}` : formatted.title;

    activities.push({
      id: key,
      stepId,
      toolName: rec.tool_name,
      type: "tool",
      title: fullTitle,
      subtitle: formatted.subtitle,
      status,
      startedAt: rec.started_at,
      completedAt: rec.completed_at,
      durationMs: rec.duration_ms,
      formattedDuration: durText,
      retryCount,
      attemptCount: retryCount + 1,
      inputArgs: sanitizeInputArgs(rec.tool_args),
      toolResult: rec.tool_result,
      error: rec.error,
    });
  }

  // 3. Fallback for on_tool_end events in logs that might not yet be in executionRecords
  for (const log of logs) {
    if (log.event === "on_tool_end" && log.details) {
      const toolName = String(log.details.tool_name || "tool");
      const stepId = String(log.details.step_id || "step");
      const dur = typeof log.duration_ms === "number" ? log.duration_ms : 0;
      const statusStr = String(log.details.status || "success");
      const isOk = statusStr === "success";
      const key = `${stepId}-${toolName}-log-${log.id}`;

      // If we already captured this step in executionRecords, skip duplicate
      const hasMatchingRec = executionRecords.some((r) => r.step_id === stepId && r.tool_name === toolName);
      if (!hasMatchingRec && !processedKeys.has(key)) {
        processedKeys.add(key);
        const args = (log.details.tool_args as Record<string, unknown>) || undefined;
        const formatted = formatToolAction(toolName, args, isOk ? "success" : "failed", 0);
        const durText = formatDuration(dur);
        const fullTitle = isOk && durText ? `${formatted.title} · ${durText}` : formatted.title;

        activities.push({
          id: key,
          stepId,
          toolName,
          type: "tool",
          title: fullTitle,
          subtitle: formatted.subtitle,
          status: isOk ? "success" : "failed",
          durationMs: dur,
          formattedDuration: durText,
          attemptCount: 1,
          inputArgs: sanitizeInputArgs(args),
          toolResult: log.details.tool_result,
          error: typeof log.details.error === "string" ? log.details.error : null,
        });
      }
    }
  }

  // 4. Currently Running Tool Step (if run is in progress and next step is active)
  if (isGenerating && executionPlan && activeNodeId === "coder") {
    const executedCount = executionRecords.length;
    if (executedCount < executionPlan.steps.length) {
      const activeStep = executionPlan.steps[executedCount];
      if (activeStep) {
        const activeKey = `active-step-${activeStep.id || executedCount + 1}`;
        const formatted = formatToolAction(
          activeStep.tool_name,
          activeStep.tool_args,
          "running",
          activeStep.retry_count || 0
        );

        activities.push({
          id: activeKey,
          stepId: activeStep.id,
          toolName: activeStep.tool_name,
          type: "tool",
          title: formatted.title,
          subtitle: formatted.subtitle || (activeStep.title !== formatted.title ? activeStep.title : undefined),
          status: "running",
          attemptCount: (activeStep.retry_count || 0) + 1,
          inputArgs: sanitizeInputArgs(activeStep.tool_args),
        });
      }
    }
  }

  // 5. Verification Activity
  const isVerifying = isGenerating && executionPlan && executionRecords.length >= executionPlan.steps.length;
  if (verification || objectiveStatus) {
    const statusVal = objectiveStatus || verification?.objective_status || "SUCCESS";
    const criteriaCount = verification?.criteria_evaluated?.length || 0;

    let verifTitle: string;
    let verifStatus: ActivityItem["status"] = "success";

    if (statusVal === "SUCCESS") {
      verifTitle = criteriaCount > 0 ? `Verification passed · ${criteriaCount} checks` : "Verification passed";
      verifStatus = "success";
    } else if (statusVal === "PARTIAL_SUCCESS") {
      verifTitle = criteriaCount > 0 ? `Verification partial · ${criteriaCount} checks` : "Verification partial";
      verifStatus = "failed"; // warn/failed
    } else {
      verifTitle = "Verification failed";
      verifStatus = "failed";
    }

    activities.push({
      id: "verification-result",
      type: "verification",
      title: verifTitle,
      subtitle: verification?.evidence_summary ? truncateString(verification.evidence_summary, 60) : undefined,
      status: verifStatus,
      verificationOutcome: statusVal,
      verificationCriteria: verification?.criteria_evaluated,
      toolResult: verification,
      attemptCount: 1,
    });
  } else if (isVerifying) {
    activities.push({
      id: "verification-in-progress",
      type: "verification",
      title: "Verifying deliverables",
      status: "running",
      attemptCount: 1,
    });
  }

  // 6. Explicit System Errors
  const lastError = logs.findLast((l) => l.event === "error" || l.severity === "error");
  if (!isGenerating && lastError && activities.every((a) => a.error !== lastError.message)) {
    activities.push({
      id: `system-error-${lastError.id}`,
      type: "error",
      title: lastError.message || "Execution error",
      subtitle: lastError.hint || undefined,
      status: "error",
      error: lastError.message,
      attemptCount: 1,
    });
  }

  return activities;
}

export function getOngoingIndicator(params: {
  isGenerating: boolean;
  activeNodeId: string | null;
  executionPlan: GoalPlan | null;
  executionRecords: ActionExecutionRecord[];
  verification: VerificationResult | null;
}): string | null {
  const { isGenerating, activeNodeId, executionPlan, executionRecords, verification } = params;

  if (!isGenerating) {
    return null; // clean stop upon finish or failure
  }

  if (activeNodeId === "planner") {
    return "Planning objective…";
  }

  if (activeNodeId === "architect") {
    return "Structuring execution plan…";
  }

  if (activeNodeId === "coder") {
    if (executionPlan && executionPlan.steps.length > 0) {
      const total = executionPlan.steps.length;
      const current = Math.min(executionRecords.length + 1, total);
      if (executionRecords.length >= total) {
        return "Verifying deliverables…";
      }
      const step = executionPlan.steps[current - 1];
      const target = step?.tool_args?.path ? getFilename(step.tool_args.path) : (step?.tool_name || "");
      return target ? `Executing step ${current} of ${total}: ${target}…` : `Executing step ${current} of ${total}…`;
    }
    return "Executing tools…";
  }

  if (verification || (executionPlan && executionRecords.length >= executionPlan.steps.length)) {
    return "Verifying deliverables…";
  }

  return "Working…";
}
