import type {
  AvatarJob,
  InferenceClient,
  InferenceImage,
  ReconstructResponse,
} from "@img2person/contracts";
import { InferenceError } from "@img2person/contracts";
import { describe, expect, it } from "vitest";
import { initialStages, runReconstruction, setStageStatus, type JobStore } from "./index.js";

function memoryStore(): JobStore & { jobs: Map<string, AvatarJob> } {
  const jobs = new Map<string, AvatarJob>();
  const artifacts = new Map<string, Uint8Array>();
  return {
    jobs,
    async create(job) {
      jobs.set(job.id, structuredClone(job));
    },
    async update(id, patch) {
      const job = jobs.get(id);
      if (!job) {
        throw new Error(`job ${id} not found`);
      }
      jobs.set(id, { ...job, ...patch });
    },
    async get(id) {
      const job = jobs.get(id);
      return job ? structuredClone(job) : undefined;
    },
    async delete(id) {
      jobs.delete(id);
      artifacts.delete(id);
    },
    async saveArtifact(id, bytes) {
      artifacts.set(id, bytes);
    },
    async artifactPath(id) {
      return artifacts.has(id) ? `memory://${id}/artifact.ply` : undefined;
    },
  };
}

function fakeInference(
  result: ReconstructResponse | Error,
): InferenceClient & { calls: InferenceImage[] } {
  const calls: InferenceImage[] = [];
  return {
    calls,
    async health() {
      return { status: "ok", mode: "test" };
    },
    async reconstruct(image) {
      calls.push(image);
      if (result instanceof Error) {
        throw result;
      }
      return result;
    },
  };
}

const ARTIFACT_BYTES = new TextEncoder().encode("ply-bytes");

function response(identityScore: number): ReconstructResponse {
  return {
    artifact: {
      format: "ply",
      encoding: "base64",
      data: Buffer.from(ARTIFACT_BYTES).toString("base64"),
    },
    identityScore,
    confidence: { front: 0.9 },
    mode: "test",
    stages: [{ stage: "intake", status: "passed" }],
  };
}

function unscoredResponse(): ReconstructResponse {
  const base = response(0.9);
  delete base.identityScore;
  return base;
}

async function seedJob(store: JobStore, id = "av_test"): Promise<void> {
  const timestamp = new Date().toISOString();
  await store.create({
    id,
    status: "queued",
    stages: initialStages(),
    createdAt: timestamp,
    updatedAt: timestamp,
  });
}

const image: InferenceImage = {
  data: new Uint8Array([137, 80, 78, 71]),
  contentType: "image/png",
  filename: "photo.png",
};

describe("stage helpers", () => {
  it("initialStages starts all three stages pending", () => {
    expect(initialStages()).toEqual([
      { stage: "intake", status: "pending" },
      { stage: "reconstruction", status: "pending" },
      { stage: "identity-gate", status: "pending" },
    ]);
  });

  it("setStageStatus updates immutably and sets detail", () => {
    const before = initialStages();
    const after = setStageStatus(before, "intake", "failed", "boom");
    expect(before[0]).toEqual({ stage: "intake", status: "pending" });
    expect(after[0]).toEqual({ stage: "intake", status: "failed", detail: "boom" });
    expect(after[1]).toEqual({ stage: "reconstruction", status: "pending" });
  });
});

