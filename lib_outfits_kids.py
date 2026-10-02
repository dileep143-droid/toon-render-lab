"""lib_outfits_kids.py - outfits + accessories for BABIES and TODDLERS (MPFB age 1-4 y), built on lib_outfits' fitting
machinery (body-copy shells, measured lathe skirts, rigid bits). lib_outfits.py itself is not changed.

Outfits (all cover level "knee": torso + hips + legs to the knee hidden from every camera)
  jhabla               loose cotton baby smock to below the knee + nappy-style shorts underneath
  baby_romper          one-piece romper (top + legs to the knee in one fabric, front snaps)
  baby_frock           puff-sleeve frock (skirt below the knee) + bloomers underneath
  toddler_kurta_shorts short kurta (mid-thigh tail) + knee shorts
  toddler_shirt_shorts half-sleeve checked shirt + knee shorts
  woollen_set          pullover sweater + woollen leggings + woollen cap with pompom + booties
Accessories: kaajal_dot (tiny black dot on the cheek), black_thread_anklet, small_bangles, nazar_bracelet
API
  dress_kid(basemesh, rig, outfit, colours=None, seed=0, **opts) -> [objects]   (raises instead of returning nothing)
  carry_baby(adult_rig, baby_rig, side="left", mode="hip"|"arms")               (poses both rigs + parents the baby)
  OUTFITS (same keys as lib_outfits.OUTFITS entries: pieces, colours, accessories, cover, footwear)
Make the child with mpfb_child.make_child(age=age_macro(1..3), hair="none"|"short01"|"bob01"...). hair="none" = no hair.
"""
import bpy, bmesh, math, random
from mathutils import Vector, Matrix
import lib_outfits as LO
from lib_outfits import fabric, solid, top, bottoms, lathe, skirt_rings, rigid, buttons, collar, waistband, _ball, _torus, GOLD

R = math.radians

OUTFITS = {
    "jhabla": {"who": ["baby", "toddler"], "pieces": ["loose smock (short sleeves) to below the knee", "nappy shorts underneath", "neck ties"],
               "colours": {"jhabla": (0.98, 0.93, 0.6), "print": (0.95, 0.55, 0.3), "nappy": (0.98, 0.98, 0.96), "tie": (0.95, 0.55, 0.3)},
               "accessories": ["kaajal_dot", "black_thread_anklet"], "footwear": "barefoot", "cover": "knee", "core": ["jhabla_top", "jhabla_tail", "nappy"]},
    "baby_romper": {"who": ["baby", "toddler"], "pieces": ["one-piece romper: body + short sleeves + legs to the knee", "front snaps"],
                    "colours": {"romper": (0.55, 0.78, 0.95), "stripe": (0.98, 0.98, 0.98), "snap": (0.98, 0.85, 0.3)},
                    "accessories": ["kaajal_dot", "black_thread_anklet"], "footwear": "barefoot", "cover": "knee", "core": ["romper_top", "romper_legs"]},
    "baby_frock": {"who": ["baby girl", "toddler girl"], "pieces": ["frock bodice with puff sleeves", "flared skirt below the knee", "bloomers", "sash"],
                   "colours": {"frock": (0.98, 0.5, 0.65), "dots": (1.0, 1.0, 1.0), "sash": (0.98, 0.9, 0.35), "bloomers": (0.99, 0.95, 0.96), "collar": (1, 1, 1)},
                   "accessories": ["kaajal_dot", "small_bangles", "black_thread_anklet"], "footwear": "barefoot", "cover": "knee", "core": ["frock_bodice", "frock_skirt", "bloomers"]},
    "toddler_kurta_shorts": {"who": ["toddler boy"], "pieces": ["short kurta (mid-thigh)", "knee shorts", "buttons"],
                             "colours": {"kurta": (0.98, 0.85, 0.35), "shorts": (0.3, 0.45, 0.7), "button": (0.75, 0.55, 0.25)},
                             "accessories": ["kaajal_dot", "nazar_bracelet", "black_thread_anklet"], "footwear": "barefoot", "cover": "knee", "core": ["kurta", "kurta_tail", "shorts"]},
    "toddler_shirt_shorts": {"who": ["toddler boy"], "pieces": ["half-sleeve checked shirt", "knee shorts"],
                             "colours": {"shirt": (0.35, 0.7, 0.45), "check": (0.95, 0.95, 0.75), "shorts": (0.25, 0.3, 0.5)},
                             "accessories": ["nazar_bracelet", "black_thread_anklet"], "footwear": "barefoot", "cover": "knee", "core": ["shirt", "shorts"]},
    "woollen_set": {"who": ["baby", "toddler"], "pieces": ["pullover sweater", "woollen leggings", "woollen cap + pompom", "booties"],
                    "colours": {"sweater": (0.85, 0.25, 0.3), "leggings": (0.95, 0.85, 0.55), "cap": (0.95, 0.85, 0.55), "pompom": (0.85, 0.25, 0.3), "booties": (0.95, 0.85, 0.55)},
                    "accessories": ["kaajal_dot"], "footwear": "booties", "cover": "knee", "core": ["leggings", "sweater_pullover", "woollen_cap"]},
}
_ALT = {
    "jhabla": [{"jhabla": (0.75, 0.9, 0.98), "print": (0.3, 0.5, 0.85), "tie": (0.3, 0.5, 0.85)}, {"jhabla": (0.98, 0.8, 0.85), "print": (0.85, 0.3, 0.45), "tie": (0.85, 0.3, 0.45)}],
    "baby_romper": [{"romper": (0.98, 0.8, 0.4)}, {"romper": (0.6, 0.85, 0.6)}],
    "baby_frock": [{"frock": (0.98, 0.85, 0.3)}, {"frock": (0.6, 0.75, 0.98)}],
    "woollen_set": [{"sweater": (0.25, 0.45, 0.75), "cap": (0.98, 0.98, 0.95), "leggings": (0.98, 0.98, 0.95), "booties": (0.98, 0.98, 0.95), "pompom": (0.25, 0.45, 0.75)}],
}

