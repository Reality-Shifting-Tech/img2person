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
      .addSplatScene(url, { showLoadingUI: true })
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
      void viewer.dispose();
    };
  }, [url]);

  return <div ref={containerRef} className="splat-viewer" />;
}
