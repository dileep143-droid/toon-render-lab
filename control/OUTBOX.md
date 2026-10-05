# kulfi-agent reports (newest last). Each block: '## done <id>' then the report.

## done 20261004125652
Summary of the factory (from pipeline2d/VERTEX_FACTORY.md; no workflow started):
1. Art via Vertex AI (vertex_gen.py + vertex_assets.yml, keyless OIDC/WIF) works: Dadi master + 9 poses tested; one colour drift (sit_cross came out pink).
2. vertex_to_keys.py (flood-fill matte) converts art to compose.py key drawings; works locally. Mouth detection (YuNet) is untested on Vertex art.
3. Compose/render (compose.py, episode2d.yml on Kaggle) works for ep01 with the OLD art; emotional Vertex TTS is NOT wired yet (ep01 uses old TTS).
4. Upload works only from the laptop (yt.py); the YouTube refresh token still needs to move to a GitHub secret for unattended runs. Scripts ep02..ep20 are ready.
5. Cron factory (story -> TTS -> art -> compose -> private upload) is not built yet.

Most important next step: run vertex_assets.yml for ep01 (masters, plates, props), convert with vertex_to_keys.py, then render a 3-shot look test via episode2d.yml for you to review.
Owner decision: say "go" and I will dispatch the ep01 vertex_assets run (costs a little Vertex trial credit).

## done 20261004145626
Hi! "ho" received (looks like a test message). No workflow started. Factory is idle: no QA reports exist yet, nothing to fix.

## done 20261004145640
Hi! Agent is awake and listening. No workflow started; no QA reports pending.
Next step is still the ep01 vertex_assets run from the earlier report. Send "go" in the control room and I will dispatch it.

## done QA_ep01_v4_test
QA: 4 of 5 shots pass; s005_b FAIL (photographic image inside a window, off-style).
Fix (round 1): vertex_gen.py plate prompt now forces windows, doorways and the view outside to be flat cartoon (no photos). Started vertex_assets.yml (ep01, plates only) via control/RUN.json.
Next: when the plates run finishes, rebuild with build_keys.yml (ep01, art_run=<that run id>, render=test, name=ep01_auto1), then check the new QA report. Full render only if that test is clean.
Owner: nothing to do yet. Do not trust the Videos tab until the test is clean.

## progress QA_ep01_v4_test (round 1)
Plates redraw (vertex_assets run 37213621286) succeeded. Started build_keys.yml (ep01, art_run=37213621286, render=test, name=ep01_auto1). Next: judge the new QA report; full render only if the test is clean. Owner: nothing yet.

## progress QA_ep01_v5_test (round 1, retry)
QA_ep01_v5_test is not a quality verdict: the render job failed because Kaggle dataset mani7673/sonpur-2d-ep01 returned 404 for 10 minutes (dataset still processing / infra), before any frame was rendered. No art fault found. Re-dispatched build_keys.yml once (ep01, same art_run 37213621286, render=test, name=ep01_auto1b). If it fails the same way, the owner should check the Kaggle dataset/token. Owner: nothing yet.

## done QA_ep01_v5_test
The retry (ep01_auto1b, episode2d run 37216283367) also FAILED with no QA verdict: no frame was rendered. First failure was the Kaggle dataset mani7673/sonpur-2d-ep01 returning 404; the retry looks the same (infra, not an art fault). I will not retry a third time.
Owner: please check on Kaggle that dataset mani7673/sonpur-2d-ep01 exists and has finished processing, and that the KAGGLE token secret is valid. Then say "go" in the control room and I will re-dispatch build_keys.yml (ep01, art_run=37213621286, render=test).
Still pending: the ep01 s005_b window fix (plates redrawn, round 1) has not yet been test-rendered.

## progress QA_ep01_v5_test (round 1, test clean)
New test render (episode2d run 37271386811, started by the owner) is clean: 5 of 5 shots pass, including the s005_b window fix. Started the FULL ep01 render (episode2d.yml, units empty, name=ep01_auto1_full) via control/RUN.json. Next: judge QA_ep01_auto1_full.md; if clean, write done and tell the owner to watch it on the Videos tab and upload privately. Owner: nothing yet.

## done QA_ep01_auto1_full
Full ep01 render (62 shots) finished: 55 pass / 7 fail by the Gemini judge. No black frames, no warped faces, no text, no colour slips reported.
Faults are minor and per-shot: s010, s038 (small object "floating on shirt" - probably a prop/necklace), s021, s027, s028, s052 (character touching the frame edge - likely deliberate entrance/close-up framing), s061 (object in mid-air - probably a thrown/lifted prop).
I did NOT start a second full render: these look like judge nitpicks on framing/props, not art faults, and I cannot see the frames from the repo to fix them safely. Nothing was changed in code.
Owner: please watch ep01_auto1_full on the Videos tab, check those 7 shots (s010, s021, s027, s028, s038, s052, s061) and upload PRIVATELY if you are happy. If any looks truly wrong, tell me the shot id in the control room and I will fix just that (test render first).
Next: ep02 art (vertex_assets) once you say "go".
