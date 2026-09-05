import { describe, expect, it } from "vitest";
import { chatTurnReducer, classifyErrorMessage, isBusy, isTerminal, stateStatusLabel } from "../chatStateMachine";

describe("chatTurnReducer", () => {
  it("moves idle -> submitting on submit", () => {
    expect(chatTurnReducer("idle", { kind: "submit" })).toBe("submitting");
  });

  it("moves submitting -> retrieving on the first status event", () => {
    expect(chatTurnReducer("submitting", { kind: "status", stage: "retrieving" })).toBe("retrieving");
  });

  it("moves submitting -> retrieving on a source event even without a status event", () => {
    expect(chatTurnReducer("submitting", { kind: "source" })).toBe("retrieving");
  });

  it("moves retrieving -> generating on the first token", () => {
    expect(chatTurnReducer("retrieving", { kind: "token" })).toBe("generating");
  });

  it("does not regress generating back to retrieving on a late status event", () => {
    expect(chatTurnReducer("generating", { kind: "status", stage: "retrieving" })).toBe("generating");
  });

  it("resolves confident, qualified, and abstention completion distinctly", () => {
    expect(chatTurnReducer("generating", { kind: "done", qualified: false, abstained: false })).toBe(
      "complete-confident",
    );
    expect(chatTurnReducer("generating", { kind: "done", qualified: true, abstained: false })).toBe(
      "complete-qualified",
    );
    expect(chatTurnReducer("generating", { kind: "done", qualified: false, abstained: true })).toBe(
      "complete-abstention",
    );
  });

  it("routes each error type to its own terminal state", () => {
    expect(chatTurnReducer("generating", { kind: "error", errorType: "network" })).toBe("error-network");
    expect(chatTurnReducer("generating", { kind: "error", errorType: "provider" })).toBe("error-provider");
    expect(chatTurnReducer("generating", { kind: "error", errorType: "database" })).toBe("error-database");
    expect(chatTurnReducer("generating", { kind: "error" })).toBe("error-unknown");
  });

  it("terminal states do not un-terminate on a stray status event", () => {
    expect(chatTurnReducer("complete-confident", { kind: "status", stage: "retrieving" })).toBe("complete-confident");
    expect(chatTurnReducer("error-network", { kind: "status", stage: "retrieving" })).toBe("error-network");
  });
});

describe("isBusy / isTerminal", () => {
  it("classifies busy states", () => {
    expect(isBusy("submitting")).toBe(true);
    expect(isBusy("retrieving")).toBe(true);
    expect(isBusy("generating")).toBe(true);
    expect(isBusy("idle")).toBe(false);
    expect(isBusy("complete-confident")).toBe(false);
  });

  it("classifies terminal states", () => {
    expect(isTerminal("complete-confident")).toBe(true);
    expect(isTerminal("complete-qualified")).toBe(true);
    expect(isTerminal("complete-abstention")).toBe(true);
    expect(isTerminal("error-network")).toBe(true);
    expect(isTerminal("generating")).toBe(false);
  });
});

describe("stateStatusLabel", () => {
  it("returns a label only for in-flight states", () => {
    expect(stateStatusLabel("retrieving")).toMatch(/retrieving/i);
    expect(stateStatusLabel("generating")).toMatch(/generating/i);
    expect(stateStatusLabel("complete-confident")).toBeNull();
    expect(stateStatusLabel("error-network")).toBeNull();
  });
});

describe("classifyErrorMessage", () => {
  it("recognizes network-shaped failures", () => {
    expect(classifyErrorMessage("Failed to fetch")).toBe("network");
    expect(classifyErrorMessage("Request failed (503)")).toBe("network");
  });

  it("recognizes provider-shaped failures", () => {
    expect(classifyErrorMessage("Ollama is unreachable")).toBe("provider");
  });

  it("recognizes database-shaped failures", () => {
    expect(classifyErrorMessage("database connection lost")).toBe("database");
  });

  it("falls back to unknown", () => {
    expect(classifyErrorMessage("something odd happened")).toBe("unknown");
  });
});