"""episode_scene.py - build (and render) one scene of a Sonpur episode from a SCENE JSON. Generic: the story, the lines
and the timings live only in the (private) scene JSON; this file only knows how to stage what the JSON asks for.

BUILD (+ coverage check, + optional stills / full render):
  blender -b -noaudio --python episode_scene.py -- <scene.json> --pack <mpfb_pack_dir> --functional <dir> --out <dir>
          [--save scene.blend] [--stills 1,200,640] [--render] [--engine eevee|cycles] [--standin]
RENDER ONLY (from a saved build; frames that failed the coverage check are never rendered):
  blender -b scene.blend --python episode_scene.py -- <scene.json> --render-only --out <dir> --engine cycles [--range 1:800] [--frames 5,9]

Scene JSON (coordinates are SET-LOCAL: the set's own layout before lib_props centring; z may be "@top:<object>[+dz]"):
  fps, frames [f0, f1], resolution [w, h], light (lib_camera preset), samples
  set        {lib, name, ref_mark, ref_local}           e.g. lib_props3 / dadi_aangan / "charpai" / [-2.9, 0.2, 0.06]
  set_edits  [{find, loc?, rot_z?, hide?}]               move / turn / hide parts of the set (names end with ".<find>")
  props      [{id, kind: asset|shelf|room|ground|cloth_dome, ...}]
  characters [{id, body, outfit, extras?, opts?, colours?, loc, rot_z, standin_height?}]   villager.make_villager
  attach     [{id, lib, name, on, where: head_top, tilt, fwd, dz, scale}]
  animals    [{id, kind: chamki|sheru, loc, rot_z, size?}]                                  lib_animals
  actions    [{t: seat|pose|move|talk|expr|blinks|gesture|lie_down|hold|show|glint|fx_mark|fx_zzz|
                  animal_play|animal_sleep|animal_walk|animal_turn|animal_expr|animal_blinks|animal_chew, ...}]
             hand-object (lib_handobj: arm IK + grip + Child Of + solved contact, logged as "EPISODE HANDOBJ"):
               count_objects {who, hand, container, objs[child names in pick order], ring{radius, z, start_deg}, line_frame,
                              word_times[s] (explicit counts), ff_times[s0, s1] (fast-forward the rest), pat_times[s], blend[4], steady}
               hand_pick_place {who, hand, obj (+container), to | to_local, frames{hover, grab, place, off[, mid]}}
               carry_to {who, obj, f_grab, f_lift, f_place, f_release, place, carry[fwd, up]}     two hands, e.g. thali -> shelf
               hand_give / hand_eat: documented stubs
  props[].rest_on {who, frame, parts, radius, gap, tilt_x}: the prop sits on that character (a thali on Dadi's lap)
  shots      [{name, f0, f1, cam: {aim, dist, az, h, lens} | {loc, aim, lens}, end?: {...}}]
     aim = [x, y, z] | {who, seg, dz} | {obj, dz} | {animal, dz};  az = degrees around the aim, 0 = from the front (-Y)
"""
import bpy, sys, os, json, math, time, traceback, importlib
from mathutils import Vector, Matrix, Euler

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
R = math.radians
ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default=None):
    if name in ARGV:
        i = ARGV.index(name)
        return ARGV[i + 1] if i + 1 < len(ARGV) and not ARGV[i + 1].startswith("--") else True
    return default


SCENE_PATH = os.path.abspath(ARGV[0])
SDIR = os.path.dirname(SCENE_PATH)
S = json.load(open(SCENE_PATH, encoding="utf-8-sig"))
OUT = os.path.abspath(opt("--out", "episode_out")); os.makedirs(OUT, exist_ok=True)
STANDIN = bool(opt("--standin", False))
T0 = time.time()
ERRORS = []


def log(*a):
    print("EPISODE", f"[{time.time() - T0:7.1f}s]", *a, flush=True)


def err(where, ex):
    ERRORS.append(f"{where}: {ex!r}"[:400]); log("ERROR", where, repr(ex)[:300]); traceback.print_exc()


sc = bpy.context.scene


# ------------------------------------------------------------------------------------------------ render setup
def setup_engine(engine, samples=None):
    r = sc.render
    r.resolution_x, r.resolution_y = S.get("resolution", [1280, 720]); r.resolution_percentage = 100
    r.fps = S.get("fps", 24); r.fps_base = 1.0
    r.image_settings.file_format = "JPEG"; r.image_settings.quality = 92
    sc.view_settings.view_transform = "Standard"
    try: sc.view_settings.look = "None"
    except Exception: pass
    if engine == "cycles":
        r.engine = "CYCLES"
        try:
            pr = bpy.context.preferences.addons["cycles"].preferences
            for kind in ("OPTIX", "CUDA"):
                try:
                    pr.compute_device_type = kind; pr.get_devices()
                    devs = [d for d in pr.devices if d.type == kind]
                    if devs:
                        for d in pr.devices: d.use = d.type == kind
                        log("CYCLES device", kind, [d.name for d in devs]); break
                except Exception as ex: log("no", kind, ex)
            sc.cycles.device = "GPU"
        except Exception as ex: log("cycles prefs", ex)
        sc.cycles.samples = int(samples or S.get("samples", 32)); sc.cycles.use_denoising = True
        sc.render.use_persistent_data = True
        # OptiX denoiser fails on Kaggle T4 ("Failed to create OptiX denoiser") -> every frame errors. OIDN works everywhere.
        sc.cycles.denoiser = "OPENIMAGEDENOISE"
        sc.cycles.max_bounces = 4; sc.cycles.transparent_max_bounces = 16
        try: sc.cycles.use_adaptive_sampling = True
        except Exception: pass
    else:
        names = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
        r.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in names else "BLENDER_EEVEE"
        try: sc.eevee.taa_render_samples = int(samples or S.get("eevee_samples", 24))
        except Exception: pass
        for a, v in (("use_gtao", True), ("use_shadows", True), ("shadow_ray_count", 2), ("shadow_step_count", 4)):
            try: setattr(sc.eevee, a, v)
            except Exception: pass
    log("ENGINE", r.engine)


