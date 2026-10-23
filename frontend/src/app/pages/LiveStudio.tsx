import { useState, useRef, useEffect, useMemo } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  Play,
  Download,
  RefreshCw,
  FileCode2,
  Folder,
  FolderOpen,
  ChevronRight,
  ChevronDown,
  Loader2,
  X,
  Key,
  Eye,
  EyeOff,
  RotateCcw,
  Menu,
} from "lucide-react";
import type { NodeId, PromptNodeSchema, WorkspaceTreeNode } from "@/app/lib/api-client";
import { ActivityFeed } from "@/app/components/ActivityFeed";
import {
  buildLockedPromptHeader,
  composePromptEditorValue,
  extractEditablePromptSuffix,
} from "@/app/store/prompt-editor";
import {
  getRememberApiKeyPreference,
  getStoredApiKey,
  saveApiKey,
} from "@/app/lib/api-key-storage";
import { useAgentStore } from "@/app/store/useAgentStore";
import { BorderBeam } from "@/app/components/ui/border-beam";

/* ─────────────────────────────────────────────────────────────────────────────
   The studio uses a near-black surface with muted blue and pink accents. Its
   panels sit side by side on wide screens and stack into a scrolling workspace
   at narrower widths, so no panel disappears on a phone.

   Almost everything here is still: only run state, arriving log lines and
   dialogs move. The tree, the editor, the toolbar and the tabs do not.

   Mount ids and data-agent-* attributes below are load-bearing — they are the
   stitching contract documented in README_STITCHING.md. Do not rename them.
   ───────────────────────────────────────────────────────────────────────── */

type NodeStatus = "idle" | "running" | "done" | "error";
type RightPanelTab = "graph" | "audit" | "prompts";

interface FileNode {
  name: string;
  path: string;
  type: "file" | "folder";
  children?: FileNode[];
}

const NODE_UI_CONFIG: Record<NodeId, { label: string; index: string; placeholder: string }> = {
  planner: {
    label: "planner",
    index: "01",
    placeholder: "Override the planner's mutable prompt body...",
  },
  architect: {
    label: "architect",
    index: "02",
    placeholder: "Override the architect's mutable prompt body...",
  },
  coder: {
    label: "coder",
    index: "03",
    placeholder: "Override the coder's mutable prompt body...",
  },
};

const SEVERITY_COLOR: Record<string, string> = {
  info: "var(--ink-2)",
  success: "var(--ok)",
  warn: "var(--warn)",
  error: "var(--bad)",
};

function toFileNodes(nodes: WorkspaceTreeNode[]): FileNode[] {
  return nodes.map((node) => ({
    name: node.name,
    path: node.path,
    type: node.type === "directory" ? "folder" : "file",
    children: node.children ? toFileNodes(node.children) : undefined,
  }));
}

function countTreeFiles(nodes: WorkspaceTreeNode[]): number {
  let total = 0;
  for (const node of nodes) {
    if (node.type === "file") {
      total += 1;
      continue;
    }
    if (node.children && node.children.length > 0) {
      total += countTreeFiles(node.children);
    }
  }
  return total;
}

function toNodeStatus(value: string | undefined): NodeStatus {
  if (value === "active") return "running";
  if (value === "completed") return "done";
  if (value === "error") return "error";
  return "idle";
}

function toSeverity(value: string | undefined): "info" | "success" | "warn" | "error" {
  if (value === "error") return "error";
  if (value === "warn") return "warn";
  if (value === "success") return "success";
  return "info";
}

function toFiniteInteger(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return Math.round(value);
  }
  if (typeof value === "string") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return Math.round(parsed);
    }
  }
  return null;
}

function formatLogTime(timestamp: string): string {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return timestamp;
  }
  return date.toLocaleTimeString([], { hour12: false });
}

function formatLogDetails(details: Record<string, unknown> | null | undefined): string | null {
  if (!details) {
    return null;
  }
  const entries = Object.entries(details).filter(([, value]) => value !== null && value !== undefined);
  if (entries.length === 0) {
    return null;
  }
  return entries
    .slice(0, 4)
    .map(([key, value]) => `${key}=${typeof value === "object" ? JSON.stringify(value) : String(value)}`)
    .join("  ");
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function FileTreeNode({
  node,
  depth,
  activeFile,
  onOpen,
}: {
  node: FileNode;
  depth: number;
  activeFile: string | null;
  onOpen: (path: string) => void;
}) {
  const [open, setOpen] = useState(depth === 0);

  if (node.type === "folder") {
    return (
      <div>
        <button
          type="button"
          className="tree-row"
          onClick={() => setOpen(!open)}
          style={{ paddingLeft: 10 + depth * 13 }}
        >
          {open ? <ChevronDown size={11} strokeWidth={1.75} /> : <ChevronRight size={11} strokeWidth={1.75} />}
          {open ? <FolderOpen size={12} strokeWidth={1.75} /> : <Folder size={12} strokeWidth={1.75} />}
          <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{node.name}</span>
        </button>
        {open &&
          node.children?.map((child) => (
            <FileTreeNode
              key={child.path}
              node={child}
              depth={depth + 1}
              activeFile={activeFile}
              onOpen={onOpen}
            />
          ))}
      </div>
    );
  }

  const isActive = activeFile === node.path;
  return (
    <button
      type="button"
      className="tree-row"
      data-active={isActive}
      data-agent-action="open-file"
      data-agent-file-path={node.path}
      onClick={() => onOpen(node.path)}
      style={{ paddingLeft: 22 + depth * 13 }}
      title={node.path}
    >
      <FileCode2 size={12} strokeWidth={1.75} />
      <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{node.name}</span>
    </button>
  );
}

/**
 * The graph, as a stacked register rather than three boxes squeezed into a
 * narrow column. The node is identified by name; colour says only what state
 * it is in, so the panel still reads correctly in greyscale.
 */
function NodeRow({
  index,
  label,
  status,
  note,
}: {
  index: string;
  label: string;
  status: NodeStatus;
  note?: string | null;
}) {
  const statusWord: Record<NodeStatus, string> = {
    idle: "Idle",
    running: "Running",
    done: "Done",
    error: "Error",
  };
  const statusColor: Record<NodeStatus, string> = {
    idle: "var(--ink-4)",
    running: "var(--accent)",
    done: "var(--ok)",
    error: "var(--bad)",
  };

  return (
    <div className="node-row" data-state={status}>
      <span className="num" style={{ fontSize: "var(--t-micro)", color: "var(--ink-4)" }}>
        {index}
      </span>
      <span style={{ minWidth: 0 }}>
        <span
          className="num"
          style={{
            fontSize: "var(--t-small)",
            color: status === "idle" ? "var(--ink-3)" : "var(--ink)",
          }}
        >
          {label}
        </span>
        {note && (
          <span
            className="num"
            style={{ display: "block", fontSize: "var(--t-micro)", color: "var(--ink-4)", marginTop: 3 }}
          >
            {note}
          </span>
        )}
      </span>
      <span
        className={status === "running" ? "label breathe" : "label"}
        style={{ color: statusColor[status] }}
      >
        {statusWord[status]}
      </span>
    </div>
  );
}

// ─── Dialogs ──────────────────────────────────────────────────────────────────

const overlayMotion = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
  transition: { duration: 0.11 },
};

