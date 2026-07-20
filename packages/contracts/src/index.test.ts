import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import {
  HttpInferenceClient,
  InferenceError,
  problemDetails,
  reconstructResponseSchema,
} from "./index.js";

describe("problemDetails", () => {
  it("builds an RFC 9457 envelope with a default type", () => {
    expect(problemDetails(404, "Not Found", "avatar av_1 not found")).toEqual({
      type: "about:blank",
      title: "Not Found",
      status: 404,
      detail: "avatar av_1 not found",
    });
  });

  it("omits detail when not provided and accepts an explicit type", () => {
    const body = problemDetails(
      422,
      "Validation Failed",
      undefined,
      "https://img2person.dev/problems/validation",
    );
    expect(body).toEqual({
      type: "https://img2person.dev/problems/validation",
      title: "Validation Failed",
      status: 422,
    });
    expect("detail" in body).toBe(false);
  });
});

describe("reconstructResponseSchema", () => {
  const valid = {
    artifact: { format: "ply", encoding: "base64", data: "QUJD" },
    identityScore: 0.87,
    confidence: { front: 0.9, profile: 0.6 },
    mode: "mock",
    stages: [{ stage: "intake", status: "passed", detail: "ok" }],
  };

  it("accepts a well-formed response", () => {
    expect(reconstructResponseSchema.parse(valid)).toEqual(valid);
  });

  it("rejects a missing artifact", () => {
    const { artifact: _artifact, ...rest } = valid;
    expect(reconstructResponseSchema.safeParse(rest).success).toBe(false);
  });

  it("rejects an out-of-range identity score", () => {
    expect(reconstructResponseSchema.safeParse({ ...valid, identityScore: 1.5 }).success).toBe(
      false,
    );
  });

  it("rejects a non-object payload", () => {
    expect(reconstructResponseSchema.safeParse("nope").success).toBe(false);
  });
});

describe("HttpInferenceClient", () => {
  let server: Server;
  let baseUrl: string;
  let handler: (status: number, body: unknown) => void;
  let next: { status: number; body: unknown } | undefined;

  beforeAll(async () => {
    server = createServer((req, res) => {
      const respond = (status: number, body: unknown) => {
        res.writeHead(status, { "content-type": "application/json" });
        res.end(JSON.stringify(body));
      };
      if (next) {
        const current = next;
        next = undefined;
        req.resume();
        respond(current.status, current.body);
        return;
      }
      if (req.method === "GET" && req.url === "/health") {
        respond(200, { status: "ok", mode: "mock" });
        return;
      }
      if (req.method === "POST" && req.url === "/v1/reconstruct") {
        req.resume();
        respond(200, {
          artifact: { format: "ply", encoding: "base64", data: "QUJD" },
          identityScore: 0.9,
          confidence: { front: 0.9 },
          mode: "mock",
          stages: [{ stage: "intake", status: "passed" }],
        });
        return;
      }
      respond(404, { type: "about:blank", title: "Not Found", status: 404 });
    });
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    const { port } = server.address() as AddressInfo;
    baseUrl = `http://127.0.0.1:${port}`;
    handler = (status, body) => {
      next = { status, body };
    };
  });

  afterAll(async () => {
    await new Promise<void>((resolve, reject) =>
      server.close((error) => (error ? reject(error) : resolve())),
    );
  });

  const image = {
    data: new Uint8Array([1, 2, 3]),
    contentType: "image/png",
    filename: "photo.png",
  };

  it("reports health", async () => {
    const client = new HttpInferenceClient(baseUrl);
    await expect(client.health()).resolves.toEqual({ status: "ok", mode: "mock" });
  });

  it("reconstructs and validates the response", async () => {
    const client = new HttpInferenceClient(baseUrl);
    const result = await client.reconstruct(image);
    expect(result.identityScore).toBe(0.9);
    expect(result.artifact.format).toBe("ply");
  });

  it("maps a problem JSON error to InferenceError", async () => {
    handler(422, {
      type: "about:blank",
      title: "Unprocessable Entity",
      status: 422,
      detail: "face not detected",
    });
    const client = new HttpInferenceClient(baseUrl);
    const error = await client.reconstruct(image).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(InferenceError);
    expect((error as InferenceError).problem).toMatchObject({
      status: 422,
      detail: "face not detected",
    });
    expect((error as InferenceError).message).toBe("face not detected");
  });

  it("synthesizes a problem when the error body is not problem JSON", async () => {
    handler(500, { unexpected: true });
    const client = new HttpInferenceClient(baseUrl);
    const error = await client.reconstruct(image).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(InferenceError);
    expect((error as InferenceError).problem.status).toBe(500);
  });

  it("rejects a 200 response that fails schema validation", async () => {
    handler(200, { identityScore: "high" });
    const client = new HttpInferenceClient(baseUrl);
    await expect(client.reconstruct(image)).rejects.toThrow();
  });
});
