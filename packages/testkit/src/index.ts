import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import type { AvatarJob, ReconstructResponse } from "@img2person/contracts";
import type { JobStore } from "@img2person/pipeline";

export const TEST_ARTIFACT_BYTES = new TextEncoder().encode("img2person-test-artifact");

export const ONE_PIXEL_PNG = new Uint8Array([
  0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x00, 0x00, 0x0d, 0x49, 0x48, 0x44, 0x52,
  0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01, 0x08, 0x06, 0x00, 0x00, 0x00, 0x1f, 0x15, 0xc4,
  0x89, 0x00, 0x00, 0x00, 0x0a, 0x49, 0x44, 0x41, 0x54, 0x78, 0x9c, 0x63, 0x00, 0x01, 0x00, 0x00,
  0x05, 0x00, 0x01, 0x0d, 0x0a, 0x2d, 0xb4, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4e, 0x44, 0xae,
  0x42, 0x60, 0x82,
]);

export interface FakeInferenceResponse {
  status: number;
  body: unknown;
}

export interface FakeInferenceServer {
  url: string;
  setResponse(response: FakeInferenceResponse): void;
  reset(): void;
  close(): Promise<void>;
}

export function cannedReconstructResponse(): ReconstructResponse {
  return {
    artifact: {
      format: "ply",
      encoding: "base64",
      data: Buffer.from(TEST_ARTIFACT_BYTES).toString("base64"),
    },
    identityScore: 0.9,
    confidence: { front: 0.9, profile: 0.7, back: 0.5 },
    mode: "test",
    stages: [{ stage: "intake", status: "passed", detail: "fake inference server" }],
  };
}

export async function createFakeInferenceServer(): Promise<FakeInferenceServer> {
  let override: FakeInferenceResponse | undefined;

  const server = createServer((req, res) => {
    const respond = (status: number, body: unknown) => {
      res.writeHead(status, { "content-type": "application/json" });
      res.end(JSON.stringify(body));
    };
    req.resume();
    if (override) {
      respond(override.status, override.body);
      return;
    }
    if (req.method === "GET" && req.url === "/health") {
      respond(200, { status: "ok", mode: "test" });
      return;
    }
    if (req.method === "POST" && req.url === "/v1/reconstruct") {
      respond(200, cannedReconstructResponse());
      return;
    }
    respond(404, { type: "about:blank", title: "Not Found", status: 404, detail: "unknown route" });
  });

  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address() as AddressInfo;

  return {
    url: `http://127.0.0.1:${port}`,
    setResponse(response) {
      override = response;
    },
    reset() {
      override = undefined;
    },
    close: () =>
      new Promise<void>((resolve, reject) =>
        server.close((error) => (error ? reject(error) : resolve())),
      ),
  };
}

export function memoryJobStore(): JobStore {
  const jobs = new Map<string, AvatarJob>();
  const artifacts = new Map<string, Uint8Array>();
  return {
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