const dialogMotion = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: 5, transition: { duration: 0.11, ease: [0.55, 0, 1, 0.45] as const } },
  transition: { duration: 0.19, ease: [0.16, 1, 0.3, 1] as const },
};

function ApiKeyModal({
  onClose,
  apiKey,
  rememberKey,
  onSave,
}: {
  onClose: () => void;
  apiKey: string;
  rememberKey: boolean;
  onSave: (key: string, remember: boolean) => void;
}) {
  const [value, setValue] = useState(apiKey);
  const [showKey, setShowKey] = useState(false);
  const [remember, setRemember] = useState(rememberKey);

  const handleSave = () => {
    onSave(value.trim(), remember);
    onClose();
  };

  return (
    <motion.div className="overlay" {...overlayMotion} onClick={onClose}>
      <motion.div
        className="dialog"
        {...dialogMotion}
        onClick={(event) => event.stopPropagation()}
        style={{ maxWidth: 520 }}
        role="dialog"
        aria-label="Groq API key"
      >
        <div className="dialog__head">
          <div>
            <p className="label label--quiet" style={{ marginBottom: 5 }}>
              Credentials
            </p>
            <h3>Groq API key</h3>
          </div>
          <button type="button" className="btn btn--sm btn--bare" onClick={onClose} aria-label="Close">
            <X size={16} strokeWidth={1.75} />
          </button>
        </div>

        <div className="dialog__body">
          <div className="notice notice--ok" style={{ marginBottom: 10 }}>
            <div className="notice__body">
              <div className="notice__title">The key stays in your browser</div>
              <p className="notice__text">
                By default it is held in <code className="tick">sessionStorage</code> and cleared
                when the browser session ends. Tick remember below to move it to{" "}
                <code className="tick">localStorage</code> instead. It is sent to the backend per
                run to build the chat model, and never persisted there.
              </p>
            </div>
          </div>

          <div className="notice notice--warn" style={{ marginBottom: 22 }}>
            <div className="notice__body">
              <div className="notice__title">Free tier has token-per-minute limits</div>
              <p className="notice__text">
                A run makes several model calls. Ask for something small and focused — a
                single-file FastAPI health check rather than a multi-module app — or the limit will
                stop the run half way.
              </p>
            </div>
          </div>

          <label className="label" htmlFor="groq-key-input" style={{ display: "block", marginBottom: 7 }}>
            Key
          </label>
          <div style={{ position: "relative", marginBottom: 14 }}>
            <input
              id="groq-key-input"
              className="field"
              type={showKey ? "text" : "password"}
              value={value}
              onChange={(event) => setValue(event.target.value)}
              placeholder="gsk_..."
              style={{ paddingRight: 40 }}
              onKeyDown={(event) => event.key === "Enter" && handleSave()}
            />
            <button
              type="button"
              className="btn btn--sm btn--bare"
              onClick={() => setShowKey(!showKey)}
              aria-label={showKey ? "Hide key" : "Show key"}
              style={{ position: "absolute", right: 3, top: "50%", transform: "translateY(-50%)" }}
            >
              {showKey ? <EyeOff size={14} strokeWidth={1.75} /> : <Eye size={14} strokeWidth={1.75} />}
            </button>
          </div>

          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: 9,
              marginBottom: 16,
              fontSize: "var(--t-small)",
              color: "var(--ink-3)",
              cursor: "pointer",
            }}
          >
            <input
              type="checkbox"
              checked={remember}
              onChange={(event) => setRemember(event.target.checked)}
              style={{ accentColor: "var(--accent)" }}
            />
            Remember this key on this device (localStorage)
          </label>

          <p className="meta">
            No key yet?{" "}
            <a className="link" href="https://console.groq.com/keys" target="_blank" rel="noopener noreferrer">
              console.groq.com/keys
            </a>
          </p>
        </div>

        <div className="dialog__foot">
          <button type="button" className="btn" onClick={onClose} style={{ flex: 1 }}>
            Cancel
          </button>
          <button type="button" className="btn btn--primary" onClick={handleSave} style={{ flex: 2 }}>
            Save key
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}

