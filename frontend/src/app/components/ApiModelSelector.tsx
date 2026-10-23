import React from "react";
import { Sparkles, Cpu, Zap, DollarSign, Activity } from "lucide-react";
import { useAgentStore } from "@/app/store/useAgentStore";
import type { ApiProvider } from "@/app/lib/api-client";

export function ApiModelSelector() {
  const availableProviders = useAgentStore((state) => state.availableProviders);
  const selectedApiId = useAgentStore((state) => state.selectedApiId);
  const setSelectedApiId = useAgentStore((state) => state.setSelectedApiId);
  const fetchAvailableProviders = useAgentStore((state) => state.fetchAvailableProviders);
  const lastUsedApiDetails = useAgentStore((state) => state.lastUsedApiDetails);

  React.useEffect(() => {
    void fetchAvailableProviders();
  }, [fetchAvailableProviders]);

  const selectedProvider = availableProviders.find((p) => p.id === selectedApiId);

  const getTierBadge = (tier: string) => {
    switch (tier) {
      case "LOW":
        return { label: "Lightweight", color: "var(--ok, #10b981)", bg: "rgba(16, 185, 129, 0.1)" };
      case "MEDIUM":
        return { label: "Balanced", color: "var(--accent, #3b82f6)", bg: "rgba(59, 130, 246, 0.1)" };
      case "HIGH":
        return { label: "High Performance", color: "var(--warn, #f59e0b)", bg: "rgba(245, 158, 11, 0.1)" };
      default:
        return { label: tier, color: "var(--ink-2)", bg: "rgba(255, 255, 255, 0.05)" };
    }
  };

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        fontSize: "var(--t-small, 12px)",
        color: "var(--ink-2, #888)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
        <Cpu size={14} style={{ color: "var(--ink-2)" }} />
        <span style={{ fontWeight: 500 }}>API / Model:</span>
      </div>

      <select
        id="agent-model-select"
        value={selectedApiId || "auto"}
        onChange={(e) => {
          const val = e.target.value;
          setSelectedApiId(val === "auto" ? null : val);
        }}
        style={{
          background: "var(--surface-2, rgba(255, 255, 255, 0.06))",
          color: "var(--ink, #fff)",
          border: "1px solid var(--hair, rgba(255, 255, 255, 0.1))",
          borderRadius: 4,
          padding: "4px 8px",
          fontSize: "12px",
          cursor: "pointer",
          outline: "none",
          maxWidth: 260,
        }}
      >
        <option value="auto">✨ Auto-select best API (Adaptive Pipeline)</option>
        {availableProviders.map((prov) => (
          <option key={prov.id} value={prov.id}>
            {prov.display_name} [{prov.capability_tier}] ({prov.cost_tier} cost)
          </option>
        ))}
      </select>

      {/* Selected Provider or Auto Badge */}
      {!selectedApiId ? (
        <span
          style={{
            padding: "2px 6px",
            borderRadius: 3,
            background: "rgba(168, 85, 247, 0.15)",
            color: "#c084fc",
            fontSize: "10px",
            fontWeight: 600,
            display: "inline-flex",
            alignItems: "center",
            gap: 3,
          }}
        >
          <Sparkles size={11} />
          Auto Routing Active
        </span>
      ) : selectedProvider ? (
        <span
          style={{
            padding: "2px 6px",
            borderRadius: 3,
            background: getTierBadge(selectedProvider.capability_tier).bg,
            color: getTierBadge(selectedProvider.capability_tier).color,
            fontSize: "10px",
            fontWeight: 600,
          }}
        >
          {getTierBadge(selectedProvider.capability_tier).label}
        </span>
      ) : null}

      {/* Post-execution resolution badge */}
      {lastUsedApiDetails && (
        <span
          title={`Executed with: ${lastUsedApiDetails.display_name || lastUsedApiDetails.model || lastUsedApiDetails.selected_api}`}
          style={{
            padding: "2px 6px",
            borderRadius: 3,
            background: "rgba(255, 255, 255, 0.05)",
            border: "1px solid var(--hair, rgba(255, 255, 255, 0.1))",
            color: "var(--ink, #ccc)",
            fontSize: "10px",
            display: "inline-flex",
            alignItems: "center",
            gap: 4,
          }}
        >
          <Activity size={10} color="var(--ok, #10b981)" />
          <span>Used: {String(lastUsedApiDetails.model || lastUsedApiDetails.selected_api || "")}</span>
        </span>
      )}
    </div>
  );
}
