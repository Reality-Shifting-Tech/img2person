import { type AvatarJob } from "@img2person/contracts";
import { SplatViewer } from "./viewer";

const REGION_ORDER = ["front", "profile", "back"];

function scoreLabel(score: number): string {
  if (score >= 0.85) {
    return "strong resemblance to the photo";
  }
  if (score >= 0.7) {
    return "likely resemblance to the photo";
  }
  return "weak resemblance — try a sharper, well-lit photo";
}

function ConfidenceBars({ confidence }: { confidence: Record<string, number> }) {
  const regions = [
    ...REGION_ORDER.filter((name) => name in confidence),
    ...Object.keys(confidence).filter((name) => !REGION_ORDER.includes(name)),
  ];
  return (
    <div className="confidence">
      {regions.map((name) => {
        const value = confidence[name];
        if (value === undefined) {
          return null;
        }
        const percent = Math.round(value * 100);
        return (
          <div key={name} className="confidence-row">
            <span className="confidence-label">{name}</span>
            <span className="confidence-track">
              <span className="confidence-fill" style={{ width: `${percent}%` }} />
            </span>
            <span className="confidence-value">{percent}%</span>
          </div>
        );
      })}
    </div>
  );
}

interface ResultViewProps {
  job: AvatarJob;
  onStartOver: () => void;
}

export function ResultView({ job, onStartOver }: ResultViewProps) {
  const artifactUrl = `/v1/avatars/${job.id}/artifact`;
  return (
    <section className="result">
      <div className="viewer-frame">
        <SplatViewer url={artifactUrl} />
      </div>
      {job.mode === "mock" && (
        <p className="badge" role="status">
          Demo reconstruction — run the inference service with a GPU for the real model.
        </p>
      )}
      {typeof job.identityScore === "number" && (
        <p className="score">
          Identity match: <strong>{Math.round(job.identityScore * 100)}%</strong> —{" "}
          {scoreLabel(job.identityScore)}.
        </p>
      )}
      {job.confidence !== undefined && <ConfidenceBars confidence={job.confidence} />}
      <p className="honesty">
        Back and profile views are synthesized from a single photo — confidence is lower there.
      </p>
      <div className="actions">
        <a className="button" href={artifactUrl} download={`avatar-${job.id}.ply`}>
          Download .ply
        </a>
        <button type="button" onClick={onStartOver}>
          Start over
        </button>
      </div>
    </section>
  );
}