def _colours(outfit, colours, seed):
    C = dict(OUTFITS[outfit]["colours"]); alts = _ALT.get(outfit, [])
    if seed and alts: C.update(alts[(seed - 1) % len(alts)])
    if colours: C.update(colours)
    return C

def _opts(outfit, opts):
    o = {a: True for a in OUTFITS[outfit].get("accessories", [])}
    o.update(opts); return o

# ----------------------------------------------------------------------------------------------- accessories
def kaajal_dot(B, side=1):
    """tiny black kaajal (nazar) dot on the cheek - side=1 is the character's left cheek"""
    ex = abs(B.bh["eye.L"].x) if "eye.L" in B.bh else 0.02 * B.Hs
    z = B.ze - 0.45 * (B.ze - B.zn)
    p = B.surf(side * 1.25 * ex, z, "front")
    if p is None: return None
    r = max(0.0025, 0.0045 * B.Hs / 1.6)
    return rigid(B, "kaajal_dot", solid("kaajal", (0.02, 0.02, 0.02), 0.6), lambda bm: _ball(bm, p + Vector((0, -0.0004, 0)), r, (1, 0.25, 1), sub=2), "head")

def black_thread_anklet(B):
    """kaala dhaaga round both ankles (thin black cord + one small black bead)"""
    out = []; m = solid("black_thread", (0.02, 0.02, 0.02), 0.8)
    for sd in (1, -1):
        A, F = B.axes[("leg", sd)]; d = (F - A).normalized(); s = "L" if sd > 0 else "R"
        c = B.c_at("leg", sd, 0.92); r0 = B.r_at("leg", sd, 0.92) + 0.002
        def build(bm, c=c, d=d, r0=r0):
            _torus(bm, c, d, r0, 0.0011, 32, 6)
            t1 = d.orthogonal().normalized(); front = Vector((0, -1, 0)); front = (front - d * front.dot(d)).normalized()
            _ball(bm, c + front * (r0 + 0.0015), 0.0026)
        out.append(rigid(B, f"black_thread_anklet{s}", m, build, f"lowerleg02.{s}"))
    return out

def small_bangles(B, count=2):
    """two thin gold bangles on each wrist (sized from the wrist, so they fit a toddler)"""
    return LO.bangles(B, count=count, gold_only=True)

