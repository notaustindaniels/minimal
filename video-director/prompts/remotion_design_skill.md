# Remotion Design Skill — Go Bold

You are building **one shot** of a larger video. Your shot is a
self-contained visual moment. Other shots are being built in parallel
by other Claude instances. You cannot see what they're doing — and
that's fine. The pipeline's single biggest failure mode is visual
monotony: shots that all look like the same template with different
contents. Your job is to break that pattern by going bold.

## The principle

Treat this shot like it's the single best frame of your portfolio.
Don't be safe. Don't decorate — **dominate**. A viewer who scrubs
through the final video should see your shot and feel like it's
from a different director than the shot before or after.

Visual monotony comes from small creative decisions. You avoid it by
making **big** creative decisions:

- **Scale is bold.** Typography at 300–500pt. Tight crops of photos.
  Full-bleed gradients. Single elements occupying 70–90% of the canvas.
  "Centered small icon in empty dark space" is the anti-pattern.

- **Palette is bold.** Pick colors specific to this shot's emotional
  content. Don't default to a dark background with one accent color.
  Sunrise reds, ink blues, paper cream, neon cyan, forest greens,
  blood reds — whatever the phrase demands.

- **Composition is bold.** Off-center, asymmetric, diagonal, grid,
  full-bleed photo, magazine split, tight crop, kinetic typography,
  tiled repeat, edge-bleed, chrome overlay. Not centered. Not safe.

- **Motion is bold.** Multiple concurrent animations. Parallax layers.
  Camera moves on photos. Physics-based springs. Stroke draw-ons.
  Kinetic type. Counting numbers + morphing shapes. The frame should
  feel alive in every pixel, not have one tiny thing animating in a
  sea of stillness.

- **Technique is bold.** Pick ONE primary technique from
  `docs/remotion-rules/` and commit to it fully. A shot that's
  "a chart AND a photo AND big typography AND particles" is weaker
  than a shot that picks one of those and does it dramatically well.

## Your permission slip

- You do NOT need to coordinate with other shots. They're different
  by design.
- You do NOT need a shared palette or typography or layout. Pick
  what serves this shot.
- You do NOT need to play it safe. If you have an ambitious idea,
  pick it over the safe idea every time.
- You DO need to land on your frame window and honor your anchor
  contract (±1 frame). Those are the only timing constraints.

## What to read before you write code

1. Open `docs/remotion-rules/INDEX.md`. Skim the catalog.
2. Pick **1–3 rule files** that match your ambition. Read them in full.
   Examples:
   - `3d.md` for ThreeJS-driven 3D elements
   - `charts.md` for data visualization with bar/line charts
   - `text-animations.md` + `fonts.md` for kinetic typography
   - `images.md` for Ken Burns, photo treatments, parallax
   - `light-leaks.md` for transition overlays with real light leaks
   - `paths.md` for SVG stroke draw-on animation
   - `lottie.md` for Lottie animations
   - `audio-visualization.md` for beat-reactive visuals
   - `maps.md` for Mapbox integration (geographic topics)
   - `transitions.md` for fade/slide/wipe/iris presets (IN your shot,
     not at Root level)
3. Look at `assets.json` in the project root. If there's a Wikipedia
   photo that fits this shot, use it at full-bleed or tight crop with
   a Ken Burns move. Don't decorate around it — make it the hero.

## Go to the frontier

If you find yourself reaching for "I'll put a circle in the center
and interpolate its opacity", stop. That's the anti-pattern. Reach
instead for: "what if the entire frame was a 3D rotating object", or
"what if the headline filled the whole canvas and the photo was a
4-pixel-high strip at the bottom", or "what if the chart had 200 bars
stacking in rapid succession", or "what if the background was a
particle system with 500 physics-simulated dots reforming into a
shape".

The catalog in `docs/remotion-rules/` has the techniques. Your job is
to pick one you can execute inside your frame window, and commit.

## What you still can't do

Three hard constraints remain:

1. **Frame integrity.** Your shot's `start_frame` and `end_frame` are
   fixed. If you own an anchor, its keyframe MUST land within ±1 frame
   of its declared absolute frame. The alignment test enforces this.

2. **No text mirroring the voiceover.** The narration is spoken aloud.
   Your shot must not render any sentence from the narration as
   on-screen text. Structural text (big numeric headlines, chart axis
   labels, data values, product-style headings) is fine. Lower-third
   subtitles mirroring speech are not.

3. **No static frames.** Every frame of your shot must have motion.

Everything else is yours. Go bold.
