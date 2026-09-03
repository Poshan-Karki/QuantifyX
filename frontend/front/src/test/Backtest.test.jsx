import React from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

import Backtest from "../Backtest";

/**
 * The regression this file exists for: a failing or malformed /hydroname
 * response used to be stored as-is and then filtered during render, which threw
 * and unmounted the whole page.
 */

function jsonResponse(body, { ok = true, status = 200 } = {}) {
  return { ok, status, json: () => Promise.resolve(body) };
}

function routeFetch(handlers) {
  return vi.fn((url) => {
    const match = Object.keys(handlers).find((path) => String(url).includes(path));
    if (!match) return Promise.resolve(jsonResponse({}, { ok: false, status: 404 }));
    return handlers[match]();
  });
}

const DEFAULTS = {
  fee_pct: 0.2,
  slippage_pct: 0.1,
  max_pos_pct: 20.0,
  cooldown_bars: 3,
};

describe("Backtest page resilience", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  it("still renders when the symbol list request fails", async () => {
    globalThis.fetch = routeFetch({
      "/hydroname": () =>
        Promise.resolve(jsonResponse({ detail: "No symbols are loaded." }, { ok: false, status: 404 })),
      "/defaults": () => Promise.resolve(jsonResponse(DEFAULTS)),
    });

    render(<Backtest />);

    expect(await screen.findByText(/No symbols are loaded/)).toBeInTheDocument();
    expect(screen.getByText(/Ready for strategy initialization/)).toBeInTheDocument();
  });

  it("still renders when the symbol list is not an array", async () => {
    globalThis.fetch = routeFetch({
      "/hydroname": () => Promise.resolve(jsonResponse({ status: "fail" })),
      "/defaults": () => Promise.resolve(jsonResponse(DEFAULTS)),
    });

    render(<Backtest />);

    // The page stands; the ticker select simply reports nothing to choose.
    expect(await screen.findByText(/No matching symbols/)).toBeInTheDocument();
  });

  it("survives the API being unreachable entirely", async () => {
    globalThis.fetch = vi.fn(() => Promise.reject(new TypeError("Failed to fetch")));

    render(<Backtest />);

    expect(await screen.findByText(/Could not reach the API/)).toBeInTheDocument();
  });

  it("takes its trade parameter defaults from the backend", async () => {
    globalThis.fetch = routeFetch({
      "/hydroname": () => Promise.resolve(jsonResponse([{ Symbol: "NTC" }])),
      "/defaults": () =>
        Promise.resolve(jsonResponse({ ...DEFAULTS, fee_pct: 0.35, cooldown_bars: 7 })),
    });

    render(<Backtest />);

    await waitFor(() => {
      expect(screen.getByLabelText("Fee (%)")).toHaveValue(0.35);
      expect(screen.getByLabelText("Cooldown (bars)")).toHaveValue(7);
    });
  });

  it("falls back to the backend's declared defaults if /defaults is down", async () => {
    globalThis.fetch = routeFetch({
      "/hydroname": () => Promise.resolve(jsonResponse([{ Symbol: "NTC" }])),
      "/defaults": () => Promise.resolve(jsonResponse({}, { ok: false, status: 500 })),
    });

    render(<Backtest />);

    // Not the old frontend-only values (0.1 / 0.05 / 100 / 0), which were the
    // most optimistic configuration available.
    await waitFor(() => {
      expect(screen.getByLabelText("Fee (%)")).toHaveValue(0.2);
      expect(screen.getByLabelText("Max Position (%)")).toHaveValue(20);
      expect(screen.getByLabelText("Cooldown (bars)")).toHaveValue(3);
    });
  });
});
