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

## done QA_ep01_v6_full
QA_ep01_v6_full is not a quality verdict: episode2d run 37275258909 (started by the owner at commit d83d711, mouth_sheet change-mask work) FAILED in the "Private bundle" step after 10 minutes, before any frame was rendered. Same signature as the earlier Kaggle 404 failures (private dataset download timing out). No art fault found; nothing changed in code. I did not retry (the run was not mine, and the earlier two retries failed the same way).
Owner: check on Kaggle that the private bundle dataset mani7673/sonpur-2d-ep01 (or the one made by make_bundle for v6) exists and finished processing, and that the Kaggle token secret is valid. Then say "go" in the control room and I will re-dispatch a test render first.
Still valid: ep01_auto1_full (55/62 pass) is ready for you on the Videos tab; check shots s010, s021, s027, s028, s038, s052, s061 and upload privately.

## done QA_ep01_v6_full (run 37276570786)
Second QA_ep01_v6_full report, run 37276570786, is again "RENDER FAILED" with no frame verdict. It was started by the owner after commit f9adf3b (episode2d now waits up to 40 min for Kaggle to finish processing a new bundle), so this is a different run from 37275258909. No art fault found; I changed no code and did not retry (owner is actively iterating on the bundle/Kaggle wait).
Owner: if this failed again at "Private bundle", the Kaggle dataset/token is still the problem (check it exists, finished processing, token secret valid). If it failed somewhere else, open run 37276570786 logs.
Still valid: ep01_auto1_full (55/62 pass) is ready on the Videos tab; check shots s010, s021, s027, s028, s038, s052, s061 and upload privately.

## done QA_ep01_v6_full (run 37280971688)
Third QA_ep01_v6_full report is again "RENDER FAILED", no frame verdict. The run was CANCELLED in the "Private bundle" step after ~37 min, on commit 536acb2, i.e. BEFORE commit 5b0446a (bundle now fetched from the private kulfi-assets release, Kaggle only as fallback). So it still used the old Kaggle wait. No art fault; I changed no code and did not retry.
Owner: re-run a test render (episode2d, ep01, units = first shots) on the current main (5b0446a or later) to check the new release-bundle path. Say "go" in the control room and I will dispatch it.
Still valid: ep01_auto1_full (55/62 pass) is ready on the Videos tab; check shots s010, s021, s027, s028, s038, s052, s061 and upload privately.

## done QA_ep01_v7_full (run 37291802741)
QA_ep01_v7_full is "RENDER FAILED", not a quality verdict. Run 37291802741 (owner-started, commit 9e2b940, ai_matte/mouth work) was CANCELLED in the Render step after ~12 min. Good news: the "Private bundle" step now SUCCEEDED in 12 s, so the release-bundle path (5b0446a) works and the old Kaggle 404 problem is gone. No frame was judged; I changed no code and did not retry (the run was not mine and looks cancelled by hand).
Owner: if you want a verdict on the new mouth/matte changes, say "go" and I will dispatch a test render (render=test) first. Still valid: ep01_auto1_full (55/62 pass) is on the Videos tab; check s010, s021, s027, s028, s038, s052, s061 and upload privately.

## done QA_ep01_v8_full
ep01_v8_full (run 37293389439, owner-started, includes the ai_matte/mouth changes up to 3b4c836) finished: 58 pass / 4 fail (better than auto1's 55/62). No black frames, warped faces, text or colour slips.
Remaining faults: s010, s038 ("laddoo floating on shirt") and s061 ("laddoo floating in mid-air") - the laddoo is a held/thrown prop, so likely judge nitpicks; s027 (character cut off at left frame edge) - probably deliberate framing. I could not see the frames, so I changed no code and started no render.
Owner: watch ep01_v8_full on the Videos tab, check s010, s027, s038, s061, and upload PRIVATELY if happy. If any is truly wrong, tell me the shot id in the control room and I will fix just that (test render first).
Next: ep02 art once you say "go".

## done QA_ep01_v9_full
ep01_v9_full (run 37296437649, mouth change back to the owner-approved v6 area, commit 181acf1) finished: 58 pass / 4 fail, same score as v8. No black frames, warped faces, text or colour slips.
Faults: s010, s038 (laddu "floating on shirt") and s061 (floating laddu) are the same held/thrown-prop nitpicks as v8. NEW vs v8: s061 and s062 mention a "stray artifact box on the floor" - this could be a real leftover rectangle (e.g. an un-keyed background patch) or a judge misreading of a prop. I cannot see frames from the repo, so I changed no code and started no render (no safe fix without seeing it).
Owner: watch ep01_v9_full on the Videos tab, look at s061 and s062 for a box on the floor, and check s010/s038. If s062 has a real box, tell me in the control room and I will fix it (test render first). Upload PRIVATELY only if happy.
Next: ep02 art once you say "go".

## done 20261004145640
Hi! The factory agent is awake. Nothing is running and there is nothing pending: QA_ep01_v9_full is already reported (58/62 pass). Newest requests "hi"/"ho" were greetings (20261004145626 is covered by this reply too).
Owner: check s061/s062 of ep01_v9_full for a box on the floor and upload PRIVATELY if happy. Tell me a shot id, or say "go" for ep02 art, and I will start (test render first).
