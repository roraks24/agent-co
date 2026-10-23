import axios, { AxiosError, AxiosInstance } from "axios";
import { getStoredApiKey } from "@/app/lib/api-key-storage";
import { notifyReachable, notifyUnreachable } from "@/app/lib/reachability";

export type NodeId = "planner" | "architect" | "coder";

export interface GraphSchemaNode {
  id: string;
  label: string;
  type: string;
  position: { x: number; y: number };
  data: Record<string, unknown>;
}

export interface GraphSchemaEdge {
  id: string;
  source: string;
  target: string;
  animated: boolean;
  type: string;
}

export interface GraphSchemaResponse {
  graph_id: string;
  nodes: GraphSchemaNode[];
  edges: GraphSchemaEdge[];
  state_model: Array<"idle" | "active" | "completed" | "error">;
  activity_model: { min: number; max: number };
}

export interface WorkspaceTreeNode {
  name: string;
  path: string;
  type: "file" | "directory";
  size?: number;
  children?: WorkspaceTreeNode[];
}

export interface WorkspaceTreeResponse {
  root: string;
  workspace_id: string;
  expires_at: string;
  nodes: WorkspaceTreeNode[];
}

export interface WorkspaceFilesResponse {
  workspace_id: string;
  expires_at: string;
  files: Record<string, string>;
  skipped_binary: string[];
}

export interface WorkspaceFileResponse {
  workspace_id: string;
  expires_at: string;
  path: string;
  content: string;
}

export interface WorkspaceSessionResponse {
  workspace_id: string;
  expires_at: string;
}

export interface RunAgentRequest {
  user_prompt: string;
  api_key?: string;
  mutable_prompt?: string | null;
  prompt_overrides?: Record<string, string> | null;
  workspace_id?: string | null;
  model?: string | null;
  recursion_limit?: number;
}

export interface PromptNodeSchema {
  immutable_prefix: string;
  default_mutable: string;
}

export interface PromptSchemaResponse {
  nodes: Record<NodeId, PromptNodeSchema>;
  policy: {
    max_mutable_prompt_chars: number;
    immutable_rules: string[];
  };
}

interface ApiErrorBody {
  code?: string;
  message?: string;
  details?: unknown;
}

interface ApiErrorEnvelope {
  error?: ApiErrorBody;
  detail?: unknown;
}

const configuredApiBaseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() ?? "";
const isLocalHost =
  typeof window !== "undefined" &&
  (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1");
const isLocalRuntime = !import.meta.env.PROD || isLocalHost;
const localDevApiBaseUrl = "http://localhost:8000";
const missingApiBaseUrlMessage =
  "API base URL is not configured. Set VITE_API_BASE_URL to your deployed backend URL.";

export const API_BASE_URL = configuredApiBaseUrl || (isLocalRuntime ? localDevApiBaseUrl : "");
let currentWorkspaceId: string | null = null;

export const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL
});

export function ensureApiBaseUrlConfigured(): void {
  if (!API_BASE_URL) {
    throw new Error(missingApiBaseUrlMessage);
  }
}

export function setWorkspaceId(workspaceId: string | null) {
  currentWorkspaceId = workspaceId?.trim() || null;
}

export function getWorkspaceId(): string | null {
  return currentWorkspaceId;
}

export function extractErrorMessage(payload: unknown, fallback = "Request failed."): string {
  if (payload == null) {
    return fallback;
  }

  if (typeof payload === "string") {
    return payload;
  }

  if (payload instanceof Error && payload.message) {
    return payload.message;
  }

  if (typeof payload !== "object" || Array.isArray(payload)) {
    return fallback;
  }

  const body = payload as ApiErrorEnvelope;
  if (body.error?.message && body.error.message.trim()) {
    return body.error.message;
  }

  if (typeof body.detail === "string" && body.detail.trim()) {
    return body.detail;
  }

  return fallback;
}