def nazar_bracelet(B, side=-1):
    """black thread bracelet with a blue-white 'evil eye' bead and small black beads (right wrist by default)"""
    s = "L" if side > 0 else "R"
    A, W = B.axes[("arm", side)]; d = (W - A).normalized()
    t = 0.9; c = B.c_at("arm", side, t); r0 = B.r_at("arm", side, t) + 0.0025
    t1 = d.orthogonal().normalized(); t2 = d.cross(t1)
    up = Vector((0, 0, 1)); up = up - d * up.dot(d)
    if up.length < 1e-4: up = t1
    up.normalize()
    blk = solid("nazar_thread", (0.02, 0.02, 0.02), 0.7)
    def thread(bm):
        _torus(bm, c, d, r0, 0.0011, 32, 6)
        for k in range(8):
            a = 2 * math.pi * (k + 0.5) / 8
            _ball(bm, c + (t1 * math.cos(a) + t2 * math.sin(a)) * (r0 + 0.001), 0.0022)
    out = [rigid(B, f"nazar_thread{s}", blk, thread, f"lowerarm02.{s}")]
    pc = c + up * (r0 + 0.003)
    out.append(rigid(B, f"nazar_bead_blue{s}", solid("nazar_blue", (0.05, 0.25, 0.85), 0.2), lambda bm: _ball(bm, pc, 0.0042, (1, 1, 1), sub=2), f"lowerarm02.{s}"))
    out.append(rigid(B, f"nazar_bead_white{s}", solid("nazar_white", (0.97, 0.97, 0.97), 0.2), lambda bm: _ball(bm, pc + up * 0.0028, 0.0024, (1, 1, 0.5), sub=2), f"lowerarm02.{s}"))
    out.append(rigid(B, f"nazar_bead_eye{s}", solid("nazar_eye", (0.02, 0.05, 0.25), 0.2), lambda bm: _ball(bm, pc + up * 0.0043, 0.0012, (1, 1, 0.5), sub=1), f"lowerarm02.{s}"))
    return out

def woollen_cap(B, colour, pompom):
    """dome cap over the head (and any hair) down to the eyebrows, with a rolled brim and a pompom"""
    Hs = B.Hs; z0 = B.ze + 0.18 * (B.zt - B.ze)
    pts = LO._head_pts(B, z0, 0.012 * Hs)
    if len(pts) < 4: return None
    cy = (min(p.y for p in pts) + max(p.y for p in pts)) / 2
    rx = max(abs(p.x) for p in pts); ry = (max(p.y for p in pts) - min(p.y for p in pts)) / 2
    h = max(0.02, B.zt - z0)
    head = [B.co[i] for i in B.body_idx if B.part[i] == "head" and B.co[i].z > z0]
    ell = lambda p, a, b, c: math.sqrt((p.x / a) ** 2 + ((p.y - cy) / b) ** 2 + ((p.z - z0) / c) ** 2)
    s = max([ell(p, rx, ry, h) for p in head] + [1.0])
    e = 0.006 + 0.012 * Hs / 1.0 * (1 if B.hair_pts else 0.3)   # room for (squashed) hair
    rx, ry, h = rx * s + e, ry * s + e, h * s + e
    # "cap hair": hair that would poke through the cap is pulled inside it (edits the hair proxy's rest shape)
    Mi = B.h.matrix_world.inverted(); squashed = 0
    for ob in set(B.rig.children_recursive) | set(B.h.children_recursive):
        if ob.type != "MESH" or ob == B.h or ob.get("outfit_piece"): continue
        nm = ob.name.lower()
        if not (LO._otype(ob) == "Hair" or "hair" in nm or any(w in nm for w in ("long01", "short0", "bob0", "braid0", "ponytail", "afro"))): continue
        M = Mi @ ob.matrix_world; Minv = M.inverted()
        for v in ob.data.vertices:
            p = M @ v.co
            if p.z < z0 - 0.01 * Hs: continue
            k = ell(p, rx, ry, h) if p.z >= z0 else math.sqrt((p.x / rx) ** 2 + ((p.y - cy) / ry) ** 2)
            if k > 0.93:
                c0 = Vector((0, cy, min(p.z, z0) if p.z < z0 else z0))
                q = c0 + (p - c0) * (0.93 / k)
                v.co = Minv @ q; squashed += 1
        ob.data.update()
    print("OUTFIT cap hair squashed verts", squashed)
    rings = []
    for k in range(10):   # top -> bottom
        phi = R(86 - 86 * k / 9)
        rings.append((z0 + h * math.sin(phi), cy, rx * math.cos(phi), ry * math.cos(phi)))
    rings.append((z0 - 0.012 * Hs, cy, rx * 1.02, ry * 1.02))
    rings.append((z0 - 0.024 * Hs, cy, rx * 1.04, ry * 1.04))
    wm = fabric("woollen_cap", colour, 0.95, 0.7, pattern={"kind": "stripes", "c2": tuple(c * 0.82 for c in colour), "scale": 0.005, "lw": 0.5})
    o = lathe(B, "woollen_cap", wm, rings, segs=48, clear=0.003, thick=0.004, wfun=lambda co: {"head": 1.0}, close_top=True)
    tp = Vector((0, cy, rings[0][0] + 0.01))
    pp = rigid(B, "cap_pompom", solid("cap_pompom", pompom, 0.95), lambda bm: _ball(bm, tp, 0.018 * Hs / 1.0, sub=2), "head")
    return [o, pp]