def render_frames(frames, prefix="f_"):
    done = 0; t = time.time()
    for f in frames:
        path = os.path.join(OUT, f"{prefix}{f:05d}.jpg")
        if os.path.exists(path) and os.path.getsize(path) > 1000: continue
        sc.frame_set(f); sc.render.filepath = path
        bpy.ops.render.render(write_still=True); done += 1
        if done % 25 == 1: log("RENDERED", f, f"{(time.time() - t) / done:.2f}s/frame")
    log("RENDER DONE", done, "frames", f"{time.time() - t:.0f}s")


def frame_list():
    al = json.load(open(os.path.join(OUT if os.path.exists(os.path.join(OUT, "allowed.json")) else SDIR, "allowed.json")))["allowed"] \
        if opt("--allowed") is None else json.load(open(opt("--allowed")))["allowed"]
    if opt("--frames"): return [f for f in (int(x) for x in str(opt("--frames")).split(",")) if f in al]
    if opt("--range"):
        a, b = (int(x) for x in str(opt("--range")).split(":")); return [f for f in al if a <= f <= b]
    return al


if opt("--render-only"):
    setup_engine(opt("--engine", "cycles"), opt("--samples"))
    render_frames(frame_list())
    sys.exit(0)

# ================================================================================================ BUILD
import lib_fx as FX
import lib_anim as A
import lib_camera as CAM
import lib_props2 as L2

for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)   # empty start (keeps extensions loaded)
sc = bpy.context.scene
F0, F1 = S.get("frames", [1, 240]); sc.frame_start, sc.frame_end = F0, F1
setup_engine(opt("--engine", "eevee"), opt("--samples"))

# ---------------- sets ("set" = one set at the origin; "sets" = several, each placed at its own world offset "at")
def descendants(o):
    out, st = [], list(o.children)
    while st:
        c = st.pop(); out.append(c); st.extend(c.children)
    return out


SETS = S.get("sets") or [dict(S["set"], id="main")]
SETROOT, SETOBJS, OFFS = {}, {}, {}
for st_ in SETS:
    sid = st_.get("id", st_["name"])
    try:
        mod = importlib.import_module(st_["lib"]); root = mod.BUILDERS[st_["name"]](sid)
        root.location = Vector(st_.get("at", [0, 0, 0])); root.rotation_euler = (0, 0, R(st_.get("rot_z", 0)))
        bpy.context.view_layer.update()
        SETROOT[sid] = root; SETOBJS[sid] = descendants(root)
        ref = None
        if st_.get("ref_mark"):
            ref = next((o for o in SETOBJS[sid] if o.name.endswith(".mark_" + st_["ref_mark"])), None)
        OFFS[sid] = (ref.matrix_world.translation - Vector(st_["ref_local"])) if ref else Vector(st_.get("at", [0, 0, 0]))
        log("SET", sid, st_["name"], "objects", len(SETOBJS[sid]), "offset", tuple(round(v, 3) for v in OFFS[sid]))
    except Exception as ex:
        err("set " + sid, ex); OFFS[sid] = Vector(st_.get("at", [0, 0, 0])); SETOBJS[sid] = []
DEFAULT_SET = SETS[0].get("id", SETS[0]["name"])
OFF = OFFS[DEFAULT_SET]


def find(key, sid=None):
    pools = [SETOBJS[sid]] if sid in SETOBJS else list(SETOBJS.values())
    for pool in pools:
        for o in pool:
            if o.name.endswith("." + key) or o.name == key: return o
    return bpy.data.objects.get(key)


def bbox(o):
    objs = [o] + descendants(o)
    lo = Vector((1e9,) * 3); hi = Vector((-1e9,) * 3)
    for x in objs:
        if x.type != "MESH": continue
        for c in x.bound_box:
            p = x.matrix_world @ Vector(c); lo = Vector(map(min, lo, p)); hi = Vector(map(max, hi, p))
    return lo, hi


def zval(z, sid=None):
    """number (set-local) -> world z;  '@top:<name>[+-dz]' -> world top of that object (+dz)"""
    if isinstance(z, str) and z.startswith("@top:"):
        body = z[5:]; dz = 0.0
        for sgn in ("+", "-"):
            if sgn in body[1:]:
                k = body.rindex(sgn); dz = float(body[k:]); body = body[:k]; break
        o = PROPS.get(body) or find(body, sid)
        bpy.context.view_layer.update()
        return bbox(o)[1].z + dz
    return float(z) + OFFS.get(sid, OFF).z


def P(p):
    """[x, y, z(, set_id)] in that set's local layout -> world"""
    sid = p[3] if len(p) > 3 else DEFAULT_SET
    o = OFFS.get(sid, OFF)
    return Vector((p[0] + o.x, p[1] + o.y, zval(p[2], sid) if len(p) > 2 else o.z))


PROPS = {}
for e in S.get("set_edits", []):
    try:
        o = find(e["find"], e.get("set"))
        if o is None: log("set_edit: not found", e["find"]); continue
        bpy.context.view_layer.update()
        if "loc" in e:
            w = P(e["loc"]); M = o.matrix_world.copy(); M.translation = w
            o.matrix_world = M
        if "rot_z" in e: o.rotation_euler.z = R(e["rot_z"])
        if e.get("hide"):
            for x in [o] + descendants(o): x.hide_render = True; x.hide_viewport = True
    except Exception as ex: err("set_edit " + str(e.get("find")), ex)

