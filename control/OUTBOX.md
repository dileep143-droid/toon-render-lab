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
