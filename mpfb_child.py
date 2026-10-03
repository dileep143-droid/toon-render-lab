"""Make dressed MPFB (MakeHuman) children inside any Blender scene. CC0 output; face units for expressions.
Needs the MPFB extension installed and the CC0 system pack + functional packs unpacked (see samples.yml)."""
import bpy, os, glob, importlib
BASE = "bl_ext.user_default.mpfb"
for _cand in ("bl_ext.user_default.mpfb", "bl_ext.blender_org.mpfb", "mpfb"):   # local Blender may install MPFB from the online repo
    try: importlib.import_module(_cand); BASE = _cand; break
    except Exception: pass
def _svc(n): return importlib.import_module(f"{BASE}.services.{n}")
HS = _svc("humanservice").HumanService; AS = _svc("assetservice").AssetService
LS = _svc("locationservice").LocationService; FS = _svc("faceservice").FaceService

def install_packs(pack_dir, functional_dir=None):
    import shutil
    ud = LS.get_user_data(); src = pack_dir
    tops = os.listdir(pack_dir)
    if len(tops) == 1 and os.path.isdir(os.path.join(pack_dir, tops[0])): src = os.path.join(pack_dir, tops[0])
    for d in os.listdir(src):
        if os.path.isdir(os.path.join(src, d)): shutil.copytree(os.path.join(src, d), os.path.join(ud, d), dirs_exist_ok=True)
    for z in sorted(glob.glob(os.path.join(functional_dir or "", "*.zip"))): AS.fix_and_extract_asset_pack_zip(z, ud)
    AS.update_all_asset_lists()
    try: AS.rescan_pack_metadata()
    except Exception: pass

def _file(kind, base):
    ud = LS.get_user_data()
    hits = glob.glob(os.path.join(ud, kind, "**", base + ".mhclo" if kind != "skins" else base + ".mhmat"), recursive=True)
    return hits[0] if hits else None

def _tint_tree(nt, rgb, fac, mode, seen):
    if nt.name in seen: return
    seen.add(nt.name)
    for n in list(nt.nodes):
        if n.bl_idname == "ShaderNodeGroup" and n.node_tree: _tint_tree(n.node_tree, rgb, fac, mode, seen)
        if n.bl_idname == "ShaderNodeTexImage" and n.image:
            nm = n.image.name.lower()
            if any(w in nm for w in ("normal", "nor", "rough", "spec", "bump", "sss", "ao", "alpha", "trans")) and not any(w in nm for w in ("diffuse", "albedo", "color", "colour")): continue
            links = list(n.outputs["Color"].links)
            if not links: continue
            mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.blend_type = mode; mix.inputs[0].default_value = fac
            mix.inputs[7].default_value = (*[c ** 2.2 for c in rgb], 1)
            nt.links.new(n.outputs["Color"], mix.inputs[6])
            for l in links:
                to = l.to_socket; nt.links.remove(l); nt.links.new(mix.outputs[2], to)

_SKIN_DONE = set()
def age_macro(years):
    """MakeHuman age macro: 0 = 1 y, 0.1875 = 11 y, 0.5 = 25 y, 1 = 90 y"""
    if years <= 11: return max(0.0, 0.1875 * (years - 1) / 10)
    if years <= 25: return 0.1875 + 0.3125 * (years - 11) / 14
    return min(1.0, 0.5 + 0.5 * (years - 25) / 65)

def make_child(gender=0.0, age=0.14, skin="young_asian_female", hair="long01", clothes=("female_casualsuit01", "shoes01"),
               skin_rgb=(0.86, 0.64, 0.48), loc=(0, 0, 0), rot_z=0.0, faces=True, weight=0.55, height=0.5):
    """returns (basemesh, rig). Works for any age (use age_macro(years)). Refuses to return an undressed character."""
    macros = {"gender": gender, "age": age, "muscle": 0.5, "weight": weight, "proportions": 0.5, "height": height, "cupsize": 0.5, "firmness": 0.5,
              "race": {"african": 0.15, "asian": 0.55, "caucasian": 0.30}}
    h = HS.create_human(macro_detail_dict=macros, feet_on_ground=True, scale=0.1)
    rig = HS.add_builtin_rig(h, "default")
    sk = _file("skins", skin)
    if sk: HS.set_character_skin(sk, h, skin_type="ENHANCED_SSS")
    for kind, base, at in (("eyes", "high-poly", "eyes"), ("eyebrows", "eyebrow010", "eyebrows"), ("eyelashes", "eyelashes01", "eyelashes"), ("hair", hair, "Hair")):
        f = _file(kind, base)
        if f: HS.add_mhclo_asset(f, h, asset_type=at)
    dressed = 0
    for c in clothes:
        f = _file("clothes", c)
        if f: HS.add_mhclo_asset(f, h, asset_type="Clothes"); dressed += 1
    if dressed == 0:
        raise RuntimeError("child has no clothes: refusing to continue")
    seen = set(_SKIN_DONE)
    for s in h.material_slots:
        if s.material and s.material.use_nodes: _tint_tree(s.material.node_tree, skin_rgb, 1.0, "MULTIPLY", seen)
    _SKIN_DONE.update(seen)
    for o in bpy.data.objects:
        if o.type == "MESH" and o.parent in (h, rig) and any(w in o.name.lower() for w in (hair.lower(), "eyebrow")):
            for s in o.material_slots:
                if s.material and s.material.use_nodes: _tint_tree(s.material.node_tree, (0.05, 0.04, 0.035), 0.85, "MIX", set())
    if faces:
        try: FS.load_targets(h, load_microsoft_visemes=True, load_meta_visemes=False, load_arkit_faceunits=True)
        except Exception as ex: print("face units not loaded:", ex)
    rig.location = loc; rig.rotation_euler = (0, 0, rot_z)
    return h, rig

def set_face(h, **weights):
    """set_face(h, mouthSmileLeft=1, mouthSmileRight=1, eyeBlinkLeft=0.5 ...)"""
    if not h.data.shape_keys: return
    kb = h.data.shape_keys.key_blocks
    for k, v in weights.items():
        if k in kb: kb[k].value = v
