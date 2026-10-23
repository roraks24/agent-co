import { create } from "zustand";

import {
  API_BASE_URL,
  createWorkspaceSession,
  createWorkspaceFolder,
  deleteWorkspaceSession,
  deleteWorkspacePath,
  ensureApiBaseUrlConfigured,
  extractErrorMessage,
  fetchGraphSchema,
  fetchPromptSchema,
  fetchWorkspaceFiles,
  fetchWorkspaceTree,
  getWorkspaceId,
  type GraphSchemaEdge,
  type GraphSchemaNode,
  type NodeId,
  type PromptSchemaResponse,
  readWorkspaceFile,
  renameWorkspacePath,
  type RunAgentRequest,
  setWorkspaceId,
  touchWorkspaceSession,
  type WorkspaceTreeNode,
  writeWorkspaceFile
} from "@/app/lib/api-client";
import { getStoredApiKey } from "@/app/lib/api-key-storage";
import { consumeSseStream } from "@/app/lib/sse";

export interface PlanActionStep {
  id: string;
  title: string;
  tool_name: string;
  tool_args?: Record<string, unknown>;
  expected_outcome?: string;
  status?: string;
  retry_count?: number;
  error_details?: string | null;
}

export interface GoalPlan {
  objective: string;
  task_type: string;
  expected_outcome: string;
  steps: PlanActionStep[];
}

export interface ActionExecutionRecord {
  step_id: string;
  tool_name: string;
  tool_args: Record<string, unknown>;
  started_at: string;
  completed_at: string;
  duration_ms: number;
  tool_result: unknown;
  status: "success" | "failed" | "error";
  error?: string | null;
  retry_count: number;
}

export interface VerificationResult {
  objective_status: string;
  criteria_evaluated: string[];
  evidence_summary: string;
  feedback?: string | null;
}

type NodeState = "idle" | "active" | "completed" | "error";

export interface AgentLogEvent {
  id: string;
  event: string;
  event_id?: number;
  timestamp: string;
  workspace_id?: string;
  node: string | null;
  state: NodeState | null;
  activity_score: number | null;
  severity: string;
  message: string;
  details?: Record<string, unknown> | null;
  hint?: string | null;
  error_type?: string | null;
  iteration?: number | null;
  duration_ms?: number | null;
  raw?: unknown;
  namespace?: unknown;
}

export interface StartAgentRunInput {
  userPrompt: string;
  workspaceMode: "fresh" | "continue";
  model?: string;
  recursionLimit?: number;
  mutablePrompt?: string | null;
}

interface AgentStoreState {
  workspaceId: string | null;
  workspaceExpiresAt: string | null;
  files: Record<string, string>;
  skippedBinary: string[];
  treeNodes: WorkspaceTreeNode[];
  graphNodes: GraphSchemaNode[];
  graphEdges: GraphSchemaEdge[];
  activeFilePath: string | null;
  activeNodeId: string | null;
  nodeStatusById: Record<string, NodeState>;
  activityByNodeId: Record<string, number>;
  logs: AgentLogEvent[];
  isGenerating: boolean;
  promptOverrides: Record<NodeId, string>;
  promptSchema: PromptSchemaResponse | null;
  maxMutablePromptChars: number;
  immutableRules: string[];
  errorMessage: string | null;
  executionPlan: GoalPlan | null;
  executionRecords: ActionExecutionRecord[];
  objectiveStatus: string | null;
  finalSummary: string | null;
  verification: VerificationResult | null;
  initWorkspaceSession: () => Promise<void>;
  resetWorkspaceSession: () => Promise<void>;
  fetchFiles: () => Promise<void>;
  fetchTree: () => Promise<void>;
  fetchGraphSchema: () => Promise<void>;
  fetchPromptSchema: () => Promise<void>;
  readFile: (path: string) => Promise<void>;
  updateFileContent: (path: string, content: string) => Promise<void>;
  createFolder: (path: string) => Promise<void>;
  renamePath: (fromPath: string, toPath: string, overwrite?: boolean) => Promise<void>;
  deletePath: (path: string, recursive?: boolean) => Promise<void>;
  resetRunVisualization: (clearLogs?: boolean) => void;
  startAgentRun: (input: StartAgentRunInput) => Promise<void>;
  syncSseEvent: (eventName: string, data: Record<string, unknown>) => void;
  downloadWorkspaceZip: () => Promise<void>;
  setActiveFilePath: (path: string | null) => void;
  setPromptOverride: (nodeId: NodeId, value: string) => void;
}

