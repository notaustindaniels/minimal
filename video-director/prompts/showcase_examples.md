# Remotion Prompt Showcase — All Prompts

Scraped from [remotion.dev/prompts](https://www.remotion.dev/prompts) and [remotion.dev/prompts/2](https://www.remotion.dev/prompts/2).

---

## 1. News Article Headline Highlight
**Author:** @Remotion · **Tool:** Claude Code · **Model:** Opus 4.5 · **Votes:** 157

```
use remotion best practices. import the following image into the project: '~/Desktop/Screenshot 2026-01-31 at 17.15.12.png' use tesseract CLI to do OCR and find the positions of the text. in remotion, make a new composition where you load the image and pad the article generously on a white full HD background. while the composition is running for 5 seconds, slowly, very subtly, zoom into it and slightly rotate the article in 3d from left to right. the overall rotation should be around 15deg for each axis. at the beginning, blur the whole composition and unblur it over 1 second. after the blur is done, evolve a highlighter from left to right using rough.js over the words "government shutdown" and "funding lapses". the image has a white background. make sure the the marker appears behind the text. when installing new dependencies, check for existing lockfiles and use the right package manager.
```

---

## 2. Travel Route on Map with 3D Landmarks
**Author:** @JNYBGR · **Tool:** Claude Code · **Model:** Opus 4.5 · **Votes:** 151

```
use remotion best practices. make a new composition and add a map and zoom out of LA while staying focused on it. once done, animate a line from LA to NY and make the camera follow it.

add another stop to the trip, this time we go to paris. animate the eiffel tower and show it in 3D!
```

---

## 3. Product Demo for Presscut
**Author:** @Shpigford · **Tool:** Claude Code · **Model:** Claude Opus 4.5 · **Votes:** 112

```
Create a demo video of the Presscut app/product using remotion. Use react componenents to replicate VI elements and replicate the UI of the app as closely as possible. The app has a LOT of features/ functionality, so take guidance from the marketing home page/index for what to highlight, while keeping language simple and to-thepoint. Really grill me with questions to nail down exactly how the final video should look/feel and what content should be there. The ultimate goal of this is to replicate what me, the founder, would be showing/doing with a product demo with a customer.
```

---

## 4. Launch Video on X (OpenClawd)
**Author:** @ghumare64 · **Tool:** Claude Code · **Model:** Opus 4.6 · **Votes:** 108

```
Create a Remotion video (1080x700, 30fps, ~37s) for OpenClawd — an open source AI desktop agent. Dark theme (#0c0a09
  background, #fbbf24 amber accent). Background music: "Walen - HEADPHONK" with 1s fade-in and 2s fade-out at 40% volume. 8
  scenes in series:

  Scene 1 — Terminal Install (120 frames / 4s)
  Mac-style terminal window with traffic light dots. Types npx openclawd-cli character by character (1 frame/char). After
  typing, shows ASCII art logo "OPENCLAWD" in amber, then server output lines appearing progressively: version banner, SDK
  backends, 20+ providers/80+ models loaded, model names (Opus 4.6, GPT-5.3, Gemini 3, etc.), MCP servers connected, "Opening
  desktop app on :3001". Terminal slides in from bottom with 3D perspective (rotateX 20deg, slight rotateY oscillation).

  Scene 2 — Home Screen (150 frames / 5s)
  Desktop app window with centered "OpenClawd" title (Georgia serif), tagline "Open Source Alternative to Claude Cowork",
  rounded chat input with send button, and provider/model selector chips (Claude Code + Opus 4.6 + Attach). Spring-animated
  fade-in with staggered delays (title → tagline → input → controls).

  Scene 3 — Chat Interface (160 frames / 5.3s)
  Three-column layout: left sidebar with chat history (MCP Integration, Code Review, etc.), center with user message "Review my
   API code" and streaming assistant response about security findings (rate limiting, SQL injection, input validation), right
  panel showing progress steps (Reading → Security analysis → Applying fixes → Creating PR) and tool calls (filesystem.read,
  bash.exec, github.create_pr) with green checkmarks.

  Scene 4 — Provider Switch (130 frames / 4.3s)
  Two dropdown panels side by side. Left: 8 providers (Claude Code, OpenCode, OpenAI, Gemini, DeepSeek, Llama 4, MiniMax,
  Ollama) with colored dots and selection indicator. Right: 7 models (Opus 4.6, Sonnet 4.5, GPT-5.3 Codex, etc.) with
  descriptions. Bottom tagline: "Claude Code + OpenCode SDK — 20+ providers · Open Source models". Staggered item reveals.

  Scene 5 — MCP Catalog (140 frames / 4.7s)
  Modal overlay with "MCP Server Catalog — 20+ servers available". Category filter pills (All, Core, Database, Developer,
  Communication). 6 server cards with icons: Filesystem, Git, GitHub (installed), PostgreSQL, Slack, Puppeteer. Auth badges
  (green "No Auth" / amber "Requires Auth"). Install/Installed buttons with checkmarks.

  Scene 6 — Messaging Bots (120 frames / 4s)
  Full-screen "Your AI, everywhere you chat" with subtitle "Full tool access · Memory · Scheduling". 4 platform cards
  (WhatsApp, Telegram, Signal, iMessage) with SVG icons, green "Connected" status dots, and feature tags (Memory, Scheduling,
  Tools). Cards scale up with spring animation.

  Scene 7 — Logo Combo (180 frames / 6s)
  Three sub-scenes: (a) Intro with converging amber lines, center burst ring, floating particles, grid background. (b) "✦
  Introducing ✦" with word-by-word reveal: "Open Source AI Desktop" in 56px white text, model names below in gray monospace.
  (c) 8 provider icons in two rows with colored dots and labels, tagline "Claude Code + OpenCode SDK · 80+ models | Desktop ·
  Messaging · API".

  Scene 8 — GitHub CTA (120 frames / 4s)
  "100% OPEN SOURCE" label, spinning GitHub logo (rotates in from -180deg), orbiting amber star icons, "Star us on GitHub" in
  36px white, pulsing scale animation, "github.com/rohitg00/openclawd" in monospace with dark card background. Floating
  particles and subtle grid.

  All transitions use spring animations with fade + scale (0.95→1 in, 1→0.95 out). Each scene inside an AppWindow component
  (mac chrome with traffic lights). Color palette: #0c0a09 bg, #1c1917 surfaces, #292524 borders, #fbbf24 amber accent, #fafaf9
   white text, #a8a29e muted text, #78716c dim text. Fonts: Inter for UI, SF Mono for code, Georgia for branding.
```

---

## 5. Rocket Launches Timeline
**Author:** @crispynotfound · **Votes:** 75

```
Animate every SpaceX rocket launch from 2015–2025 in chronological order. Show the launch parabolas with trajectory fading. Use an abstract, minimalist aesthetic. Give me three versions first, then I'll pick one and refine it via feedback.
```

---

## 6. Transparent Call-To-Action Overlay
**Author:** @Remotion · **Tool:** Claude Code · **Model:** Opus 4.5 · **Votes:** 63

```
use remotion best practices. this is our youtube channel: https://www.youtube.com/@remotion_dev. use curl scrape youtube to find the avatar and the subscriber count. multiple subscriber counts appear on the page, find the right one. make a white lower third that slides in from the bottom center. show the name, subscriber count and avatar.  display a typical fixed width black youtube subscribe button that changes from "Subscribe" to "Subscribed". use a ease-out animation and for pressing in the button and a spring animation with a slight bounce once the button is released. fade out the lower third. render it as a transparent prores video.
```

---

## 7. Cinematic Tech Intro (Jensen Huang)
**Author:** @tiw_ari_ayu · **Tool:** Gemini · **Model:** k2.5 · **Votes:** 56

```
Create a high-energy Remotion video component (1920x1080, 30fps) for a cinematic "CEO Introduction" featuring Jensen Huang, styled with a Cyberpunk/Tech-Corporate aesthetic. The scene should use a clean white background with a subtle radial noise texture and feature masssive, centered "JENSEN HUANG" text in the "Knewave" font (NVIDIA Green #76B900) that animates with a dramatic "pop-in" effect (scaling down from 3x to 1x). At frame 40, introduce a cutout image of Jensen on the right side with an explosive spring entrance, continuous floating motion, and occasional digital glitch distortion (skew/hue-rotate), layered above rotating dashed tech rings and falling Matrix-style data streams. Simultaneously, slide in a Glassmorphism HUD panel from the left (dark semi-transparent green with a cut-corner clip-path) that displays "CEO & Co-Founder" and bio details using a Monospace font; ensure the text slides in from the far left (-600px) for a dynamic reveal. Enhance the visual depth with a vertical green scanner line, animated corner brackets, and floating geometric particles (triangles/hexagons), using spring and interpolate for all smooth physics-based transitions.
```

---

## 8. Three.js "Top 20 Games Sold" Ranking
**Author:** @DilumSanjaya · **Tool:** Claude Code · **Votes:** 46

```
here is an empty remotion project with the default react three fiber example.

I want to create a 3D video to visualize top 20 videos games by copies of all time.Create a Remotion video that visualizes the top 20 best-selling video games as a vertical "tower", use boxes as towers with height representing the amount of copies.

remove the default example from this project and create a remotion + react three fiber example to do this visualization.
Resolution: 1920x1080
FPS:60

animate the camera from the bottom of the last rank to the top of the first rank. stop the camera on the top of each rank for a few miliseconds.

here is the game ranking data you need

# [data as a JSON string]
# More instructions: https://x.com/DilumSanjaya/status/2018367621381620142
```

---

## 9. Real Estate Investing
**Author:** HarisShah2345 · **Tool:** Claude Code · **Model:** Opus 4.5 · **Votes:** 34

```
You are a high-end real estate video editor, motion graphics designer, and short-form content strategist.

I will upload a raw real estate video.

Your task is to transform it into a 15–30 second professional cash cow style video optimized for high retention, authority, and engagement.

The final output must include:

Cinematic real estate motion graphics
Premium typography
Dynamic transitions
Strategic pacing
Background music
Subtle but powerful branding elements

🔹 PROMPT 1 — VIDEO ANALYSIS
Analyze the uploaded video and:
Identify key visual highlights (luxury interiors, exterior shots, amenities, skyline, etc.)
Detect weak or slow sections and suggest trims
Break the video into strong 1–3 second micro-scenes
Suggest the ideal final duration (15–30 seconds max)
Provide a timestamp breakdown before editing.

🔹 PROMPT 2 — STRUCTURED TIMELINE EDIT PLAN
Create a second-by-second timeline plan:
For each timestamp include:
Scene description
Motion effect (zoom in, parallax, speed ramp, pan, drone enhancement)
Transition style (whip, smooth zoom, fade through black, motion blur)
On-screen text (if applicable)
Text animation style
Keep pacing fast, premium, and cinematic.

🔹 PROMPT 3 — REAL ESTATE MOTION GRAPHICS PACKAGE
Add professional real estate motion graphics such as:
Property price reveal animation
Location lower-third with animated map pin
Bedroom/Bath/Sqft animated icon counters
"For Sale" / "Just Listed" / "Luxury Living" animated title
Subtle blueprint grid overlay (low opacity)
Animated frame lines or corner brackets
Design style: Clean, Minimal, Premium, Corporate luxury
Color palette: Black + Gold (luxury) OR White + Navy (corporate)

🔹 PROMPT 4 — TYPOGRAPHY & TEXT STYLE
Use high-end real estate fonts:
Headline font: Modern serif or bold sans-serif
Subtext font: Clean minimal sans-serif
Text animation style: Smooth fade + slide, Mask reveal, Word-by-word emphasis for hooks
Include: Subtle text shadow, Light glow or stroke, Clean spacing

🔹 PROMPT 5 — CINEMATIC ENHANCEMENTS
Add: Light leaks (subtle), Cinematic color grading (warm highlights, rich shadows), Slight film grain, Slow zoom on still frames, Ambient luxury background sound design
Background music: Deep house / cinematic corporate / luxury instrumental
Beat drop aligned with best visual moment
Audio balanced professionally

🔹 PROMPT 6 — RETENTION OPTIMIZATION
Improve engagement by:
Strong hook in first 2 seconds
Pattern interrupt at 5–7 seconds
Slight speed ramp during highlight scene
Ending with: Loop-style cut OR Strong CTA ("Book a private tour today")

🔹 PROMPT 7 — FINAL EXPORT SETTINGS
Optimize for: TikTok / Reels / Shorts, 9:16 vertical format, 1080x1920, Sharp compression, Loud but clean audio
Ensure: No clutter, Professional spacing, High-end real estate brand feel
Deliver output as: Step-by-step editing guide, Timestamp structured, Ready-to-execute professional instructions
```

---

## 10. Shape to Words Transformation
**Author:** @tiw_ari_ayu · **Tool:** Gemini · **Model:** k2.5 · **Votes:** 31

```
Create a premium 10-second motion graphics intro using Remotion and React.

Background: Clean white canvas with a subtle light-gray grid pattern.

Sequence of Events:

Scene 1 (The Setup): precise row of 8 colorful, filled geometric shapes (Pentagon, Triangle, Square, Circle, Hexagon, Diamond, Circle, Triangle) centered on screen with even spacing (90px). They should have a gentle, organic "breathing" idle animation.
Scene 2 (The Morph): Trigger a dynamic sequence where the shapes jump up, spin 180 degrees in mid-air, and smoothly morph (using flubber) into the bold block letters "R-E-M-O-T-I-O-N". Add a ghost-trail effect behind them during the jump for speed.
Scene 3 (The Arrival): Fly in the Remotion Logo from the left side to hover near the 'R'. Have it snap into place with a spring animation and immediately perform a full 360-degree rotation.
Scene 4 (The Wipe): Execute a slow, cinematic exit. The logo should slide smoothly across the entire screen from left to right. Implement a "Wipe Logic" where each letter of "REMOTION" vanishes (scales down/fades out) exactly in sync as the logo passes over it, creating an erasing effect.
Technical Requirements: Use remotion springs for all physics (damping: 14 for jumps, damping: 300 for the slow wipe). No strokes on shapes, only filled vibrant colors.
```

---

## 11. Bar + Line Chart (Combined)
**Author:** samohovets · **Tool:** OpenCode · **Model:** Opus 4.5 · **Votes:** 31

```
Create a 1920x1080 dark-themed (#1A1A2E) composition called 'BarLineChart' with a combination chart showing monthly sales data — bars for revenue ($8K, $12K, $15K, $11K, $18K, $22K for Jan-Jun) that grow upward from the baseline, overlaid with a blue (#0B84F3) line tracking conversion rate (2.1%, 2.8%, 3.2%, 2.9%, 3.8%, 4.2%) that draws progressively with a glowing effect, bars animate sequentially with slight overlap while the line follows behind, include axis labels and a pulsing dot marker at the line tip, smooth spring-based timing over 120 frames at 30fps — use remotion-best-practices skill.
```

---

## 12. Promotion Video for VVTerm
**Author:** @wiedymi · **Tool:** Claude Code · **Model:** Opus 4.5 · **Votes:** 29

```
Make a promotion video in Apple presentation style for VVTerm. Check its website VVTerm.com for details and assets like logo. Use nerd fonts and inter. Make it around 20 seconds.
```

---

## 13. Cursor Agent Skills Announcement
**Author:** @edwinarbus · **Tool:** Cursor · **Votes:** 19

```
Create a video project announcing Agent Skills, following Cursor brand rules. 1920×1080, 60fps. Typewriter text effect at about 1 character per frame, then hold for 3 seconds after typing on every title card. Line 1 types first, then line 2.

Card 1: "Agent Skills are now available" on line 1 and "in Cursor" on line 2
Card 2: "Skills let agents discover and run" and line 2 "specialized prompts and code."
Then play the skills.mp4 recording full-screen, framed top-aligned for first 2 seconds, then zoom in (with easing) to the top-left by about 125%. Should be continuous zoom!
Final card: "This video was made entirely in Cursor" on line 1 and "with Remotion skills." on line 2, then hold;
End with the existing end.mp4 animation full-screen.

Render and open the file inside Cursor's browser tool to let me see it here!

# Notes:
# 1. Uses an existing screen recording @ericzakariasson made.
# 2. Uses our existing end card animation.
# 3. Had a Cursor rule with our brand guidelines and colors.
```

---

## 14. Strava Run Visualized
**Author:** @JNYBGR · **Tool:** Claude Code · **Model:** Opus 4.5 · **Votes:** 18

```
[download GPX from strava website]

use remotion best practices. turn my run today into an animated instagram story: ~/Downloads/Afternoon_Run.gpx

show a map, the route and live metrics for my run. use font sizes that will be legible when user watches as a story
```

---

## 15. Spinning, Glitching SVG Logo Turned 3D
**Author:** @Remotion · **Tool:** Claude Code · **Model:** Opus 4.5 · **Votes:** 15

*(Multi-turn conversation prompt)*

```
use remotion best practices. create a new composition with the following SVG in 3D. add a metallic material to it: <svg width="988" height="317" viewBox="0 0 988 317" fill="none" xmlns="http://www.w3.org/2000/svg">
[... full REMOTION SVG path data ...]
</svg>

make it smaller and more silver

it still is pretty dark. change the material and lighting to make it much more silver and bright

ok, now it is completely white. find a middle ground so it still is a bit metallic

right now you can see the backside of the logo. make it rotate only from -90 to 90 degree and then start over at -90

add the following glitch effect to it: https://react-postprocessing.docs.pmnd.rs/effects/glitch

yes please, please make everything deterministic

export this as a transparent video i can use in after effects

did not work, check the docs: https://www.remotion.dev/docs/transparent-videos/
```

---

## 16. 3D Retro Pixel Font
**Author:** @GogHeng · **Tool:** Claude Code · **Model:** Opus 4.6 · **Votes:** 13

```
use remotion skills Create a 1080×1080 brand animation video, 8 seconds, black background.                                                              
                                                                                                                                    
  Core effect: Pixel block text-building animation. 4 colored cursors (purple, blue, pink, indigo) fly in from off-screen, scatter to 
  four corners, line up on the left side, then each cursor "builds" its assigned section of pixel text — blocks light up one by one as
   the cursor passes over them, like multiple people collaboratively editing code in real-time.                                       
                                                                                                                                    
  Text: Line 1 "SHILIU", Line 2 "VIBEKNOW" 

  Block style: 20px squares with 3D layered depth effect — dark purple base with concentric inset borders creating an
  embossed/recessed look.

  Timeline:
  - 0–0.4s: First cursor enters from top-left
  - 0.4–0.9s: 4 cursors scatter to different positions
  - 0.9–1.6s: Cursors line up on the left side
  - 1.6–5.0s: Cursors split up and build the pixel text simultaneously
  - 5.0–5.8s: Subtitle "coming soon" types in at the bottom
  - 5.5–8.0s: Cursors float away to the top, gently bobbing

  Color variant: Red edition (replace purple block palette with red tones)
```

---

## 17. History
**Author:** Shiam56 · **Model:** Opus 4.5 · **Votes:** 12

```
Create a 1920x1080 dark-themed (#1A1A2E) composition called 'BarLineChart' with a combination chart showing monthly sales data — bars for revenue ($8K, $12K, $15K, $11K, $18K, $22K for Jan-Jun) that grow upward from the baseline, overlaid with a blue (#0B84F3) line tracking conversion rate (2.1%, 2.8%, 3.2%, 2.9%, 3.8%, 4.2%) that draws progressively with a glowing effect, bars animate sequentially with slight overlap while the line follows behind, include axis labels and a pulsing dot marker at the line tip, smooth spring-based timing over 120 frames at 30fps — use remotion-best-practices skill.
```

*(Note: This page appears to share the same prompt as "Bar + Line Chart (combined)" but includes the full generated code output as well.)*

---

## 18. The Kinetic Marketing
**Author:** @tiw_ari_ayu · **Tool:** Gemini · **Model:** k2.5 · **Votes:** 8

```
A high-velocity kinetic typography promo for a modern developer tool.

Visual Style: Premium "Aurora Glassmorphism" aesthetic. Backgrounds are seamless, breathing radial gradients in Pastel Pink, Lavender, and Soft Blue. Key Elements: Dozens of 3D Floating React Logos drift through the scene with heavy depth-of-field blur. Rotating dashed "Radar Rings" and "Pulse Circles" add technical texture behind the text. Color Palette: Electric Azure Blue (#0b84f3) for primary accents against Deep Black bold typography (Poppins Black). Motion Physics: Elastic "Layout Smoothing" – new words crash in and physically push existing text aside. Transitions: Elements rotate -15° and shrink to zero to vanish. Scenes switch via massive Blue Iris Wipes and Ring Tunnels. Matches a 140 BPM fast-paced beat.
```

---

## 19. Audio Spectrum Visualizer
**Author:** samohovets · **Votes:** 8

```
Create a 1920x1080 dark-themed composition called 'AudioSpectrum' featuring an audio spectrum visualizer synced to funk.mp3 from the public folder, displaying 32 vertical frequency bars that bounce and pulse reactively to the bass, mids, and highs, with a vibrant gradient from magenta to cyan across the bars, each bar having a subtle glow effect and smooth rounded tops, the bars reflecting faintly on a glossy dark surface below, centered horizontally with gentle horizontal padding, the whole visualization fading in smoothly at the start, duration matching the full audio length at 30fps — allow changing the bar count, gradient colors, bar width, and glow intensity — use remotion-best-practices skill.
```

---

## 20. BMS Active Cell Balancing Animation — 8S1P Pack with Energy Flow Visualization
**Author:** pasrom · **Tool:** Claude Code · **Model:** Opus 4.6 · **Votes:** 6

```
Create a Remotion project that renders a BMS Active Cell Balancing animation. 10 seconds, 30fps, 1280x720, output as MP4.                                                                                   
                                         
  Setup:                                                                                                                                                                                                      
  mkdir remotion-bms && cd remotion-bms                                                                                                                                                                       
  npm init -y                                                                                                                                                                                                 
  npm i remotion react react-dom                            
  npm i -D @remotion/cli typescript
  tsconfig.json: ES2022, jsx: react-jsx, moduleResolution: bundler, module: ESNext

  Project structure: src/index.ts, src/Root.tsx, src/BmsCellBalancing.tsx

  Animation (BmsCellBalancing.tsx):
  8 cells (8S1P) in a pack, dark theme (#0b1120), Courier New font. Initial voltages unbalanced between 3.3V and 4.05V. Background with subtle grid lines.

  Phases (at 300 frames total):
  - Frame 0..60: IDLE, show unbalanced cells
  - Frame 60..90: MEASURING CELLS... (yellow status dot)
  - Frame 90..240: BALANCING (green pulsing dot), voltages converge via smoothstep to average
  - Frame 240..300: BALANCED (blue)

  Each cell shows:
  - Color-coded SOC fill level (green when high, orange when medium, red when low) with gradient
  - Terminal nub on top, bus bars top/bottom connecting all cells
  - Voltage display (3 decimal places), cell label (C1..C8), SOC in %, temperature
  - During balancing: green border + arrow down for cells below avg (Charging), orange border + arrow up for cells above avg (Discharging)
  - Particle animation visualizing energy flow
  - Shimmer effect on the fill level

  Info panel at bottom with spring animation: Pack Voltage, Max Delta (color-coded: green below 10mV, orange below 50mV, red above), Avg Cell, Config (8S1P), Pack SOC, Method: Active

  Legend at bottom: "▲ Discharging (high cell)" orange, "▼ Charging (low cell)" green

  Render: npx remotion render src/index.ts BmsCellBalancing out/bms-cell-balancing.mp4
```