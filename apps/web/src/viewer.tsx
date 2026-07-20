import { useEffect, useRef } from "react";
import * as GaussianSplats3D from "@mkkellogg/gaussian-splats-3d";

interface SplatViewerProps {
  url: string;
}

export function SplatViewer({ url }: SplatViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const rootElement = containerRef.current;
    if (!rootElement) {
      return;
    }
    let disposed = false;
    const viewer = new GaussianSplats3D.Viewer({
      rootElement,
      cameraUp: [0, 1, 0],
      initialCameraPosition: [0, 1.2, 3.2],
      initialCameraLookAt: [0, 0.9, 0],
    });
    viewer
      .addSplatScene(url, { format: GaussianSplats3D.SceneFormat.Ply, showLoadingUI: true })
      .then(() => {
        if (!disposed) {
          viewer.start();
        }
      })
      .catch((err: unknown) => {
        if (!disposed) {
          console.error("failed to load splat scene", err);
        }
      });
    return () => {
      disposed = true;
      // Upstream dispose() also removes rootElement from document.body, but it
      // only appended it there when it created the element itself. With a
      // caller-supplied rootElement that removeChild always throws — after all
      // real cleanup has run — so the rejection is safe to swallow.
      void viewer.dispose().catch(() => {});
    };
  }, [url]);

  return <div ref={containerRef} className="splat-viewer" />;
}
