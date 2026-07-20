import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { loadConfig, type Config } from "@img2person/config";
import type { AvatarJob, ProblemDetails } from "@img2person/contracts";
import { HttpInferenceClient } from "@img2person/contracts";
import {
  createFakeInferenceServer,
  ONE_PIXEL_PNG,
  TEST_ARTIFACT_BYTES,
  type FakeInferenceServer,
} from "@img2person/testkit";
import type { Hono } from "hono";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { createApp } from "./app.js";
import { DiskJobStore } from "./disk-store.js";

let storageDir: string;
let server: FakeInferenceServer;
let app: Hono;
let store: DiskJobStore;

function makeConfig(overrides: NodeJS.ProcessEnv = {}): Config {
  return loadConfig({ STORAGE_DIR: storageDir, ...overrides });
}

async function waitForJob(id: string): Promise<AvatarJob> {
  for (let attempt = 0; attempt < 200; attempt++) {
    const job = await store.get(id);
    if (job && (job.status === "complete" || job.status === "failed")) {
      return job;
    }
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
  throw new Error(`job ${id} did not finish`);
}

function uploadRequest(body?: FormData): RequestInit {
  return { method: "POST", ...(body ? { body } : {}) };
}

function imageForm(file?: File): FormData {
  const form = new FormData();
  if (file) {
    form.append("image", file);
  }
  return form;
}

beforeAll(async () => {
  storageDir = await mkdtemp(join(tmpdir(), "img2person-api-test-"));
  server = await createFakeInferenceServer();
  store = new DiskJobStore(storageDir);
  app = createApp({
    config: makeConfig(),
    store,
    inference: new HttpInferenceClient(server.url),
  });
});

afterAll(async () => {
  await server.close();
  await rm(storageDir, { recursive: true, force: true });
});

describe("health", () => {
  it("GET /healthz returns ok", async () => {
    const res = await app.request("/healthz");
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ status: "ok" });
  });
});

describe("avatar lifecycle", () => {
  it("POST returns 202, the job completes, and the artifact downloads", async () => {
    const form = imageForm(new File([ONE_PIXEL_PNG], "photo.png", { type: "image/png" }));
    const created = await app.request("/v1/avatars", uploadRequest(form));
    expect(created.status).toBe(202);
    const { id, status } = (await created.json()) as { id: string; status: string };
    expect(id).toMatch(/^av_/);
    expect(status).toBe("queued");

    const job = await waitForJob(id);
    expect(job.status).toBe("complete");
    expect(job.identityScore).toBe(0.9);
    expect(job.mode).toBe("test");
    expect(job.stages.map((stage) => [stage.stage, stage.status])).toEqual([
      ["intake", "passed"],
      ["reconstruction", "passed"],
      ["identity-gate", "passed"],
    ]);

    const polled = await app.request(`/v1/avatars/${id}`);
    expect(polled.status).toBe(200);
    const polledJob = (await polled.json()) as AvatarJob;
    expect(polledJob.id).toBe(id);
    expect(polledJob.status).toBe("complete");

    const artifact = await app.request(`/v1/avatars/${id}/artifact`);
    expect(artifact.status).toBe(200);
    expect(artifact.headers.get("content-type")).toBe("application/octet-stream");
    expect(artifact.headers.get("content-disposition")).toBe(
      `attachment; filename="avatar-${id}.ply"`,
    );
    const bytes = new Uint8Array(await artifact.arrayBuffer());
    expect(bytes).toEqual(TEST_ARTIFACT_BYTES);
  });

  it("DELETE removes the job and subsequent reads 404", async () => {
    const form = imageForm(new File([ONE_PIXEL_PNG], "photo.png", { type: "image/png" }));
    const created = await app.request("/v1/avatars", uploadRequest(form));
    const { id } = (await created.json()) as { id: string };
    await waitForJob(id);

    const deleted = await app.request(`/v1/avatars/${id}`, { method: "DELETE" });
    expect(deleted.status).toBe(204);

    const res = await app.request(`/v1/avatars/${id}`);
    expect(res.status).toBe(404);
  });
});

describe("error envelopes", () => {
  it("404 for an unknown avatar uses problem JSON", async () => {
    const res = await app.request("/v1/avatars/av_missing");
    expect(res.status).toBe(404);
    expect(res.headers.get("content-type")).toContain("application/problem+json");
    const body = (await res.json()) as ProblemDetails;
    expect(body).toMatchObject({
      type: "about:blank",
      title: "Not Found",
      status: 404,
    });
    expect(body.detail).toContain("av_missing");
  });

  it("404 for DELETE of an unknown avatar", async () => {
    const res = await app.request("/v1/avatars/av_missing", { method: "DELETE" });
    expect(res.status).toBe(404);
    expect(res.headers.get("content-type")).toContain("application/problem+json");
  });

  it("404 for an artifact that does not exist yet", async () => {
    const res = await app.request("/v1/avatars/av_missing/artifact");
    expect(res.status).toBe(404);
    expect(res.headers.get("content-type")).toContain("application/problem+json");
  });

  it("400 when the image field is missing", async () => {
    const res = await app.request("/v1/avatars", uploadRequest(imageForm()));
    expect(res.status).toBe(400);
    const body = (await res.json()) as ProblemDetails;
    expect(body.detail).toContain("image");
  });

  it("415 for a non-image content type", async () => {
    const form = imageForm(
      new File([new TextEncoder().encode("hello")], "notes.txt", {
        type: "text/plain",
      }),
    );
    const res = await app.request("/v1/avatars", uploadRequest(form));
    expect(res.status).toBe(415);
    const body = (await res.json()) as ProblemDetails;
    expect(body.detail).toContain("text/plain");
  });

  it("413 when the upload exceeds MAX_UPLOAD_BYTES", async () => {
    const smallStore = new DiskJobStore(storageDir);
    const smallApp = createApp({
      config: makeConfig({ MAX_UPLOAD_BYTES: "8" }),
      store: smallStore,
      inference: new HttpInferenceClient(server.url),
    });
    const form = imageForm(new File([ONE_PIXEL_PNG], "photo.png", { type: "image/png" }));
    const res = await smallApp.request("/v1/avatars", uploadRequest(form));
    expect(res.status).toBe(413);
    const body = (await res.json()) as ProblemDetails;
    expect(body.detail).toContain("exceeds maximum size");
  });
});

describe("inference failures", () => {
  it("marks the job failed when the inference service rejects the image", async () => {
    server.setResponse({
      status: 422,
      body: {
        type: "about:blank",
        title: "Unprocessable Entity",
        status: 422,
        detail: "face not detected",
      },
    });
    try {
      const form = imageForm(new File([ONE_PIXEL_PNG], "photo.png", { type: "image/png" }));
      const created = await app.request("/v1/avatars", uploadRequest(form));
      expect(created.status).toBe(202);
      const { id } = (await created.json()) as { id: string };

      const job = await waitForJob(id);
      expect(job.status).toBe("failed");
      expect(job.error).toBe("face not detected");
      expect(job.stages[1]?.status).toBe("failed");

      const artifact = await app.request(`/v1/avatars/${id}/artifact`);
      expect(artifact.status).toBe(404);
    } finally {
      server.reset();
    }
  });
});
