declare module "@mkkellogg/gaussian-splats-3d" {
  export interface ViewerOptions {
    rootElement?: HTMLElement;
    cameraUp?: [number, number, number];
    initialCameraPosition?: [number, number, number];
    initialCameraLookAt?: [number, number, number];
  }

  export interface SplatSceneOptions {
    showLoadingUI?: boolean;
  }

  export class Viewer {
    constructor(options?: ViewerOptions);
    addSplatScene(path: string, options?: SplatSceneOptions): Promise<void>;
    start(): void;
    stop(): void;
    dispose(): Promise<void>;
  }
}