function WorkspaceRolloverModal({
  workspaceId,
  fileCount,
  canContinueWorkspace,
  onClose,
  onContinue,
  onStartFresh,
}: {
  workspaceId: string | null;
  fileCount: number;
  canContinueWorkspace: boolean;
  onClose: () => void;
  onContinue: () => void;
  onStartFresh: () => void;
}) {
  return (
    <motion.div className="overlay" {...overlayMotion} onClick={onClose}>
      <motion.div
        className="dialog"
        {...dialogMotion}
        onClick={(event) => event.stopPropagation()}
        style={{ maxWidth: 460 }}
        role="dialog"
        aria-label="Start a new run"
      >
        <div className="dialog__head">
          <div>
            <p className="label label--quiet" style={{ marginBottom: 5 }}>
              New run
            </p>
            <h3>Where should it write?</h3>
          </div>
          <button type="button" className="btn btn--sm btn--bare" onClick={onClose} aria-label="Close">
            <X size={16} strokeWidth={1.75} />
          </button>
        </div>

        <div className="dialog__body">
          <p style={{ fontSize: "var(--t-small)", lineHeight: 1.65, color: "var(--ink-2)", marginBottom: 18 }}>
            This workspace already holds files. Continuing lets the agent read and extend them; a
            fresh workspace starts from nothing.
          </p>
          <dl className="spec">
            <dt>Workspace</dt>
            <dd className="num" style={{ wordBreak: "break-all" }}>
              {workspaceId ?? "not initialized yet"}
            </dd>
            <dt>Files</dt>
            <dd className="num">{fileCount}</dd>
          </dl>
          {!canContinueWorkspace && (
            <p className="meta" style={{ marginTop: 12, color: "var(--warn)" }}>
              Continue is unavailable until a workspace session exists.
            </p>
          )}
        </div>

        <div className="dialog__foot">
          <button
            type="button"
            className="btn"
            onClick={onContinue}
            disabled={!canContinueWorkspace}
            style={{ flex: 1 }}
          >
            Continue current
          </button>
          <button type="button" className="btn btn--primary" onClick={onStartFresh} style={{ flex: 1 }}>
            Start fresh
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}

// ─── Prompt override panel ────────────────────────────────────────────────────

function PromptOverridePanel({
  promptSchema,
  immutableRules,
  maxMutableChars,
  overrides,
  onChange,
}: {
  promptSchema: Record<NodeId, PromptNodeSchema> | null;
  immutableRules: string[];
  maxMutableChars: number;
  overrides: Record<NodeId, string>;
  onChange: (node: NodeId, value: string) => void;
}) {
  const nodeKeys: NodeId[] = ["planner", "architect", "coder"];
  const [selectedNode, setSelectedNode] = useState<NodeId>("planner");
  const cfg = NODE_UI_CONFIG[selectedNode];
  const schemaNode = promptSchema?.[selectedNode];
  const currentOverride = overrides[selectedNode] ?? "";
  const defaultMutable = schemaNode?.default_mutable ?? "";
  const editableValue = currentOverride || defaultMutable;
  const isModified = currentOverride.trim().length > 0;
  const lockedHeader = buildLockedPromptHeader(immutableRules, schemaNode?.immutable_prefix ?? "");
  const editorValue = composePromptEditorValue(lockedHeader, editableValue);
  const overLimit = editableValue.length > maxMutableChars;

  const handleEditorChange = (nextEditorValue: string) => {
    const editableSuffix = extractEditablePromptSuffix(nextEditorValue, lockedHeader);
    if (editableSuffix === null) {
      return;
    }
    onChange(selectedNode, editableSuffix);
  };

  return (
    <div style={{ overflowY: "auto", flex: 1, minHeight: 0 }}>
      <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "flex" }}>
          {nodeKeys.map((nodeKey) => {
            const nodeCfg = NODE_UI_CONFIG[nodeKey];
            const selected = selectedNode === nodeKey;
            return (
              <button
                key={nodeKey}
                type="button"
                onClick={() => setSelectedNode(nodeKey)}
                className="num"
                style={{
                  flex: 1,
                  padding: "7px 4px",
                  border: "1px solid var(--rule)",
                  borderRightWidth: nodeKey === "coder" ? 1 : 0,
                  borderBottomWidth: 2,
                  borderBottomColor: selected ? "var(--accent)" : "var(--rule)",
                  background: selected ? "var(--surface-2)" : "transparent",
                  color: selected ? "var(--ink)" : "var(--ink-4)",
                  fontSize: "var(--t-micro)",
                  cursor: "pointer",
                  transition: "color var(--dur-fast) linear, border-color var(--dur-fast) linear",
                }}
              >
                {nodeCfg.label}
              </button>
            );
          })}
        </div>

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
          <span className="label">
            {cfg.index} · {cfg.label}
            {isModified ? " · overridden" : ""}
          </span>
          {isModified && (
            <button
              type="button"
              className="btn btn--sm btn--bare"
              onClick={() => onChange(selectedNode, "")}
              title="Reset to the backend default mutable text"
            >
              <RotateCcw size={11} strokeWidth={1.75} />
              Reset
            </button>
          )}
        </div>

        <textarea
          className="field"
          value={editorValue}
          onChange={(event) => handleEditorChange(event.target.value)}
          placeholder={cfg.placeholder}
          rows={18}
          spellCheck={false}
          style={{ lineHeight: 1.7, resize: "vertical" }}
        />

        <div
          className="num"
          style={{
            fontSize: "var(--t-micro)",
            textAlign: "right",
            color: overLimit ? "var(--bad)" : "var(--ink-4)",
          }}
        >
          {editableValue.length} / {maxMutableChars}
        </div>

        <p className="meta" style={{ fontSize: "var(--t-micro)", lineHeight: 1.7, color: "var(--ink-4)" }}>
          Everything above the divider is locked. Only the text below it is sent, as{" "}
          <span style={{ color: "var(--ink-2)" }}>prompt_overrides</span> for {cfg.label}.
        </p>
      </div>
    </div>
  );
}

// ─── Execution Audit Trail Panel ─────────────────────────────────────────────

