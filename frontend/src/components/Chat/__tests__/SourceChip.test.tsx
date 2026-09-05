import { describe, expect, it } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SourceChip } from "../SourceChip";

describe("SourceChip", () => {
  it("shows the episode and guest without the chunk text collapsed by default", () => {
    render(
      <SourceChip
        source={{
          episode_title: "Scaling Growth Loops",
          guest_name: "Casey Winters",
          locator: "12:34",
          similarity: 0.91,
          chunk_text: "The full underlying transcript excerpt goes here.",
        }}
      />,
    );

    expect(screen.getByText("Scaling Growth Loops")).toBeInTheDocument();
    expect(screen.getByText(/Casey Winters/)).toBeInTheDocument();
    expect(screen.queryByText(/full underlying transcript excerpt/)).not.toBeInTheDocument();
  });

  it("expands the chunk text on click and collapses again on a second click", () => {
    render(
      <SourceChip
        source={{
          episode_title: "Scaling Growth Loops",
          guest_name: "Casey Winters",
          locator: "12:34",
          similarity: 0.91,
          chunk_text: "The full underlying transcript excerpt goes here.",
        }}
      />,
    );

    const chip = screen.getByRole("button");
    expect(chip).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(chip);
    expect(chip).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/full underlying transcript excerpt/)).toBeInTheDocument();

    fireEvent.click(chip);
    expect(chip).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(/full underlying transcript excerpt/)).not.toBeInTheDocument();
  });

  it("does not expand when there is no chunk text to show", () => {
    render(
      <SourceChip
        source={{
          episode_title: "Scaling Growth Loops",
          guest_name: null,
          locator: null,
          similarity: 0.91,
        }}
      />,
    );

    const chip = screen.getByRole("button");
    fireEvent.click(chip);
    expect(chip).toHaveAttribute("aria-expanded", "false");
  });
});