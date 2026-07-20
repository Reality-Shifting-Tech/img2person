declare module "@mkkellogg/gaussian-splats-3d" {
  export interface ViewerOptions {
    rootElement?: HTMLElement;
    sharedMemoryForWorkers?: boolean;
    sceneRevealMode?: SceneRevealModeValue;
    cameraUp?: [number, number, number];
    initialCameraPosition?: [number, number, number];
    initialCameraLookAt?: [number, number, number];
  }

  export const SceneFormat: {
    readonly Splat: 0;
    readonly KSplat: 1;
    readonly Ply: 2;
    readonly Spz: 3;
  };
  export type SceneFormatValue = (typeof SceneFormat)[keyof typeof SceneFormat];

  export const SceneRevealMode: {
    readonly Default: 0;
    readonly Gradual: 1;
    readonly Instant: 2;
  };
  export type SceneRevealModeValue = (typeof SceneRevealMode)[keyof typeof SceneRevealMode];

  export interface SplatSceneOptions {
    format?: SceneFormatValue;
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