const NODE_IDS: NodeId[] = ["planner", "architect", "coder"];
const WORKFLOW_NODE_ID_SET = new Set<string>(NODE_IDS);
let activeRunAbortController: AbortController | null = null;
let activeRunAbortReason: "session_reset" | null = null;
let activeRunToken = 0;

function nowIso(): string {
  return new Date().toISOString();
}

function isWorkflowNode(nodeId: unknown): nodeId is NodeId {
  return typeof nodeId === "string" && WORKFLOW_NODE_ID_SET.has(nodeId);
}

function asRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}

function toNodeState(value: unknown): NodeState | null {
  if (value === "idle" || value === "active" || value === "completed" || value === "error") {
    return value;
  }
  return null;
}

function toNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
}

function toInteger(value: unknown): number | null {
  const numeric = toNumber(value);
  if (numeric === null) {
    return null;
  }
  return Number.isInteger(numeric) ? numeric : Math.round(numeric);
}

function buildPromptOverrides(overrides: Record<NodeId, string>): Record<string, string> {
  const payload: Record<string, string> = {};
  for (const nodeId of NODE_IDS) {
    const value = overrides[nodeId]?.trim();
    if (value) {
      payload[nodeId] = value;
    }
  }
  return payload;
}

function pushStoreError(set: (fn: (state: AgentStoreState) => Partial<AgentStoreState>) => void, message: string) {
  set((state) => ({
    errorMessage: message,
    logs: [
      ...state.logs,
      {
        id: `${Date.now()}-${state.logs.length + 1}`,
        event: "error",
        timestamp: nowIso(),
        node: null,
        state: "error",
        activity_score: 0,
        severity: "error",
        message,
        raw: null
      }
    ]
  }));
}

function toErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return String(error);
}

function isAbortLikeError(error: unknown): boolean {
  const message = toErrorMessage(error).toLowerCase();
  const objectError = toObjectOrNull(error);
  const name = typeof objectError?.name === "string" ? objectError.name.toLowerCase() : "";
  return name === "aborterror" || message.includes("aborted") || message.includes("abort");
}

function normalizeErrorMessage(message: string): string {
  let next = message.trim();
  while (/^error:\s*/i.test(next)) {
    next = next.replace(/^error:\s*/i, "").trim();
  }
  return next;
}

type RunErrorType =
  | "connection_error"
  | "rate_limit"
  | "auth_error"
  | "context_limit"
  | "invalid_request"
  | "unknown_error";

interface RunErrorClassification {
  message: string;
  errorType: RunErrorType;
  hint: string;
  rawMessage: string;
}

function classifyRunError(error: unknown): RunErrorClassification {
  const fallbackMessage = "Workflow failed during streaming.";
  const errorObject = toObjectOrNull(error);
  const details = toObjectOrNull(errorObject?.details);

  const rawMessage = normalizeErrorMessage(toErrorMessage(error)) || fallbackMessage;
  const explicitErrorType = typeof details?.error_type === "string" ? details.error_type : null;
  const explicitHint =
    typeof details?.hint === "string"
      ? details.hint.trim()
      : typeof errorObject?.hint === "string"
        ? errorObject.hint.trim()
        : "";

  const lower = rawMessage.toLowerCase();
  let errorType: RunErrorType;
  if (explicitErrorType === "connection_error") {
    errorType = "connection_error";
  } else if (explicitErrorType === "rate_limit") {
    errorType = "rate_limit";
  } else if (explicitErrorType === "auth_error") {
    errorType = "auth_error";
  } else if (explicitErrorType === "context_limit") {
    errorType = "context_limit";
  } else if (explicitErrorType === "invalid_request") {
    errorType = "invalid_request";
  } else if (lower.includes("rate limit") || lower.includes(" 429") || lower.includes("status 429")) {
    errorType = "rate_limit";
  } else if (
    lower.includes("api key") ||
    lower.includes("authentication") ||
    lower.includes("unauthorized") ||
    lower.includes("forbidden") ||
    lower.includes("status 401") ||
    lower.includes("status 403")
  ) {
    errorType = "auth_error";
  } else if (
    lower.includes("connection refused") ||
    lower.includes("connection error") ||
    lower.includes("connecterror") ||
    lower.includes("econnrefused") ||
    lower.includes("timeout") ||
    lower.includes("timed out") ||
    lower.includes("failed to fetch") ||
    lower.includes("network error") ||
    lower.includes("winerror 10061")
  ) {
    errorType = "connection_error";
  } else if (
    lower.includes("context length") ||
    lower.includes("too many tokens") ||
    lower.includes("max tokens")
  ) {
    errorType = "context_limit";
  } else if (
    lower.includes("validation") ||
    lower.includes("invalid request") ||
    lower.includes("schema") ||
    lower.includes("status 422")
  ) {
    errorType = "invalid_request";
  } else {
    errorType = "unknown_error";
  }

  const hintByType: Record<RunErrorType, string> = {
    connection_error: "Network connection to provider failed. Verify network/provider access and retry.",
    rate_limit: "Provider rate limit hit. Retry later or reduce prompt/output size.",
    auth_error: "Authentication failed. Check your API key and try again.",
    context_limit: "Prompt or context is too large. Reduce prompt size or mutable overrides.",
    invalid_request: "Request validation failed. Review request inputs and retry.",
    unknown_error: "Unexpected workflow error. Retry and inspect logs if it persists.",
  };
  const messageByType: Record<RunErrorType, string> = {
    connection_error: "Provider connection failed.",
    rate_limit: "Provider rate limit reached.",
    auth_error: "Authentication failed.",
    context_limit: "Prompt exceeds provider context limits.",
    invalid_request: "Request validation failed.",
    unknown_error: rawMessage,
  };

  return {
    message: messageByType[errorType] || fallbackMessage,
    errorType,
    hint: explicitHint || hintByType[errorType],
    rawMessage,
  };
}

