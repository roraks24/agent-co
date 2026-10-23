import { useState, useRef, useEffect, useMemo } from "react";
import {
  FileCode2,
  FileText,
  Search,
  Terminal,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Sparkles,
  ShieldCheck,
  ChevronRight,
  ChevronDown,
  Copy,
  Check,
  RotateCcw,
  Globe,
} from "lucide-react";
import {
  type ActivityItem,
  buildActivityFeed,
  getOngoingIndicator,
} from "@/app/lib/activity-feed";
import type {
  ActionExecutionRecord,
  AgentLogEvent,
  GoalPlan,
  VerificationResult,
} from "@/app/store/useAgentStore";

interface ActivityFeedProps {
  logs: AgentLogEvent[];
  executionRecords: ActionExecutionRecord[];
  executionPlan: GoalPlan | null;
  verification: VerificationResult | null;
  objectiveStatus: string | null;
  isGenerating: boolean;
  activeNodeId: string | null;
  errorMessage?: string | null;
}

function getActivityIcon(item: ActivityItem) {
  if (item.status === "running") {
    return <Loader2 size={13} className="animate-spin" style={{ color: "var(--accent)" }} />;
  }

  if (item.status === "failed" || item.status === "error") {
    return <AlertCircle size={13} style={{ color: "var(--bad)" }} />;
  }

  switch (item.type) {
    case "plan":
      return <Sparkles size={13} style={{ color: "var(--accent)" }} />;
    case "verification":
      return <ShieldCheck size={13} style={{ color: "var(--ok)" }} />;
    case "tool":
      if (item.toolName === "write_file") {
        return <FileCode2 size={13} style={{ color: "var(--ok)" }} />;
      }
      if (item.toolName === "read_file" || item.toolName?.includes("file")) {
        return <FileText size={13} style={{ color: "var(--ink-3)" }} />;
      }
      if (item.toolName === "web_search" || item.toolName === "fetch_url_content") {
        return <Search size={13} style={{ color: "var(--accent)" }} />;
      }
      if (item.toolName === "run_command" || item.toolName === "bash") {
        return <Terminal size={13} style={{ color: "var(--ink-2)" }} />;
      }
      if (item.toolName?.includes("github")) {
        return <Globe size={13} style={{ color: "var(--ink-2)" }} />;
      }
      return <CheckCircle2 size={13} style={{ color: "var(--ok)" }} />;
    default:
      return <CheckCircle2 size={13} style={{ color: "var(--ok)" }} />;
  }
}

