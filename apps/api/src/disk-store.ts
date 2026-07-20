import { access, mkdir, readFile, rename, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import type { AvatarJob } from "@img2person/contracts";
import type { JobStore } from "@img2person/pipeline";

export class DiskJobStore implements JobStore {
  readonly #root: string;

  constructor(root: string) {
    this.#root = root;
  }

  #dir(id: string): string {
    return join(this.#root, id);
  }

  async #writeAtomic(path: string, data: Uint8Array | string): Promise<void> {
    const tmp = `${path}.tmp-${crypto.randomUUID()}`;
    await writeFile(tmp, data);
    await rename(tmp, path);
  }

  async create(job: AvatarJob): Promise<void> {
    await mkdir(this.#dir(job.id), { recursive: true });
    await this.#writeAtomic(join(this.#dir(job.id), "job.json"), JSON.stringify(job, null, 2));
  }

  async update(id: string, patch: Partial<AvatarJob>): Promise<void> {
    const job = await this.get(id);
    if (!job) {
      throw new Error(`job ${id} not found`);
    }
    await this.#writeAtomic(
      join(this.#dir(id), "job.json"),
      JSON.stringify({ ...job, ...patch }, null, 2),
    );
  }

  async get(id: string): Promise<AvatarJob | undefined> {
    try {
      const raw = await readFile(join(this.#dir(id), "job.json"), "utf8");
      return JSON.parse(raw) as AvatarJob;
    } catch {
      return undefined;
    }
  }

  async delete(id: string): Promise<void> {
    await rm(this.#dir(id), { recursive: true, force: true });
  }

  async saveImage(id: string, bytes: Uint8Array): Promise<void> {
    await this.#writeAtomic(join(this.#dir(id), "image"), bytes);
  }

  async saveArtifact(id: string, bytes: Uint8Array): Promise<void> {
    await this.#writeAtomic(join(this.#dir(id), "artifact.ply"), bytes);
  }

  async artifactPath(id: string): Promise<string | undefined> {
    const path = join(this.#dir(id), "artifact.ply");
    try {
      await access(path);
      return path;
    } catch {
      return undefined;
    }
  }
}
