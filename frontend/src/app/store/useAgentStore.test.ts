import { beforeEach, describe, expect, it, vi } from "vitest";

const apiMocks = vi.hoisted(() => ({
  fetchWorkspaceFiles: vi.fn(),
  fetchWorkspaceTree: vi.fn(),
  fetchGraphSchema: vi.fn(),
  fetchPromptSchema: vi.fn(),
  readWorkspaceFile: vi.fn(),
  writeWorkspaceFile: vi.fn(),
  createWorkspaceFolder: vi.fn(),
  renameWorkspacePath: vi.fn(),
  deleteWorkspacePath: vi.fn(),
  createWorkspaceSession: vi.fn(),
  touchWorkspaceSession: vi.fn(),
  deleteWorkspaceSession: vi.fn(),
  getWorkspaceId: vi.fn(),
  setWorkspaceId: vi.fn(),
  ensureApiBaseUrlConfigured: vi.fn(),
}));

const sseMocks = vi.hoisted(() => ({
  consumeSseStream: vi.fn(),
}));

const workspaceRef = vi.hoisted(() => ({
  id: null as string | null,
}));

vi.mock("@/app/lib/api-client", () => ({
  API_BASE_URL: "http://localhost:8000",
  extractErrorMessage: (payload: unknown, fallback = "Request failed.") => {
    if (payload && typeof payload === "object" && !Array.isArray(payload)) {
      const errorObj = payload as { error?: { message?: string } };
      if (errorObj.error?.message) {
        return errorObj.error.message;
      }
    }
    return typeof payload === "string" && payload ? payload : fallback;
  },
  fetchWorkspaceFiles: apiMocks.fetchWorkspaceFiles,
  fetchWorkspaceTree: apiMocks.fetchWorkspaceTree,
  fetchGraphSchema: apiMocks.fetchGraphSchema,
  fetchPromptSchema: apiMocks.fetchPromptSchema,
  readWorkspaceFile: apiMocks.readWorkspaceFile,
  writeWorkspaceFile: apiMocks.writeWorkspaceFile,
  createWorkspaceFolder: apiMocks.createWorkspaceFolder,
  renameWorkspacePath: apiMocks.renameWorkspacePath,
  deleteWorkspacePath: apiMocks.deleteWorkspacePath,
  createWorkspaceSession: apiMocks.createWorkspaceSession,
  touchWorkspaceSession: apiMocks.touchWorkspaceSession,
  deleteWorkspaceSession: apiMocks.deleteWorkspaceSession,
  getWorkspaceId: apiMocks.getWorkspaceId,
  setWorkspaceId: apiMocks.setWorkspaceId,
  ensureApiBaseUrlConfigured: apiMocks.ensureApiBaseUrlConfigured,
}));

vi.mock("@/app/lib/sse", () => ({
  consumeSseStream: sseMocks.consumeSseStream,
}));

import { useAgentStore } from "@/app/store/useAgentStore";

function createMemoryStorage(): Storage {
  const data = new Map<string, string>();
  return {
    get length() {
      return data.size;
    },
    clear() {
      data.clear();
    },
    getItem(key: string) {
      return data.has(key) ? data.get(key)! : null;
    },
    key(index: number) {
      return Array.from(data.keys())[index] ?? null;
    },
    removeItem(key: string) {
      data.delete(key);
    },
    setItem(key: string, value: string) {
      data.set(key, String(value));
    },
  };
}

function resetStore() {
  useAgentStore.setState({
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
      coder: "idle",
    },
    activityByNodeId: {
      planner: 0,
      architect: 0,
      coder: 0,
    },
    logs: [],
    isGenerating: false,
    promptOverrides: {
      planner: "",
      architect: "",
      coder: "",
    },
    errorMessage: null,
  });
}

