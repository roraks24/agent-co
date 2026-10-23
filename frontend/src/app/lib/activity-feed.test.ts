import { describe, expect, it } from "vitest";
import {
  buildActivityFeed,
  formatDuration,
  formatToolAction,
  getOngoingIndicator,
  sanitizeInputArgs,
  sanitizeValue,
} from "./activity-feed";
import type { ActionExecutionRecord, AgentLogEvent, GoalPlan, VerificationResult } from "@/app/store/useAgentStore";

describe("activity-feed formatting and redaction", () => {
  it("formats real durations correctly without fabricating numbers", () => {
    expect(formatDuration(null)).toBe("");
    expect(formatDuration(undefined)).toBe("");
    expect(formatDuration(-10)).toBe("");
    expect(formatDuration(0)).toBe("0 ms");
    expect(formatDuration(45)).toBe("45 ms");
    expect(formatDuration(850)).toBe("850 ms");
    expect(formatDuration(1200)).toBe("1.2 s");
    expect(formatDuration(15400)).toBe("15 s");
  });

  it("redacts sensitive keys and credentials in input arguments", () => {
    const rawArgs = {
      path: "src/index.html",
      api_key: "gsk_1234567890abcdef1234567890",
      Authorization: "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz",
      secretToken: "sk-secret99999999999999999999",
      nested: {
        password: "supersecretpassword",
        normalField: "hello world",
      },
    };

    const sanitized = sanitizeInputArgs(rawArgs);
    expect(sanitized?.path).toBe("src/index.html");
    expect(sanitized?.api_key).toBe("[REDACTED]");
    expect(sanitized?.Authorization).toBe("[REDACTED]");
    expect(sanitized?.secretToken).toBe("[REDACTED]");
    expect((sanitized?.nested as any)?.password).toBe("[REDACTED]");
    expect((sanitized?.nested as any)?.normalField).toBe("hello world");
  });

  it("formats write_file actions concisely like Antigravity", () => {
    expect(formatToolAction("write_file", { path: "style.css" }, "running")).toEqual({
      title: "Writing style.css",
      subtitle: "style.css",
    });

    expect(formatToolAction("write_file", { path: "style.css" }, "success")).toEqual({
      title: "Wrote style.css",
      subtitle: "style.css",
    });

    expect(formatToolAction("write_file", { path: "style.css" }, "failed")).toEqual({
      title: "Writing style.css · Failed",
      subtitle: "style.css",
    });

    expect(formatToolAction("write_file", { path: "style.css" }, "running", 1)).toEqual({
      title: "Retrying style.css (attempt 2)",
      subtitle: "style.css",
    });
  });

  it("formats list_files and web_search actions concisely", () => {
    expect(formatToolAction("list_files", {}, "running")).toEqual({
      title: "Inspecting workspace files",
      subtitle: undefined,
    });

    expect(formatToolAction("list_files", { path: "frontend" }, "success")).toEqual({
      title: "Inspected frontend directory",
      subtitle: undefined,
    });

    expect(formatToolAction("web_search", { query: "Tailwind CSS CDN" }, "running")).toEqual({
      title: 'Searching web for "Tailwind CSS CDN"',
      subtitle: undefined,
    });

    expect(formatToolAction("web_search", { query: "Tailwind CSS CDN" }, "success")).toEqual({
      title: 'Searched web for "Tailwind CSS CDN"',
      subtitle: undefined,
    });
  });
});