function isWorkspaceAuthError(error: unknown): boolean {
  const message = toErrorMessage(error).toLowerCase();
  return (
    message.includes("workspace_unauthorized") ||
    message.includes("workspace api authentication required") ||
    (message.includes("workspace") && message.includes("x-api-key"))
  );
}

function setWorkspaceAuthBlocked(setState: (value: Partial<AgentStoreState>) => void): void {
  setState({
    errorMessage: "Workspace access requires an API key. Add your key to continue.",
  });
}

async function readErrorPayload(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    try {
      return await response.json();
    } catch {
      return null;
    }
  }

  try {
    return await response.text();
  } catch {
    return null;
  }
}

function toObjectOrNull(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return null;
}

function deriveActiveNodeId(nodeStatusById: Record<string, NodeState>): string | null {
  for (const nodeId of NODE_IDS) {
    if (nodeStatusById[nodeId] === "active") {
      return nodeId;
    }
  }
  return null;
}

function shouldDisplayLogEvent(
  eventName: string,
  node: string | null,
  severity: string
): boolean {
  if (severity === "warn" || severity === "error") {
    return true;
  }
  if (eventName === "run_started" || eventName === "run_complete" || eventName === "error") {
    return true;
  }
  if ((eventName === "on_node_start" || eventName === "on_node_end") && isWorkflowNode(node)) {
    return true;
  }
  if (
    eventName === "on_action_plan" ||
    eventName === "on_tool_start" ||
    eventName === "on_tool_end" ||
    eventName === "on_tool_error" ||
    eventName === "on_verification"
  ) {
    return true;
  }
  return false;
}