# ---------------- light
try:
    if S.get("lights"):            # [[frame, preset], ...] time-of-day changes at scene cuts
        for f, nm in S["lights"]:
            CAM.light_preset(nm, frame=f)
            if f > F0: CAM.light_preset(prev, frame=f - 1); CAM.light_preset(nm, frame=f)
            prev = nm
    else:
        CAM.light_preset(S.get("light", "morning"))
except Exception as ex: err("light", ex)


# ---------------- props
def mat(name, rgb, rough=0.7):
    m = bpy.data.materials.get(name)
    if m: return m
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    lin = tuple(c ** 2.2 for c in rgb[:3])
    b.inputs["Base Color"].default_value = (*lin, 1); b.inputs["Roughness"].default_value = rough
    m.diffuse_color = (*lin, 1)
    return m


def box(name, size, loc, m, parent=None):
    import bmesh
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Diagonal((*size, 1)))
    bm.to_mesh(me); bm.free(); me.materials.append(m)
    o = bpy.data.objects.new(name, me); sc.collection.objects.link(o); o.location = loc
    if parent: o.parent = parent
    return o


def dome(name, r, h, m):
    import bmesh
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=12, radius=1.0)
    for v in list(bm.verts):
        if v.co.z < -0.05: bm.verts.remove(v)
    for v in bm.verts:
        v.co = Vector((v.co.x * r * (1 + 0.15 * max(0, 0.3 - v.co.z)), v.co.y * r * (1 + 0.15 * max(0, 0.3 - v.co.z)), max(0.0, v.co.z) * h))
    bm.to_mesh(me); bm.free(); me.materials.append(m)
    for p in me.polygons: p.use_smooth = True
    o = bpy.data.objects.new(name, me); sc.collection.objects.link(o)
    md = o.modifiers.new("thick", "SOLIDIFY"); md.thickness = 0.004
    return o


for p in S.get("props", []):
    try:
        k = p.get("kind", "asset"); pid = p["id"]
        if k == "asset":
            mod = importlib.import_module(p["lib"]); o = mod.BUILDERS[p["name"]](pid)
            o.location = P(p["loc"]); o.rotation_euler = (0, 0, R(p.get("rot_z", 0))); s = p.get("scale", 1.0); o.scale = (s, s, s)
        elif k == "shelf":   # two posts + a plank (+ a back board): a tall wooden rack
            o = bpy.data.objects.new(pid, None); sc.collection.objects.link(o); o.location = P(p["loc"]); o.rotation_euler = (0, 0, R(p.get("rot_z", 0)))
            w, d = p.get("size", [0.6, 0.3]); top = p["top"]; wood = mat("ep_wood", p.get("color", [0.55, 0.36, 0.2]))
            for sx in (-1, 1): box(f"{pid}_post{sx}", (0.06, 0.06, top + 0.25), (sx * (w / 2 - 0.03), d / 2 - 0.03, (top + 0.25) / 2), wood, o)
            box(f"{pid}_plank", (w, d, 0.035), (0, 0, top - 0.0175), wood, o)
            box(f"{pid}_lower", (w, d, 0.03), (0, 0, top * 0.45), wood, o)
            box(f"{pid}_back", (w, 0.02, 0.3), (0, d / 2 - 0.01, top + 0.12), wood, o)
        elif k == "room":    # open-front dark room behind a doorway: back, floor, ceiling, sides
            o = bpy.data.objects.new(pid, None); sc.collection.objects.link(o); o.location = P(p["loc"])
            w, d, h = p["size"]; m = mat("ep_room_" + pid, p.get("color", [0.16, 0.11, 0.08]), 0.95)
            box(pid + "_back", (w, 0.05, h), (0, d, h / 2), m, o); box(pid + "_floor", (w, d, 0.04), (0, d / 2, -0.02), mat("ep_room_floor", p.get("floor", [0.42, 0.3, 0.2])), o)
            box(pid + "_ceil", (w, d, 0.05), (0, d / 2, h), m, o)
            for sx in (-1, 1): box(f"{pid}_side{sx}", (0.05, d, h), (sx * w / 2, d / 2, h / 2), m, o)
        elif k == "ground":
            s = p.get("size", 160.0); o = box(pid, (s, s, 0.02), P([0, 0, p.get("z", -0.012)]), mat("ep_ground", p.get("color", [0.55, 0.5, 0.32]), 0.95))
        elif k == "cloth_dome":
            o = dome(pid, p["radius"], p["height"], mat("ep_cloth_" + pid, p.get("color", [0.85, 0.15, 0.15]), 0.85))
            par = PROPS.get(p.get("parent"))
            if par: o.parent = par; o.location = Vector(p.get("offset", [0, 0, 0]))
            else: o.location = P(p["loc"])
        elif k == "ball":
            import bmesh
            me = bpy.data.meshes.new(pid); bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=20, v_segments=12, radius=p["radius"])
            bm.to_mesh(me); bm.free(); me.materials.append(mat("ep_ball_" + pid, p.get("color", [0.95, 0.7, 0.25]), 0.8))
            for pl in me.polygons: pl.use_smooth = True
            o = bpy.data.objects.new(pid, me); sc.collection.objects.link(o); o.location = P(p["loc"])
            if p.get("squash"): o.scale = (1, 1, p["squash"])
        else:
            log("unknown prop kind", k); continue
        PROPS[pid] = o
    except Exception as ex: err("prop " + str(p.get("id")), ex)
log("PROPS", list(PROPS))

# ---------------- characters
CH = {}
if not STANDIN:
    import villager as VL
    VL.setup(opt("--pack"), opt("--functional"))
import lib_outfits as LO

