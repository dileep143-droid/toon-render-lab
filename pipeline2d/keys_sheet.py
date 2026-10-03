"""Contact sheet of generated key drawings: python keys_sheet.py <glob under out/keys> <out.jpg> [tile_h]"""
import glob, os, sys
from PIL import Image, ImageDraw
HERE = os.path.dirname(os.path.abspath(__file__)); K = os.path.join(HERE, "out", "keys")


def sheet(pattern, out, th=300, cols=13):
    fs = sorted(glob.glob(os.path.join(K, pattern, "rgba.png")))
    tiles = []
    for f in fs:
        im = Image.open(f).convert("RGBA"); bg = Image.new("RGBA", im.size, (225, 225, 225, 255)); bg.alpha_composite(im)
        t = bg.convert("RGB"); t = t.resize((int(t.size[0] * th / t.size[1]), th))
        d = ImageDraw.Draw(t); d.text((4, 4), os.path.relpath(os.path.dirname(f), K).replace(os.sep, "/")[-34:], fill=(200, 0, 0)); tiles.append(t)
    if not tiles: print("none"); return
    tw = max(t.size[0] for t in tiles); rows = (len(tiles) + cols - 1) // cols
    S = Image.new("RGB", (cols * tw, rows * th), "white")
    for i, t in enumerate(tiles): S.paste(t, ((i % cols) * tw, (i // cols) * th))
    S.save(out, quality=85); print(len(tiles), "->", out)


if __name__ == "__main__":
    sheet(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 300)
