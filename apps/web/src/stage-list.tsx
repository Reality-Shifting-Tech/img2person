import { type Stage, type StageStatus } from "@img2person/contracts";

const STATUS_LABEL: Record<StageStatus, string> = {
  pending: "Pending",
  running: "Running",
  passed: "Passed",
  failed: "Failed",
};

export function StageList({ stages }: { stages: Stage[] }) {
  return (
    <ul className="stages">
      {stages.map((stage) => (
        <li key={stage.stage} className={`stage stage-${stage.status}`}>
          <span className="stage-name">{stage.stage}</span>
          <span className="stage-status">{STATUS_LABEL[stage.status]}</span>
          {stage.detail !== undefined && <span className="stage-detail">{stage.detail}</span>}
        </li>
      ))}
    </ul>
  );
}