for c in S.get("characters", []):
    cid = c["id"]
    try:
        if STANDIN:
            rig, info = A.make_character("doll", name=cid, height=c.get("standin_height", 1.2), girl=c.get("standin_girl", False))
            h = None; arm = rig.arm
        else:
            try:
                h, arm = VL.make_villager(c["body"], c["outfit"], colours=c.get("colours"), extras=c.get("extras", []), name=cid, seed=c.get("seed", 0), **c.get("opts", {}))
            except Exception as ex:
                err(f"make_villager {cid} (toon)", ex)
                h, arm = VL.make_villager(c["body"], c["outfit"], colours=c.get("colours"), extras=c.get("extras", []), name=cid, toon=False, seed=c.get("seed", 0), **c.get("opts", {}))
            rig = A.Rig(arm)
        arm.location = P(c["loc"]); arm.rotation_euler = (0, 0, R(c.get("rot_z", 0)))
        bpy.context.view_layer.update()
        CH[cid] = {"h": h, "arm": arm, "rig": rig, "spec": c, "anchor": None}
        log("CHARACTER", cid, "height", round(h.dimensions.z, 3) if h else "standin", "faces", len(rig.face_keys()))
    except Exception as ex: err("character " + cid, ex)


def head_anchor(cid):
    """world-aligned empty that follows the head bone (FX marks, zzz)"""
    ch = CH[cid]
    if ch["anchor"]: return ch["anchor"]
    rig = ch["rig"]; bn = rig.map["head"][0]
    e = bpy.data.objects.new(cid + "_head_anchor", None); sc.collection.objects.link(e); e.empty_display_size = 0.05
    cn = e.constraints.new("COPY_LOCATION"); cn.target = rig.arm; cn.subtarget = bn; cn.head_tail = 1.0
    ch["anchor"] = e
    return e


# ---------------- attachments (hero props on a character)
for a in S.get("attach", []):
    try:
        ch = CH[a["on"]]; arm = ch["arm"]; rig = ch["rig"]
        if a.get("of"): o = PROPS[a["of"]]                     # an already-built prop
        else: mod = importlib.import_module(a["lib"]); o = mod.BUILDERS[a["name"]](a["id"])
        s = a.get("scale", 1.0); o.scale = (s, s, s)
        pp = arm.data.pose_position; arm.data.pose_position = "REST"; bpy.context.view_layer.update()
        Mi = arm.matrix_world.inverted()
        hb = arm.data.bones[rig.map["head"][0]]
        hc = (hb.head_local + hb.tail_local) / 2
        top = -1e9
        meshes = [ch["h"]] if ch["h"] else []
        meshes += [m for m in arm.children_recursive if m.type == "MESH" and "hair" in m.name.lower()]
        for m in meshes:
            dg = bpy.context.evaluated_depsgraph_get(); ev = m.evaluated_get(dg); me = ev.to_mesh()
            for v in me.vertices:
                q = Mi @ (m.matrix_world @ v.co)
                if abs(q.x - hc.x) < 0.06 and abs(q.y - hc.y) < 0.08: top = max(top, q.z)
            ev.to_mesh_clear()
        if top < -1e8: top = rig.head_top
        local = Vector((hc.x, hc.y - a.get("fwd", 0.03), top + a.get("dz", -0.01)))
        if a.get("where") == "mouth" and ch["h"] is not None:      # front of the face, just under the nose
            dg = bpy.context.evaluated_depsgraph_get(); ev = ch["h"].evaluated_get(dg); me = ev.to_mesh()
            hz = [Mi @ (ch["h"].matrix_world @ v.co) for v in me.vertices]; ev.to_mesh_clear()
            near = [q for q in hz if abs(q.x - hc.x) < 0.02 and hc.z - 0.07 < q.z < hc.z - 0.02]
            if near:
                fr_ = min(near, key=lambda q: q.y); local = Vector((hc.x, fr_.y - 0.004, fr_.z + a.get("dz", 0.0)))
        o.matrix_world = arm.matrix_world @ Matrix.Translation(local) @ Euler((R(a.get("tilt", -65)), 0, 0)).to_matrix().to_4x4() @ Matrix.Diagonal((s, s, s, 1))
        bpy.context.view_layer.update()
        A.attach(o, rig, a.get("seg", "head"))
        arm.data.pose_position = pp; bpy.context.view_layer.update()
        PROPS[a["id"]] = o
        log("ATTACH", a["id"], "on", a["on"], "head top z(local)", round(top, 3))
    except Exception as ex: err("attach " + str(a.get("id")), ex)

# ---------------- animals
AN = {}
try:
    import lib_animals as LA
except Exception as ex:
    LA = None; err("import lib_animals", ex)
for a in S.get("animals", []):
    try:
        mk = LA.make_chamki if a["kind"] == "chamki" else LA.make_sheru
        root, arm = mk(loc=tuple(P(a["loc"])), rot_z=a.get("rot_z", 0), name=a["id"], size=a.get("size", 1.0))
        AN[a["id"]] = {"root": root, "arm": arm}
        log("ANIMAL", a["id"], "ok")
    except Exception as ex: err("animal " + a["id"], ex)

# ---------------- camera (ONE camera for the whole scene: billboards face it)
CAMO = CAM.camera((0, -10, 2), (0, 0, 1), 35, name="EP_cam")
sc.camera = CAMO
CAMO.data.clip_start = 0.05; CAMO.data.sensor_width = 36


# ---------------- actions
def seated(rig, seat_z):
    d = A.sit_height_drop(rig, seat_z)
    return {"hips": {"loc": (-0.04, 0, -d)}, "thigh_L": {"aim": (1, 0.12, -0.02)}, "thigh_R": {"aim": (1, 0.12, -0.02)},
            "shin_L": {"aim": (0.08, 0.05, -1)}, "shin_R": {"aim": (0.08, 0.05, -1)}, "spine": {"fwd": 4},
            "arm_L": {"aim": (0.45, 0.3, -0.8)}, "arm_R": {"aim": (0.45, 0.3, -0.8)}, "forearm_L": {"fwd": 25}, "forearm_R": {"fwd": 25}}


