import { z } from "zod";

// RFC 9457 problem details

export const problemDetailsSchema = z.object({
  type: z.string(),
  title: z.string(),
  status: z.number().int(),
  detail: z.string().optional(),
});

export type ProblemDetails = z.infer<typeof problemDetailsSchema>;

export function problemDetails(
  status: number,
  title: string,
  detail?: string,
  type = "about:blank",
): ProblemDetails {
  const problem: ProblemDetails = { type, title, status };
  if (detail !== undefined) {
    problem.detail = detail;
  }
  return problem;
}

// Avatar job model

export type JobStatus = "queued" | "processing" | "complete" | "failed";

export type StageStatus = "pending" | "running" | "passed" | "failed";

export interface Stage {
  stage: string;
  status: StageStatus;
  detail?: string | undefined;
}

export interface AvatarJob {
  id: string;
  status: JobStatus;
  stages: Stage[];
  mode?: string | undefined;
  identityScore?: number | undefined;
  confidence?: Record<string, number> | undefined;
  error?: string | undefined;
  createdAt: string;
  updatedAt: string;
}

// Inference service contract

export const reconstructResponseSchema = z.object({
  artifact: z.object({
    format: z.string(),
    encoding: z.string(),
    data: z.string(),
  }),
  identityScore: z.number().min(0).max(1),
  confidence: z.record(z.number()),
  mode: z.string(),
  stages: z.array(
    z.object({
      stage: z.string(),
      status: z.enum(["pending", "running", "passed", "failed"]),
      detail: z.string().optional(),
    }),
  ),
});

export type ReconstructResponse = z.infer<typeof reconstructResponseSchema>;

export interface InferenceImage {
  data: Uint8Array;
  contentType: string;
  filename: string;
}

export interface InferenceClient {
  health(): Promise<{ status: string; mode: string }>;
  reconstruct(image: InferenceImage): Promise<ReconstructResponse>;
}

export class InferenceError extends Error {
  readonly problem: ProblemDetails;

  constructor(problem: ProblemDetails) {
    super(problem.detail ?? problem.title);
    this.name = "InferenceError";
    this.problem = problem;
  }
}

async function readProblem(response: Response): Promise<ProblemDetails> {
  try {
    const body: unknown = await response.json();
    const parsed = problemDetailsSchema.safeParse(body);
    if (parsed.success) {
      return parsed.data;
    }
  } catch {
    // fall through to the synthesized problem below
  }
  return {
    type: "about:blank",
    title: response.statusText || "Inference Error",
    status: response.status,
  };
}

export class HttpInferenceClient implements InferenceClient {
  readonly #baseUrl: string;

  constructor(baseUrl: string) {
    this.#baseUrl = baseUrl.replace(/\/+$/, "");
  }

  async health(): Promise<{ status: string; mode: string }> {
    const response = await fetch(`${this.#baseUrl}/health`);
    if (!response.ok) {
      throw new InferenceError(await readProblem(response));
    }
    return (await response.json()) as { status: string; mode: string };
  }

  async reconstruct(image: InferenceImage): Promise<ReconstructResponse> {
    const form = new FormData();
    form.append("image", new Blob([image.data], { type: image.contentType }), image.filename);
    const response = await fetch(`${this.#baseUrl}/v1/reconstruct`, {
      method: "POST",
      body: form,
    });
    if (!response.ok) {
      throw new InferenceError(await readProblem(response));
    }
    const body: unknown = await response.json();
    return reconstructResponseSchema.parse(body);
  }
}