function buildDisplayLogMessage(
  eventName: string,
  node: string | null,
  data: Record<string, unknown>
): string {
  const details = toObjectOrNull(data.details);
  const iteration = toInteger(data.iteration);
  const iterationSuffix = typeof iteration === "number" ? ` (iteration ${iteration})` : "";
  const nodeLabel = node ? `${node[0]?.toUpperCase() ?? ""}${node.slice(1)}` : "Workflow";
  const rawMessage = typeof data.message === "string" ? data.message.trim() : "";

  if (eventName === "on_action_plan") {
    const stepCount = data.plan && typeof data.plan === 'object' && Array.isArray((data.plan as any).steps) ? (data.plan as any).steps.length : 'Multiple';
    return `Plan created: ${stepCount} action steps planned.`;
  }
  if (eventName === "on_tool_start") {
    return `Running tool '${data.tool_name ?? "tool"}': ${data.title ?? ""}`;
  }
  if (eventName === "on_tool_end") {
    return `Tool '${data.tool_name ?? "tool"}' completed (${data.duration_ms ?? 0}ms) [${data.status ?? "success"}]`;
  }
  if (eventName === "on_tool_error") {
    return `Tool '${data.tool_name ?? "tool"}' error: ${data.error ?? "Failed"}`;
  }
  if (eventName === "on_verification") {
    return `Verification complete: status is ${data.objective_status ?? "SUCCESS"}`;
  }
  if (eventName === "run_started") {
    return "Workflow run started.";
  }
  if (eventName === "run_complete") {
    const objStatus = typeof data.objective_status === "string" ? data.objective_status : null;
    if (objStatus === "FAILED") {
      return "Workflow completed: objective FAILED.";
    }
    if (objStatus === "PARTIAL_SUCCESS") {
      return "Workflow completed: objective PARTIAL_SUCCESS.";
    }
    return "Workflow finished successfully.";
  }
  if (eventName === "on_node_start" && node) {
    return `${nodeLabel} started${iterationSuffix}.`;
  }
  if (eventName === "on_node_end" && node) {
    const summary = typeof details?.text === "string" ? details.text.trim() : "";
    if (summary) {
      return `${nodeLabel} completed${iterationSuffix}: ${summary}.`;
    }
    return `${nodeLabel} completed${iterationSuffix}.`;
  }
  if (rawMessage) {
    return rawMessage;
  }
  return `${nodeLabel}: ${eventName}`;
}

function buildLogDetails(data: Record<string, unknown>): Record<string, unknown> | null {
  const details = toObjectOrNull(data.details);
  const raw = data.raw;
  if (details && raw !== undefined) {
    return { ...details, raw };
  }
  if (details) {
    return details;
  }
  if (raw !== undefined) {
    return { raw };
  }
  return null;
}