def half_seated(rig, seat_z):
    d = A.sit_height_drop(rig, seat_z)
    return {"hips": {"loc": (-0.02, 0, -d * 0.5)}, "spine": {"fwd": 25}, **A.leg_ik(rig, "L", 0.03, 0, d * 0.5), **A.leg_ik(rig, "R", 0.03, 0, d * 0.5)}


def seat_rel(ch, seat):
    return zval(seat) - ch["arm"].location.z


def tup(spec):
    """JSON lists -> tuples inside a pose dict"""
    return {k: {kk: (tuple(vv) if isinstance(vv, list) else vv) for kk, vv in v.items()} for k, v in spec.items()}


def key_interp(obj, frame, mode):
    for fc in FX.fcurves(obj):
        for kp in fc.keyframe_points:
            if abs(kp.co.x - frame) < 0.5: kp.interpolation = mode


def anim_target(a):
    return AN[a["who"]]["arm"]


def do_action(a):
    t = a["t"]
    if t in ("seat", "pose", "move", "talk", "expr", "blinks", "gesture", "lie_down", "fx_mark", "fx_zzz", "anim"):
        ch = CH[a["who"]]; rig = ch["rig"]; arm = ch["arm"]
    if t == "seat":
        A._seq(rig, a["frame"], [(0, seated(rig, seat_rel(ch, a["seat"])))])
    elif t == "pose":
        cache = {}
        for k in a["keys"]:
            f, pose = k[0], tup(k[1]); base = k[2] if len(k) > 2 else a.get("base", "stand")
            if base in ("seated", "half"):
                key = (base, a.get("seat"))
                if key not in cache: cache[key] = (seated if base == "seated" else half_seated)(rig, seat_rel(ch, a["seat"]))
                b = cache[key]
            elif base == "lying":      # on the back (put the rig on the bed first with a 'move')
                lie = rig.hip_z - 0.09 * rig.leg_len
                b = {"hips": {"loc": (0, 0, -lie), "fwd": -90}, "arm_L": {"aim": (0.3, 0.6, -0.75)}, "arm_R": {"aim": (0.3, 0.6, -0.75)}, "head": {"fwd": 8}}
            elif base == "crouch":
                d = 0.14 * rig.leg_len
                b = {"hips": {"loc": (0, 0, -d)}, "spine": {"fwd": 22}, **A.leg_ik(rig, "L", 0.02, 0, d), **A.leg_ik(rig, "R", 0.02, 0, d)}
            else: b = None
            if a.get("layer"): A._seq(rig, f, [(0, pose)], layer=True)
            else: A._seq(rig, f, [(0, pose)], base=b)
    elif t == "move":
        for k in a["keys"]:
            f, loc = k[0], k[1]; rz = k[2] if len(k) > 2 else None
            arm.location = P(loc); arm.keyframe_insert("location", frame=f)
            if rz is not None: arm.rotation_euler = (0, 0, R(rz)); arm.keyframe_insert("rotation_euler", frame=f)
            if len(k) > 3 and k[3]: key_interp(arm, f, k[3])
            elif a.get("interp"): key_interp(arm, f, a["interp"])
    elif t == "talk":
        A.talk(rig, a["frame"], rhubarb_json=os.path.join(SDIR, a["rhubarb"]), strength=a.get("strength", 1.0), head_bob=a.get("head_bob", False))
    elif t == "expr":
        A.expression(rig, a["name"], a["frame"], a.get("end"), weight=a.get("weight", 1.0))
    elif t == "blinks":
        A.blink_loop(rig, a["f0"], a["f1"], seed=a.get("seed", 0))
    elif t == "gesture":
        A.gesture(rig, a["name"], a["frame"], hold=a.get("hold", 24))
    elif t == "lie_down":
        A.lie_down(rig, a["frame"], breathe_to=a.get("until"), on=a.get("on", "back"))
    elif t == "fx_mark":
        FX.mark(a.get("kind", "?"), head_anchor(a["who"]), a["frame"], a.get("end"), size=a.get("size", 1.0), offset=tuple(a.get("offset", (0, 0, 0.32))))
    elif t == "fx_zzz":
        FX.zzz(head_anchor(a["who"]), a["f0"], a["f1"], size=a.get("size", 1.0))
    elif t == "show":
        o = PROPS[a["obj"]]; s = o.scale.copy(); f = a["frame"]
        o.scale = (0.001,) * 3
        for ff in sorted({F0, max(F0, f - 1)}): o.keyframe_insert("scale", frame=ff)
        o.scale = s * 1.15; o.keyframe_insert("scale", frame=f + a.get("dur", 6) - 2)
        o.scale = s; o.keyframe_insert("scale", frame=f + a.get("dur", 6))
    elif t == "hide":
        o = PROPS[a["obj"]]; f = a["frame"]
        s = o.scale.copy(); o.keyframe_insert("scale", frame=max(F0, f - 1))
        o.scale = (0.001,) * 3; o.keyframe_insert("scale", frame=f); key_interp(o, max(F0, f - 1), "CONSTANT")
        o.scale = s
    elif t == "obj_move":           # keys [[frame, [x,y,z(,set)], rot_z?], ...]
        o = PROPS[a["obj"]]
        for k in a["keys"]:
            o.location = P(k[1]); o.keyframe_insert("location", frame=k[0])
            if len(k) > 2: o.rotation_euler.z = R(k[2]); o.keyframe_insert("rotation_euler", index=2, frame=k[0])
            if a.get("interp"): key_interp(o, k[0], a["interp"])
    elif t == "anim":                # any lib_anim helper: fn(rig, **args); point-like args are converted to world
        args = dict(a.get("args", {}))
        for kk in list(args):
            if kk.endswith("_world") and isinstance(args[kk], list): args[kk] = tuple(P(args[kk]))
            elif isinstance(args[kk], list): args[kk] = tuple(args[kk])
        getattr(A, a["fn"])(rig, **args)
    elif t == "fx":                  # lib_fx effect anchored on a head: fn(anchor, **args)
        tgt = head_anchor(a["who"]) if a.get("who") in CH else (LA.head_of(AN[a["animal"]]["arm"]) if a.get("animal") else P(a["at"]))
        getattr(FX, a["fn"])(tgt, **a.get("args", {}))
    elif t == "animal_move":         # root keys (teleports between sets: CONSTANT)
        root = AN[a["who"]]["root"]
        for k in a["keys"]:
            root.location = P(k[1]); root.keyframe_insert("location", frame=k[0])
            if len(k) > 2: root.rotation_euler.z = R(k[2]); root.keyframe_insert("rotation_euler", index=2, frame=k[0])
            key_interp(root, k[0], a.get("interp", "CONSTANT"))
    elif t == "torch":
        fo = A.follower(CH[a["who"]]["rig"], a.get("seg", "hand_R"))
        lo = CAM.torch(fo, energy=a.get("energy", 60.0))
        for f, e in a.get("energy_keys", []):
            lo.data.energy = e; lo.data.keyframe_insert("energy", frame=f); key_interp(lo.data, f, "CONSTANT")
    elif t == "glint":
        L2.glint(PROPS[a["obj"]], a["frame"], a.get("length", 8))
    elif t == "animal_play":
        LA.play(anim_target(a), a["action"], a["frame"], loops=a.get("loops", 1), speed=a.get("speed", 1.0), overlay=a.get("overlay"))
    elif t == "animal_sleep":
        LA.sleep(anim_target(a), a["f0"], a["f1"], zzz=a.get("zzz", True))
    elif t == "animal_walk":
        LA.walk_along(anim_target(a), [P(p) for p in a["points"]], speed=a.get("speed"), start_frame=a["frame"], action=a.get("action", "walk"),
                      settle=a.get("settle", "idle"))
    elif t == "animal_turn":
        root = AN[a["who"]]["root"]; f = a["frame"]
        fc = next((c for c in FX.fcurves(root) if c.data_path == "rotation_euler" and c.array_index == 2), None)
        z0 = fc.evaluate(f) if fc else root.rotation_euler.z
        z1 = R(a["rot_z"])
        while z1 - z0 > math.pi: z1 -= 2 * math.pi
        while z1 - z0 < -math.pi: z1 += 2 * math.pi
        root.rotation_euler.z = z0; root.keyframe_insert("rotation_euler", index=2, frame=f)
        root.rotation_euler.z = z1; root.keyframe_insert("rotation_euler", index=2, frame=f + a.get("dur", 10))
    elif t == "animal_expr":
        LA.expression(anim_target(a), a["name"], a["frame"], hold=a.get("hold", 24))
    elif t == "animal_blinks":
        LA.blink_loop(anim_target(a), a["f0"], a["f1"], seed=a.get("seed", 0))
    elif t == "animal_chew":
        LA.chew(anim_target(a), a["f0"], a["f1"])
    else:
        log("unknown action", t)


