import { describe, expect, it, vi, beforeEach } from "vitest";

import { getList, getJson, postJson } from "../api";

function jsonResponse(body, { ok = true, status = 200 } = {}) {
  return { ok, status, json: () => Promise.resolve(body) };
}

describe("getList", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  it("returns the array when the API returns one", async () => {
    globalThis.fetch.mockResolvedValue(jsonResponse([{ Symbol: "NTC" }]));

    await expect(getList("/hydroname")).resolves.toEqual([{ Symbol: "NTC" }]);
  });

  it("returns an empty array when the body is not a list", async () => {
    // The shape that used to reach setList and throw inside render.
    globalThis.fetch.mockResolvedValue(jsonResponse({ status: "fail" }));

    await expect(getList("/hydroname")).resolves.toEqual([]);
  });
});

describe("error reporting", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  it("surfaces a plain HTTPException detail", async () => {
    globalThis.fetch.mockResolvedValue(
      jsonResponse({ detail: "No data found for ZZZZ." }, { ok: false, status: 404 }),
    );

    await expect(getJson("/anything")).rejects.toThrow("No data found for ZZZZ.");
  });

  it("flattens a 422 validation list into one sentence", async () => {
    globalThis.fetch.mockResolvedValue(
      jsonResponse(
        {
          detail: [
            { loc: ["body", "investment"], msg: "Input should be greater than 0" },
          ],
        },
        { ok: false, status: 422 },
      ),
    );

    await expect(postJson("/bbband", {})).rejects.toThrow(
      "investment: Input should be greater than 0",
    );
  });

  it("explains an unreachable API rather than leaking the fetch error", async () => {
    globalThis.fetch.mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(getJson("/anything")).rejects.toThrow(/Could not reach the API/);
  });

  it("still produces a message when the error body is unparseable", async () => {
    globalThis.fetch.mockResolvedValue({
      ok: false,
      status: 500,
      json: () => Promise.reject(new Error("not json")),
    });

    await expect(getJson("/anything")).rejects.toThrow("HTTP 500");
  });
});
