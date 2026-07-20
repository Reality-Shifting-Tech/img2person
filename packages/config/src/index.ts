import { z } from "zod";

const envSchema = z.object({
  API_PORT: z.coerce.number().int().min(1).max(65535).default(3000),
  STORAGE_DIR: z.string().min(1).default("./storage"),
  INFERENCE_URL: z.string().url().default("http://localhost:8000"),
  MAX_UPLOAD_BYTES: z.coerce.number().int().positive().default(10485760),
  WEB_ORIGIN: z.string().url().default("http://localhost:5173"),
});

const configSchema = envSchema.transform((env) => ({
  apiPort: env.API_PORT,
  storageDir: env.STORAGE_DIR,
  inferenceUrl: env.INFERENCE_URL,
  maxUploadBytes: env.MAX_UPLOAD_BYTES,
  webOrigin: env.WEB_ORIGIN,
}));

export type Config = z.infer<typeof configSchema>;

export class ConfigError extends Error {
  readonly issues: z.ZodIssue[];

  constructor(issues: z.ZodIssue[]) {
    const lines = issues.map((issue) => `  ${issue.path.join(".")}: ${issue.message}`);
    super(`Invalid environment configuration:\n${lines.join("\n")}`);
    this.name = "ConfigError";
    this.issues = issues;
  }
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): Config {
  const result = configSchema.safeParse(env);
  if (!result.success) {
    throw new ConfigError(result.error.issues);
  }
  return result.data;
}
