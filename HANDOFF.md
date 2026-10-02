# Sonpur ki Toli — 3D cartoon pipeline: status and how to continue

Last updated: 2 Oct 2026 (session paused by the owner).

## What this project is
A free, open-source pipeline to make Infobells-style 3D Indian-village kids' cartoons ("सोनपुर की टोली", Hindi, moral + comedy, 10 min episodes) with Blender driven by Python scripts.
- **Code:** this public GitHub repo (`dileep143-droid/toon-render-lab`).
- **Heavy builds:** Kaggle free GPU (2× Tesla T4), account `mani7673`, API token in the owner's `.env` as `KAGGLE_KEY1` (a `KGAT_` token → set env `KAGGLE_API_TOKEN`).
- **Asset database:** private Kaggle dataset `mani7673/sonpur-asset-library-data` (Blender `.blend` per asset + thumbnail `.png` + `catalogue.json`; also the Hindi stories, kept private).
- **Tests:** GitHub Actions workflows in `.github/workflows/` (Blender 4.2.3 LTS on Ubuntu, CPU). Use GitHub only for tests/stills, not full-episode renders (GitHub terms); full renders go to Kaggle.

## DONE (built, checked)
| Part | Where | Count |
|---|---|---|
| Story audit of the 20 Hindi scripts (370 needs) | private dataset `stories/` (ASSET_NEEDS.md/.json) | 370 rows |
| Props, buildings, fields, decor (clean procedural, real sizes) | `lib_props.py` (69), `lib_props2.py` (223 story props, food, school, play, mela, sets, small animals, Kachra Rakshas, chewed variants), `lib_props3.py` (68: Dadi's aangan, cricket ground, school yard, chowk, temple courtyard, rivers/bends/island, canal, pond, waterfall, bridges, boats incl. paper boat, fish/ducks/frog/turtle, baby items, chakki/radio/TV, monsoon kit), `lib_props4.py` (43: vehicles, festival kits, haat/vet clinic/post office/…, cat/monkey/parrot/calf/…, sky) | **403 in the database** |
| Animated animals (Quaternius CC0: cow, bull, donkey, horse ×2, husky, shiba inu, deer, fox, alpaca, stag, wolf) | `fetch_cartoon_assets.py`, database `animals/` | 12 |
| Cast of 30 (+3 toddlers/baby added) | `cast.json`, database `cast/` (**draft**: old outfits, pale skin on some) | 30 built |
| Body library (separate from outfits) | `bodies.json` (28 bodies: baby, toddlers, kids 6–13, adults, fat, bald, elders) + `villager.py` `make_villager(body_id, outfit, …)` | defined |
| Outfits (19 adult + 6 kids), coverage-checked on 7 body types | `lib_outfits.py`, `lib_outfits_kids.py` | fit OK, **look needs work** |
| Physics/effects (74), animation (walk/run/jump/fall/dance/sit/… + habits, 29 face presets, talk/blink, CMU mocap retarget), lighting & camera | `lib_fx.py`, `lib_anim.py`, `lib_camera.py`, `demo_fx.py`, `fetch_mocap.py` (CMU BVH: never commit the .bvh files), `fetch_sfx.py` (≈890 CC0 sounds; run locally, don't commit `sfx/`) | done |
| MPFB characters with skin tint, hair, eyes, 85 face units (smile/blink/visemes) | `mpfb_child.py` | done |
| Story 1 (`01_magic_laddoo`) | **APPROVED by the owner** (read via English translation — always send scripts in English for review) | 1 of 20 |

## UNFINISHED (stopped mid-work on 2 Oct — re-test before use)
1. **Outfit look + fit pass** (`lib_outfits.py`): owner said outfits/collars "not good" and "not fitted perfectly". Needed: natural folds (short cloth sim), real nivi saree drape, kachha dhoti, straight lungi/kurta, real collars per outfit, cotton/silk materials, snug fit (≤5–8 mm air at shoulders/chest/waist, measured per region), FLUX reference pictures, neck/shoulder/waist close-ups, fit on fat bodies, a neutral `base_layer` outfit for stored bodies.
2. **Maa carrying a toddler** (`lib_outfits_kids.carry_baby`): owner said "worst of all". Needed: Maa's hip pushed out, child straddling the hip, Maa's forearm UNDER the child's bottom, child's arm round her neck, no intersections; in-arms carry with a closed swaddle.
3. **Chamki (goat) + Sheru (dog)** (`lib_animals.py`, `preview_animals.py`, `animals.yml`): nearly done (its 2nd GitHub run passed) — run a final test.
4. **Cartoon look** (`lib_toon.py`, `toon.yml`, call added in `build_library.py`): code written, before/after renders not done.
5. **Hairstyles + expressions** (`lib_hair.py`, `preview_hair.py`, `hair.yml`, `lib_expressions.py` just started): tied Indian hair (koppu bun, long jada with kuchulu, bun with flowers, half-tied, Dadi's small grey bun, school two-jadas with ribbons), kumkum bottu / bindi / sindoor / vibhuti / tilak / kaajal, bald styles, moustaches/beards; expressions incl. head wobble, shy, sulking, cunning (sly smirk, scheming eyebrow, fake innocent…).
6. **Physics layer** (`lib_physics.py` not written yet): cloth per shot with pinned tops + body collision, hair/pallu springs, rigid-body settle, ground snap, hold/sit/carry contacts, foot lock, `check_scene` validator (penetrations, floating, foot slide, cloth explosions) + auto-fix.
7. **Hunyuan3D-2 on Kaggle** (`kaggle/hunyuan`): stuck for hours — stop/re-run shape-only, or skip (goat/peacock/buffalo).
8. **Then:** rebuild the cast on Kaggle with fixed outfits + cartoon look + hair; 1-minute test of story 1 scene 1 (Dadi's aangan, Dadi, Chhotu, Chamki, snoring Sheru, Hindi voices, lip-sync, title card + 5–10 s jingle — no theme song needed).

## HARD RULES
- Never render or save an image of any character without a complete outfit; coverage check before every render.
- No voices/audio for a story until the owner approves its script (only story 1 is approved).
- Licences: only CC0 / CC-BY (credit) / MIT / Apache / clearly free-commercial. No NC. CMU mocap: don't redistribute the BVH files.
- PowerShell 5.1 `Set-Content -Encoding UTF8` writes a BOM that breaks JSON/Kaggle metadata — write files with Python/UTF-8.
- Kaggle kernel output keeps only the LATEST version: after each build, download it, merge into the local library and `kaggle datasets version` the database.

## Run everything from GitHub (no laptop needed)
The repo has encrypted secrets `KAGGLE_KEY1`…`KAGGLE_KEY20` (key 1 = account `mani7673`, which owns the kernels and the database). Workflow `.github/workflows/kaggle.yml` (Actions tab → "kaggle" → Run workflow):
- `action=list` — show kernels + datasets (tested OK on 2 Oct).
- `action=build`, `kernel_dir=kaggle/library`, `only=props|cast|animals`, `mods=lib_props4` (or a comma list) — starts a GPU build on Kaggle.
- `action=status` — kernel status.
- `action=sync` — waits for the build to finish, merges its output into the private dataset `mani7673/sonpur-asset-library-data` and publishes a new version (`kaggle/sync_library.py`).
Test workflows (outfits.yml, kids.yml, hair.yml, toon.yml, animals.yml, fx.yml, samples.yml) also run from the Actions tab. A cloud Claude session only needs GitHub access to drive all of this.

## How to run things
- Build part of the library on Kaggle: edit `kaggle/library/build_on_kaggle.py` (`ONLY = "props"|"cast"|"animals"`, `MODS = "lib_props4"` etc.), then `kaggle kernels push -p kaggle/library` (env `KAGGLE_API_TOKEN`). Download: `kaggle kernels output mani7673/sonpur-asset-library -p <dir>`.
- Locally: `blender -b --python preview_props.py -- <out> [names] [--workbench|--check|--ref]` (same for preview_props2/3/4).
- Tests on GitHub: dispatch a workflow (outfits.yml, kids.yml, hair.yml, toon.yml, animals.yml, fx.yml, samples.yml) with the Actions API or the Actions tab.
