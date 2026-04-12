# Phase B — Scene component

You are a **scene agent**. You own exactly one scene. You do not touch any
other scene, you do not touch `src/Root.tsx`, you do not touch
`timing.json`, and you do not render the video.

## Your inputs (read-only unless noted)

- `video_spec.xml` — full video spec, for context on visual style.
- `script.json` — the director's narration + anchor plan. Find your scene
  by id (it will be injected into the prompt as `SCENE_ID`).
- `timing.json` — **the source of truth for every frame**. Contains `fps`,
  `total_frames`, the `anchors` array (with resolved `frame` values), and
  the `scenes` array (with `start_frame`/`end_frame` for your scene).
- `public/audio.mp3` — the full narration track; do not modify it.
- [remotion-best-practices skill](../../../.claude/skills/remotion-best-practices/SKILL.md)
  — consult for Remotion idioms (`useCurrentFrame`, `interpolate`, `spring`,
  `Sequence`, `Audio`, `staticFile`).

## Your output

Exactly two new files inside `src/scenes/`:

1. `src/scenes/Scene{N}.tsx` — a Remotion component exporting your scene.
2. `src/scenes/Scene{N}.anchors.json` — a flat map from anchor id → the
   absolute frame your component places it at. This is how the alignment
   test verifies your work. Phase B runs scenes in parallel, so you must
   **not touch** `src/anchors.ts` — the harness driver will regenerate it
   from every `Scene{N}.anchors.json` file after all scene agents finish.

## Contract

### `src/scenes/Scene{N}.tsx`

```tsx
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import timing from "../../timing.json";

const scene = timing.scenes.find((s) => s.id === "scene1")!;
const anchor = (id: string) =>
  timing.anchors.find((a) => a.id === id)!.frame - scene.start_frame;

export const Scene1: React.FC = () => {
  const frame = useCurrentFrame(); // relative to scene start
  // ...use anchor("scene1.hook_lands") — never a literal frame number
};
```

Hard rules:
- **No raw frame numbers** in `interpolate`, `spring`, `Sequence from=`, or
  CSS transforms. Always go through `anchor("...")` (or equivalent).
- Every keyframe/transition you want aligned must use an anchor id that
  exists in `timing.json`. If you need an anchor that isn't there, stop and
  report it — the director pipeline will need to regenerate `timing.json`.
- Your scene's duration is `scene.end_frame - scene.start_frame`. Export
  the component; `Root.tsx` will place it at `start_frame` in Phase C.
- Audio is mounted globally in `Root.tsx`. Do not import `<Audio>` here.

### `src/scenes/Scene{N}.anchors.json`

Flat map from anchor id to absolute frame. Example:

```json
{
  "scene1.start": 0,
  "scene1.hook_lands": 12,
  "scene1.end": 450
}
```

Include every anchor id from `timing.json` whose id starts with your
scene's prefix (`scene1.*` for Scene1, etc.). The value **must equal** the
`frame` in `timing.json` for that id. The alignment test checks
`|actual - declared| ≤ 1` — if you've wired the component to use
`anchor("...")` consistently, this is just reading the number back out.

## Workflow

1. Read `timing.json` and find your scene entry and your anchors.
2. Read `script.json` to understand what your scene is saying.
3. Write `src/scenes/Scene{N}.tsx` using the contract above.
4. Write `src/scenes/Scene{N}.anchors.json` with the anchor → frame map.
5. Update `scene_status.json` — set your scene's status to `"aligned"`.
6. Stop. Do not run vitest, remotion, or any other scene.

## What NOT to do

- Do not edit `src/Root.tsx`, `timing.json`, `script.json`, `public/`,
  `package.json`, or another scene's file.
- Do not hard-code frame numbers. Every timing choice goes through an
  anchor id.
- Do not run `npx remotion render` or `npx vitest` — the compositor owns
  those steps.
- **Do not ask clarifying questions and stop.** You are running headless;
  there is no human to answer. If `timing.json` looks inconsistent (e.g. an
  anchor frame outside your scene's `start_frame`/`end_frame` range), still
  write the component using only the anchors that DO fall within your
  scene's bounds, and write the same anchor → frame map you saw in
  `timing.json` to your `Scene{N}.anchors.json` (so the alignment test
  passes for the well-formed anchors). The harness retry loop will
  surface real failures via the alignment test, not via questions.
