# toon-render-lab

A test: building and rendering a short cartoon entirely by script with Blender on GitHub Actions.

- `render_scene.py` builds the scene (an original character, "Gudu"), animates it and renders the frames.
- `.github/workflows/render.yml` downloads Blender, renders, adds simple sound effects with ffmpeg and uploads the video as an artifact.

Run it from the Actions tab: **render-sample → Run workflow**. Occasional short renders only.
