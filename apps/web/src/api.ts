import { type AvatarJob, type ProblemDetails } from "@img2person/contracts";

export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(problem: ProblemDetails) {
    super(problem.detail ?? problem.title);
    this.name = "ApiError";
    this.status = problem.status;
    this.detail = problem.detail ?? problem.title;
  }
}

async function readProblem(response: Response): Promise<ProblemDetails> {
  try {
    const body = (await response.json()) as Partial<ProblemDetails>;
    if (typeof body.title === "string" && typeof body.status === "number") {
      return {
        type: body.type ?? "about:blank",
        title: body.title,
        status: body.status,
        detail: body.detail,
      };
    }
  } catch {
    // fall through to the generic problem below
  }
  return {
    type: "about:blank",
    title: response.statusText || "Request failed",
    status: response.status,
  };
}

export async function uploadAvatar(image: File): Promise<{ id: string; status: string }> {
  const form = new FormData();
  form.append("image", image);
  const response = await fetch("/v1/avatars", { method: "POST", body: form });
  if (!response.ok) {
    throw new ApiError(await readProblem(response));
  }
  return (await response.json()) as { id: string; status: string };
}

export async function fetchAvatar(id: string): Promise<AvatarJob> {
  const response = await fetch(`/v1/avatars/${id}`);
  if (!response.ok) {
    throw new ApiError(await readProblem(response));
  }
  return (await response.json()) as AvatarJob;
}

export async function deleteAvatar(id: string): Promise<void> {
  const response = await fetch(`/v1/avatars/${id}`, { method: "DELETE" });
  if (!response.ok && response.status !== 404) {
    throw new ApiError(await readProblem(response));
  }
}
