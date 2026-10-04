# Vertex episode factory — handoff (4 Oct 2026)

Goal: Kulfi Kahani episodes in the "kathala bandi" look (clean vector cutouts on painted sets, limited animation),
made end-to-end on GitHub Actions + Vertex AI (Google trial credit, project `project-5ab72bd2-b72e-41ff-a08`,
owner mounikagoddu12345@gmail.com) with NO API keys (org policy forbids them): GitHub OIDC -> Workload Identity
Federation -> service account `toon-render@project-5ab72bd2-b72e-41ff-a08.iam.gserviceaccount.com` (roles/aiplatform.user).
Provider: `projects/830634294242/locations/global/workloadIdentityPools/github/providers/github` (repo-restricted).

## Pieces (all in pipeline2d/)
| step | file | status |
|---|---|---|
| art: masters, poses (reference-image consistency, no LoRA), plates, props | `vertex_gen.py`, workflow `.github/workflows/vertex_assets.yml` | WORKING (Dadi master + 9 poses tested 4 Oct; one colour drift: sit_cross came out pink) |
| convert art -> key drawings for compose.py | `vertex_to_keys.py` (flood-fill matte from the border, keeps white clothes; names actions via keyactor.POSE2KEY) | WORKING locally |
| mouth position | keyactor.mouth_pts (YuNet) auto-detects on each rgba.png; cache out/keys/mouth_pts.json | untested on Vertex art |
| voices with emotion | Vertex TTS `gemini-2.5-flash-preview-tts` / `gemini-3.8-flash-tts` (style prompt per line, Hindi) | NOT WIRED (ep01 used the old TTS -> out/ep01/mix.wav) |
| compose (mouth flaps, blinks, pans, props, MCU) | `compose.py` + `render_parallel.py`, workflow `episode2d.yml` (Kaggle private dataset in/out) | WORKING for ep01 with old art |
| upload | C:\Users\goddu\repos\youtube_upload\yt.py (OAuth token C:\1st\youtube_token.json) | works from the laptop; move the refresh token to a GitHub secret for unattended runs |
| story | Desktop\Sonpur_Hindi_20_stories.md has 20 finished Hindi scripts (ep01 = laddoo) | ep02..ep20 ready; plan.json per episode via plan.py |

## Next steps, in order
1. `vertex_assets.yml` run for ep01 (masters, plates, props) -> artifact -> `vertex_to_keys.py <artifact> out/ep01/plan.json out/keys out/ep01/keys_selection.json --assets out/ep01/assets`
2. Dispatch `vertex_assets.yml` with only=poses for all chars (62 poses, ~₹200). Add walk cycles: name extra drawings `<char>__walk_0..2.png`.
3. Render 3 shots (look test) with compose.py on GitHub (episode2d.yml), check: mouths detected, cutout edges, scale per character (keyactor uses the stand drawing's bbox as the size reference, so all masters must be drawn at the same scale: full body, feet at the bottom).
4. Owner reviews the 3-shot test, then the full ep01 remake, then ep02.
5. Factory workflow (cron): story -> TTS -> art -> compose -> upload PRIVATE -> owner taps public.

## Gotchas
- Vertex trial quota is low: expect 429 bursts; vertex_gen.py retries with backoff (9 images ≈ 2 min).
- Local runs: `gcloud auth login` must be mounikagoddu12345 (goddudileep cannot see the project). Never print tokens.
- Gemini outputs pure-white backgrounds; a chroma key would punch holes in white saris, hence the flood-fill matte.
- CLIP 77-token prompt limit only matters for the open-source (Kaggle DreamShaper) path, which is now the fallback.