def do_hold(a):
    """hold contact: the object follows a hand from f_grab (blend in) until f_release, then rests at `place`.
    Copy Location only, so a plate stays level."""
    o = PROPS[a["obj"]]
    fg, fr = a["f_grab"], a["f_release"]; bi, bo = a.get("blend_in", 4), a.get("blend_out", 5)
    sc.frame_set(fg); bpy.context.view_layer.update()
    sock = bpy.data.objects.new(a["obj"] + f"_socket_{fg}", None); sc.collection.objects.link(sock); sock.empty_display_size = 0.05
    start = o.matrix_world.translation.copy()
    off = Vector(a.get("offset", [0, 0, 0]))
    if a.get("animal"):              # held in an animal's mouth (follows its head)
        hd = LA.head_of(AN[a["animal"]]["arm"]); hw = hd.matrix_world.translation.copy()
        sock.location = hw + off if a.get("snap") == "hand" else start
        mw = sock.matrix_world.copy(); sock.parent = hd; sock.matrix_world = mw
    else:
        rig = CH[a["who"]]["rig"]
        hand = rig.map[a.get("seg", "hand_R")][-1]
        pb = rig.arm.pose.bones[hand]; hw = rig.arm.matrix_world @ pb.tail
        sock.location = start if a.get("snap", "object") == "object" else hw + off
        A.attach(sock, rig, a.get("seg", "hand_R"))
    cn = o.constraints.new("COPY_LOCATION"); cn.target = sock; cn.name = f"hold_{fg}"
    for f, v in ((F0, 0.0), (fg - bi, 0.0), (fg, 1.0), (fr, 1.0), (fr + bo, 0.0)):
        if f == F0 and fg - bi <= F0: continue
        cn.influence = v; cn.keyframe_insert("influence", frame=max(F0, f))
    if a.get("place") is not None:
        o.location = start; o.keyframe_insert("location", frame=max(F0, fr - 1))
        o.location = P(a["place"]); o.keyframe_insert("location", frame=fr)
        key_interp(o, max(F0, fr - 1), "CONSTANT")
    log("HOLD", a["obj"], "grab", fg, "release", fr, "hand at grab", tuple(round(x, 2) for x in hw), "object at grab", tuple(round(x, 2) for x in start))


