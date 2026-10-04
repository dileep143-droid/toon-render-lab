# Kulfi Kahani episode factory — handoff (updated 4 Oct 2026, 18:45 IST)

Goal: Hindi kids episodes (Sonpur cast: Dadi, Chhotu, Gudiya, Pinky, Raju, Bablu, Lallan, Masterji, Bhootu, Chamki the goat, Sheru the dog)
in the "kathala bandi" look (clean vector cutouts on painted sets, limited animation, drawn mouth states), made end-to-end on
GitHub Actions + Kaggle + Google Vertex. The owner reviews a PRIVATE YouTube upload and says "accepted" before anything goes public.

## Control room (owner's phone): https://kulfi-control.pages.dev
Tabs: Runs (start/watch/cancel workflows), Videos (renders in Kaggle dataset sonpur-renders, private YouTube upload, make public),
Chat (Gemini with tools), Ask Claude (THIS agent: requests arrive in control/INBOX.md, reports go to control/OUTBOX.md), Notes, Settings
(accounts + keys live in Cloudflare KV; nothing on the laptop). The cloud agent starts workflows by committing control/RUN.json
({"workflow":"episode2d.yml","inputs":{...},"note":"..."}); .github/workflows/control_run.yml dispatches it.

## Pipeline per episode (ep01 = the laddoo story; ep02..ep20 scripts exist on the owner's laptop, not yet in the repo)
1. Art (Vertex, keyless WIF, ~₹350/episode): workflow `vertex_assets.yml` (inputs ep, only=masters,poses,mouths,plates,props) or locally
   `python vertex_gen.py out/<ep>/plan.json out/series.json <artdir> --only ...` — 5 parallel lanes (regions/models), reference-image
   consistency (no LoRA). Animals are drawn four-legged; props must have no faces; walk cycles are extra drawings `<char>__walk_N.png`.
2. Cutouts: `python vertex_to_keys.py <artdir> out/<ep>/plan.json out/keys out/<ep>/keys_selection.json --assets out/<ep>/assets`
   (fixed-range flood fill; halo rule skipped for mostly-white figures).
3. Mouths: `python vertex_mouths.py <artdir> out/keys out/<ep>/keys_selection.json` (Gemini half/open edits → patches; mouth width clamped to 7–16% of figure width).
4. Gate: `python gate_coverage.py <ep>` must print GATE 1 OK (every pose/plate/prop/mouth covered; no fallback to old puppets).
5. Bundle: `python make_bundle.py <ep> --key 1` → private Kaggle dataset mani7673/sonpur-2d-<ep> (300 MB).
6. Render: workflow `episode2d.yml` (ep, name, units "" or a:b, mouth_patches=1, draw_mouth=0) → mp4 in Kaggle dataset sonpur-renders (~20 min).
7. QA: `python qa_shots.py <ep> <mp4> <dir>` → one frame per shot, 6 sheets; check props in style, no halos, mouths moving, no warped faces.
8. Owner review → upload PRIVATE (Videos tab) → owner accepts → public.

## State on 4 Oct evening
- ep01 renders: ep01_vertex_full2.mp4 (props/halo/sari fixed; 3 shots had an oversized mouth patch on Chhotu) → fix applied, ep01_vertex_full3 rendering.
- NOT built yet: TTS step on GitHub (ep01 audio exists; design = two voices Gacrux/Puck, episodes/voice_cast.json, 11 free Gemini keys as lanes,
  then split_full.py + Rhubarb which still use Windows paths), automatic gates 2–4 (consistency score + auto-redraw, cutout check, VLM judge),
  the daily timer. Episode 2+ needs: script → plan.json (plan.py) → audio → steps 1–8.
- Google: Vertex project project-5ab72bd2-b72e-41ff-a08 (₹28.8k credit, 90 days); API keys are forbidden there, WIF only.
- Rules from the owner: props and mouths drawn in the series style (never pasted shapes), locked cameras, readable faces, every beat checked
  against the script before sending, nothing public without "accepted".
