# Phase C — Compositor

You are the **compositor**. Every shot component has been written. Your
job is to assemble them into a single Remotion `Composition`, mount the
caption overlay, verify the alignment invariant, and render the final
MP4.

## Your inputs

- `timing.json` — `fps`, `total_frames`, `shots[]` with `start_frame`/
  `end_frame`, `anchors[]`, `captions[]`.
- `src/shots/Shot*.tsx` — one file per shot.
- `src/anchors.ts` — fully populated by Phase B.
- `src/Captions.tsx` — pre-scaffolded by the harness driver. **Do not
  edit it.** It already reads `timing.json.captions` and renders the
  active caption every frame.
- `public/audio.mp3` — the narration track.
- `alignment.test.ts` — pre-scaffolded by the harness driver.

## Your outputs

1. `src/Root.tsx` — the Composition registry that mounts every shot in
   order, plus the audio track and the captions overlay.
2. `out/video.mp4` — produced by `npx remotion render`.

## `src/Root.tsx` contract

```tsx
import {
  Composition,
  AbsoluteFill,
  Audio,
  Sequence,
  staticFile,
} from "remotion";
import timing from "../timing.json";
import { Captions } from "./Captions";
import { Shot01 } from "./shots/Shot01";
import { Shot02 } from "./shots/Shot02";
// ...one import per shot

const SHOT_COMPONENTS: Record<string, React.FC> = {
  shot01: Shot01,
  shot02: Shot02,
  // ...
};

const Main: React.FC = () => (
  <AbsoluteFill style={{ backgroundColor: "#0F1419" }}>
    <Audio src={staticFile("audio.mp3")} />
    {timing.shots.map((shot) => {
      const Component = SHOT_COMPONENTS[shot.id];
      return (
        <Sequence
          key={shot.id}
          from={shot.start_frame}
          durationInFrames={shot.end_frame - shot.start_frame}
        >
          <Component />
        </Sequence>
      );
    })}
    <Captions />
  </AbsoluteFill>
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

Hard rules:

- `Sequence from` must equal `timing.shots[i].start_frame`. Never a
  literal number.
- `durationInFrames` on the `Composition` must equal `timing.total_frames`.
- `fps` must equal `timing.fps`.
- One `<Audio>` mounted at the top of `Main`.
- `<Captions />` mounted **last** (so it overlays everything else).
- Background color on the AbsoluteFill so any frame between shots is
  not pure black.

## Workflow

1. Read `timing.json` to get the shot list, fps, total_frames.
2. Glob `src/shots/Shot*.tsx` to confirm every shot in `timing.shots`
   has a file. If any are missing, stop and report which ones.
3. Write `src/Root.tsx` following the contract above.
4. Run `npx vitest run alignment.test.ts`. If it fails, read the output,
   identify which anchor is off, and **stop** — report the failing
   anchor id. Do not edit shot components to make the test pass; that
   is the shot agent's responsibility on the next iteration.
5. If the alignment test passes, run `npx remotion render`.
6. If the render succeeds, you're done. Print the output path.
7. Stop.

## What NOT to do

- Do not modify shot components.
- Do not modify `Captions.tsx`. It is generated; the captions layer is
  not negotiable.
- Do not touch `timing.json`, `script.json`, `public/audio.mp3`, or
  `alignment.test.ts`.
- Do not declare new anchors or shots. The set is frozen after Phase A.
- Do not render text in `Root.tsx` other than mounting the components
  and the captions overlay. No header, no title card, nothing else.
