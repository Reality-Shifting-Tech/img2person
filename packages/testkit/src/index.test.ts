import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { HttpInferenceClient, InferenceError } from "@img2person/contracts";
import {
  createFakeInferenceServer,
  memoryJobStore,
  ONE_PIXEL_PNG,
  TEST_ARTIFACT_BYTES,
  type FakeInferenceServer,
} from "./index.js";

describe("createFakeInferenceServer", () => {
  let server: FakeInferenceServer;

  beforeAll(async () => {
    server = await createFakeInferenceServer();
  });

  afterAll(async () => {
    await server.close();
  });

  it("answers health and reconstruct with the canned response", async () => {
    const client = new HttpInferenceClient(server.url);
    await expect(client.health()).resolves.toEqual({ status: "ok", mode: "test" });

    const result = await client.reconstruct({
      data: ONE_PIXEL_PNG,
      contentType: "image/png",
      filename: "pixel.png",
    });
    expect(result.identityScore).toBe(0.9);
    expect(result.mode).toBe("test");
    expect(Buffer.from(result.artifact.data, "base64")).toEqual(Buffer.from(TEST_ARTIFACT_BYTES));
  });

  it("setResponse forces a failure problem response", async () => {
    server.setResponse({
      status: 422,
      body: {
        type: "about:blank",
        title: "Unprocessable Entity",
        status: 422,
        detail: "face not detected",
      },
    });
    const client = new HttpInferenceClient(server.url);
    const error = await client
      .reconstruct({ data: ONE_PIXEL_PNG, contentType: "image/png", filename: "pixel.png" })
      .catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(InferenceError);
    expect((error as InferenceError).problem.detail).toBe("face not detected");
    server.reset();
  });
});

describe("memoryJobStore", () => {
  it("round-trips jobs and artifacts", async () => {
    const store = memoryJobStore();
    const timestamp = new Date().toISOString();
    await store.create({
      id: "av_1",
      status: "queued",
      stages: [{ stage: "intake", status: "pending" }],
      createdAt: timestamp,
      updatedAt: timestamp,
    });

    await store.update("av_1", { status: "complete" });
    const job = await store.get("av_1");
    expect(job?.status).toBe("complete");
    expect(job?.createdAt).toBe(timestamp);

    await store.saveArtifact("av_1", new Uint8Array([1, 2, 3]));
    expect(await store.artifactPath("av_1")).toBe("memory://av_1/artifact.ply");

    await store.delete("av_1");
    expect(await store.get("av_1")).toBeUndefined();
    expect(await store.artifactPath("av_1")).toBeUndefined();
  });

  it("rejects updates for unknown jobs", async () => {
    const store = memoryJobStore();
    await expect(store.update("av_nope", { status: "failed" })).rejects.toThrow("av_nope");
  });
});

describe("ONE_PIXEL_PNG", () => {
  it("has the PNG magic header", () => {
    expect(Array.from(ONE_PIXEL_PNG.subarray(0, 8))).toEqual([
      0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a,
    ]);
  });
});