# ----------------------------------------------------------------------------------------------- outfits
def _build(B, outfit, C, o):
    Hs = B.Hs; G = []
    if outfit == "jhabla":
        G.append(bottoms(B, "nappy", fabric("nappy", C["nappy"], 0.85, 0.3), B.zw + 0.01 * Hs, leg_t=0.2, style="shorts", offset=0.012, ease=0.016))
        pat = {"kind": "dots", "c2": C["print"], "scale": 0.03 * Hs, "r": 0.18}
        G.append(top(B, "jhabla_top", fabric("jhabla", C["jhabla"], 0.75, 0.3, pattern=pat), B.zh - 0.02 * Hs, sleeve_t=0.22, neck_depth=0.02 * Hs, neck_angle=25,
                     offset=0.009, loose=0.008, sleeve_loose=0.4, clear=0.007))
        rings = skirt_rings(B, B.zh, B.zk - 0.06 * Hs, flare=1.3, ease=0.022, top_ease=0.014)
        G.append(lathe(B, "jhabla_tail", fabric("jhabla_tail", C["jhabla"], 0.75, 0.3, pattern=pat, border={"c": C["print"], "mode": "v_hi", "w": 0.05}, coord="uv"),
                       rings, segs=96, pleats=10, amp=0.02))
        p = B.surf(0, B.zn - 0.02 * Hs, "front")   # neck tie bow
        if p is not None:
            tm = solid("jhabla_tie", C["tie"], 0.6)
            G.append(rigid(B, "jhabla_tie", tm, lambda bm: [_ball(bm, p + Vector((sd * 0.008 * Hs, -0.002, 0)), 0.008 * Hs, (1.3, 0.4, 0.7)) for sd in (1, -1)] + [_ball(bm, p + Vector((0, -0.003, -0.012 * Hs)), 0.004 * Hs, (0.6, 0.4, 2.2))],
                           wfun=lambda co: B.kd_weights(co, ("torso",), drop=("arm",))))
    elif outfit == "baby_romper":
        pat = {"kind": "stripes", "c2": C["stripe"], "scale": 0.02 * Hs, "lw": 0.3, "dir": "h"}
        G.append(bottoms(B, "romper_legs", fabric("romper_legs", C["romper"], 0.75, 0.3, pattern=pat), B.zw + 0.02 * Hs, leg_t=0.68, style="shorts", offset=0.01, ease=0.014))
        G.append(top(B, "romper_top", fabric("romper", C["romper"], 0.75, 0.3, pattern=pat), B.zx + 0.01 * Hs, sleeve_t=0.24, neck_depth=0.018 * Hs, neck_angle=25,
                     offset=0.008, sleeve_loose=0.25, clear=0.007))
        G.append(buttons(B, B.zn - 0.03 * Hs, B.zw, 4, C["snap"], name="romper_snaps"))
    elif outfit == "baby_frock":
        G.append(bottoms(B, "bloomers", fabric("bloomers", C["bloomers"], 0.8, 0.3), B.zw + 0.01 * Hs, leg_t=0.32, style="shorts", offset=0.01, ease=0.018))
        pat = {"kind": "dots", "c2": C["dots"], "scale": 0.03 * Hs, "r": 0.25}
        G.append(top(B, "frock_bodice", fabric("baby_frock", C["frock"], 0.6, 0.5, pattern=pat), B.zw - 0.02 * Hs, sleeve_t=0.2, neck_depth=0.02 * Hs, neck_angle=25,
                     offset=0.008, sleeve_loose=0.45, clear=0.007))
        rings = skirt_rings(B, B.zw + 0.005 * Hs, B.zk - 0.05 * Hs, flare=1.6, ease=0.016)
        G.append(lathe(B, "frock_skirt", fabric("baby_frock_skirt", C["frock"], 0.6, 0.5, pattern=pat, border={"c": C["dots"], "mode": "v_hi", "w": 0.06}, coord="uv"),
                       rings, segs=120, pleats=20, amp=0.06))
        G.append(waistband(B, B.zw + 0.022 * Hs, fabric("baby_sash", C["sash"], 0.6, 0.6), h=0.025 * Hs, ease=0.014, name="sash"))
        # no collar: lib_outfits.collar() sits on the neck ring, which on a toddler's short neck flares up under the chin
    elif outfit == "toddler_kurta_shorts":
        G.append(bottoms(B, "shorts", fabric("toddler_shorts", C["shorts"], 0.7, 0.3), B.zw + 0.01 * Hs, leg_t=0.58, style="shorts", offset=0.009, ease=0.014, clear=0.006))
        G.append(top(B, "kurta", fabric("toddler_kurta", C["kurta"], 0.65, 0.35), B.zh - 0.02 * Hs, sleeve_t=0.3, neck_depth=0.012 * Hs, neck_angle=25, offset=0.008,
                     sleeve_loose=0.25, loose=0.005, clear=0.007))
        rings = skirt_rings(B, B.zh, B.zx - 0.5 * (B.zx - B.zk), flare=1.12, ease=0.02, top_ease=0.012)
        G.append(lathe(B, "kurta_tail", fabric("toddler_kurta_tail", C["kurta"], 0.65, 0.35), rings, segs=96))
        G.append(buttons(B, B.zn - 0.025 * Hs, B.zc - 0.02 * Hs, 3, C["button"]))
    elif outfit == "toddler_shirt_shorts":
        sm = fabric("toddler_shirt", C["shirt"], 0.6, 0.3, pattern={"kind": "checks", "c2": C["check"], "scale": 0.016 * Hs})
        G.append(bottoms(B, "shorts", fabric("toddler_knee_shorts", C["shorts"], 0.7, 0.3), B.zw + 0.008 * Hs, leg_t=0.58, style="shorts", offset=0.009, ease=0.014, clear=0.006))
        G.append(top(B, "shirt", sm, B.zh - 0.03 * Hs, sleeve_t=0.27, neck_depth=0.014 * Hs, neck_angle=25, offset=0.008, sleeve_loose=0.25, clear=0.007))
        G.append(buttons(B, B.zn - 0.03 * Hs, B.zw + 0.02 * Hs, 4, (0.95, 0.95, 0.92)))
    elif outfit == "woollen_set":
        lm = fabric("leggings", C["leggings"], 0.95, 0.6, pattern={"kind": "stripes", "c2": tuple(c * 0.85 for c in C["leggings"]), "scale": 0.005, "lw": 0.5})
        G.append(bottoms(B, "leggings", lm, B.zw + 0.02 * Hs, leg_t=0.96, style="straight", offset=0.008, ease=0.01))
        G += LO._sweater(B, "pullover", C["sweater"])
        cap = woollen_cap(B, C["cap"], C["pompom"])
        if cap: G += cap
    else:
        raise KeyError(f"unknown kid outfit {outfit}; known: {sorted(OUTFITS)}")
    return G