apiClient.interceptors.request.use((config) => {
  if (!API_BASE_URL) {
    return Promise.reject(new Error(missingApiBaseUrlMessage));
  }

  const key = getStoredApiKey();

  if (key) {
    config.headers = config.headers ?? {};
    config.headers["X-API-KEY"] = key;
  }
  if (currentWorkspaceId) {
    config.headers = config.headers ?? {};
    config.headers["X-Workspace-ID"] = currentWorkspaceId;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => {
    notifyReachable();
    return response;
  },
  (error: unknown) => {
    const axiosError = error as AxiosError;

    // A response of any status proves the backend is up; only a request that
    // never completed a round trip counts as unreachable. Errors raised by the
    // request interceptor have neither a response nor a transport code, so they
    // are deliberately left alone.
    if (axiosError.response) {
      notifyReachable();
    } else if (axiosError.code === "ERR_NETWORK" || axiosError.code === "ECONNABORTED") {
      notifyUnreachable(axiosError.message || "The request did not reach the backend.");
    }

    const payload = axiosError.response?.data;
    const fallback = axiosError.message || "Request failed.";
    const message = extractErrorMessage(payload, fallback);
    return Promise.reject(new Error(message));
  }
);

export async function fetchWorkspaceTree(): Promise<WorkspaceTreeResponse> {
  const response = await apiClient.get<WorkspaceTreeResponse>("/workspace/tree");
  return response.data;
}

export async function fetchWorkspaceFiles(): Promise<WorkspaceFilesResponse> {
  const response = await apiClient.get<WorkspaceFilesResponse>("/workspace/files");
  return response.data;
}

export async function readWorkspaceFile(path: string): Promise<WorkspaceFileResponse> {
  const response = await apiClient.get<WorkspaceFileResponse>("/workspace/file", { params: { path } });
  return response.data;
}

export async function writeWorkspaceFile(path: string, content: string): Promise<WorkspaceFileResponse> {
  const response = await apiClient.put<WorkspaceFileResponse>("/workspace/file", { path, content });
  return response.data;
}

export async function createWorkspaceFolder(path: string): Promise<{ path: string }> {
  const response = await apiClient.post<{ path: string }>("/workspace/folder", { path });
  return response.data;
}

export async function renameWorkspacePath(
  fromPath: string,
  toPath: string,
  overwrite = false
): Promise<{ path: string }> {
  const response = await apiClient.post<{ path: string }>("/workspace/rename", {
    from_path: fromPath,
    to_path: toPath,
    overwrite
  });
  return response.data;
}

export async function deleteWorkspacePath(path: string, recursive = false): Promise<{ path: string }> {
  const response = await apiClient.delete<{ path: string }>("/workspace/path", {
    params: { path, recursive }
  });
  return response.data;
}

export async function fetchGraphSchema(): Promise<GraphSchemaResponse> {
  const response = await apiClient.get<GraphSchemaResponse>("/graph/schema");
  return response.data;
}

export async function fetchPromptSchema(): Promise<PromptSchemaResponse> {
  const response = await apiClient.get<PromptSchemaResponse>("/api/prompts");
  return response.data;
}

export async function createWorkspaceSession(): Promise<WorkspaceSessionResponse> {
  const response = await apiClient.post<WorkspaceSessionResponse>("/workspace/session");
  return response.data;
}

export async function touchWorkspaceSession(workspaceId: string): Promise<WorkspaceSessionResponse> {
  const response = await apiClient.post<WorkspaceSessionResponse>(
    `/workspace/session/${encodeURIComponent(workspaceId)}/touch`
  );
  return response.data;
}

export async function deleteWorkspaceSession(workspaceId: string): Promise<{ workspace_id: string; deleted: boolean }> {
  const response = await apiClient.delete<{ workspace_id: string; deleted: boolean }>(
    `/workspace/session/${encodeURIComponent(workspaceId)}`
  );
  return response.data;
}

export function workspaceDownloadUrl(): string {
  return `${API_BASE_URL}/workspace/download`;
}


// ──────────────────────────────────────────────────────────────────────────────
// Provider/Model Selection API
// ──────────────────────────────────────────────────────────────────────────────

export interface ApiProvider {
  id: string;
  provider_name: string;
  display_name: string;
  base_url: string | null;
  model_name: string;
  capability_tier: "LOW" | "MEDIUM" | "HIGH";
  supported_tasks: string[];
  context_window: number;
  max_output_tokens: number;
  latency_tier: string;
  cost_tier: string;
  is_active: boolean;
  is_default: boolean;
  priority: number;
  health_status: string;
  has_api_key: boolean;
  api_key_masked: string;
  created_at: string;
  updated_at: string;
}

export interface CreateProviderRequest {
  id?: string;
  provider_name: string;
  display_name: string;
  api_key?: string;
  base_url?: string | null;
  model_name: string;
  capability_tier?: "LOW" | "MEDIUM" | "HIGH";
  supported_tasks?: string[];
  context_window?: number;
  max_output_tokens?: number;
  latency_tier?: string;
  cost_tier?: string;
  is_active?: boolean;
  is_default?: boolean;
  priority?: number;
}

export interface UpdateProviderRequest {
  provider_name?: string;
  display_name?: string;
  api_key?: string;
  base_url?: string | null;
  model_name?: string;
  capability_tier?: "LOW" | "MEDIUM" | "HIGH";
  supported_tasks?: string[];
  context_window?: number;
  max_output_tokens?: number;
  latency_tier?: string;
  cost_tier?: string;
  is_active?: boolean;
  is_default?: boolean;
  priority?: number;
  health_status?: string;
}

export async function fetchProviders(activeOnly = false): Promise<ApiProvider[]> {
  const response = await apiClient.get<ApiProvider[]>("/api/providers", {
    params: { active_only: activeOnly },
  });
  return response.data;
}

export async function createProvider(data: CreateProviderRequest): Promise<ApiProvider> {
  const response = await apiClient.post<ApiProvider>("/api/providers", data);
  return response.data;
}

export async function updateProvider(
  providerId: string,
  data: UpdateProviderRequest
): Promise<ApiProvider> {
  const response = await apiClient.patch<ApiProvider>(
    `/api/providers/${encodeURIComponent(providerId)}`,
    data
  );
  return response.data;
}

export async function deleteProvider(providerId: string): Promise<{ deleted: boolean }> {
  const response = await apiClient.delete<{ deleted: boolean }>(
    `/api/providers/${encodeURIComponent(providerId)}`
  );
  return response.data;
}

export async function testProvider(
  providerId: string
): Promise<{ provider_id: string; status: string; message: string; has_key: boolean }> {
  const response = await apiClient.post<{
    provider_id: string;
    status: string;
    message: string;
    has_key: boolean;
  }>(`/api/providers/${encodeURIComponent(providerId)}/test`);
  return response.data;
}
