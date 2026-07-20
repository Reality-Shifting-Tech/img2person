import { mkdir } from "node:fs/promises";
import { serve } from "@hono/node-server";
import { loadConfig } from "@img2person/config";
import { HttpInferenceClient } from "@img2person/contracts";
import { createApp } from "./app.js";
import { DiskJobStore } from "./disk-store.js";

const config = loadConfig(process.env);
await mkdir(config.storageDir, { recursive: true });

const store = new DiskJobStore(config.storageDir);
const inference = new HttpInferenceClient(config.inferenceUrl);
const app = createApp({ config, store, inference });

serve({ fetch: app.fetch, port: config.apiPort }, (info) => {
  console.log(`img2person api listening on http://localhost:${info.port}`);
});