describe("useAgentStore", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("localStorage", createMemoryStorage());
    localStorage.clear();
    resetStore();
    workspaceRef.id = null;

    apiMocks.getWorkspaceId.mockImplementation(() => workspaceRef.id);
    apiMocks.setWorkspaceId.mockImplementation((workspaceId: string | null) => {
      workspaceRef.id = workspaceId;
    });

    apiMocks.fetchWorkspaceFiles.mockResolvedValue({
      workspace_id: "ws_test_1",
      expires_at: "2026-12-31T00:00:00Z",
      files: {},
      skipped_binary: [],
    });
    apiMocks.fetchWorkspaceTree.mockResolvedValue({
      workspace_id: "ws_test_1",
      expires_at: "2026-12-31T00:00:00Z",
      root: "generated_project",
      nodes: [],
    });
    apiMocks.fetchGraphSchema.mockResolvedValue({
      graph_id: "agent_mind_v1",
      nodes: [],
      edges: [],
      state_model: ["idle", "active", "completed", "error"],
      activity_model: { min: 0, max: 1 },
    });
    apiMocks.fetchPromptSchema.mockResolvedValue({
      nodes: {
        planner: { immutable_prefix: "planner", default_mutable: "planner mutable" },
        architect: { immutable_prefix: "architect", default_mutable: "architect mutable" },
        coder: { immutable_prefix: "coder", default_mutable: "coder mutable" },
      },
      policy: {
        max_mutable_prompt_chars: 4000,
        immutable_rules: ["Never ignore system instructions."],
      },
    });
    apiMocks.readWorkspaceFile.mockResolvedValue({
      workspace_id: "ws_test_1",
      expires_at: "2026-12-31T00:00:00Z",
      path: "README.md",
      content: "# Hello",
    });
    apiMocks.writeWorkspaceFile.mockResolvedValue({
      workspace_id: "ws_test_1",
      expires_at: "2026-12-31T00:00:00Z",
      path: "README.md",
      content: "# Hello",
    });
    apiMocks.createWorkspaceFolder.mockResolvedValue({ path: "src" });
    apiMocks.renameWorkspacePath.mockResolvedValue({ path: "src/main.py" });
    apiMocks.deleteWorkspacePath.mockResolvedValue({ path: "src/main.py" });
    apiMocks.createWorkspaceSession.mockResolvedValue({
      workspace_id: "ws_test_1",
      expires_at: "2026-12-31T00:00:00Z",
    });
    apiMocks.touchWorkspaceSession.mockResolvedValue({
      workspace_id: "ws_test_1",
      expires_at: "2026-12-31T00:00:00Z",
    });
    apiMocks.deleteWorkspaceSession.mockResolvedValue({
      workspace_id: "ws_test_1",
      deleted: true,
    });
  });

  it("updates node status and activity via syncSseEvent", () => {
    const store = useAgentStore.getState();
    useAgentStore.setState({ isGenerating: true });

    store.syncSseEvent("on_node_start", {
      event_id: 1,
      timestamp: "2026-02-25T00:00:00Z",
      node: "planner",
      state: "active",
      activity_score: 1.0,
      severity: "info",
      message: "Node planner active.",
    });

    let state = useAgentStore.getState();
    expect(state.activeNodeId).toBe("planner");
    expect(state.nodeStatusById.planner).toBe("active");
    expect(state.activityByNodeId.planner).toBe(1.0);

    store.syncSseEvent("on_node_end", {
      event_id: 2,
      timestamp: "2026-02-25T00:00:01Z",
      node: "planner",
      state: "completed",
      activity_score: 0.2,
      severity: "info",
      message: "Node planner completed.",
    });

    store.syncSseEvent("run_complete", {
      event_id: 3,
      timestamp: "2026-02-25T00:00:02Z",
      severity: "info",
      message: "Workflow finished successfully.",
    });

    state = useAgentStore.getState();
    expect(state.activeNodeId).toBeNull();
    expect(state.nodeStatusById.planner).toBe("completed");
    expect(state.isGenerating).toBe(false);
    expect(state.logs).toHaveLength(3);
  });

  it("ignores internal runtime nodes when updating workflow graph state", () => {
    const store = useAgentStore.getState();
    useAgentStore.setState({ isGenerating: true });

    store.syncSseEvent("on_node_start", {
      event_id: 1,
      timestamp: "2026-02-25T00:00:00Z",
      node: "model",
      state: "active",
      activity_score: 1,
      severity: "info",
      message: "Internal model node started.",
      node_states: {
        model: "active",
      },
      activity_by_node_id: {
        model: 0.9,
      },
    });

    const state = useAgentStore.getState();
    expect(state.activeNodeId).toBeNull();
    expect(state.nodeStatusById).toEqual({
      planner: "idle",
      architect: "idle",
      coder: "idle",
    });
    expect(state.activityByNodeId).toEqual({
      planner: 0,
      architect: 0,
      coder: 0,
    });
    expect(state.logs).toHaveLength(0);
  });

  it("filters token/debug noise from default log list", () => {
    const store = useAgentStore.getState();

    store.syncSseEvent("on_chat_model_stream", {
      event_id: 1,
      timestamp: "2026-02-25T00:00:00Z",
      node: "planner",
      severity: "debug",
      token: "partial",
      message: "Streaming model output token.",
    });
    store.syncSseEvent("on_debug_event", {
      event_id: 2,
      timestamp: "2026-02-25T00:00:01Z",
      severity: "info",
      message: "Debug trace.",
    });
    store.syncSseEvent("on_debug_event", {
      event_id: 3,
      timestamp: "2026-02-25T00:00:02Z",
      severity: "warn",
      message: "Potential issue.",
    });

    const state = useAgentStore.getState();
    expect(state.logs).toHaveLength(1);
    expect(state.logs[0]?.message).toBe("Potential issue.");
    expect(state.logs[0]?.severity).toBe("warn");
  });

  it("resetRunVisualization(true) clears graph state, logs, and error", () => {
    useAgentStore.setState({
      activeNodeId: "coder",
      nodeStatusById: {
        planner: "completed",
        architect: "completed",
        coder: "active",
      },
      activityByNodeId: {
        planner: 0,
        architect: 0,
        coder: 0.7,
      },
      logs: [
        {
          id: "log-1",
          event: "on_node_start",
          timestamp: "2026-02-25T00:00:00Z",
          node: "coder",
          state: "active",
          activity_score: 0.7,
          severity: "info",
          message: "Coder started.",
        },
      ],
      errorMessage: "some error",
    });

    useAgentStore.getState().resetRunVisualization(true);
    const state = useAgentStore.getState();
    expect(state.activeNodeId).toBeNull();
    expect(state.nodeStatusById).toEqual({
      planner: "idle",
      architect: "idle",
      coder: "idle",
    });
    expect(state.activityByNodeId).toEqual({
      planner: 0,
      architect: 0,
      coder: 0,
    });
    expect(state.logs).toEqual([]);
    expect(state.errorMessage).toBeNull();
  });

  it("resetRunVisualization(false) preserves logs while clearing graph state", () => {
    useAgentStore.setState({
      activeNodeId: "planner",
      nodeStatusById: {
        planner: "active",
        architect: "idle",
        coder: "idle",
      },
      activityByNodeId: {
        planner: 1,
        architect: 0,
        coder: 0,
      },
      logs: [
        {
          id: "log-2",
          event: "run_started",
          timestamp: "2026-02-25T00:00:00Z",
          node: null,
          state: null,
          activity_score: null,
          severity: "info",
          message: "Workflow run started.",
        },
      ],
      errorMessage: "another error",
    });

    useAgentStore.getState().resetRunVisualization(false);
    const state = useAgentStore.getState();
    expect(state.activeNodeId).toBeNull();
    expect(state.nodeStatusById).toEqual({
      planner: "idle",
      architect: "idle",
      coder: "idle",
    });
    expect(state.activityByNodeId).toEqual({
      planner: 0,
      architect: 0,
      coder: 0,
    });
    expect(state.logs).toHaveLength(1);
    expect(state.logs[0]?.id).toBe("log-2");
    expect(state.errorMessage).toBeNull();
  });

  it("runs startAgentRun and consumes SSE events", async () => {
    localStorage.setItem("X-API-KEY", "test-api-key");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("", {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    sseMocks.consumeSseStream.mockImplementation(async (_response, onEvent) => {
      onEvent({
        event: "on_node_start",
        data: {
          event_id: 1,
          timestamp: "2026-02-25T00:00:00Z",
          node: "planner",
          state: "active",
          activity_score: 1.0,
          severity: "info",
          message: "Node planner active.",
          node_states: {
            planner: "active",
            architect: "idle",
            coder: "idle",
          },
          activity_by_node_id: {
            planner: 1.0,
            architect: 0.0,
            coder: 0.0,
          },
        },
      });
      onEvent({
        event: "run_complete",
        data: {
          event_id: 2,
          timestamp: "2026-02-25T00:00:01Z",
          severity: "info",
          message: "Workflow finished successfully.",
        },
      });
    });

    await useAgentStore.getState().startAgentRun({
      userPrompt: "Build a simple API.",
      workspaceMode: "continue",
    });

    const state = useAgentStore.getState();
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/stream",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "X-API-KEY": "test-api-key",
        }),
      })
    );
    expect(sseMocks.consumeSseStream).toHaveBeenCalledTimes(1);
    expect(state.logs.some((entry) => entry.event === "run_complete")).toBe(true);
    expect(state.nodeStatusById.planner).toBe("completed");
    expect(state.isGenerating).toBe(false);

  });

  it("reuses the current workspace when workspaceMode is continue", async () => {
    localStorage.setItem("X-API-KEY", "test-api-key");
    workspaceRef.id = "ws_existing";
    useAgentStore.setState({
      workspaceId: "ws_existing",
      workspaceExpiresAt: "2026-12-31T00:00:00Z",
    });

    const fetchMock = vi.fn().mockResolvedValue(
      new Response("", {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    sseMocks.consumeSseStream.mockImplementationOnce(async (_response, onEvent) => {
      onEvent({
        event: "run_complete",
        data: {
          event_id: 2,
          timestamp: "2026-02-25T00:00:01Z",
          severity: "info",
          message: "Workflow finished successfully.",
        },
      });
    });

    await useAgentStore.getState().startAgentRun({
      userPrompt: "Continue workspace run.",
      workspaceMode: "continue",
    });

    expect(apiMocks.createWorkspaceSession).not.toHaveBeenCalled();
    const request = fetchMock.mock.calls[0]?.[1] as RequestInit | undefined;
    const headers = (request?.headers ?? {}) as Record<string, string>;
    expect(headers["X-Workspace-ID"]).toBe("ws_existing");
    const body = JSON.parse(String(request?.body));
    expect(body.workspace_id).toBe("ws_existing");
  });

  it("creates a fresh workspace in fresh mode and clears stale workspace state before streaming", async () => {
    localStorage.setItem("X-API-KEY", "test-api-key");
    workspaceRef.id = "ws_old";
    useAgentStore.setState({
      workspaceId: "ws_old",
      workspaceExpiresAt: "2026-12-31T00:00:00Z",
      files: { "old.txt": "old content" },
      treeNodes: [{ name: "old.txt", path: "old.txt", type: "file" }],
      activeFilePath: "old.txt",
      skippedBinary: ["old.bin"],
      logs: [
        {
          id: "old-log",
          event: "run_complete",
          timestamp: "2026-02-24T00:00:00Z",
          node: null,
          state: "completed",
          activity_score: 0,
          severity: "info",
          message: "Old run complete.",
        },
      ],
      activeNodeId: "planner",
      nodeStatusById: {
        planner: "active",
        architect: "idle",
        coder: "idle",
      },
      activityByNodeId: {
        planner: 1,
        architect: 0,
        coder: 0,
      },
    });
    apiMocks.createWorkspaceSession.mockResolvedValueOnce({
      workspace_id: "ws_fresh",
      expires_at: "2026-12-31T00:00:00Z",
    });
    apiMocks.fetchWorkspaceFiles.mockResolvedValueOnce({
      workspace_id: "ws_fresh",
      expires_at: "2026-12-31T00:00:00Z",
      files: {},
      skipped_binary: [],
    });
    apiMocks.fetchWorkspaceTree.mockResolvedValueOnce({
      workspace_id: "ws_fresh",
      expires_at: "2026-12-31T00:00:00Z",
      root: "generated_project",
      nodes: [],
    });

    const fetchMock = vi.fn().mockResolvedValue(
      new Response("", {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    sseMocks.consumeSseStream.mockImplementationOnce(async (_response, onEvent) => {
      const stateAtStreamStart = useAgentStore.getState();
      expect(stateAtStreamStart.files).toEqual({});
      expect(stateAtStreamStart.treeNodes).toEqual([]);
      expect(stateAtStreamStart.activeFilePath).toBeNull();
      expect(stateAtStreamStart.skippedBinary).toEqual([]);
      expect(stateAtStreamStart.logs).toEqual([]);
      expect(stateAtStreamStart.activeNodeId).toBeNull();
      expect(stateAtStreamStart.nodeStatusById).toEqual({
        planner: "idle",
        architect: "idle",
        coder: "idle",
      });
      onEvent({
        event: "run_complete",
        data: {
          event_id: 22,
          timestamp: "2026-02-25T00:00:01Z",
          severity: "info",
          message: "Workflow finished successfully.",
        },
      });
    });

    await useAgentStore.getState().startAgentRun({
      userPrompt: "Fresh workspace run.",
      workspaceMode: "fresh",
    });

    expect(apiMocks.createWorkspaceSession).toHaveBeenCalledTimes(1);
    const request = fetchMock.mock.calls[0]?.[1] as RequestInit | undefined;
    const headers = (request?.headers ?? {}) as Record<string, string>;
    expect(headers["X-Workspace-ID"]).toBe("ws_fresh");
    const body = JSON.parse(String(request?.body));
    expect(body.workspace_id).toBe("ws_fresh");
  });

  it("resetWorkspaceSession aborts active generation and keeps logs with a stop row", async () => {
    localStorage.setItem("X-API-KEY", "test-api-key");
    workspaceRef.id = "ws_active";
    useAgentStore.setState({
      workspaceId: "ws_active",
      workspaceExpiresAt: "2026-12-31T00:00:00Z",
      files: { "old.txt": "old content" },
      treeNodes: [{ name: "old.txt", path: "old.txt", type: "file" }],
      activeFilePath: "old.txt",
    });

    const fetchMock = vi.fn().mockImplementation((_url: unknown, init?: RequestInit) => {
      return new Promise<Response>((_resolve, reject) => {
        const signal = init?.signal as AbortSignal | undefined;
        if (!signal) {
          reject(new Error("missing signal"));
          return;
        }
        if (signal.aborted) {
          const abortedError = Object.assign(new Error("aborted"), { name: "AbortError" });
          reject(abortedError);
          return;
        }
        signal.addEventListener(
          "abort",
          () => {
            const abortedError = Object.assign(new Error("aborted"), { name: "AbortError" });
            reject(abortedError);
          },
          { once: true }
        );
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const runPromise = useAgentStore.getState().startAgentRun({
      userPrompt: "Run and abort.",
      workspaceMode: "continue",
    });

    await Promise.resolve();
    await useAgentStore.getState().resetWorkspaceSession();
    await runPromise;

    const state = useAgentStore.getState();
    expect(state.isGenerating).toBe(false);
    expect(state.workspaceId).toBe("ws_test_1");
    expect(state.files).toEqual({});
    expect(state.treeNodes).toEqual([]);
    expect(state.activeFilePath).toBeNull();
    expect(state.logs.some((entry) => entry.message === "Generation stopped by session reset.")).toBe(true);
    expect(state.logs.some((entry) => entry.severity === "error")).toBe(false);
  });

  it("classifies stream request failures and surfaces actionable hints", async () => {
    localStorage.setItem("X-API-KEY", "test-api-key");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            code: "workflow_error",
            message: "Workflow execution failed.",
            details: {
              run_id: "run_123",
              error_type: "connection_error",
              hint: "Network connection to provider failed. Verify network/provider access and retry.",
            },
          },
        }),
        {
          status: 500,
          headers: { "Content-Type": "application/json" },
        }
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    await useAgentStore.getState().startAgentRun({
      userPrompt: "Build a simple API.",
      workspaceMode: "continue",
    });

    const state = useAgentStore.getState();
    const latestLog = state.logs.at(-1);
    expect(latestLog?.event).toBe("error");
    expect(latestLog?.error_type).toBe("connection_error");
    expect(latestLog?.hint).toContain("Network connection to provider failed");
    expect(latestLog?.message).toBe("Provider connection failed.");
    expect(state.errorMessage).toContain("Provider connection failed.");
    expect(state.errorMessage).toContain("Network connection to provider failed");
    expect(state.isGenerating).toBe(false);
    expect(sseMocks.consumeSseStream).not.toHaveBeenCalled();
  });

  it("handles secure workspace auth failures without noisy logs", async () => {
    apiMocks.fetchWorkspaceFiles.mockRejectedValueOnce(
      new Error("Workspace API authentication required. Provide a non-empty X-API-KEY header.")
    );

    await useAgentStore.getState().fetchFiles();

    const state = useAgentStore.getState();
    expect(state.errorMessage).toContain("Workspace access requires an API key");
    expect(state.logs).toHaveLength(0);
  });

  it("records a descriptive error when workspace fetch fails", async () => {
    apiMocks.fetchWorkspaceFiles.mockRejectedValueOnce(new Error("workspace unavailable"));

    await useAgentStore.getState().fetchFiles();

    const state = useAgentStore.getState();
    expect(state.errorMessage).toContain("workspace unavailable");
    expect(state.logs.at(-1)?.event).toBe("error");
  });
});
