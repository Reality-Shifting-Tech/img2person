import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { type AvatarJob } from "@img2person/contracts";
import { App } from "./app";

vi.mock("./viewer", () => ({
  SplatViewer: ({ url }: { url: string }) => <div data-testid="splat-viewer" data-url={url} />,
}));

const now = new Date().toISOString();

const queuedJob: AvatarJob = {
  id: "av_test",
  status: "queued",
  stages: [
    { stage: "intake", status: "pending" },
    { stage: "reconstruction", status: "pending" },
    { stage: "identity-gate", status: "pending" },
  ],
  createdAt: now,
  updatedAt: now,
};

const completeJob: AvatarJob = {
  ...queuedJob,
  status: "complete",
  stages: [
    { stage: "intake", status: "passed", detail: "photo accepted" },
    { stage: "reconstruction", status: "passed", detail: "splats baked" },
    { stage: "identity-gate", status: "passed", detail: "score above threshold" },
  ],
  mode: "mock",
  identityScore: 0.87,
  confidence: { front: 0.9, profile: 0.6, back: 0.4 },
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function photoFile(name = "face.png", type = "image/png"): File {
  return new File([new Uint8Array([1, 2, 3])], name, { type });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("renders the upload form", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: "img2person" })).toBeTruthy();
    expect(screen.getByText(/facing the camera, works best/i)).toBeTruthy();
    expect(screen.getByLabelText("Photo upload")).toBeTruthy();
  });

  it("rejects a non-image file without calling the API", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    fireEvent.change(screen.getByLabelText("Photo upload"), {
      target: { files: [photoFile("notes.txt", "text/plain")] },
    });
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("not an image");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("uploads, polls to completion, and shows the result", async () => {
    let polls = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url === "/v1/avatars" && init?.method === "POST") {
        return jsonResponse({ id: "av_test", status: "queued" }, 202);
      }
      polls += 1;
      return jsonResponse(polls > 1 ? completeJob : queuedJob);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.change(screen.getByLabelText("Photo upload"), {
      target: { files: [photoFile()] },
    });

    const viewer = await screen.findByTestId("splat-viewer", undefined, { timeout: 5000 });
    expect(viewer.getAttribute("data-url")).toBe("/v1/avatars/av_test/artifact");
    expect(screen.getByText("87%")).toBeTruthy();
    expect(screen.getByText(/Demo reconstruction/)).toBeTruthy();
    expect(screen.getByText(/synthesized from a single photo/)).toBeTruthy();
    const download = screen.getByRole("link", { name: /download/i });
    expect(download.getAttribute("href")).toBe("/v1/avatars/av_test/artifact");
    expect(download.getAttribute("download")).toBe("avatar-av_test.ply");
  });
});
