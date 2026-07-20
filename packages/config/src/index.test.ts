import { describe, expect, it } from "vitest";
import { ConfigError, loadConfig } from "./index.js";

describe("loadConfig", () => {
  it("applies defaults for an empty environment", () => {
    expect(loadConfig({})).toEqual({
      apiPort: 3000,
      storageDir: "./storage",
      inferenceUrl: "http://localhost:8000",
      maxUploadBytes: 10485760,
      webOrigin: "http://localhost:5173",
    });
  });

  it("coerces numeric strings", () => {
    const config = loadConfig({ API_PORT: "8080", MAX_UPLOAD_BYTES: "2048" });
    expect(config.apiPort).toBe(8080);
    expect(config.maxUploadBytes).toBe(2048);
  });

  it("rejects an invalid INFERENCE_URL", () => {
    expect(() => loadConfig({ INFERENCE_URL: "not-a-url" })).toThrow(ConfigError);
  });

  it("rejects a non-numeric API_PORT with a readable message", () => {
    try {
      loadConfig({ API_PORT: "abc" });
      expect.unreachable();
    } catch (error) {
      expect(error).toBeInstanceOf(ConfigError);
      expect((error as ConfigError).message).toContain("API_PORT");
    }
  });

  it("rejects a negative MAX_UPLOAD_BYTES", () => {
    expect(() => loadConfig({ MAX_UPLOAD_BYTES: "-1" })).toThrow(ConfigError);
  });
});