describe("runReconstruction", () => {
  it("completes the happy path and persists the decoded artifact", async () => {
    const store = memoryStore();
    await seedJob(store);
    const inference = fakeInference(response(0.9));

    await runReconstruction({ jobId: "av_test", image, maxUploadBytes: 1024, inference, store });

    const job = await store.get("av_test");
    expect(job?.status).toBe("complete");
    expect(job?.mode).toBe("test");
    expect(job?.identityScore).toBe(0.9);
    expect(job?.confidence).toEqual({ front: 0.9 });
    expect(job?.stages).toEqual([
      { stage: "intake", status: "passed" },
      { stage: "reconstruction", status: "passed" },
      { stage: "identity-gate", status: "passed" },
    ]);
    expect(await store.artifactPath("av_test")).toBe("memory://av_test/artifact.ply");
    expect(inference.calls).toHaveLength(1);
  });

  it("fails intake for an empty image without calling inference", async () => {
    const store = memoryStore();
    await seedJob(store);
    const inference = fakeInference(response(0.9));

    await runReconstruction({
      jobId: "av_test",
      image: { ...image, data: new Uint8Array(0) },
      maxUploadBytes: 1024,
      inference,
      store,
    });

    const job = await store.get("av_test");
    expect(job?.status).toBe("failed");
    expect(job?.error).toBe("image is empty");
    expect(job?.stages[0]).toEqual({ stage: "intake", status: "failed", detail: "image is empty" });
    expect(inference.calls).toHaveLength(0);
  });

  it("fails intake for oversized images and non-image content types", async () => {
    const store = memoryStore();
    await seedJob(store, "av_big");
    await seedJob(store, "av_text");
    const inference = fakeInference(response(0.9));

    await runReconstruction({
      jobId: "av_big",
      image: { ...image, data: new Uint8Array(2048) },
      maxUploadBytes: 1024,
      inference,
      store,
    });
    await runReconstruction({
      jobId: "av_text",
      image: { ...image, contentType: "text/plain" },
      maxUploadBytes: 1024,
      inference,
      store,
    });

    expect((await store.get("av_big"))?.error).toContain("exceeds maximum size");
    expect((await store.get("av_text"))?.stages[0]).toMatchObject({
      stage: "intake",
      status: "failed",
      detail: "unsupported content type: text/plain",
    });
    expect(inference.calls).toHaveLength(0);
  });

  it("fails the identity gate when the score is below threshold", async () => {
    const store = memoryStore();
    await seedJob(store);
    const inference = fakeInference(response(0.3));

    await runReconstruction({ jobId: "av_test", image, maxUploadBytes: 1024, inference, store });

    const job = await store.get("av_test");
    expect(job?.status).toBe("failed");
    expect(job?.error).toBe("identity score below threshold");
    expect(job?.stages[1]?.status).toBe("passed");
    expect(job?.stages[2]).toEqual({
      stage: "identity-gate",
      status: "failed",
      detail: "identity score below threshold",
    });
    expect(await store.artifactPath("av_test")).toBeDefined();
  });

  it("passes the identity gate with a note when no score is produced", async () => {
    const store = memoryStore();
    await seedJob(store);
    const inference = fakeInference(unscoredResponse());

    await runReconstruction({ jobId: "av_test", image, maxUploadBytes: 1024, inference, store });

    const job = await store.get("av_test");
    expect(job?.status).toBe("complete");
    expect(job?.identityScore).toBeUndefined();
    expect(job?.stages[2]).toEqual({
      stage: "identity-gate",
      status: "passed",
      detail: "identity score unavailable",
    });
  });

  it("fails the job with the problem detail when inference errors", async () => {
    const store = memoryStore();
    await seedJob(store);
    const inference = fakeInference(
      new InferenceError({
        type: "about:blank",
        title: "Unprocessable Entity",
        status: 422,
        detail: "face not detected",
      }),
    );

    await runReconstruction({ jobId: "av_test", image, maxUploadBytes: 1024, inference, store });

    const job = await store.get("av_test");
    expect(job?.status).toBe("failed");
    expect(job?.error).toBe("face not detected");
    expect(job?.stages[1]).toMatchObject({ stage: "reconstruction", status: "failed" });
    expect(await store.artifactPath("av_test")).toBeUndefined();
  });

  it("never rejects, even when the store is broken", async () => {
    const store = memoryStore();
    const inference = fakeInference(response(0.9));
    await expect(
      runReconstruction({ jobId: "av_missing", image, maxUploadBytes: 1024, inference, store }),
    ).resolves.toBeUndefined();
  });
});