describe("buildActivityFeed", () => {
  it("creates clean planning activity item when plan is established", () => {
    const plan: GoalPlan = {
      objective: "Build portfolio website",
      task_type: "coding",
      expected_outcome: "A responsive portfolio site",
      steps: [
        { id: "step-1", title: "Write HTML", tool_name: "write_file", tool_args: { path: "index.html" } },
        { id: "step-2", title: "Write CSS", tool_name: "write_file", tool_args: { path: "style.css" } },
      ],
    };

    const feed = buildActivityFeed({
      logs: [],
      executionRecords: [],
      executionPlan: plan,
      verification: null,
      objectiveStatus: null,
      isGenerating: false,
      activeNodeId: null,
    });

    expect(feed.length).toBe(1);
    expect(feed[0].title).toBe("Plan created · 2 steps");
    expect(feed[0].type).toBe("plan");
    expect(feed[0].status).toBe("success");
  });

  it("groups execution records and includes real duration in title", () => {
    const plan: GoalPlan = {
      objective: "Build portfolio website",
      task_type: "coding",
      expected_outcome: "A responsive portfolio site",
      steps: [
        { id: "step-1", title: "Write HTML", tool_name: "write_file", tool_args: { path: "index.html" } },
        { id: "step-2", title: "Write CSS", tool_name: "write_file", tool_args: { path: "style.css" } },
      ],
    };

    const records: ActionExecutionRecord[] = [
      {
        step_id: "step-1",
        tool_name: "write_file",
        tool_args: { path: "index.html" },
        started_at: "2026-10-24T00:00:00Z",
        completed_at: "2026-10-24T00:00:01Z",
        duration_ms: 850,
        tool_result: { success: true },
        status: "success",
        retry_count: 0,
      },
    ];

    const feed = buildActivityFeed({
      logs: [],
      executionRecords: records,
      executionPlan: plan,
      verification: null,
      objectiveStatus: null,
      isGenerating: false,
      activeNodeId: null,
    });

    expect(feed.length).toBe(2);
    expect(feed[0].title).toBe("Plan created · 2 steps");
    expect(feed[1].title).toBe("Wrote index.html · 850 ms");
    expect(feed[1].durationMs).toBe(850);
    expect(feed[1].status).toBe("success");
  });

  it("preserves genuine retries and failed attempts rather than swallowing them", () => {
    const plan: GoalPlan = {
      objective: "Build portfolio website",
      task_type: "coding",
      expected_outcome: "site",
      steps: [{ id: "step-1", title: "Write style", tool_name: "write_file", tool_args: { path: "style.css" } }],
    };

    const records: ActionExecutionRecord[] = [
      {
        step_id: "step-1",
        tool_name: "write_file",
        tool_args: { path: "style.css" },
        started_at: "2026-10-24T00:00:00Z",
        completed_at: "2026-10-24T00:00:01Z",
        duration_ms: 300,
        tool_result: { error: "Permission denied" },
        status: "failed",
        error: "Permission denied",
        retry_count: 0,
      },
      {
        step_id: "step-1",
        tool_name: "write_file",
        tool_args: { path: "style.css" },
        started_at: "2026-10-24T00:00:02Z",
        completed_at: "2026-10-24T00:00:03Z",
        duration_ms: 450,
        tool_result: { success: true },
        status: "success",
        retry_count: 1,
      },
    ];

    const feed = buildActivityFeed({
      logs: [],
      executionRecords: records,
      executionPlan: plan,
      verification: null,
      objectiveStatus: null,
      isGenerating: false,
      activeNodeId: null,
    });

    expect(feed.length).toBe(3); // plan + failed attempt + retry success
    expect(feed[1].title).toBe("Writing style.css · Failed");
    expect(feed[1].status).toBe("failed");
    expect(feed[1].error).toBe("Permission denied");

    expect(feed[2].title).toBe("Wrote style.css · 450 ms");
    expect(feed[2].retryCount).toBe(1);
    expect(feed[2].status).toBe("success");
  });

  it("handles verification item with checks count", () => {
    const verification: VerificationResult = {
      objective_status: "SUCCESS",
      criteria_evaluated: ["HTML valid", "CSS styles applied", "Script attached", "No placeholders"],
      evidence_summary: "All deliverables verified successfully.",
    };

    const feed = buildActivityFeed({
      logs: [],
      executionRecords: [],
      executionPlan: null,
      verification,
      objectiveStatus: "SUCCESS",
      isGenerating: false,
      activeNodeId: null,
    });

    expect(feed.length).toBe(1);
    expect(feed[0].title).toBe("Verification passed · 4 checks");
    expect(feed[0].status).toBe("success");
    expect(feed[0].type).toBe("verification");
  });

  it("displays running step when generation is actively executing", () => {
    const plan: GoalPlan = {
      objective: "Build app",
      task_type: "coding",
      expected_outcome: "App",
      steps: [
        { id: "step-1", title: "Write HTML", tool_name: "write_file", tool_args: { path: "index.html" } },
        { id: "step-2", title: "Write CSS", tool_name: "write_file", tool_args: { path: "style.css" } },
      ],
    };

    const records: ActionExecutionRecord[] = [
      {
        step_id: "step-1",
        tool_name: "write_file",
        tool_args: { path: "index.html" },
        started_at: "2026-10-24T00:00:00Z",
        completed_at: "2026-10-24T00:00:01Z",
        duration_ms: 500,
        tool_result: {},
        status: "success",
        retry_count: 0,
      },
    ];

    const feed = buildActivityFeed({
      logs: [],
      executionRecords: records,
      executionPlan: plan,
      verification: null,
      objectiveStatus: null,
      isGenerating: true,
      activeNodeId: "coder",
    });

    expect(feed.length).toBe(3); // plan + completed step 1 + active running step 2
    expect(feed[2].title).toBe("Writing style.css");
    expect(feed[2].status).toBe("running");
  });
});

describe("getOngoingIndicator", () => {
  it("returns null when not generating (stops cleanly)", () => {
    expect(
      getOngoingIndicator({
        isGenerating: false,
        activeNodeId: "coder",
        executionPlan: null,
        executionRecords: [],
        verification: null,
      })
    ).toBeNull();
  });

  it("returns Planning objective… when planner is active", () => {
    expect(
      getOngoingIndicator({
        isGenerating: true,
        activeNodeId: "planner",
        executionPlan: null,
        executionRecords: [],
        verification: null,
      })
    ).toBe("Planning objective…");
  });

  it("returns step progress when coder is executing", () => {
    const plan: GoalPlan = {
      objective: "Build website",
      task_type: "coding",
      expected_outcome: "site",
      steps: [
        { id: "step-1", title: "HTML", tool_name: "write_file", tool_args: { path: "index.html" } },
        { id: "step-2", title: "CSS", tool_name: "write_file", tool_args: { path: "style.css" } },
        { id: "step-3", title: "JS", tool_name: "write_file", tool_args: { path: "script.js" } },
      ],
    };

    const records: ActionExecutionRecord[] = [
      {
        step_id: "step-1",
        tool_name: "write_file",
        tool_args: { path: "index.html" },
        started_at: "",
        completed_at: "",
        duration_ms: 100,
        tool_result: {},
        status: "success",
        retry_count: 0,
      },
    ];

    expect(
      getOngoingIndicator({
        isGenerating: true,
        activeNodeId: "coder",
        executionPlan: plan,
        executionRecords: records,
        verification: null,
      })
    ).toBe("Executing step 2 of 3: style.css…");
  });
});