def _accessories(B, o, G):
    for nm, fn in (("kaajal_dot", kaajal_dot), ("black_thread_anklet", black_thread_anklet), ("small_bangles", small_bangles), ("nazar_bracelet", nazar_bracelet)):
        if not o.get(nm): continue
        try:
            r = fn(B)
            if isinstance(r, list): G.extend(r)
            elif r is not None: G.append(r)
        except Exception as ex:
            import traceback; traceback.print_exc(); print("OUTFIT WARN kid accessory", nm, repr(ex)[:200])

def dress_kid(basemesh, rig, outfit, colours=None, seed=0, **opts):
    """remove the MPFB clothes, build the kid outfit + accessories (+ booties for woollen_set) and return the garment objects.
    Raises (never returns an empty / partial outfit) if a core piece is missing.
    opts: kaajal_dot, black_thread_anklet, small_bangles, nazar_bracelet (True/False), footwear ("barefoot"|"chappal"|"booties")."""
    if outfit not in OUTFITS: raise KeyError(f"unknown kid outfit {outfit}; known: {sorted(OUTFITS)}")
    random.seed(seed)
    LO.strip_clothes(basemesh, rig)
    pp = rig.data.pose_position; rig.data.pose_position = "REST"; bpy.context.view_layer.update()
    try:
        B = LO.body_of(basemesh, rig, refresh=True)
        C = _colours(outfit, colours, seed); o = _opts(outfit, opts)
        G = _build(B, outfit, C, o)
        G = [g for g in G if g is not None]
        names = {g.name.split(".")[0] for g in G}
        missing = [c for c in OUTFITS[outfit]["core"] if c not in names]
        if missing:
            for g in G: bpy.data.objects.remove(g, do_unlink=True)
            raise RuntimeError(f"kid outfit {outfit} is missing core pieces {missing}: refusing to return a partial outfit")
        _accessories(B, o, G)
        fw = o.get("footwear", OUTFITS[outfit].get("footwear", "barefoot"))
        if fw == "booties":
            bt = LO.footwear(basemesh, rig, "shoes", colour=C.get("booties", (0.95, 0.85, 0.55)), _body=B)
            wm = fabric("booties_wool", C.get("booties", (0.95, 0.85, 0.55)), 0.95, 0.7)
            for b in bt:
                b.data.materials.clear(); b.data.materials.append(wm)
            G += bt
        elif fw and fw != "barefoot":
            G += LO.footwear(basemesh, rig, fw, _body=B)
    finally:
        rig.data.pose_position = pp; bpy.context.view_layer.update()
    G = [g for g in G if g is not None]
    if not G: raise RuntimeError("dress_kid produced no garments: refusing to return an undressed child")
    for g in G: g["outfit"] = outfit
    basemesh["outfit"] = outfit
    print("OUTFIT built kid", outfit, "pieces", [g.name for g in G])
    return G