def rest_on_props():
    """props with "rest_on": {who, frame, parts?, radius?, gap?} sit on that character (e.g. a thali on Dadi's lap): the prop's
    origin z is set to the highest vertex of the named garment/body parts inside its footprint, at that (posed) frame"""
    for p in S.get("props", []):
        ro = p.get("rest_on")
        if not ro or p["id"] not in PROPS: continue
        try:
            o = PROPS[p["id"]]; ch = CH[ro["who"]]; sc.frame_set(ro.get("frame", F0)); bpy.context.view_layer.update()
            parts = ro.get("parts", ["skirt", "pleats"]); rad = ro.get("radius", 0.1)
            c = o.matrix_world.translation.copy(); top = -1e9; n = 0; dg = bpy.context.evaluated_depsgraph_get()
            tx = math.tan(R(ro.get("tilt_x", 0.0)))           # tilt (deg) about x: +y side up (a thali on a sloping lap)
            for m in ch["rig"].meshes:
                if m.type != "MESH" or not any(k in m.name for k in parts): continue
                ev = m.evaluated_get(dg); me = ev.to_mesh()
                for v in me.vertices:
                    q = m.matrix_world @ v.co
                    if (q.x - c.x) ** 2 + (q.y - c.y) ** 2 < rad * rad: top = max(top, q.z - (q.y - c.y) * tx); n += 1
                ev.to_mesh_clear()
            if n:
                o.location.z += top + ro.get("gap", 0.004) - c.z; o.rotation_euler.x = R(ro.get("tilt_x", 0.0)); bpy.context.view_layer.update()
            log("REST_ON", p["id"], "on", ro["who"], "verts", n, "top z", round(top, 3), "prop z", round(o.matrix_world.translation.z, 3))
        except Exception as ex: err("rest_on " + p["id"], ex)


HAND_ACTS = ("hand_pick_place", "count_objects", "carry_to", "hand_give", "hand_eat")


def _child(cont, key):
    return next((o for o in [cont] + descendants(cont) if o.name.endswith("." + key) or o.name == key), None)


def do_hand(a):
    """hand-object actions (lib_handobj): the hand really reaches, grips, carries and places (IK + Child Of + contact solve)"""
    import lib_handobj as HO
    t = a["t"]; fps = S.get("fps", 24)
    if t in ("hand_give", "hand_eat"):
        log("HANDOBJ", t, "is a documented stub (lib_handobj) - skipped"); return
    ch = CH[a["who"]]; rig = ch["rig"]; arm = ch["arm"]
    fr_t = lambda x: int(round(a.get("line_frame", 0) + x * fps))
    if t == "count_objects":
        cont = PROPS[a["container"]]; objs = [_child(cont, k) for k in a["objs"]]
        if any(o is None for o in objs): raise RuntimeError(f"count_objects: missing {[k for k, o in zip(a['objs'], objs) if o is None]}")
        b0 = a["blend"][0]; sc.frame_set(b0); bpy.context.view_layer.update()
        M = cont.matrix_world.copy(); c = M.translation.copy(); A3 = arm.matrix_world.to_3x3(); Mi3 = M.to_3x3().inverted()
        left = (A3 @ rig.cs((0, 1, 0))).normalized(); fwd = (A3 @ rig.cs((1, 0, 0))).normalized(); up = Vector((0, 0, 1))
        rl = Mi3 @ -left; rl.z = 0; rl.normalize(); fl = Mi3 @ fwd; fl.z = 0; fl.normalize()     # her right / forward, container-local
        ring = a["ring"]; n = len(objs); step = R(ring.get("step_deg", 360.0 / n)); a0 = R(ring.get("start_deg", 0))
        dests = [M @ (ring["radius"] * (math.cos(a0 + i * step) * rl + math.sin(a0 + i * step) * fl) + Vector((0, 0, ring["z"]))) for i in range(n)]
        words = [fr_t(x) for x in a.get("word_times", [])]
        beats = [{"word": w} for w in words]
        nf = n - len(words)
        if nf > 0:
            f0, f1 = (fr_t(x) for x in a["ff_times"])
            beats += [{"fast": int(round(f0 + k * (f1 - f0) / nf))} for k in range(nf)]
        pats = [fr_t(x) for x in a.get("pat_times", [])]
        steady = None
        if a.get("steady"):
            sd = a["steady"]; lat = left if sd == "L" else -left
            steady = (sd, c + lat * a.get("steady_r", 0.12) + up * 0.012)
        bl = a["blend"]
        HO.count_objects(rig, objs, dests, beats, hand_side=a.get("hand", "R"), steady=steady, pats=pats,
                         blend=(bl[0], bl[1], bl[2], bl[3]), container=cont, radius=a.get("obj_radius", 0.021), look_off=a.get("look_off"))
    elif t == "hand_pick_place":
        cont = PROPS.get(a.get("container")); o = _child(cont, a["obj"]) if cont else PROPS[a["obj"]]
        to = P(a["to"]) if "to" in a else cont.matrix_world @ Vector(a["to_local"])
        fr = a["frames"]; bl = a.get("blend", [fr["hover"] - 8, fr["hover"], fr["off"], fr["off"] + 8])
        hd = HO.hand(rig, a.get("hand", "R")); hd.clear_fk(bl[0] + 1, bl[3] - 1)
        hd.influence(*bl); HO.look(rig).influence(bl[0], bl[1], bl[2], bl[3])
        sc.frame_set(bl[0]); w0, y0 = hd.wrist_world(); hd.key_wrist(bl[0], w0, y0)
        HO.reach_grab_move_place(rig, a.get("hand", "R"), o, to, fr, look_rig=rig, radius=a.get("obj_radius", 0.021), tag="pick")
    elif t == "carry_to":
        HO.carry_to(rig, PROPS[a["obj"]], a["f_grab"], a["f_lift"], a["f_place"], a["f_release"], P(a["place"]),
                    carry=tuple(a.get("carry", (0.3, -0.28))), rim=a.get("rim", 0.125))