export function ActivityFeed({
  logs,
  executionRecords,
  executionPlan,
  verification,
  objectiveStatus,
  isGenerating,
  activeNodeId,
  errorMessage,
}: ActivityFeedProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const userScrolledUpRef = useRef(false);

  const activities = useMemo(() => {
    return buildActivityFeed({
      logs,
      executionRecords,
      executionPlan,
      verification,
      objectiveStatus,
      isGenerating,
      activeNodeId,
    });
  }, [logs, executionRecords, executionPlan, verification, objectiveStatus, isGenerating, activeNodeId]);

  const ongoingText = useMemo(() => {
    return getOngoingIndicator({
      isGenerating,
      activeNodeId,
      executionPlan,
      executionRecords,
      verification,
    });
  }, [isGenerating, activeNodeId, executionPlan, executionRecords, verification]);

  // Auto-scroll to bottom unless user scrolled up
  useEffect(() => {
    if (!userScrolledUpRef.current && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [activities, ongoingText]);

  const handleScroll = () => {
    if (!containerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    const distanceToBottom = scrollHeight - (scrollTop + clientHeight);
    userScrolledUpRef.current = distanceToBottom > 40;
  };

  const copyToClipboard = (key: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => {
      setCopiedKey((prev) => (prev === key ? null : prev));
    }, 1500);
  };

  const toggleExpand = (id: string) => {
    setExpandedId((prev) => (prev === id ? null : id));
  };

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      className="activity-feed-container"
      style={{
        flex: 1,
        overflowY: "auto",
        display: "flex",
        flexDirection: "column",
        minHeight: 0,
        padding: "6px 0 16px",
      }}
    >
      {activities.length === 0 && !ongoingText && !errorMessage && (
        <div style={{ padding: "24px 16px", color: "var(--ink-4)", textAlign: "center", lineHeight: 1.7 }}>
          <p className="meta" style={{ fontSize: "var(--t-small)" }}>
            No agent activity yet. Actions, file operations, and verification will stream here.
          </p>
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column" }}>
        {activities.map((item, index) => {
          const isExpanded = expandedId === item.id;
          const hasExpandableContent = Boolean(
            item.inputArgs ||
            item.toolResult !== undefined ||
            item.error ||
            item.stepId ||
            item.toolName ||
            item.verificationCriteria
          );

          return (
            <div
              key={item.id}
              className={`activity-item activity-item--${item.status}`}
              style={{
                borderBottom: "1px solid var(--hair)",
                background: isExpanded ? "var(--surface-2)" : "transparent",
                transition: "background var(--dur-fast) ease",
              }}
            >
              {/* Row summary line */}
              <button
                type="button"
                onClick={() => hasExpandableContent && toggleExpand(item.id)}
                disabled={!hasExpandableContent}
                style={{
                  width: "100%",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "7px 12px",
                  background: "transparent",
                  border: "none",
                  cursor: hasExpandableContent ? "pointer" : "default",
                  textAlign: "left",
                  color: "inherit",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 9, minWidth: 0, flex: 1 }}>
                  <span
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      width: 18,
                      height: 18,
                      flexShrink: 0,
                    }}
                  >
                    {getActivityIcon(item)}
                  </span>

                  <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
                    <span
                      style={{
                        fontSize: "var(--t-small)",
                        color: item.status === "failed" || item.status === "error" ? "var(--bad)" : "var(--ink)",
                        fontWeight: 450,
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        letterSpacing: "-0.01em",
                      }}
                    >
                      {item.title}
                    </span>
                    {item.subtitle && !item.title.includes(item.subtitle) && (
                      <span
                        className="num"
                        style={{
                          fontSize: "var(--t-micro)",
                          color: "var(--ink-4)",
                          marginTop: 1,
                          whiteSpace: "nowrap",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                        }}
                      >
                        {item.subtitle}
                      </span>
                    )}
                  </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0, marginLeft: 8 }}>
                  {item.retryCount !== undefined && item.retryCount > 0 && (
                    <span
                      className="num"
                      style={{
                        fontSize: "var(--t-micro)",
                        padding: "1px 5px",
                        borderRadius: 3,
                        background: "var(--warn-soft)",
                        color: "var(--warn)",
                      }}
                    >
                      Retry {item.retryCount}
                    </span>
                  )}

                  {hasExpandableContent && (
                    <span style={{ color: "var(--ink-4)", display: "flex", alignItems: "center" }}>
                      {isExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                    </span>
                  )}
                </div>
              </button>

              {/* Expandable details drawer */}
              {isExpanded && (
                <div
                  style={{
                    padding: "8px 12px 12px 36px",
                    display: "flex",
                    flexDirection: "column",
                    gap: 8,
                    fontSize: "var(--t-micro)",
                    background: "rgba(0,0,0,0.18)",
                    borderTop: "1px solid var(--hair)",
                  }}
                >
                  {/* Metadata chips */}
                  <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
                    {item.toolName && (
                      <span
                        className="num"
                        style={{
                          padding: "2px 6px",
                          borderRadius: 3,
                          background: "var(--surface)",
                          border: "1px solid var(--rule)",
                          color: "var(--accent)",
                        }}
                      >
                        tool: {item.toolName}
                      </span>
                    )}

                    {item.stepId && (
                      <span className="num" style={{ color: "var(--ink-3)" }}>
                        step: {item.stepId}
                      </span>
                    )}

                    {item.durationMs !== undefined && (
                      <span className="num" style={{ color: "var(--ink-3)" }}>
                        duration: {item.formattedDuration || `${item.durationMs}ms`}
                      </span>
                    )}

                    {item.attemptCount !== undefined && (
                      <span className="num" style={{ color: "var(--ink-3)" }}>
                        attempt: {item.attemptCount}
                      </span>
                    )}

                    {item.startedAt && (
                      <span className="num" style={{ color: "var(--ink-4)" }}>
                        at: {item.startedAt.split("T")[1]?.slice(0, 8) || item.startedAt}
                      </span>
                    )}
                  </div>

                  {/* Error if failed */}
                  {item.error && (
                    <div
                      style={{
                        padding: "6px 8px",
                        borderRadius: 4,
                        background: "var(--bad-soft)",
                        border: "1px solid var(--bad)",
                        color: "var(--bad)",
                        wordBreak: "break-word",
                      }}
                    >
                      <strong>Error:</strong> {item.error}
                    </div>
                  )}

                  {/* Verification criteria if present */}
                  {item.verificationCriteria && item.verificationCriteria.length > 0 && (
                    <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                      <span style={{ color: "var(--ink-3)", fontWeight: 500 }}>Criteria Evaluated:</span>
                      {item.verificationCriteria.map((crit, idx) => (
                        <div key={idx} style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--ink-2)" }}>
                          <Check size={11} style={{ color: "var(--ok)", flexShrink: 0 }} />
                          <span>{crit}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Input Arguments (sanitized) */}
                  {item.inputArgs && Object.keys(item.inputArgs).length > 0 && (
                    <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                        <span style={{ color: "var(--ink-3)", fontWeight: 500 }}>Input Arguments:</span>
                        <button
                          type="button"
                          className="btn btn--sm btn--bare"
                          onClick={() => copyToClipboard(`args-${item.id}`, JSON.stringify(item.inputArgs, null, 2))}
                          style={{ padding: "1px 5px", height: "auto", fontSize: "10px" }}
                        >
                          {copiedKey === `args-${item.id}` ? <Check size={10} /> : <Copy size={10} />}
                          {copiedKey === `args-${item.id}` ? "Copied" : "Copy"}
                        </button>
                      </div>
                      <pre
                        style={{
                          margin: 0,
                          padding: 8,
                          borderRadius: 4,
                          background: "var(--surface)",
                          border: "1px solid var(--hair)",
                          maxHeight: 140,
                          overflowY: "auto",
                          color: "var(--ink-2)",
                          fontFamily: "var(--face-mono)",
                          fontSize: "11px",
                          lineHeight: 1.45,
                        }}
                      >
                        {JSON.stringify(item.inputArgs, null, 2)}
                      </pre>
                    </div>
                  )}

                  {/* Tool Result / Output summary */}
                  {item.toolResult !== undefined && item.toolResult !== null && (
                    <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                        <span style={{ color: "var(--ink-3)", fontWeight: 500 }}>Output:</span>
                        <button
                          type="button"
                          className="btn btn--sm btn--bare"
                          onClick={() =>
                            copyToClipboard(
                              `res-${item.id}`,
                              typeof item.toolResult === "string"
                                ? item.toolResult
                                : JSON.stringify(item.toolResult, null, 2)
                            )
                          }
                          style={{ padding: "1px 5px", height: "auto", fontSize: "10px" }}
                        >
                          {copiedKey === `res-${item.id}` ? <Check size={10} /> : <Copy size={10} />}
                          {copiedKey === `res-${item.id}` ? "Copied" : "Copy"}
                        </button>
                      </div>
                      <pre
                        style={{
                          margin: 0,
                          padding: 8,
                          borderRadius: 4,
                          background: "var(--surface)",
                          border: "1px solid var(--hair)",
                          maxHeight: 140,
                          overflowY: "auto",
                          color: "var(--ink-2)",
                          fontFamily: "var(--face-mono)",
                          fontSize: "11px",
                          lineHeight: 1.45,
                          whiteSpace: "pre-wrap",
                          wordBreak: "break-word",
                        }}
                      >
                        {typeof item.toolResult === "string"
                          ? item.toolResult
                          : JSON.stringify(item.toolResult, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Ongoing activity indicator (stops cleanly when !isGenerating) */}
      {isGenerating && ongoingText && (
        <div
          className="ongoing-activity-indicator"
          style={{
            margin: "8px 12px 4px",
            padding: "6px 10px",
            borderRadius: 6,
            background: "var(--accent-soft)",
            border: "1px solid var(--accent-line)",
            display: "flex",
            alignItems: "center",
            gap: 8,
          }}
        >
          <Loader2 size={13} className="animate-spin" style={{ color: "var(--accent)" }} />
          <span
            style={{
              fontSize: "var(--t-small)",
              color: "var(--accent)",
              fontWeight: 500,
              letterSpacing: "-0.01em",
            }}
          >
            {ongoingText}
          </span>
        </div>
      )}

      {/* Explicit error banner if run aborted with error */}
      {errorMessage && (
        <div className="notice notice--bad" style={{ margin: "8px 10px" }}>
          <div className="notice__body">
            <div className="notice__title">Workflow Error</div>
            <p className="notice__text">{errorMessage}</p>
          </div>
        </div>
      )}
    </div>
  );
}
