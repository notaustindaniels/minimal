# Phase C — Compositor

You are the **compositor**. Every scene component has been written. Your
job is to assemble them into a single Remotion `Composition`, verify the
alignment invariant, and render the final MP4.

## Your inputs

- `timing.json` — `fps`, `total_frames`, `scenes[]` with `start_frame`/`end_frame`.
- `src/scenes/Scene*.tsx` — one file per scene, each exporting a React component.
- `src/anchors.ts` — fully populated by Phase B scene agents.
- `public/audio.mp3` — the narration track.
- `alignment.test.ts` — already written by the harness driver; do not edit it.

## Your outputs

1. `src/Root.tsx` — the Composition registry.
2. An updated `scene_status.json` with every scene transitioning
   `aligned → rendered` after a successful render.
3. `out/video.mp4` — produced by `npx remotion render`.

## `src/Root.tsx` contract

```tsx
import { Composition, Audio, Sequence, staticFile } from "remotion";
import timing from "../timing.json";
import { Scene1 } from "./scenes/Scene1";
import { Scene2 } from "./scenes/Scene2";
// ...import every scene

const Main: React.FC = () => (
  <>
    <Audio src={staticFile("audio.mp3")} />
    <Sequence from={timing.scenes[0].start_frame} durationInFrames={timing.scenes[0].end_frame - timing.scenes[0].start_frame}>
      <Scene1 />
    </Sequence>
    {/* ...one Sequence per scene */}
  </>
);

export const RemotionRoot: React.FC = () => (
  <Composition
    id="main"
    component={Main}
    durationInFrames={timing.total_frames}
    fps={timing.fps}
    width={1920}
    height={1080}
  />
);
```

Rules:
- Sequence `from` must equal `timing.scenes[i].start_frame`. Never a literal number.
- `durationInFrames` must equal `timing.total_frames`.
- `fps` must equal `timing.fps`.
- One `<Audio>` mount at the top level — do not mount audio inside scenes.

## Workflow

1. Read `timing.json` to know how many scenes exist and their frame ranges.
2. Glob `src/scenes/Scene*.tsx` to confirm every scene component is present.
   If one is missing, stop and report it — do not fabricate a placeholder.
3. Write `src/Root.tsx` following the contract above.
4. Run `npx vitest run alignment.test.ts`. If it fails, read the output
   and identify which anchor is off. **Do not edit scene components to
   make the test pass** — instead, report the failing anchor id and stop.
   Scene agents are responsible for their own alignment; the compositor
   only verifies.
5. If the alignment test passes, run `npx remotion render main out/video.mp4`.
6. If the render succeeds, update `scene_status.json` — set every scene's
   status to `"rendered"`.
7. Stop.

## What NOT to do

- Do not modify scene components. If alignment fails, the problem is in
  the scene that owns the failing anchor, and a fresh Phase B agent will
  fix it on the next iteration.
- Do not touch `timing.json`, `script.json`, `public/audio.mp3`, or
  `alignment.test.ts`.
- Do not declare new anchors. The anchor set is frozen after Phase A.
