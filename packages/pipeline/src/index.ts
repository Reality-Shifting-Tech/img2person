import type {
  AvatarJob,
  InferenceClient,
  InferenceImage,
  Stage,
  StageStatus,
} from "@img2person/contracts";

export const IDENTITY_SCORE_THRESHOLD = 0.5;

export interface JobStore {
  create(job: AvatarJob): Promise<void>;
  update(id: string, patch: Partial<AvatarJob>): Promise<void>;
  get(id: string): Promise<AvatarJob | undefined>;
  delete(id: string): Promise<void>;
  saveArtifact(id: string, bytes: Uint8Array): Promise<void>;
  artifactPath(id: string): Promise<string | undefined>;
}

export function initialStages(): Stage[] {
  return [
    { stage: "intake", status: "pending" },
    { stage: "reconstruction", status: "pending" },
    { stage: "identity-gate", status: "pending" },
  ];
}

export function setStageStatus(
  stages: Stage[],
  stage: string,
  status: StageStatus,
  detail?: string,
): Stage[] {
  return stages.map((current) => {
    if (current.stage !== stage) {
      return { ...current };
    }
    const next: Stage = { ...current, status };
    if (detail !== undefined) {
      next.detail = detail;
    } else {
      delete next.detail;
    }
    return next;
  });
}

export interface RunReconstructionOptions {
  jobId: string;
  image: InferenceImage;
  maxUploadBytes: number;
  inference: InferenceClient;
  store: JobStore;
}

function validateImage(image: InferenceImage, maxUploadBytes: number): string | undefined {
  if (image.data.byteLength === 0) {
    return "image is empty";
  }
  if (image.data.byteLength > maxUploadBytes) {
    return `image exceeds maximum size of ${maxUploadBytes} bytes`;
  }
  if (!image.contentType.startsWith("image/")) {
    return `unsupported content type: ${image.contentType || "unknown"}`;
  }
  return undefined;
}

export async function runReconstruction(options: RunReconstructionOptions): Promise<void> {
  const { jobId, image, maxUploadBytes, inference, store } = options;
  const now = () => new Date().toISOString();

  const fail = async (stages: Stage[], message: string): Promise<void> => {
    await store.update(jobId, { status: "failed", stages, error: message, updatedAt: now() });
  };

  try {
    const job = await store.get(jobId);
    if (!job) {
      return;
    }

    let stages = setStageStatus(job.stages, "intake", "running");
    await store.update(jobId, { status: "processing", stages, updatedAt: now() });

    const intakeError = validateImage(image, maxUploadBytes);
    if (intakeError) {
      await fail(setStageStatus(stages, "intake", "failed", intakeError), intakeError);
      return;
    }

    stages = setStageStatus(stages, "intake", "passed");
    stages = setStageStatus(stages, "reconstruction", "running");
    await store.update(jobId, { stages, updatedAt: now() });

    const result = await inference.reconstruct(image);
    await store.saveArtifact(jobId, Buffer.from(result.artifact.data, "base64"));
    stages = setStageStatus(stages, "reconstruction", "passed");

    const gatePassed = result.identityScore >= IDENTITY_SCORE_THRESHOLD;
    stages = gatePassed
      ? setStageStatus(stages, "identity-gate", "passed")
      : setStageStatus(stages, "identity-gate", "failed", "identity score below threshold");

    await store.update(jobId, {
      status: gatePassed ? "complete" : "failed",
      stages,
      mode: result.mode,
      identityScore: result.identityScore,
      confidence: result.confidence,
      ...(gatePassed ? {} : { error: "identity score below threshold" }),
      updatedAt: now(),
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    const job = await store.get(jobId).catch(() => undefined);
    const stages = job
      ? setStageStatus(job.stages, "reconstruction", "failed", message)
      : initialStages();
    await store
      .update(jobId, { status: "failed", stages, error: message, updatedAt: now() })
      .catch(() => undefined);
  }
}