ACTS = S.get("actions", [])
for a in ACTS:
    if a["t"] == "hold" or a["t"] in HAND_ACTS: continue
    try: do_action(a)
    except Exception as ex: err(f"action {a.get('t')} {a.get('who', a.get('obj', ''))} @{a.get('frame', a.get('f0', ''))}", ex)
rest_on_props()
for a in ACTS:
    if a["t"] != "hold": continue
    try: do_hold(a)
    except Exception as ex: err(f"hold {a.get('obj')}", ex)
for a in ACTS:
    if a["t"] not in HAND_ACTS: continue
    try: do_hand(a)
    except Exception as ex: err(f"hand action {a['t']} {a.get('who', '')}", ex)
log("ACTIONS done", len(ACTS))


# ---------------- shots -> keys on the one camera
def aim_point(aim, f):
    if isinstance(aim, list): return P(aim)
    sc.frame_set(f); bpy.context.view_layer.update()
    dz = aim.get("dz", 0.0)
    if "who" in aim:
        ch = CH[aim["who"]]; rig = ch["rig"]; seg = aim.get("seg", "head")
        bn = rig.map[seg][0]; pb = rig.arm.pose.bones[bn]
        p = rig.arm.matrix_world @ ((pb.head + pb.tail) / 2)
    elif "obj" in aim:
        p = PROPS[aim["obj"]].matrix_world.translation.copy()
    elif "animal" in aim:
        hd = LA.head_of(AN[aim["animal"]]["arm"]); p = hd.matrix_world.translation.copy()
    else: p = Vector()
    return p + Vector((aim.get("dx", 0.0), aim.get("dy", 0.0), dz))


def cam_at(spec, f):
    t = aim_point(spec["aim"], f)
    if "loc" in spec: loc = P(spec["loc"])
    else:
        az = R(spec.get("az", 0)); d = spec.get("dist", 2.0)
        loc = t + Vector((d * math.sin(az), -d * math.cos(az), spec.get("h", 0.0)))
    return loc, t, spec.get("lens", 35)


SHOTS = S.get("shots", [])
for s in SHOTS:
    try:
        f0, f1 = s["f0"], s["f1"]
        l0, t0, n0 = cam_at(s["cam"], f0)
        l1, t1, n1 = cam_at(dict(s["cam"], **s["end"]), f1) if s.get("end") else (l0, t0, n0)
        for f, l, tt, n in ((f0, l0, t0, n0), (f1, l1, t1, n1)):
            CAMO.location = l; CAM.look_at(CAMO, tt); CAMO.data.lens = n
            CAMO.keyframe_insert("location", frame=f); CAMO.keyframe_insert("rotation_euler", frame=f); CAMO.data.keyframe_insert("lens", frame=f)
        s["_cam"] = [list(l0), list(l1)]
    except Exception as ex: err("shot " + s.get("name", "?"), ex)
for idb in (CAMO, CAMO.data):
    for fc in FX.fcurves(idb):
        for kp in fc.keyframe_points: kp.interpolation = "BEZIER"; kp.handle_left_type = kp.handle_right_type = "AUTO_CLAMPED"
log("SHOTS keyed", len(SHOTS))

# ---------------- coverage check (never render a frame where a body shows): per shot, first / middle / last frame
TOL = 0.002
COV = {"tol": TOL, "shots": {}}
allowed = []
for s in SHOTS:
    f0, f1 = s["f0"], s["f1"]; ok = True; rep = {}
    if not STANDIN:
        for f in sorted({f0, (f0 + f1) // 2, f1}):
            sc.frame_set(f); bpy.context.view_layer.update()
            cl = CAMO.matrix_world.translation.copy()
            for cid, ch in CH.items():
                if ch["h"] is None: continue
                if (ch["arm"].matrix_world.translation - cl).length > S.get("coverage_radius", 18.0): continue   # other set / offstage
                try:
                    lvl = LO.OUTFITS.get(ch["spec"]["outfit"], {}).get("cover", "knee")
                    r = LO.coverage(ch["h"], ch["arm"], {"cam": cl}, level=lvl, step=S.get("coverage_step", 2))["cam"]
                    rep[f"{cid}@{f}"] = round(r["frac"], 4)
                    if r["frac"] > TOL: ok = False; rep[f"{cid}@{f}_bones"] = r.get("exposed_bones")
                except Exception as ex:
                    ok = False; rep[f"{cid}@{f}"] = "error " + repr(ex)[:120]
    COV["shots"][s.get("name", str(f0))] = {"f0": f0, "f1": f1, "ok": ok, "checks": rep}
    log("COVERAGE", s.get("name"), "OK" if ok else "FAIL", rep)
    if ok: allowed += list(range(f0, f1 + 1))
try:
    A.assert_no_undressed_humans(); COV["undressed_check"] = "ok"
except Exception as ex:
    COV["undressed_check"] = repr(ex)[:300]; allowed = []; err("assert_no_undressed_humans", ex)
COV["errors"] = ERRORS
json.dump({"allowed": allowed}, open(os.path.join(OUT, "allowed.json"), "w"))
json.dump(COV, open(os.path.join(OUT, "coverage.json"), "w"), indent=1, default=str)
log("ALLOWED frames", len(allowed), "of", F1 - F0 + 1, "errors", len(ERRORS))

if opt("--save"):
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(opt("--save")), compress=False)
    log("SAVED", opt("--save"))
if opt("--stills"):
    fr = [int(x) for x in str(opt("--stills")).split(",")]
    render_frames([f for f in fr if f in allowed], prefix="still_")
    log("STILLS skipped (coverage)", [f for f in fr if f not in allowed])
elif opt("--render"):
    render_frames(allowed)
log("EPISODE SCENE DONE")