# ----------------------------------------------------------------------------------------------- carrying
def _arm(x):
    """accept a raw bpy armature object or a lib_anim rig wrapper (which has .arm)"""
    return getattr(x, "arm", x)

def _bone_world(rig, bn, at="head"):
    pb = rig.pose.bones[bn]
    return rig.matrix_world @ (pb.head if at == "head" else pb.tail if at == "tail" else (pb.head + pb.tail) / 2)

def carry_baby(adult_rig, baby_rig, side="left", mode="hip", offset=(0.0, 0.0, 0.0)):
    """Pose an MPFB adult carrying an MPFB baby/toddler and PARENT the baby to the adult so it follows every later move.
      mode="hip":  child sits on the adult's hip (side), legs straddling, facing the adult; adult's arm wraps under its bottom.
                   Baby is bone-parented to the adult's 'spine05' (pelvis) so walking keeps it on the hip.
      mode="arms": baby lies across both forearms, face up, head in the crook of the `side` elbow (newborn cradle).
                   Baby is bone-parented to the adult's 'lowerarm01.<side>'.
    offset: extra (x, y, z) metres in the adult's local frame to fine-tune contact. Call after both are dressed.
    Manual alternative (any pose): put the baby where you want it, then
        mw = baby.matrix_world.copy(); baby.parent = adult; baby.parent_type = 'BONE'; baby.parent_bone = 'lowerarm01.L'
        bpy.context.view_layer.update(); baby.matrix_world = mw
    Returns the baby rig."""
    A, Bb = _arm(adult_rig), _arm(baby_rig)
    sd = 1 if side.lower().startswith("l") else -1; s = "L" if sd > 0 else "R"; o_ = "R" if sd > 0 else "L"
    for rig in (A, Bb):
        rig.data.pose_position = "POSE"
    if Bb.parent is not None:
        mw = Bb.matrix_world.copy(); Bb.parent = None; Bb.matrix_world = mw
    bpy.context.view_layer.update()
    rot = LO._rot
    if mode == "hip":
        rot(A, f"upperarm01.{s}", "Y", sd * 32); rot(A, f"upperarm01.{s}", "X", -10)
        rot(A, f"lowerarm01.{s}", "X", -80); rot(A, f"lowerarm01.{s}", "Z", -sd * 30)
        rot(A, "spine04", "Y", -sd * 6)                       # lean away from the load
        rot(Bb, "upperleg01.L", "X", -65); rot(Bb, "upperleg01.R", "X", -65)
        rot(Bb, "upperleg01.L", "Y", -30); rot(Bb, "upperleg01.R", "Y", 30)
        rot(Bb, "lowerleg01.L", "X", 70); rot(Bb, "lowerleg01.R", "X", 70)
        rot(Bb, f"upperarm01.{o_}", "Y", (1 if o_ == "L" else -1) * 35)   # inner arm towards the adult
    else:
        for x, k in ((s, sd), (o_, -sd)):
            rot(A, f"upperarm01.{x}", "Y", k * 40); rot(A, f"upperarm01.{x}", "X", -35)
            rot(A, f"lowerarm01.{x}", "X", -75); rot(A, f"lowerarm01.{x}", "Z", -k * 35)
        rot(Bb, "upperleg01.L", "X", -35); rot(Bb, "upperleg01.R", "X", -35)
        rot(Bb, "lowerleg01.L", "X", 40); rot(Bb, "lowerleg01.R", "X", 40)
    bpy.context.view_layer.update()
    AR = A.matrix_world.to_3x3().normalized()
    X, Y, Z = AR @ Vector((1, 0, 0)), AR @ Vector((0, 1, 0)), AR @ Vector((0, 0, 1))
    if mode == "hip":
        face = (-sd * X - 0.7 * Y).normalized()                # towards the adult's front-centre
        bz = Z; by = -face; bx = by.cross(bz).normalized(); by = bz.cross(bx)
        mid = _bone_world(A, f"lowerarm01.{s}", "mid")
        target = mid + Z * 0.04 + sd * X * 0.02
    else:
        bz = sd * X; by = -Z; bx = by.cross(bz).normalized()   # head towards `side`, face up
        target = (_bone_world(A, f"lowerarm01.{s}", "mid") + _bone_world(A, f"lowerarm01.{o_}", "mid")) / 2 + Z * 0.05
    target += AR @ Vector(offset)
    M3 = Matrix((bx, by, bz)).transposed()
    sc = Bb.matrix_world.to_scale()
    Bb.matrix_world = Matrix.Translation(Vector((0, 0, 0))) @ M3.to_4x4() @ Matrix.Diagonal((*sc, 1))
    bpy.context.view_layer.update()
    pel = (_bone_world(Bb, "upperleg01.L") + _bone_world(Bb, "upperleg01.R")) / 2
    if mode == "arms": pel = (pel + _bone_world(Bb, "spine03")) / 2   # cradle at the middle of the back
    Bb.matrix_world = Matrix.Translation(target - pel) @ Bb.matrix_world
    bpy.context.view_layer.update()
    pb = "spine05" if mode == "hip" else f"lowerarm01.{s}"
    if pb not in A.pose.bones: pb = next(b for b in ("pelvis", "spine05", "root") if b in A.pose.bones)
    mw = Bb.matrix_world.copy()
    Bb.parent = A; Bb.parent_type = "BONE"; Bb.parent_bone = pb
    bpy.context.view_layer.update(); Bb.matrix_world = mw; bpy.context.view_layer.update()
    print("CARRY", mode, side, "parent", pb)
    return Bb
