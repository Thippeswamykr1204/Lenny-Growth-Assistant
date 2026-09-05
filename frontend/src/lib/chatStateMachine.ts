/**
 * Tier 7 — explicit interaction state machine for a single assistant turn.
 *
 * Tiers 1–6 tracked turn progress with one `busy`/`isLoading` boolean, which
 * cannot express design.md's Key Interaction States (idle, retrieving,
 * generating, qualified-complete, abstention-complete, error-per-type). This
 * module is the single source of truth for "what state is this turn in" so
 * ChatPane never has to infer state from which fields happen to be set.
 *
 * One machine instance per assistant message. `sessionId` init (Tier 4's
 * fetch-on-mount) is deliberately NOT part of this machine — it's a
 * page-level concern, not a per-turn one.
 */

export type ChatTurnState =
  | "idle"
  | "submitting"
  | "retrieving"
  | "generating"
  | "complete-confident"
  | "complete-qualified"
  | "complete-abstention"
  | "error-network"
  | "error-provider"
  | "error-database"
  | "error-unknown";

export type ChatTurnEvent =
  | { kind: "submit" }
  | { kind: "status"; stage: string }
  | { kind: "source" }
  | { kind: "token" }
  | { kind: "done"; qualified: boolean; abstained: boolean }
  | { kind: "error"; errorType?: "network" | "provider" | "database" | "unknown" };

/** Pure reducer — no side effects, so it's trivially unit-testable and so
 * ChatPane can stay a thin dispatcher around it. */
export function chatTurnReducer(state: ChatTurnState, event: ChatTurnEvent): ChatTurnState {
  switch (event.kind) {
    case "submit":
      return "submitting";
    case "status":
      if (state === "generating" || state.startsWith("complete") || state.startsWith("error")) {
        return state;
      }
      return "retrieving";
    case "source":
      return state === "submitting" ? "retrieving" : state;
    case "token":
      return "generating";
    case "done":
      if (event.abstained) return "complete-abstention";
      if (event.qualified) return "complete-qualified";
      return "complete-confident";
    case "error":
      switch (event.errorType) {
        case "network":
          return "error-network";
        case "provider":
          return "error-provider";
        case "database":
          return "error-database";
        default:
          return "error-unknown";
      }
    default:
      return state;
  }
}

export function isTerminal(state: ChatTurnState): boolean {
  return state.startsWith("complete") || state.startsWith("error");
}

export function isBusy(state: ChatTurnState): boolean {
  return state === "submitting" || state === "retrieving" || state === "generating";
}

export function stateStatusLabel(state: ChatTurnState): string | null {
  switch (state) {
    case "submitting":
      return "Sending…";
    case "retrieving":
      return "Retrieving relevant transcripts…";
    case "generating":
      return "Generating answer…";
    default:
      return null;
  }
}

export function classifyErrorMessage(message: string): ChatTurnEvent["errorType"] {
  const m = message.toLowerCase();
  if (m.includes("failed to fetch") || m.includes("networkerror") || m.includes("request failed")) {
    return "network";
  }
  if (m.includes("provider") || m.includes("ollama") || m.includes("model")) return "provider";
  if (m.includes("database") || m.includes("db ")) return "database";
  return "unknown";
}