function AuditTrailPanel({
  executionPlan,
  executionRecords,
  objectiveStatus,
  finalSummary,
  verification,
}: {
  executionPlan: any;
  executionRecords: any[];
  objectiveStatus: string | null;
  finalSummary: string | null;
  verification: any;
}) {
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);

  if (!executionPlan && executionRecords.length === 0 && !objectiveStatus) {
    return (
      <div style={{ padding: 20, color: "var(--ink-4)", textAlign: "center", lineHeight: 1.8 }}>
        <p className="meta">
          No execution recorded yet. Start a run to inspect the dynamic plan, real tool calls,
          argument inspection, and verified evidence.
        </p>
      </div>
    );
  }

  const toggleExpand = (index: number) => {
    setExpandedIndex(expandedIndex === index ? null : index);
  };

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: 14, display: "flex", flexDirection: "column", gap: 14, minHeight: 0 }}>
      {/* Objective & Verification Banner */}
      {objectiveStatus && (
        <div
          className={
            objectiveStatus === "SUCCESS"
              ? "notice notice--ok"
              : objectiveStatus === "PARTIAL_SUCCESS"
              ? "notice notice--warn"
              : "notice notice--bad"
          }
        >
          <div className="notice__body">
            <div className="notice__title" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span>Verification Status: {objectiveStatus}</span>
            </div>
            {verification?.evidence_summary && (
              <p className="notice__text" style={{ marginTop: 4 }}>
                {verification.evidence_summary}
              </p>
            )}
            {verification?.criteria_evaluated && verification.criteria_evaluated.length > 0 && (
              <div style={{ marginTop: 8, fontSize: "var(--t-micro)", color: "var(--ink-3)" }}>
                {verification.criteria_evaluated.map((c: string, i: number) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span>•</span>
                    <span>{c}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Structured Action Plan */}
      {executionPlan && (
        <div style={{ border: "1px solid var(--rule)", borderRadius: 6, padding: 12, background: "var(--surface)" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
            <span className="label">Planned Action Steps</span>
            <span className="num" style={{ fontSize: "var(--t-micro)", color: "var(--accent)" }}>
              {executionPlan.task_type?.toUpperCase()}
            </span>
          </div>
          <p style={{ fontSize: "var(--t-small)", color: "var(--ink)", marginBottom: 10, fontWeight: 500 }}>
            {executionPlan.objective}
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {executionPlan.steps?.map((step: any, idx: number) => (
              <div
                key={step.id || idx}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "6px 8px",
                  background: "var(--surface-2)",
                  borderRadius: 4,
                  fontSize: "var(--t-small)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
                  <span className="num" style={{ fontSize: "var(--t-micro)", color: "var(--ink-4)" }}>
                    {idx + 1}
                  </span>
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {step.title}
                  </span>
                </div>
                <span
                  className="num"
                  style={{
                    fontSize: "var(--t-micro)",
                    padding: "2px 6px",
                    borderRadius: 3,
                    background: "var(--rule)",
                    color: "var(--ink-2)",
                    flexShrink: 0,
                  }}
                >
                  {step.tool_name}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tool Execution Cards */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span className="label">Executed Actions ({executionRecords.length})</span>
        </div>

        {executionRecords.map((rec: any, idx: number) => {
          const isExpanded = expandedIndex === idx;
          const isSuccess = rec.status === "success";

          return (
            <div
              key={idx}
              style={{
                border: "1px solid var(--rule)",
                borderRadius: 5,
                background: "var(--surface)",
                overflow: "hidden",
                fontSize: "var(--t-small)",
              }}
            >
              <div
                onClick={() => toggleExpand(idx)}
                style={{
                  padding: "8px 12px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  cursor: "pointer",
                  background: isExpanded ? "var(--surface-2)" : "transparent",
                  borderBottom: isExpanded ? "1px solid var(--rule)" : "none",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span
                    className="dot"
                    style={{
                      background: isSuccess ? "var(--ok)" : "var(--bad)",
                      width: 7,
                      height: 7,
                    }}
                  />
                  <span style={{ fontWeight: 600, color: "var(--ink)" }}>{rec.tool_name}</span>
                  <span className="num" style={{ fontSize: "var(--t-micro)", color: "var(--ink-4)" }}>
                    {rec.step_id}
                  </span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span className="num" style={{ fontSize: "var(--t-micro)", color: "var(--ink-3)" }}>
                    {rec.duration_ms}ms
                  </span>
                  <span
                    className="num"
                    style={{
                      fontSize: "var(--t-micro)",
                      color: isSuccess ? "var(--ok)" : "var(--bad)",
                      textTransform: "uppercase",
                    }}
                  >
                    {rec.status}
                  </span>
                  {isExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                </div>
              </div>

              {isExpanded && (
                <div style={{ padding: "10px 12px", display: "flex", flexDirection: "column", gap: 8, background: "var(--bg)" }}>
                  <div>
                    <span className="label" style={{ fontSize: "var(--t-micro)", display: "block", marginBottom: 4 }}>
                      Input Parameters
                    </span>
                    <pre
                      style={{
                        margin: 0,
                        padding: 8,
                        borderRadius: 4,
                        background: "var(--surface)",
                        fontSize: "var(--t-micro)",
                        fontFamily: "var(--face-mono)",
                        overflowX: "auto",
                        color: "var(--ink-2)",
                      }}
                    >
                      {JSON.stringify(rec.tool_args, null, 2)}
                    </pre>
                  </div>

                  <div>
                    <span className="label" style={{ fontSize: "var(--t-micro)", display: "block", marginBottom: 4 }}>
                      Output Result
                    </span>
                    <pre
                      style={{
                        margin: 0,
                        padding: 8,
                        borderRadius: 4,
                        background: "var(--surface)",
                        fontSize: "var(--t-micro)",
                        fontFamily: "var(--face-mono)",
                        maxHeight: 180,
                        overflowY: "auto",
                        color: rec.error ? "var(--bad)" : "var(--ink-2)",
                        whiteSpace: "pre-wrap",
                      }}
                    >
                      {rec.error || (typeof rec.tool_result === "object" ? JSON.stringify(rec.tool_result, null, 2) : String(rec.tool_result ?? "No output"))}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Deliverable Summary */}
      {finalSummary && (
        <div style={{ border: "1px solid var(--rule)", borderRadius: 6, padding: 12, background: "var(--surface)" }}>
          <span className="label" style={{ display: "block", marginBottom: 8 }}>
            Executive Deliverable
          </span>
          <div
            style={{
              fontSize: "var(--t-small)",
              lineHeight: 1.7,
              color: "var(--ink-2)",
              whiteSpace: "pre-wrap",
              fontFamily: "var(--face-mono)",
            }}
          >
            {finalSummary}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Studio ───────────────────────────────────────────────────────────────────

export function LiveStudio() {
  const [prompt, setPrompt] = useState("");
  const [wheelTurn, setWheelTurn] = useState(0);
  const wheelFace = ((wheelTurn % 3) + 3) % 3;
  const [rightTab, setRightTab] = useState<RightPanelTab>("graph");
  const [showGraphLogs, setShowGraphLogs] = useState(false);
  const [showApiModal, setShowApiModal] = useState(false);
  const [showWorkspaceRolloverModal, setShowWorkspaceRolloverModal] = useState(false);
  const [apiKey, setApiKey] = useState(() => getStoredApiKey());
  const [rememberApiKey, setRememberApiKey] = useState(() => getRememberApiKeyPreference());
  const [editorContent, setEditorContent] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  const logsContainerRef = useRef<HTMLDivElement>(null);
  const wheelFaceRefs = useRef<Array<HTMLElement | null>>([]);
  const wheelDragStartRef = useRef<number | null>(null);
  const lastWheelTurnRef = useRef(0);
  const shouldStickToBottomRef = useRef(true);
  const workspaceId = useAgentStore((state) => state.workspaceId);
  const workspaceExpiresAt = useAgentStore((state) => state.workspaceExpiresAt);
  const files = useAgentStore((state) => state.files);
  const skippedBinary = useAgentStore((state) => state.skippedBinary);
  const treeNodes = useAgentStore((state) => state.treeNodes);
  const activeFile = useAgentStore((state) => state.activeFilePath);
  const activeNodeId = useAgentStore((state) => state.activeNodeId);
  const logs = useAgentStore((state) => state.logs);
  const isRunning = useAgentStore((state) => state.isGenerating);
  const promptOverrides = useAgentStore((state) => state.promptOverrides);
  const nodeStatusById = useAgentStore((state) => state.nodeStatusById);
  const promptSchema = useAgentStore((state) => state.promptSchema);
  const maxMutablePromptChars = useAgentStore((state) => state.maxMutablePromptChars);
  const immutableRules = useAgentStore((state) => state.immutableRules);
  const errorMessage = useAgentStore((state) => state.errorMessage);
  const executionPlan = useAgentStore((state) => state.executionPlan);
  const executionRecords = useAgentStore((state) => state.executionRecords);
  const objectiveStatus = useAgentStore((state) => state.objectiveStatus);
  const finalSummary = useAgentStore((state) => state.finalSummary);
  const verification = useAgentStore((state) => state.verification);

  const initWorkspaceSession = useAgentStore((state) => state.initWorkspaceSession);
  const resetWorkspaceSession = useAgentStore((state) => state.resetWorkspaceSession);
  const fetchFiles = useAgentStore((state) => state.fetchFiles);
  const fetchTree = useAgentStore((state) => state.fetchTree);
  const fetchGraphSchema = useAgentStore((state) => state.fetchGraphSchema);
  const fetchPromptSchema = useAgentStore((state) => state.fetchPromptSchema);
  const readFile = useAgentStore((state) => state.readFile);
  const updateFileContent = useAgentStore((state) => state.updateFileContent);
  const startAgentRun = useAgentStore((state) => state.startAgentRun);
  const resetRunVisualization = useAgentStore((state) => state.resetRunVisualization);
  const downloadWorkspaceZip = useAgentStore((state) => state.downloadWorkspaceZip);
  const setActiveFilePath = useAgentStore((state) => state.setActiveFilePath);
  const setPromptOverride = useAgentStore((state) => state.setPromptOverride);
  const lastSubmittedPromptRef = useRef(prompt.trim());
  const hasResetForPromptDraftRef = useRef(false);

  useEffect(() => {
    void (async () => {
      await initWorkspaceSession();
      await Promise.all([fetchFiles(), fetchTree(), fetchGraphSchema(), fetchPromptSchema()]);
    })();
  }, [fetchFiles, fetchGraphSchema, fetchPromptSchema, fetchTree, initWorkspaceSession]);

  useEffect(() => {
    const container = logsContainerRef.current;
    if (!container || !shouldStickToBottomRef.current) {
      return;
    }
    container.scrollTop = container.scrollHeight;
  }, [logs]);

  useEffect(() => {
    wheelFaceRefs.current.forEach((face, index) => {
      if (face) face.inert = index !== wheelFace;
    });
  }, [wheelFace]);

  useEffect(() => {
    if (errorMessage?.toLowerCase().includes("workspace access requires an api key")) {
      setShowApiModal(true);
    }
  }, [errorMessage]);

  useEffect(() => {
    if (!isRunning) {
      return;
    }
    void fetchTree();
    const intervalId = window.setInterval(() => {
      void fetchTree();
    }, 1200);

    return () => window.clearInterval(intervalId);
  }, [fetchTree, isRunning]);

  useEffect(() => {
    if (!activeFile) {
      setEditorContent("");
      return;
    }
    setEditorContent(files[activeFile] ?? "");
  }, [activeFile, files]);

  const handleSaveKey = (key: string, remember: boolean) => {
    const trimmed = key.trim();
    setApiKey(trimmed);
    setRememberApiKey(remember);
    saveApiKey(trimmed, remember);
  };

  const handleOverrideChange = (node: NodeId, value: string) => {
    setPromptOverride(node, value.slice(0, maxMutablePromptChars));
  };

  const handlePromptChange = (nextPrompt: string) => {
    setPrompt(nextPrompt);
    if (isRunning) {
      return;
    }

    const normalizedPrompt = nextPrompt.trim();
    const lastSubmittedPrompt = lastSubmittedPromptRef.current;
    if (normalizedPrompt === lastSubmittedPrompt) {
      hasResetForPromptDraftRef.current = false;
      return;
    }

    if (!hasResetForPromptDraftRef.current) {
      resetRunVisualization(true);
      hasResetForPromptDraftRef.current = true;
    }
  };

  const runWithWorkspaceMode = (workspaceMode: "fresh" | "continue") => {
    if (!prompt.trim() || isRunning) return;
    lastSubmittedPromptRef.current = prompt.trim();
    hasResetForPromptDraftRef.current = false;
    setShowWorkspaceRolloverModal(false);
    void startAgentRun({ userPrompt: prompt, workspaceMode });
  };

  const handleRun = () => {
    if (!prompt.trim() || isRunning) return;
    if (!getStoredApiKey()) {
      setShowApiModal(true);
      return;
    }
    if (!hasWorkspaceArtifacts) {
      runWithWorkspaceMode("continue");
      return;
    }
    setShowWorkspaceRolloverModal(true);
  };

  const handleRefresh = () => {
    void Promise.all([fetchFiles(), fetchTree()]);
  };

  const handleOpenFile = (path: string) => {
    void readFile(path);
  };

  const handleSaveFile = () => {
    if (!activeFile) return;
    setIsSaving(true);
    void updateFileContent(activeFile, editorContent).finally(() => setIsSaving(false));
  };

  const handleDownload = () => {
    void downloadWorkspaceZip();
  };

  const handleResetWorkspace = () => {
    void resetWorkspaceSession().then(() => Promise.all([fetchFiles(), fetchTree()]));
  };

  const handleLogsScroll = () => {
    const container = logsContainerRef.current;
    if (!container) {
      return;
    }
    const distanceFromBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    shouldStickToBottomRef.current = distanceFromBottom <= 48;
  };

  const fileNodes = useMemo(() => toFileNodes(treeNodes), [treeNodes]);
  const activePreviewFile = useMemo(() => {
    const entry = Object.entries(files).find(([path]) => /(^|\/)index\.html$/i.test(path));
    return entry?.[0] ?? null;
  }, [files]);

  const previewHtml = useMemo(() => {
    const entry = Object.entries(files).find(([path]) => /(^|\/)index\.html$/i.test(path));
    if (!entry) return "";
    let html = entry[1];

    // Inline relative CSS files from workspace
    html = html.replace(/<link[^>]+rel=["']stylesheet["'][^>]+href=["']([^"']+)["'][^>]*>/gi, (match, href) => {
      const cleanHref = href.replace(/^\.?\//, "");
      const matchedCss = Object.entries(files).find(([p]) => p === cleanHref || p.endsWith("/" + cleanHref));
      if (matchedCss) {
        return `<style>/* inlined ${cleanHref} */\n${matchedCss[1]}</style>`;
      }
      return match;
    });

    // Inline relative JS files from workspace
    html = html.replace(/<script[^>]+src=["']([^"']+)["'][^>]*>\s*<\/script>/gi, (match, src) => {
      if (src.startsWith("http://") || src.startsWith("https://") || src.startsWith("//")) return match;
      const cleanSrc = src.replace(/^\.?\//, "");
      const matchedJs = Object.entries(files).find(([p]) => p === cleanSrc || p.endsWith("/" + cleanSrc));
      if (matchedJs) {
        return `<script>/* inlined ${cleanSrc} */\n${matchedJs[1]}</script>`;
      }
      return match;
    });

    return html;
  }, [files]);
  const hasRun = logs.some((log) => log.event === "run_complete");
  const fileCount = useMemo(() => countTreeFiles(treeNodes), [treeNodes]);
  const hasWorkspaceArtifacts =
    Boolean(workspaceId) && (fileCount > 0 || Object.keys(files).length > 0);
  const canContinueWorkspace = Boolean(workspaceId);
  const isDirty = activeFile ? editorContent !== (files[activeFile] ?? "") : false;
  const nodeStatuses = {
    planner: toNodeStatus(nodeStatusById.planner),
    architect: toNodeStatus(nodeStatusById.architect),
    coder: toNodeStatus(nodeStatusById.coder),
  };
  const keyIsSet = apiKey.length > 0;
  const activeIteration = useMemo(() => {
    if (!activeNodeId) {
      return null;
    }
    for (let index = logs.length - 1; index >= 0; index -= 1) {
      const log = logs[index];
      if (log.node === activeNodeId && typeof log.iteration === "number") {
        return log.iteration;
      }
    }
    return null;
  }, [activeNodeId, logs]);

  const coderFileProgress = useMemo(() => {
    let totalFiles: number | null = null;
    let completedFiles = 0;

    for (let index = 0; index < logs.length; index += 1) {
      const log = logs[index];
      if (!log.details) {
        continue;
      }

      const totalSteps = toFiniteInteger(log.details.total_steps);
      if (typeof totalSteps === "number" && totalSteps > 0) {
        totalFiles = totalFiles === null ? totalSteps : Math.max(totalFiles, totalSteps);
      }

      if (log.node === "coder" && log.event === "on_node_end") {
        const currentStepIdx = toFiniteInteger(log.details.current_step_idx);
        if (typeof currentStepIdx === "number") {
          completedFiles = Math.max(completedFiles, currentStepIdx);
        }
      }
    }

    if (totalFiles === null || totalFiles <= 0) {
      return null;
    }

    const normalizedCompleted = Math.min(Math.max(completedFiles, 0), totalFiles);
    const isCoderRunning = activeNodeId === "coder" && nodeStatuses.coder === "running";
    const activeFile = isCoderRunning
      ? Math.min(normalizedCompleted + 1, totalFiles)
      : null;

    return {
      totalFiles,
      completedFiles: normalizedCompleted,
      activeFile,
    };
  }, [activeNodeId, logs, nodeStatuses.coder]);

  const activeNodeSummary = useMemo(() => {
    if (!activeNodeId) {
      return null;
    }
    if (activeNodeId === "coder" && coderFileProgress) {
      const { activeFile, completedFiles, totalFiles } = coderFileProgress;
      if (activeFile !== null) {
        return `working on file ${activeFile}/${totalFiles} (${completedFiles}/${totalFiles} completed)`;
      }
      return `${completedFiles}/${totalFiles} files completed`;
    }
    if (typeof activeIteration === "number") {
      return `iteration ${activeIteration}`;
    }
    return null;
  }, [activeIteration, activeNodeId, coderFileProgress]);

  const coderNote =
    coderFileProgress && (activeNodeId === "coder" || nodeStatuses.coder !== "idle")
      ? `${coderFileProgress.completedFiles}/${coderFileProgress.totalFiles} files${
          coderFileProgress.activeFile !== null ? ` · on ${coderFileProgress.activeFile}` : ""
        }`
      : null;

  return (
    <div className="studio-page" style={{ flex: 1, minHeight: 0 }}>
      <div
        className="studio-wheel"
        role="region"
        aria-label="Studio workspace wheel. Use left and right arrows, scroll, or drag to switch faces."
        tabIndex={0}
        onWheel={(event) => {
          if (Math.abs(event.deltaX) < 32 && Math.abs(event.deltaY) < 32) return;
          const target = event.target as HTMLElement;
          const canConsumeWheel = (element: HTMLElement, delta: number, axis: "x" | "y") => {
            const style = window.getComputedStyle(element);
            const overflow = axis === "y" ? style.overflowY : style.overflowX;
            if (!/(auto|scroll|overlay)/.test(overflow)) return false;
            const scrollSize = axis === "y" ? element.scrollHeight : element.scrollWidth;
            const clientSize = axis === "y" ? element.clientHeight : element.clientWidth;
            const scrollPosition = axis === "y" ? element.scrollTop : element.scrollLeft;
            if (scrollSize <= clientSize + 1) return false;
            return delta > 0
              ? scrollPosition + clientSize < scrollSize - 1
              : scrollPosition > 0;
          };
          for (let element: HTMLElement | null = target; element && element !== event.currentTarget; element = element.parentElement) {
            if (event.deltaY && canConsumeWheel(element, event.deltaY, "y")) return;
            if (event.deltaX && canConsumeWheel(element, event.deltaX, "x")) return;
          }
          const now = Date.now();
          if (now - lastWheelTurnRef.current < 650) return;
          lastWheelTurnRef.current = now;
          const direction = event.deltaX || event.deltaY;
          setWheelTurn((turn) => turn + (direction > 0 ? 1 : -1));
        }}
        onPointerDown={(event) => {
          if ((event.target as HTMLElement).closest("button, textarea, input, select, a, [contenteditable='true']")) return;
          wheelDragStartRef.current = event.clientX;
        }}
        onPointerUp={(event) => {
          const start = wheelDragStartRef.current;
          wheelDragStartRef.current = null;
          if (start === null || Math.abs(event.clientX - start) < 48) return;
          setWheelTurn((turn) => turn + (event.clientX < start ? 1 : -1));
        }}
        onPointerCancel={() => {
          wheelDragStartRef.current = null;
        }}
        onKeyDown={(event) => {
          if ((event.target as HTMLElement).closest("button, textarea, input, select, a, [contenteditable='true']")) return;
          if (event.key === "ArrowRight") {
            event.preventDefault();
            setWheelTurn((turn) => turn + 1);
          } else if (event.key === "ArrowLeft") {
            event.preventDefault();
            setWheelTurn((turn) => turn - 1);
          }
        }}
      >
        <div
          className="studio-wheel-track"
          style={{ transform: `translateZ(calc(var(--studio-wheel-depth) * -1)) rotateY(${-wheelTurn * 120}deg)` }}
        >
          <section
            ref={(element) => { wheelFaceRefs.current[0] = element; }}
            className="studio-wheel-face studio-wheel-face--command"
            style={{ transform: "translate(-50%, -50%) rotateY(0deg) translateZ(var(--studio-wheel-depth))" }}
            aria-hidden={wheelFace !== 0}
          >
      <section className="studio-intro" aria-labelledby="studio-title">
        <h1 id="studio-title">How can I help today?</h1>
        <p>Type a command or ask a question</p>
      </section>
      {/* ── Toolbar ──────────────────────────────────────────────────────── */}
      <div
        className="studio-toolbar"
      >
        <BorderBeam
          className="studio-prompt-beam studio-prompt-beam--ocean"
          size="line"
          colorVariant="ocean"
          theme="dark"
          strength={0.78}
          duration={2.7}
          borderRadius={11}
          style={{ flex: "1 1 100%", minWidth: 0 }}
        >
          <BorderBeam
            className="studio-prompt-beam studio-prompt-beam--candy"
            size="line"
            colorVariant="candy"
            theme="dark"
            strength={0.58}
            duration={3.6}
            borderRadius={11}
            staticColors
          >
            <textarea
              id="agent-user-prompt"
              className="field studio-prompt"
              value={prompt}
              onChange={(event) => handlePromptChange(event.target.value)}
              rows={1}
              spellCheck={false}
              placeholder="Describe what to build — keep it small enough for the free Groq tier"
              style={{ flex: "1 1 100%", minWidth: 0, resize: "vertical" }}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  handleRun();
                }
              }}
            />
          </BorderBeam>
        </BorderBeam>

        <button
          id="agent-run-button"
          type="button"
          data-agent-action="run-agent"
          className="btn btn--primary"
          onClick={handleRun}
          disabled={isRunning || !prompt.trim()}
        >
          {isRunning ? (
            <>
              <Loader2 size={13} strokeWidth={2} className="rotate" />
              Running
            </>
          ) : (
            <>
              <Play size={12} strokeWidth={2} fill="currentColor" />
              Run
            </>
          )}
        </button>

        <button
          id="agent-download-button"
          type="button"
          data-agent-action="download-zip"
          className="btn"
          onClick={handleDownload}
          disabled={fileCount === 0}
          title="Download the workspace as a ZIP"
        >
          <Download size={13} strokeWidth={1.75} />
          <span className="hidden sm:inline">ZIP</span>
        </button>

        <button
          type="button"
          className={keyIsSet ? "btn btn--ok" : "btn btn--warn"}
          onClick={() => setShowApiModal(true)}
          title="Set the Groq API key"
        >
          <Key size={13} strokeWidth={1.75} />
          <span className="hidden sm:inline">{keyIsSet ? "Key set" : "Add key"}</span>
        </button>

        <button
          type="button"
          className="btn btn--bad"
          onClick={handleResetWorkspace}
          title="Reset the ephemeral workspace session"
        >
          <RotateCcw size={13} strokeWidth={1.75} />
          <span className="hidden sm:inline">Reset</span>
        </button>

        <button
          type="button"
          className="btn studio-graph-toggle"
          onClick={() => setShowGraphLogs((open) => !open)}
          aria-expanded={showGraphLogs}
          aria-controls="agent-graph-logs-panel"
          aria-label={showGraphLogs ? "Close Graph & Logs" : "Open Graph & Logs"}
          title={showGraphLogs ? "Close Graph & Logs" : "Open Graph & Logs"}
        >
          {showGraphLogs ? <X size={14} /> : <Menu size={14} />}
          <span className="hidden sm:inline">Graph &amp; Logs</span>
        </button>

        <div className="studio-workspace-status" style={{ marginLeft: "auto", textAlign: "right" }}>
          <div className="num" style={{ fontSize: "var(--t-micro)", color: "var(--ink-4)" }}>
            ws {workspaceId ?? "initializing..."}
          </div>
          {workspaceExpiresAt && (
            <div className="num" style={{ fontSize: "var(--t-micro)", color: "var(--ink-4)" }}>
              expires {new Date(workspaceExpiresAt).toLocaleTimeString([], { hour12: false })}
            </div>
          )}
        </div>
      </div>

          </section>

          <section
            ref={(element) => { wheelFaceRefs.current[1] = element; }}
            className="studio-wheel-face studio-wheel-face--preview"
            style={{ transform: "translate(-50%, -50%) rotateY(120deg) translateZ(var(--studio-wheel-depth))" }}
            aria-hidden={wheelFace !== 1}
            aria-label="Application preview"
          >
            <div className="studio-preview-window">
              <div className="pane-head studio-face-title">
                <span className="label">App preview</span>
                <span className="studio-preview-state">{previewHtml ? "Workspace preview" : "Waiting for app"}</span>
              </div>
              {previewHtml ? (
                <iframe
                  className="studio-preview-frame"
                  title="Generated application preview"
                  sandbox="allow-scripts allow-forms allow-modals"
                  srcDoc={previewHtml}
                />
              ) : (
                <div className="studio-preview-empty">
                  <div className="studio-preview-empty-window" aria-hidden="true">
                    <span />
                    <span />
                    <span />
                    <div />
                  </div>
                  <p className="label">Your app will appear here</p>
                  <p className="meta">A standalone <code>index.html</code> in the workspace is needed for this preview.</p>
                </div>
              )}
            </div>
          </section>

          <section
            ref={(element) => { wheelFaceRefs.current[2] = element; }}
            className="studio-wheel-face studio-wheel-face--code"
            style={{ transform: "translate(-50%, -50%) rotateY(240deg) translateZ(var(--studio-wheel-depth))" }}
            aria-hidden={wheelFace !== 2}
            aria-label="Workspace files and code"
          >
      {/* ── Panels ───────────────────────────────────────────────────────── */}
      <div className="studio-body">
        {/* File tree */}
        <div id="agent-file-tree" className="studio-tree">
          <div className="pane-head" style={{ justifyContent: "space-between" }}>
            <span className="label">
              Files {fileCount > 0 && <span style={{ color: "var(--ink-4)" }}>· {fileCount}</span>}
            </span>
            <button
              type="button"
              className="btn btn--sm btn--bare"
              data-agent-action="refresh-files"
              onClick={handleRefresh}
              aria-label="Refresh files"
              style={{ padding: 4 }}
            >
              <RefreshCw size={11} strokeWidth={1.75} />
            </button>
          </div>

          {fileNodes.length === 0 && (
            <p className="meta" style={{ padding: "14px 12px", color: "var(--ink-4)", lineHeight: 1.7 }}>
              Empty. Run the agent and files appear here as they are written.
            </p>
          )}

          <div style={{ paddingTop: 4 }}>
            {fileNodes.map((node) => (
              <FileTreeNode
                key={node.path}
                node={node}
                depth={0}
                activeFile={activeFile}
                onOpen={handleOpenFile}
              />
            ))}
          </div>

          {skippedBinary.length > 0 && (
            <p className="meta" style={{ marginTop: 10, padding: "0 12px", fontSize: "var(--t-micro)", color: "var(--warn)" }}>
              {skippedBinary.length} binary file(s) skipped
            </p>
          )}
        </div>

        {/* Editor */}
        <div id="agent-editor" className="studio-editor">
          <div
            className="pane-head"
            style={{ background: "var(--surface)", padding: activeFile ? "0 10px 0 0" : undefined }}
          >
            {activeFile ? (
              <>
                <div
                  className="num"
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    alignSelf: "stretch",
                    padding: "0 14px",
                    fontSize: "var(--t-small)",
                    color: "var(--ink)",
                    background: "var(--bg)",
                    borderRight: "1px solid var(--hair)",
                  }}
                >
                  <FileCode2 size={11} strokeWidth={1.75} />
                  <span>{activeFile.split("/").pop()}</span>
                  {isDirty && <span style={{ color: "var(--warn)" }}>•</span>}
                  <button
                    type="button"
                    onClick={() => setActiveFilePath(null)}
                    aria-label="Close file"
                    style={{
                      background: "none",
                      border: 0,
                      padding: 2,
                      cursor: "pointer",
                      color: "var(--ink-4)",
                      display: "flex",
                    }}
                  >
                    <X size={11} strokeWidth={2} />
                  </button>
                </div>
                <span
                  className="num hidden xl:inline"
                  style={{ fontSize: "var(--t-micro)", color: "var(--ink-4)", marginLeft: 12 }}
                >
                  {activeFile}
                </span>
                <button
                  type="button"
                  data-agent-action="save-file"
                  data-agent-file-path={activeFile}
                  data-agent-source-id="agent-editor-input"
                  className={isDirty ? "btn btn--sm btn--ok" : "btn btn--sm"}
                  onClick={handleSaveFile}
                  disabled={!isDirty || isSaving}
                  style={{ marginLeft: "auto" }}
                >
                  {isSaving ? "Saving" : isDirty ? "Save" : "Saved"}
                </button>
              </>
            ) : (
              <span className="label label--quiet">Editor</span>
            )}
          </div>

          <div style={{ flex: 1, overflowY: "auto", background: "var(--bg)", minHeight: 0 }}>
            {activeFile ? (
              <textarea
                id="agent-editor-input"
                value={editorContent}
                onChange={(event) => setEditorContent(event.target.value)}
                spellCheck={false}
                style={{
                  width: "100%",
                  minHeight: "100%",
                  margin: 0,
                  padding: "18px 22px",
                  fontSize: "var(--t-small)",
                  lineHeight: 1.85,
                  color: "var(--ink)",
                  fontFamily: "var(--face-mono)",
                  background: "transparent",
                  border: "none",
                  outline: "none",
                  resize: "none",
                  boxSizing: "border-box",
                  tabSize: 2,
                }}
                onKeyDown={(event) => {
                  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
                    event.preventDefault();
                    handleSaveFile();
                  }
                }}
              />
            ) : (
              <div
                className="studio-editor-empty"
                style={{
                  height: "100%",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <p
                  className="meta"
                  style={{ color: "var(--ink-4)", textAlign: "center", maxWidth: "44ch", lineHeight: 1.75 }}
                >
                  No file open. Pick one from the tree — you can edit it while the run is still
                  going and save it straight back to the workspace.
                </p>
              </div>
            )}
          </div>
        </div>

      </div>
          </section>
        </div>

        {/* Right panel stays above the rotating faces so its existing toolbar toggle works from any face. */}
        <div
          id="agent-graph-logs-panel"
          className={`studio-aside studio-aside--popover${showGraphLogs ? " is-open" : ""}`}
          aria-hidden={!showGraphLogs}
          hidden={!showGraphLogs}
        >
          <div style={{ display: "flex", borderBottom: "1px solid var(--hair)", flexShrink: 0, background: "var(--surface)" }}>
            <button
              type="button"
              className="tab"
              data-active={rightTab === "graph"}
              onClick={() => setRightTab("graph")}
            >
              Graph &amp; logs
            </button>
            <button
              type="button"
              className="tab"
              data-active={rightTab === "audit"}
              onClick={() => setRightTab("audit")}
            >
              Audit Trail
              {executionRecords.length > 0 && (
                <span className="num" style={{ marginLeft: 6, fontSize: "var(--t-micro)", color: "var(--accent)" }}>
                  ({executionRecords.length})
                </span>
              )}
            </button>
            <button
              type="button"
              className="tab"
              data-active={rightTab === "prompts"}
              onClick={() => setRightTab("prompts")}
            >
              Prompts
            </button>
            <button
              type="button"
              className="btn btn--sm btn--bare"
              onClick={() => setShowGraphLogs(false)}
              aria-label="Close Graph & Logs panel"
              title="Close Graph & Logs"
              style={{
                flex: "0 0 34px",
                width: 34,
                height: 34,
                margin: 5,
                padding: 0,
                display: "grid",
                placeItems: "center",
              }}
            >
              <X size={14} strokeWidth={1.8} />
            </button>
          </div>

          {rightTab === "graph" && (
            <div style={{ display: "flex", flexDirection: "column", flex: 1, overflow: "hidden", minHeight: 0 }}>
              {/* Graph */}
              <div id="agent-graph" style={{ borderBottom: "1px solid var(--hair)", flexShrink: 0 }}>
                <div className="pane-head">
                  <span className="label">Graph</span>
                  {isRunning && (
                    <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6 }}>
                      <span className="dot breathe" style={{ background: "var(--accent)" }} />
                      <span className="label" style={{ color: "var(--accent)" }}>
                        Live
                      </span>
                    </span>
                  )}
                </div>

                <NodeRow
                  index="01"
                  label="planner"
                  status={nodeStatuses.planner}
                  note={activeNodeId === "planner" ? activeNodeSummary : null}
                />
                <NodeRow
                  index="02"
                  label="architect"
                  status={nodeStatuses.architect}
                  note={activeNodeId === "architect" ? activeNodeSummary : null}
                />
                <NodeRow index="03" label="coder" status={nodeStatuses.coder} note={coderNote} />

                {hasRun && (
                  <div
                    className={
                      objectiveStatus === "SUCCESS"
                        ? "notice notice--ok"
                        : objectiveStatus === "PARTIAL_SUCCESS"
                        ? "notice notice--warn"
                        : "notice notice--bad"
                    }
                    style={{ margin: 10 }}
                  >
                    <div className="notice__body">
                      <div className="notice__title">
                        {objectiveStatus === "SUCCESS"
                          ? "Run complete — Objective Succeeded"
                          : objectiveStatus === "PARTIAL_SUCCESS"
                          ? "Run complete — Partial Success"
                          : "Run complete — Objective Failed"}
                      </div>
                      <p className="notice__text">
                        {finalSummary ||
                          `${fileCount} file(s) in the workspace. Take them with the ZIP button.`}
                      </p>
                    </div>
                  </div>
                )}
              </div>

              {/* Activity Feed */}
              <div id="agent-logs" style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", minHeight: 0 }}>
                <div className="pane-head">
                  <span className="label">Activity</span>
                  {isRunning && (
                    <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6 }}>
                      <span className="dot breathe" style={{ background: "var(--accent)" }} />
                      <span className="label" style={{ color: "var(--accent)" }}>
                        Live
                      </span>
                    </span>
                  )}
                </div>

                <ActivityFeed
                  logs={logs}
                  executionRecords={executionRecords}
                  executionPlan={executionPlan}
                  verification={verification}
                  objectiveStatus={objectiveStatus}
                  isGenerating={isRunning}
                  activeNodeId={activeNodeId}
                  errorMessage={errorMessage}
                />
              </div>
            </div>
          )}

          {rightTab === "audit" && (
            <AuditTrailPanel
              executionPlan={executionPlan}
              executionRecords={executionRecords}
              objectiveStatus={objectiveStatus}
              finalSummary={finalSummary}
              verification={verification}
            />
          )}

          {rightTab === "prompts" && (
            <PromptOverridePanel
              promptSchema={promptSchema?.nodes ?? null}
              immutableRules={immutableRules}
              maxMutableChars={maxMutablePromptChars}
              overrides={promptOverrides}
              onChange={handleOverrideChange}
            />
          )}
        </div>
        <div className="studio-wheel-hint" aria-live="polite">
          <button
            type="button"
            className="btn btn--bare"
            onClick={() => setWheelTurn(0)}
            style={{
              color: wheelFace === 0 ? "var(--ink)" : "var(--ink-4)",
              fontWeight: wheelFace === 0 ? 600 : 400,
              padding: "2px 6px",
              cursor: "pointer",
            }}
          >
            01 Create
          </button>
          <span style={{ color: "var(--rule-strong)" }}>·</span>
          <button
            type="button"
            className="btn btn--bare"
            onClick={() => setWheelTurn(1)}
            style={{
              color: wheelFace === 1 ? "var(--ink)" : "var(--ink-4)",
              fontWeight: wheelFace === 1 ? 600 : 400,
              padding: "2px 6px",
              cursor: "pointer",
            }}
          >
            02 Preview
          </button>
          <span style={{ color: "var(--rule-strong)" }}>·</span>
          <button
            type="button"
            className="btn btn--bare"
            onClick={() => setWheelTurn(2)}
            style={{
              color: wheelFace === 2 ? "var(--ink)" : "var(--ink-4)",
              fontWeight: wheelFace === 2 ? 600 : 400,
              padding: "2px 6px",
              cursor: "pointer",
            }}
          >
            03 Code
          </button>
          <span className="studio-wheel-hint-detail">Drag, scroll, or use ← → to rotate</span>
        </div>
      </div>

      <AnimatePresence>
        {showWorkspaceRolloverModal && (
          <WorkspaceRolloverModal
            workspaceId={workspaceId}
            fileCount={fileCount}
            canContinueWorkspace={canContinueWorkspace}
            onClose={() => setShowWorkspaceRolloverModal(false)}
            onContinue={() => runWithWorkspaceMode("continue")}
            onStartFresh={() => runWithWorkspaceMode("fresh")}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {showApiModal && (
          <ApiKeyModal
            onClose={() => setShowApiModal(false)}
            apiKey={apiKey}
            rememberKey={rememberApiKey}
            onSave={handleSaveKey}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