export const useAgentStore = create<AgentStoreState>((set, get) => ({
  workspaceId: null,
  workspaceExpiresAt: null,
  files: {},
  skippedBinary: [],
  treeNodes: [],
  graphNodes: [],
  graphEdges: [],
  activeFilePath: null,
  activeNodeId: null,
  nodeStatusById: {
    planner: "idle",
    architect: "idle",
    coder: "idle"
  },
  activityByNodeId: {
    planner: 0,
    architect: 0,
    coder: 0
  },
  logs: [],
  isGenerating: false,
  promptOverrides: {
    planner: "",
    architect: "",
    coder: ""
  },
  promptSchema: null,
  maxMutablePromptChars: 4000,
  immutableRules: [],
  errorMessage: null,
  executionPlan: null,
  executionRecords: [],
  objectiveStatus: null,
  finalSummary: null,
  verification: null,
  initWorkspaceSession: async () => {
    try {
      const existingWorkspaceId = get().workspaceId ?? getWorkspaceId();
      if (existingWorkspaceId) {
        const touched = await touchWorkspaceSession(existingWorkspaceId);
        setWorkspaceId(touched.workspace_id);
        set({
          workspaceId: touched.workspace_id,
          workspaceExpiresAt: touched.expires_at,
          errorMessage: null,
        });
        return;
      }

      const created = await createWorkspaceSession();
      setWorkspaceId(created.workspace_id);
      set({
        workspaceId: created.workspace_id,
        workspaceExpiresAt: created.expires_at,
        errorMessage: null,
      });
    } catch (error) {
      if (isWorkspaceAuthError(error)) {
        setWorkspaceAuthBlocked(set);
        return;
      }
      pushStoreError(set, `Failed to initialize workspace session: ${String(error)}`);
    }
  },
  resetWorkspaceSession: async () => {
    try {
      if (get().isGenerating && activeRunAbortController) {
        activeRunAbortReason = "session_reset";
        activeRunAbortController.abort();
        get().resetRunVisualization(false);
        set((state) => ({
          isGenerating: false,
          logs: [
            ...state.logs,
            {
              id: `${Date.now()}-${state.logs.length + 1}`,
              event: "system",
              timestamp: nowIso(),
              node: null,
              state: null,
              activity_score: 0,
              severity: "info",
              message: "Generation stopped by session reset.",
              raw: null,
            },
          ],
        }));
      }

      const previousWorkspaceId = get().workspaceId;
      if (previousWorkspaceId) {
        await deleteWorkspaceSession(previousWorkspaceId);
      }

      const created = await createWorkspaceSession();
      setWorkspaceId(created.workspace_id);
      set({
        workspaceId: created.workspace_id,
        workspaceExpiresAt: created.expires_at,
        files: {},
        treeNodes: [],
        activeFilePath: null,
        skippedBinary: [],
        errorMessage: null,
      });
    } catch (error) {
      if (isWorkspaceAuthError(error)) {
        setWorkspaceAuthBlocked(set);
        return;
      }
      pushStoreError(set, `Failed to reset workspace session: ${String(error)}`);
    }
  },
  fetchFiles: async () => {
    try {
      if (!get().workspaceId) {
        await get().initWorkspaceSession();
        if (!get().workspaceId) {
          return;
        }
      }
      const response = await fetchWorkspaceFiles();
      const paths = Object.keys(response.files).sort();
      setWorkspaceId(response.workspace_id);
      set((state) => ({
        workspaceId: response.workspace_id,
        workspaceExpiresAt: response.expires_at,
        files: response.files,
        skippedBinary: response.skipped_binary,
        activeFilePath:
          paths.length > 0
            ? state.activeFilePath && response.files[state.activeFilePath] !== undefined
              ? state.activeFilePath
              : paths[0]
            : null,
        errorMessage: null
      }));
    } catch (error) {
      if (isWorkspaceAuthError(error)) {
        setWorkspaceAuthBlocked(set);
        return;
      }
      pushStoreError(set, `Failed to load workspace files: ${String(error)}`);
    }
  },
  fetchTree: async () => {
    try {
      if (!get().workspaceId) {
        await get().initWorkspaceSession();
        if (!get().workspaceId) {
          return;
        }
      }
      const response = await fetchWorkspaceTree();
      setWorkspaceId(response.workspace_id);
      set({
        workspaceId: response.workspace_id,
        workspaceExpiresAt: response.expires_at,
        treeNodes: response.nodes,
        errorMessage: null,
      });
    } catch (error) {
      if (isWorkspaceAuthError(error)) {
        setWorkspaceAuthBlocked(set);
        return;
      }
      pushStoreError(set, `Failed to load workspace tree: ${String(error)}`);
    }
  },
  fetchGraphSchema: async () => {
    try {
      const response = await fetchGraphSchema();
      set({ graphNodes: response.nodes, graphEdges: response.edges, errorMessage: null });
    } catch (error) {
      pushStoreError(set, `Failed to load graph schema: ${String(error)}`);
    }
  },
  fetchPromptSchema: async () => {
    try {
      const response = await fetchPromptSchema();
      set({
        promptSchema: response,
        maxMutablePromptChars: response.policy.max_mutable_prompt_chars,
        immutableRules: response.policy.immutable_rules,
        errorMessage: null,
      });
    } catch (error) {
      pushStoreError(set, `Failed to load prompt schema: ${String(error)}`);
    }
  },
  readFile: async (path: string) => {
    try {
      if (!get().workspaceId) {
        await get().initWorkspaceSession();
        if (!get().workspaceId) {
          return;
        }
      }
      const response = await readWorkspaceFile(path);
      setWorkspaceId(response.workspace_id);
      set((state) => ({
        workspaceId: response.workspace_id,
        workspaceExpiresAt: response.expires_at,
        files: {
          ...state.files,
          [response.path]: response.content
        },
        activeFilePath: response.path,
        errorMessage: null
      }));
    } catch (error) {
      if (isWorkspaceAuthError(error)) {
        setWorkspaceAuthBlocked(set);
        return;
      }
      pushStoreError(set, `Failed to read file '${path}': ${String(error)}`);
    }
  },
  updateFileContent: async (path: string, content: string) => {
    set((state) => ({
      files: {
        ...state.files,
        [path]: content
      }
    }));

    try {
      if (!get().workspaceId) {
        await get().initWorkspaceSession();
        if (!get().workspaceId) {
          throw new Error("Workspace session is not available.");
        }
      }
      const response = await writeWorkspaceFile(path, content);
      setWorkspaceId(response.workspace_id);
      set({
        workspaceId: response.workspace_id,
        workspaceExpiresAt: response.expires_at,
        errorMessage: null,
      });
    } catch (error) {
      if (isWorkspaceAuthError(error)) {
        setWorkspaceAuthBlocked(set);
        throw error;
      }
      pushStoreError(set, `Failed to save file '${path}': ${String(error)}`);
      throw error;
    }
  },
  createFolder: async (path: string) => {
    try {
      if (!get().workspaceId) {
        await get().initWorkspaceSession();
        if (!get().workspaceId) {
          return;
        }
      }
      await createWorkspaceFolder(path);
      await Promise.all([get().fetchTree(), get().fetchFiles()]);
      set({ errorMessage: null });
    } catch (error) {
      if (isWorkspaceAuthError(error)) {
        setWorkspaceAuthBlocked(set);
        return;
      }
      pushStoreError(set, `Failed to create folder '${path}': ${String(error)}`);
    }
  },
  renamePath: async (fromPath: string, toPath: string, overwrite = false) => {
    try {
      if (!get().workspaceId) {
        await get().initWorkspaceSession();
        if (!get().workspaceId) {
          return;
        }
      }
      await renameWorkspacePath(fromPath, toPath, overwrite);
      await Promise.all([get().fetchTree(), get().fetchFiles()]);
      if (get().activeFilePath === fromPath) {
        set({ activeFilePath: toPath });
      }
      set({ errorMessage: null });
    } catch (error) {
      if (isWorkspaceAuthError(error)) {
        setWorkspaceAuthBlocked(set);
        return;
      }
      pushStoreError(set, `Failed to rename '${fromPath}' to '${toPath}': ${String(error)}`);
    }
  },
  deletePath: async (path: string, recursive = false) => {
    try {
      if (!get().workspaceId) {
        await get().initWorkspaceSession();
        if (!get().workspaceId) {
          return;
        }
      }
      await deleteWorkspacePath(path, recursive);
      await Promise.all([get().fetchTree(), get().fetchFiles()]);
      if (get().activeFilePath === path) {
        set({ activeFilePath: null });
      }
      set({ errorMessage: null });
    } catch (error) {
      if (isWorkspaceAuthError(error)) {
        setWorkspaceAuthBlocked(set);
        return;
      }
      pushStoreError(set, `Failed to delete '${path}': ${String(error)}`);
    }
  },
  resetRunVisualization: (clearLogs = true) => {
    set((state) => ({
      activeNodeId: null,
      nodeStatusById: {
        planner: "idle",
        architect: "idle",
        coder: "idle",
      },
      activityByNodeId: {
        planner: 0,
        architect: 0,
        coder: 0,
      },
      executionPlan: null,
      executionRecords: [],
      objectiveStatus: null,
      finalSummary: null,
      verification: null,
      errorMessage: null,
      ...(clearLogs ? { logs: [] } : { logs: state.logs }),
    }));
  },
  startAgentRun: async (input: StartAgentRunInput) => {
    const userPrompt = input.userPrompt.trim();
    if (!userPrompt) {
      pushStoreError(set, "Prompt cannot be empty.");
      return;
    }

    const localApiKey = getStoredApiKey();
    if (!localApiKey) {
      pushStoreError(set, "Missing API key. Add an API key in session storage or enable remember-key mode.");
      return;
    }
    const runToken = ++activeRunToken;
    const abortController = new AbortController();
    activeRunAbortController = abortController;
    activeRunAbortReason = null;

    get().resetRunVisualization(true);
    set({
      isGenerating: true,
      ...(input.workspaceMode === "fresh"
        ? {
            files: {},
            treeNodes: [],
            activeFilePath: null,
            skippedBinary: [],
          }
        : {}),
      errorMessage: null
    });

    try {
      let workspaceId: string | null = null;

      if (input.workspaceMode === "fresh") {
        const createdWorkspace = await createWorkspaceSession();
        workspaceId = createdWorkspace.workspace_id;
        setWorkspaceId(workspaceId);
        set({
          workspaceId: createdWorkspace.workspace_id,
          workspaceExpiresAt: createdWorkspace.expires_at,
          errorMessage: null,
        });
      } else {
        workspaceId = get().workspaceId ?? getWorkspaceId();
        if (!workspaceId) {
          await get().initWorkspaceSession();
          workspaceId = get().workspaceId;
        }
      }

      if (!workspaceId) {
        throw new Error("Workspace session is not available.");
      }

      const requestPayload: RunAgentRequest = {
        user_prompt: userPrompt,
        model: input.model,
        recursion_limit: input.recursionLimit,
        mutable_prompt: input.mutablePrompt ?? null,
        prompt_overrides: buildPromptOverrides(get().promptOverrides),
        workspace_id: workspaceId,
        api_key: localApiKey
      };

      ensureApiBaseUrlConfigured();

      const response = await fetch(`${API_BASE_URL}/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-KEY": localApiKey,
          ...(workspaceId ? { "X-Workspace-ID": workspaceId } : {}),
        },
        signal: abortController.signal,
        body: JSON.stringify(requestPayload)
      });

      if (!response.ok) {
        const payload = await readErrorPayload(response);
        const message = extractErrorMessage(payload, `Stream request failed with status ${response.status}`);
        const envelope = toObjectOrNull(payload);
        const errorBody = toObjectOrNull(envelope?.error);
        const details = toObjectOrNull(errorBody?.details);
        const requestError = new Error(message) as Error & {
          details?: Record<string, unknown>;
          error_type?: string;
          hint?: string;
        };
        if (details) {
          requestError.details = details;
          if (typeof details.error_type === "string") {
            requestError.error_type = details.error_type;
          }
          if (typeof details.hint === "string") {
            requestError.hint = details.hint;
          }
        }
        throw requestError;
      }

      await consumeSseStream(response, (event) => {
        if (runToken !== activeRunToken) {
          return;
        }
        get().syncSseEvent(event.event, event.data);
      });

      await Promise.all([get().fetchFiles(), get().fetchTree()]);
    } catch (error) {
      if (runToken === activeRunToken && isAbortLikeError(error) && activeRunAbortReason === "session_reset") {
        return;
      }
      const classified = classifyRunError(error);
      get().syncSseEvent("error", {
        event_id: Date.now(),
        timestamp: nowIso(),
        node: get().activeNodeId,
        state: "error",
        activity_score: 0,
        severity: "error",
        error_type: classified.errorType,
        hint: classified.hint,
        message: classified.message,
        details: {
          error_type: classified.errorType,
          hint: classified.hint,
        },
        raw: { source: "startAgentRun", error: classified.rawMessage }
      });
    } finally {
      if (runToken === activeRunToken) {
        activeRunAbortController = null;
        activeRunAbortReason = null;
        set({ isGenerating: false });
      }
    }
  },
  syncSseEvent: (eventName: string, data: Record<string, unknown>) => {
    const node = typeof data.node === "string" ? data.node : null;
    const workflowNode = isWorkflowNode(node) ? node : null;
    const state = toNodeState(data.state);
    const score = toNumber(data.activity_score);
    const severity = typeof data.severity === "string" ? data.severity : "info";
    const workspaceId = typeof data.workspace_id === "string" ? data.workspace_id : null;
    if (workspaceId) {
      setWorkspaceId(workspaceId);
    }
    const emittedNodeStates = asRecord(data.node_states);
    const emittedActivityByNode = asRecord(data.activity_by_node_id);

    set((store) => {
      const nextNodeStatus = { ...store.nodeStatusById };
      const nextActivity = { ...store.activityByNodeId };

      for (const [key, value] of Object.entries(emittedNodeStates)) {
        if (!isWorkflowNode(key)) {
          continue;
        }
        const normalized = toNodeState(value);
        if (normalized) {
          nextNodeStatus[key] = normalized;
        }
      }

      for (const [key, value] of Object.entries(emittedActivityByNode)) {
        if (!isWorkflowNode(key)) {
          continue;
        }
        const normalized = toNumber(value);
        if (normalized !== null) {
          nextActivity[key] = normalized;
        }
      }

      if (workflowNode && state) {
        nextNodeStatus[workflowNode] = state;
        
        // Auto-complete previous nodes
        if (state === "active") {
          if (workflowNode === "architect") {
            if (nextNodeStatus["planner"] !== "error") nextNodeStatus["planner"] = "completed";
          } else if (workflowNode === "coder") {
            if (nextNodeStatus["planner"] !== "error") nextNodeStatus["planner"] = "completed";
            if (nextNodeStatus["architect"] !== "error") nextNodeStatus["architect"] = "completed";
          }
        }
      }
      if (workflowNode && score !== null) {
        nextActivity[workflowNode] = score;
      }

      if (eventName === "run_complete") {
        for (const nodeId of NODE_IDS) {
          if (nextNodeStatus[nodeId] === "active") {
            nextNodeStatus[nodeId] = "completed";
          }
        }
      }
      if (eventName === "error") {
        const activeNodeId = deriveActiveNodeId(nextNodeStatus);
        if (activeNodeId) {
          nextNodeStatus[activeNodeId] = "error";
          nextActivity[activeNodeId] = 0;
        }
      }

      const hint = typeof data.hint === "string" ? data.hint.trim() : "";
      const errorType = typeof data.error_type === "string" ? data.error_type : null;
      const errorMessageBase =
        typeof data.message === "string" && data.message.trim()
          ? data.message.trim()
          : "Workflow failed.";
      const errorMessageWithHint =
        hint && !errorMessageBase.toLowerCase().includes(hint.toLowerCase())
          ? `${errorMessageBase} ${hint}`
          : errorMessageBase;

      const includeLog = shouldDisplayLogEvent(eventName, node, severity);

      const nextLog: AgentLogEvent = {
        id:
          typeof data.event_id === "number"
            ? String(data.event_id)
            : `${Date.now()}-${store.logs.length + 1}`,
        event: eventName,
        event_id: typeof data.event_id === "number" ? data.event_id : undefined,
        timestamp: typeof data.timestamp === "string" ? data.timestamp : nowIso(),
        workspace_id: workspaceId ?? undefined,
        node,
        state,
        activity_score: score,
        severity,
        message: buildDisplayLogMessage(eventName, node, data),
        details: buildLogDetails(data),
        hint: hint || null,
        error_type: errorType,
        iteration: toInteger(data.iteration),
        duration_ms: toInteger(data.duration_ms),
        raw: data.raw,
        namespace: data.namespace
      };

      let nextPlan = store.executionPlan;
      let nextRecords = store.executionRecords;
      let nextObjStatus = store.objectiveStatus;
      let nextSummary = store.finalSummary;
      let nextVerif = store.verification;

      if (eventName === "on_action_plan" && data.plan && typeof data.plan === "object") {
        nextPlan = data.plan as GoalPlan;
      }
      if (eventName === "on_tool_end") {
        const er = data.execution_record as ActionExecutionRecord | undefined;
        if (er) {
          nextRecords = [...nextRecords, er];
        }
      }
      if (eventName === "on_verification") {
        if (typeof data.objective_status === "string") nextObjStatus = data.objective_status;
        if (typeof data.final_summary === "string") nextSummary = data.final_summary;
        if (data.verification && typeof data.verification === "object") nextVerif = data.verification as VerificationResult;
      }
      if (eventName === "run_complete") {
        if (typeof data.objective_status === "string") nextObjStatus = data.objective_status;
        if (typeof data.final_summary === "string") nextSummary = data.final_summary;
      }

      return {
        workspaceId: workspaceId ?? store.workspaceId,
        logs: includeLog ? [...store.logs, nextLog] : store.logs,
        activeNodeId: deriveActiveNodeId(nextNodeStatus),
        nodeStatusById: nextNodeStatus,
        activityByNodeId: nextActivity,
        executionPlan: nextPlan,
        executionRecords: nextRecords,
        objectiveStatus: nextObjStatus,
        finalSummary: nextSummary,
        verification: nextVerif,
        isGenerating:
          eventName === "run_complete" || eventName === "error" ? false : store.isGenerating,
        errorMessage:
          eventName === "error"
            ? errorMessageWithHint
            : store.errorMessage
      };
    });
  },
  downloadWorkspaceZip: async () => {
    ensureApiBaseUrlConfigured();
    const localApiKey = getStoredApiKey();
    if (!get().workspaceId) {
      await get().initWorkspaceSession();
      if (!get().workspaceId) {
        return;
      }
    }
    const workspaceId = get().workspaceId;
    try {
      const response = await fetch(`${API_BASE_URL}/workspace/download`, {
        headers: {
          ...(localApiKey ? { "X-API-KEY": localApiKey } : {}),
          ...(workspaceId ? { "X-Workspace-ID": workspaceId } : {}),
        },
      });
      if (!response.ok) {
        const payload = await readErrorPayload(response);
        throw new Error(
          extractErrorMessage(payload, `Download failed with status ${response.status}`)
        );
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "generated_project.zip";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      if (isWorkspaceAuthError(error)) {
        setWorkspaceAuthBlocked(set);
        return;
      }
      pushStoreError(set, `Failed to download workspace zip: ${String(error)}`);
    }
  },
  setActiveFilePath: (path: string | null) => {
    set({ activeFilePath: path });
  },
  setPromptOverride: (nodeId: NodeId, value: string) => {
    set((state) => ({
      promptOverrides: {
        ...state.promptOverrides,
        [nodeId]: value
      }
    }));
  }
}));
