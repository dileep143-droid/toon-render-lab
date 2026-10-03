#!/bin/bash
# Blender 4.2.3 LTS + MPFB extension + MakeHuman CC0 system assets + functional packs (same recipe as kids.yml / build_on_kaggle.py)
set -e
curl -sSL -o b.tar.xz https://download.blender.org/release/Blender4.2/blender-4.2.3-linux-x64.tar.xz
tar -xf b.tar.xz && mv blender-4.2.3-linux-x64 blender && rm b.tar.xz
python3 - <<'EOF'
import json, urllib.request
H = {"User-Agent": "Blender/4.2.3 (toon-render-lab)"}
d = json.load(urllib.request.urlopen(urllib.request.Request("https://extensions.blender.org/api/v1/extensions/", headers=H), timeout=60))
e = next(x for x in d.get("data", d) if x.get("id") == "mpfb")
print("MPFB", e.get("version"))
open("mpfb.zip", "wb").write(urllib.request.urlopen(urllib.request.Request(e["archive_url"], headers=H), timeout=120).read())
EOF
./blender/blender -b --command extension install-file -r user_default -e mpfb.zip > /dev/null
if [ -d pack ] && [ -n "$(ls -A pack 2>/dev/null)" ] && [ -f functional/visemes01.zip ]; then
  echo "MakeHuman packs restored from cache"
else
  curl -fsSL -A "Mozilla/5.0" -o pack.zip https://files2.makehumancommunity.org/asset_packs/makehuman_system_assets/makehuman_system_assets_cc0.zip
  mkdir -p pack functional && unzip -q pack.zip -d pack && rm pack.zip
  for p in faceunits01 visemes01; do curl -fsSL -A "Mozilla/5.0" -o functional/$p.zip https://files2.makehumancommunity.org/functional/$p.zip; done
fi
echo "BLENDER+MPFB READY"
