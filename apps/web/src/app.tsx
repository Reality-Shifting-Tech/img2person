import { useEffect, useState } from "react";
import { type AvatarJob } from "@img2person/contracts";
import { deleteAvatar, fetchAvatar } from "./api";
import { ResultView } from "./result";
import { StageList } from "./stage-list";
import { UploadForm } from "./upload-form";

const POLL_INTERVAL_MS = 1000;

type Step = "upload" | "processing" | "result";

export function App() {
  const [step, setStep] = useState<Step>("upload");
  const [avatarId, setAvatarId] = useState<string | null>(null);
  const [job, setJob] = useState<AvatarJob | null>(null);

  useEffect(() => {
    if (step !== "processing" || avatarId === null) {
      return;
    }
    let stopped = false;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const next = await fetchAvatar(avatarId);
        if (stopped) {
          return;
        }
        setJob(next);
        if (next.status === "complete" || next.status === "failed") {
          setStep("result");
          return;
        }
      } catch {
        // transient poll failure — keep trying until the job turns up or the user leaves
      }
      if (!stopped) {
        timer = window.setTimeout(() => void poll(), POLL_INTERVAL_MS);
      }
    };
    void poll();
    return () => {
      stopped = true;
      if (timer !== undefined) {
        window.clearTimeout(timer);
      }
    };
  }, [step, avatarId]);

  const startOver = () => {
    const id = avatarId;
    setStep("upload");
    setAvatarId(null);
    setJob(null);
    if (id !== null) {
      void deleteAvatar(id).catch(() => undefined);
    }
  };

  return (
    <main className="app">
      <header className="app-header">
        <h1>img2person</h1>
        <p>Turn one photo into a 3D avatar you can inspect from any angle.</p>
      </header>
      {step === "upload" && (
        <UploadForm
          onAccepted={(id) => {
            setAvatarId(id);
            setJob(null);
            setStep("processing");
          }}
        />
      )}
      {step === "processing" && (
        <section>
          <h2>Reconstructing your avatar</h2>
          {job === null ? <p>Queued…</p> : <StageList stages={job.stages} />}
        </section>
      )}
      {step === "result" && job?.status === "complete" && (
        <ResultView job={job} onStartOver={startOver} />
      )}
      {step === "result" && job?.status === "failed" && (
        <section>
          <h2>Reconstruction failed</h2>
          <StageList stages={job.stages} />
          {job.error !== undefined && (
            <p className="error" role="alert">
              {job.error}
            </p>
          )}
          <div className="actions">
            <button type="button" onClick={startOver}>
              Try another photo
            </button>
          </div>
        </section>
      )}
    </main>
  );
}
