"""Mix-and-match villagers: any BODY from bodies.json + any OUTFIT from lib_outfits / lib_outfits_kids, assembled when a story needs it.

    import villager as VL
    VL.setup(pack_dir, functional_dir)                    # once per Blender session (MPFB assets)
    h, rig = VL.make_villager("girl_9y", "langa_voni", colours=None, extras=["bindi", "gajra"], loc=(0, 0, 0))
    h, rig = VL.make_villager("elder_woman_70y", "saree_elder", extras=["glasses"])
    h, rig = VL.make_villager("toddler_girl_2y", "baby_frock")

A villager is NEVER returned undressed: if the outfit fails, the body is deleted and an error is raised."""
import bpy, json, os, importlib
HERE = os.path.dirname(os.path.abspath(__file__))
_BODIES = None
KID_OUTFITS = {"jhabla", "baby_romper", "baby_frock", "toddler_kurta_shorts", "toddler_shirt_shorts", "woollen_set"}

def bodies():
    global _BODIES
    if _BODIES is None:
        _BODIES = {b["id"]: b for b in json.load(open(os.path.join(HERE, "bodies.json"), encoding="utf-8-sig"))["bodies"]}
    return _BODIES

def setup(pack_dir, functional_dir):
    import mpfb_child as MC
    if not pack_dir: return            # packs already installed in MPFB's user data (e.g. a local Blender)
    MC.install_packs(pack_dir, functional_dir)

def _delete(objs):
    for o in objs:
        try: bpy.data.objects.remove(o, do_unlink=True)
        except Exception: pass

def make_villager(body_id, outfit, colours=None, extras=(), footwear="chappal", loc=(0, 0, 0), rot_z=0.0, toon=True, seed=0, name=None, **opts):
    import mpfb_child as MC
    b = bodies()[body_id]; fem = b["gender"] == "f"
    before = set(bpy.data.objects)
    base_clothes = ("female_casualsuit01", "shoes01") if fem else ("male_casualsuit01", "shoes02")
    h, rig = MC.make_child(gender=0.0 if fem else 1.0, age=MC.age_macro(b["age"]), skin=b["skin"], hair=b["hair"], clothes=base_clothes,
                           skin_rgb=tuple(b["skin_rgb"]), weight=b.get("weight", 0.5), height=b.get("height", 0.5))
    try:
        if toon:
            try:
                LT = importlib.import_module("lib_toon")
                if getattr(LT, "TOON_BEFORE_DRESS", True): LT.toonify(h, rig, skin_rgb=tuple(b["skin_rgb"]), age=b["age"])
            except ImportError: pass
        if outfit in KID_OUTFITS:
            garments = importlib.import_module("lib_outfits_kids").dress_kid(h, rig, outfit, colours=colours, seed=seed)
        else:
            LO = importlib.import_module("lib_outfits")
            garments = LO.dress(h, rig, outfit, colours=colours, seed=seed, char=name or body_id, **opts)
        if not garments: raise RuntimeError(f"outfit {outfit} produced no garments")
        LO = importlib.import_module("lib_outfits")
        for ex in extras:
            f = getattr(LO, ex, None)
            if callable(f): f(h, rig)
        if footwear and hasattr(LO, "footwear") and outfit not in KID_OUTFITS: LO.footwear(h, rig, footwear)
        if toon:
            try:
                LT = importlib.import_module("lib_toon")
                if not getattr(LT, "TOON_BEFORE_DRESS", True): LT.toonify(h, rig, skin_rgb=tuple(b["skin_rgb"]), age=b["age"])
                if hasattr(LT, "toonify_scene"): LT.toonify_scene()
            except ImportError: pass
    except Exception:
        _delete([o for o in bpy.data.objects if o not in before])   # never leave an undressed body behind
        raise
    rig.location = loc; rig.rotation_euler = (0, 0, rot_z)
    rig["body_id"] = body_id; rig["outfit"] = outfit
    if name: rig.name = name
    return h, rig

def cast_member(cast_id):
    """Build a named story character from cast.json (body + outfit recipe)."""
    c = json.load(open(os.path.join(HERE, "cast.json"), encoding="utf-8-sig"))
    m = next(x for x in c["main"] + c["extras"] if x["id"] == cast_id)
    body = m.get("body") or _nearest_body(m)
    return make_villager(body, m["outfit"], extras=m.get("extras", []), name=cast_id)

def _nearest_body(m):
    best, bd = None, 1e9
    for bid, b in bodies().items():
        if b["gender"] != m["gender"]: continue
        d = abs(b["age"] - m["age"]) + 10 * abs(b.get("weight", 0.5) - m.get("weight", 0.5))
        if d < bd: best, bd = bid, d
    return best
