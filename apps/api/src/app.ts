import { readFile } from "node:fs/promises";
import type { Config } from "@img2person/config";
import { problemDetails, type AvatarJob, type InferenceClient } from "@img2person/contracts";
import { initialStages, runReconstruction } from "@img2person/pipeline";
import { Hono, type Context } from "hono";
import { cors } from "hono/cors";
import type { DiskJobStore } from "./disk-store.js";

export interface AppDeps {
  config: Config;
  store: DiskJobStore;
  inference: InferenceClient;
}

type ErrorStatus = 400 | 404 | 413 | 415;

const ERROR_TITLES: Record<ErrorStatus, string> = {
  400: "Bad Request",
  404: "Not Found",
  413: "Payload Too Large",
  415: "Unsupported Media Type",
};

function problem(c: Context, status: ErrorStatus, detail: string) {
  return c.json(problemDetails(status, ERROR_TITLES[status], detail), status, {
    "content-type": "application/problem+json",
  });
}

export function createApp(deps: AppDeps): Hono {
  const { config, store, inference } = deps;
  const app = new Hono();

  app.use("/*", cors({ origin: config.webOrigin }));

  app.get("/healthz", (c) => c.json({ status: "ok" }));

  app.post("/v1/avatars", async (c) => {
    const body = await c.req.parseBody();
    const file = body["image"];
    if (!(file instanceof File)) {
      return problem(c, 400, "multipart field 'image' is required");
    }
    if (!file.type.startsWith("image/")) {
      return problem(c, 415, `unsupported content type: ${file.type || "unknown"}`);
    }
    if (file.size > config.maxUploadBytes) {
      return problem(c, 413, `image exceeds maximum size of ${config.maxUploadBytes} bytes`);
    }
    const bytes = new Uint8Array(await file.arrayBuffer());
    if (bytes.byteLength === 0) {
      return problem(c, 400, "image is empty");
    }
    if (bytes.byteLength > config.maxUploadBytes) {
      return problem(c, 413, `image exceeds maximum size of ${config.maxUploadBytes} bytes`);
    }

    const id = `av_${crypto.randomUUID()}`;
    const timestamp = new Date().toISOString();
    const job: AvatarJob = {
      id,
      status: "queued",
      stages: initialStages(),
      createdAt: timestamp,
      updatedAt: timestamp,
    };
    await store.create(job);
    await store.saveImage(id, bytes);

    void runReconstruction({
      jobId: id,
      image: { data: bytes, contentType: file.type, filename: file.name || "image" },
      maxUploadBytes: config.maxUploadBytes,
      inference,
      store,
    });

    return c.json({ id, status: "queued" }, 202);
  });

  app.get("/v1/avatars/:id", async (c) => {
    const id = c.req.param("id");
    const job = await store.get(id);
    if (!job) {
      return problem(c, 404, `avatar ${id} not found`);
    }
    return c.json(job);
  });

  app.get("/v1/avatars/:id/artifact", async (c) => {
    const id = c.req.param("id");
    const job = await store.get(id);
    const path = await store.artifactPath(id);
    if (!job || job.status !== "complete" || !path) {
      return problem(c, 404, `artifact for avatar ${id} not found`);
    }
    const bytes = await readFile(path);
    return c.body(new Uint8Array(bytes), 200, {
      "content-type": "application/octet-stream",
      "content-disposition": `attachment; filename="avatar-${id}.ply"`,
    });
  });

  app.delete("/v1/avatars/:id", async (c) => {
    const id = c.req.param("id");
    const job = await store.get(id);
    if (!job) {
      return problem(c, 404, `avatar ${id} not found`);
    }
    await store.delete(id);
    return c.body(null, 204);
  });

  return app;
}
