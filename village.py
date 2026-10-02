"""Our Indian village: a reusable cartoon set (houses, people, animals, props) built by script in Blender.
Every future story imports this and adds its own action:   from village import *;  build_village(scene)
Style: flat 'drawing' colours (emission shaders) + ink outlines (Freestyle). All characters are original."""
import bpy, math, random

R = math.radians
_MATS = {}
STYLE = {"mode": "flat"}      # "flat" = drawing look (emission + ink lines); "shaded" = 3D kids-show look (sunlight, shadows)

def setup_shaded(fast=False, frames=240, fps=24):
    """Infobells-style look: Eevee, warm sun with soft shadows, sky ambient light, no ink lines."""
    STYLE["mode"] = "shaded"
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try: sc.render.engine = eng; break
        except Exception: pass
    try: sc.eevee.taa_render_samples = 32 if fast else 64
    except Exception: pass
    for prop in ("use_gtao", "use_soft_shadows", "use_shadows"):
        try: setattr(sc.eevee, prop, True)
        except Exception: pass
    sc.render.resolution_x, sc.render.resolution_y = (640, 360) if fast else (1280, 720)
    sc.render.fps = fps; sc.frame_start, sc.frame_end = 1, frames
    sc.render.image_settings.file_format = "PNG"
    sc.render.use_freestyle = False
    try: sc.view_settings.view_transform = "AgX"; sc.view_settings.look = "AgX - Punchy"
    except Exception: sc.view_settings.view_transform = "Standard"
    w = bpy.data.worlds.new("sky"); sc.world = w; w.use_nodes = True
    bg = w.node_tree.nodes["Background"]; bg.inputs[0].default_value = (0.55, 0.75, 1.0, 1); bg.inputs[1].default_value = 0.9
    sun_d = bpy.data.lights.new("sun", "SUN"); sun_d.energy = 4.0; sun_d.color = (1.0, 0.93, 0.82); sun_d.angle = R(6)
    sun = bpy.data.objects.new("sun_light", sun_d); sc.collection.objects.link(sun); sun.rotation_euler = (R(48), R(8), R(35))
    return sc

def setup_scene(fast=False, frames=240, fps=24):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 8; sc.cycles.use_denoising = False
    sc.render.resolution_x, sc.render.resolution_y = (640, 360) if fast else (1280, 720)
    sc.render.fps = fps; sc.frame_start, sc.frame_end = 1, frames; sc.frame_step = 2 if fast else 1
    sc.view_settings.view_transform = "Standard"
    sc.render.image_settings.file_format = "PNG"
    sc.render.use_freestyle = True; sc.render.line_thickness_mode = "ABSOLUTE"; sc.render.line_thickness = 2.2
    fs = sc.view_layers[0].freestyle_settings
    ls = fs.linesets[0] if len(fs.linesets) else fs.linesets.new("ink")
    ls.select_silhouette = ls.select_border = ls.select_crease = True
    if ls.linestyle is None: ls.linestyle = bpy.data.linestyles.new("ink")
    ls.linestyle.color = (0.18, 0.11, 0.08); ls.linestyle.thickness = 2.4       # warm brown ink, like a pen drawing
    w = bpy.data.worlds.new("sky"); sc.world = w; w.use_nodes = True
    bg = w.node_tree.nodes["Background"]; bg.inputs[0].default_value = (0.70 ** 2.2, 0.88 ** 2.2, 0.98 ** 2.2, 1); bg.inputs[1].default_value = 1
    return sc, ls

def mat(name, rgb):
    if name in _MATS: return _MATS[name]
    m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree; nt.nodes.clear()
    lin = tuple(c ** 2.2 for c in rgb)        # palette is written as screen colours; Blender wants linear values
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    if STYLE["mode"] == "shaded":
        b = nt.nodes.new("ShaderNodeBsdfPrincipled"); b.inputs["Base Color"].default_value = (*lin, 1); b.inputs["Roughness"].default_value = 0.62
        try: b.inputs["Specular IOR Level"].default_value = 0.3
        except Exception: pass
        nt.links.new(b.outputs["BSDF"], o.inputs["Surface"])
    else:
        e = nt.nodes.new("ShaderNodeEmission"); e.inputs["Color"].default_value = (*lin, 1); e.inputs["Strength"].default_value = 1
        nt.links.new(e.outputs["Emission"], o.inputs["Surface"])
    _MATS[name] = m; return m

C = dict(  # the village palette: warm, earthy, friendly
    grass=(0.62, 0.80, 0.38), field=(0.40, 0.72, 0.22), field2=(0.33, 0.62, 0.18), road=(0.86, 0.70, 0.48), mud=(0.80, 0.52, 0.32),
    thatch=(0.86, 0.68, 0.34), wood=(0.52, 0.32, 0.16), darkwood=(0.32, 0.19, 0.10), stone=(0.70, 0.68, 0.64), water=(0.42, 0.72, 0.92),
    white=(0.98, 0.97, 0.93), black=(0.08, 0.07, 0.07), skin=(0.74, 0.50, 0.34), skin2=(0.60, 0.38, 0.24), skin3=(0.84, 0.62, 0.46),
    leaf=(0.30, 0.62, 0.24), leaf2=(0.22, 0.52, 0.20), palm=(0.40, 0.66, 0.22), saffron=(1.0, 0.56, 0.12), red=(0.86, 0.18, 0.16),
    pink=(0.95, 0.42, 0.62), magenta=(0.82, 0.16, 0.48), yellow=(1.0, 0.84, 0.20), blue=(0.24, 0.42, 0.82), teal=(0.16, 0.62, 0.62),
    brass=(0.86, 0.66, 0.22), cream=(0.96, 0.90, 0.78), hill=(0.56, 0.74, 0.62), cloud=(1, 1, 1), sun=(1.0, 0.86, 0.36),
    wallblue=(0.62, 0.80, 0.92), wallpink=(0.98, 0.74, 0.74), wallyellow=(0.99, 0.90, 0.56), green=(0.20, 0.56, 0.30), grey=(0.55, 0.55, 0.58))

def E(name, loc=(0, 0, 0), parent=None, rot=(0, 0, 0)):
    o = bpy.data.objects.new(name, None); bpy.context.scene.collection.objects.link(o)
    o.parent = parent; o.location = loc; o.rotation_euler = rot; return o

def add(kind, name, color, parent=None, loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1), **kw):
    ops = {"ball": bpy.ops.mesh.primitive_uv_sphere_add, "cyl": bpy.ops.mesh.primitive_cylinder_add, "cone": bpy.ops.mesh.primitive_cone_add,
           "box": bpy.ops.mesh.primitive_cube_add, "torus": bpy.ops.mesh.primitive_torus_add, "plane": bpy.ops.mesh.primitive_plane_add}
    if kind == "ball": kw.setdefault("segments", 24); kw.setdefault("ring_count", 12)
    if kind in ("cyl", "cone"): kw.setdefault("vertices", 20)
    if kind == "box": kw.setdefault("size", 1)
    ops[kind](location=(0, 0, 0), **kw)
    o = bpy.context.active_object; o.name = name
    if color: o.data.materials.append(mat(color, C[color]) if isinstance(color, str) else color)
    if kind in ("ball", "torus"): bpy.ops.object.shade_smooth()
    o.parent = parent; o.location = loc; o.rotation_euler = rot; o.scale = scale
    return o

def key(o, path, frame, value, interp=None):
    setattr(o, path, value); o.keyframe_insert(data_path=path, frame=frame)

def linear(o):
    """make all of an object's keyframes linear (for steady movement / spinning)"""
    a = o.animation_data.action if o.animation_data else None
    if not a: return
    try: fcs = list(a.fcurves)
    except AttributeError:
        fcs = [fc for l in a.layers for s in l.strips for sl in a.slots for cb in [s.channelbag(sl)] if cb for fc in cb.fcurves]
    for fc in fcs:
        for kp in fc.keyframe_points: kp.interpolation = "LINEAR"

# ---------------- buildings and props ----------------
def hut(name, loc, wall="mud", roof="thatch", rot=0):
    h = E(name, loc, rot=(0, 0, R(rot)))
    add("cyl", name + "_wall", wall, h, (0, 0, 0.8), radius=1.2, depth=1.6)
    add("cone", name + "_roof", roof, h, (0, 0, 2.15), radius1=1.65, radius2=0.05, depth=1.3)
    add("box", name + "_door", "darkwood", h, (0, -1.17, 0.6), scale=(0.55, 0.1, 1.1))
    add("cyl", name + "_rangoli", "white", h, (0, -1.9, 0.01), scale=(0.5, 0.5, 0.01), radius=1, depth=1)
    for i in range(6):
        a = 2 * math.pi * i / 6
        add("ball", f"{name}_dot{i}", "red" if i % 2 else "yellow", h, (0.3 * math.cos(a), -1.9 + 0.3 * math.sin(a), 0.03), scale=(0.07, 0.07, 0.02))
    return h

def house(name, loc, wall="wallblue", rot=0):
    h = E(name, loc, rot=(0, 0, R(rot)))
    add("box", name + "_body", wall, h, (0, 0, 1.1), scale=(3.2, 2.2, 2.2))
    add("box", name + "_roof", "cream", h, (0, 0, 2.3), scale=(3.5, 2.5, 0.25))
    add("box", name + "_parapet", wall, h, (0, -1.12, 2.55), scale=(3.4, 0.12, 0.35))
    add("box", name + "_door", "teal", h, (0, -1.12, 0.75), scale=(0.7, 0.08, 1.5))
    for sx in (-1, 1):
        add("box", f"{name}_win{sx}", "darkwood", h, (1.0 * sx, -1.12, 1.35), scale=(0.55, 0.08, 0.55))
        add("box", f"{name}_bar{sx}", "white", h, (1.0 * sx, -1.17, 1.35), scale=(0.06, 0.04, 0.55))
    add("box", name + "_step", "stone", h, (0, -1.4, 0.08), scale=(1.2, 0.5, 0.16))
    return h

def temple(name, loc, rot=0):
    t = E(name, loc, rot=(0, 0, R(rot)))
    add("box", name + "_base", "stone", t, (0, 0, 0.3), scale=(3, 3, 0.6))
    add("box", name + "_hall", "white", t, (0, 0, 1.4), scale=(2.2, 2.2, 1.6))
    for i, (s, z) in enumerate([(1.9, 2.5), (1.5, 3.0), (1.1, 3.45), (0.7, 3.85)]):
        add("box", f"{name}_tier{i}", "saffron" if i % 2 else "white", t, (0, 0, z), scale=(s, s, 0.5))
    add("cone", name + "_top", "brass", t, (0, 0, 4.4), radius1=0.3, radius2=0.02, depth=0.7)
    add("cyl", name + "_pole", "darkwood", t, (0.0, 0, 5.0), radius=0.03, depth=0.9)
    flag = add("box", name + "_flag", "saffron", t, (0.25, 0, 5.3), scale=(0.5, 0.02, 0.3))
    add("box", name + "_door", "darkwood", t, (0, -1.12, 1.1), scale=(0.7, 0.08, 1.2))
    add("box", name + "_bell", "brass", t, (0, -1.5, 1.9), scale=(0.18, 0.18, 0.22))
    return t, flag

def banyan(name, loc):
    b = E(name, loc)
    add("cyl", name + "_platform", "stone", b, (0, 0, 0.25), radius=2.2, depth=0.5)
    add("cyl", name + "_trunk", "wood", b, (0, 0, 2.0), radius=0.55, depth=3.2)
    canopy = E(name + "_canopy", (0, 0, 4.2), b)
    for i, (x, y, z, s) in enumerate([(0, 0, 0.4, 2.4), (-2.0, 0.2, -0.2, 1.8), (2.0, -0.2, -0.1, 1.9), (-0.9, -0.8, 0.9, 1.5), (1.0, 0.6, 1.0, 1.6), (0, 1.2, 0.0, 1.7)]):
        add("ball", f"{name}_leaf{i}", "leaf" if i % 2 else "leaf2", canopy, (x, y, z), scale=(s, s * 0.9, s * 0.75))
    for i, x in enumerate((-2.4, -1.6, 1.7, 2.5)):
        add("cyl", f"{name}_root{i}", "wood", b, (x, -0.3, 2.3), radius=0.05, depth=2.6)
    return b, canopy

def palm(name, loc, lean=8):
    p = E(name, loc, rot=(0, R(lean), 0))
    add("cyl", name + "_trunk", "wood", p, (0, 0, 2.5), radius=0.18, depth=5, vertices=12)
    top = E(name + "_top", (0, 0, 5.0), p)
    for i in range(7):
        a = 2 * math.pi * i / 7
        add("ball", f"{name}_frond{i}", "palm", top, (1.0 * math.cos(a), 1.0 * math.sin(a), -0.15), rot=(0, R(20), a), scale=(1.3, 0.22, 0.08))
    for i in range(3):
        add("ball", f"{name}_nut{i}", "wood", top, (0.18 * math.cos(i * 2.1), 0.18 * math.sin(i * 2.1), -0.25), scale=(0.15, 0.15, 0.15))
    return p, top

def well(name, loc):
    w = E(name, loc)
    add("cyl", name + "_ring", "stone", w, (0, 0, 0.45), radius=0.9, depth=0.9)
    add("cyl", name + "_water", "water", w, (0, 0, 0.91), radius=0.72, depth=0.02)
    for sx in (-1, 1): add("cyl", f"{name}_post{sx}", "darkwood", w, (0.8 * sx, 0, 1.4), radius=0.06, depth=1.9)
    add("cyl", name + "_bar", "darkwood", w, (0, 0, 2.3), rot=(0, R(90), 0), radius=0.05, depth=1.7)
    bucket = add("cyl", name + "_bucket", "brass", w, (0, 0, 1.4), radius=0.17, depth=0.25)
    add("cyl", name + "_rope", "cream", w, (0, 0, 1.85), radius=0.015, depth=0.9)
    return w, bucket

def tea_stall(name, loc):
    s = E(name, loc)
    add("box", name + "_counter", "wood", s, (0, 0, 0.55), scale=(2.4, 1.0, 1.1))
    add("box", name + "_board", "yellow", s, (0, -0.52, 0.85), scale=(1.6, 0.04, 0.35))
    for i in range(6):
        add("box", f"{name}_awning{i}", "red" if i % 2 else "white", s, (-1.0 + 0.4 * i, -0.2, 2.25), rot=(R(-18), 0, 0), scale=(0.4, 1.6, 0.06))
    for sx in (-1, 1): add("cyl", f"{name}_pole{sx}", "darkwood", s, (1.15 * sx, -0.85, 1.1), radius=0.05, depth=2.2)
    add("ball", name + "_kettle", "grey", s, (-0.6, 0, 1.25), scale=(0.25, 0.25, 0.22))
    for i in range(3): add("cyl", f"{name}_glass{i}", "cream", s, (0.3 + 0.25 * i, -0.2, 1.2), radius=0.07, depth=0.18)
    add("box", name + "_bench", "wood", s, (0, -1.6, 0.35), scale=(2.0, 0.4, 0.12))
    return s

def charpai(name, loc, rot=0):
    c = E(name, loc, rot=(0, 0, R(rot)))
    add("box", name + "_top", "cream", c, (0, 0, 0.45), scale=(1.9, 0.9, 0.06))
    for sx in (-1, 1):
        for sy in (-1, 1): add("box", f"{name}_leg{sx}{sy}", "wood", c, (0.9 * sx, 0.42 * sy, 0.22), scale=(0.08, 0.08, 0.45))
    return c

def haystack(name, loc, s=1.0):
    h = E(name, loc)
    add("cyl", name + "_base", "thatch", h, (0, 0, 0.5 * s), radius=1.0 * s, depth=1.0 * s)
    add("cone", name + "_top", "thatch", h, (0, 0, 1.45 * s), radius1=1.05 * s, radius2=0.05, depth=0.9 * s)
    return h

def clothesline(name, loc):
    c = E(name, loc)
    for sx in (-1, 1): add("cyl", f"{name}_pole{sx}", "darkwood", c, (1.6 * sx, 0, 0.9), radius=0.04, depth=1.8)
    add("cyl", name + "_line", "cream", c, (0, 0, 1.75), rot=(0, R(90), 0), radius=0.012, depth=3.2)
    cloths = []
    for i, col in enumerate(("magenta", "yellow", "teal", "saffron")):
        piv = E(f"{name}_peg{i}", (-1.2 + 0.8 * i, 0, 1.75), c)
        add("box", f"{name}_cloth{i}", col, piv, (0, 0, -0.45), scale=(0.6, 0.02, 0.9)); cloths.append(piv)
    return c, cloths

# ---------------- people (original, simple) ----------------
def person(name, loc, top="white", bottom="white", skin="skin", kind="man", hair="black", head_item=None, rot=0, size=1.0):
    """kind: man (dhoti/pants), woman (saree), kid (shorts). Returns dict of parts to animate."""
    root = E(name, loc, rot=(0, 0, R(rot))); root.scale = (size, size, size)
    body = E(name + "_body", (0, 0, 0), root)
    parts = {"root": root, "body": body}
    hips = []
    for sx in (-1, 1):
        hp = E(f"{name}_hip{sx}", (0.13 * sx, 0, 0.82), body)
        add("cyl", f"{name}_leg{sx}", skin if kind != "kid" else skin, hp, (0, 0, -0.38), radius=0.07, depth=0.76, vertices=10)
        add("ball", f"{name}_foot{sx}", "darkwood", hp, (0, -0.07, -0.78), scale=(0.09, 0.15, 0.05))
        hips.append(hp)
    parts["hips"] = hips
    if kind == "woman":
        add("cone", name + "_saree", bottom, body, (0, 0, 0.55), radius1=0.42, radius2=0.22, depth=1.0)
    elif kind == "kid":
        add("cyl", name + "_shorts", bottom, body, (0, 0, 0.82), radius=0.24, depth=0.25)
    else:
        add("cone", name + "_dhoti", bottom, body, (0, 0, 0.6), radius1=0.32, radius2=0.25, depth=0.6)
    add("cyl", name + "_torso", top, body, (0, 0, 1.2), radius=0.26, depth=0.65)
    if kind == "woman":
        add("box", name + "_pallu", bottom, body, (0.05, -0.2, 1.25), rot=(0, R(30), 0), scale=(0.18, 0.04, 0.7))
    arms = []
    for sx in (-1, 1):
        sh = E(f"{name}_sh{sx}", (0.32 * sx, 0, 1.45), body)
        add("cyl", f"{name}_arm{sx}", top if kind != "kid" else skin, sh, (0, 0, -0.28), radius=0.06, depth=0.56, vertices=10)
        add("ball", f"{name}_hand{sx}", skin, sh, (0, 0, -0.6), scale=(0.07, 0.07, 0.07))
        arms.append(sh)
    parts["arms"] = arms
    head = E(name + "_head", (0, 0, 1.78), body)
    add("ball", name + "_face", skin, head, (0, 0, 0), scale=(0.25, 0.24, 0.27))
    add("ball", name + "_hair", hair, head, (0, 0.04, 0.08), scale=(0.26, 0.25, 0.22))
    for sx in (-1, 1):
        add("ball", f"{name}_eye{sx}", "black", head, (0.09 * sx, -0.22, 0.03), scale=(0.035, 0.02, 0.045))
    add("box", name + "_smile", "black", head, (0, -0.235, -0.09), scale=(0.1, 0.01, 0.018))
    if kind == "woman": add("ball", name + "_bindi", "red", head, (0, -0.245, 0.12), scale=(0.025, 0.01, 0.025))
    if kind == "man": add("box", name + "_mustache", "black", head, (0, -0.24, -0.04), scale=(0.16, 0.02, 0.035))
    if head_item == "turban":
        add("torus", name + "_turban", "saffron" if top == "white" else "red", head, (0, 0, 0.17), major_radius=0.2, minor_radius=0.08)
    if head_item == "pot":
        add("ball", name + "_pot", "brass", head, (0, 0, 0.42), scale=(0.24, 0.24, 0.22))
        add("cyl", name + "_potneck", "brass", head, (0, 0, 0.6), radius=0.09, depth=0.1)
    if head_item == "cap": add("ball", name + "_cap", "white", head, (0, 0.02, 0.17), scale=(0.2, 0.2, 0.09))
    parts["head"] = head
    return parts

def walk(p, path, f0, f1, step=6, swing=0.5):
    """walk along path [(x,y,z),...] spread evenly between frames f0..f1; legs and arms swing; little bounce."""
    root = p["root"]; n = len(path) - 1
    for i, pt in enumerate(path):
        key(root, "location", int(f0 + (f1 - f0) * i / n), pt)
    linear(root)
    for f in range(f0, f1 + 1, step):
        s = 1 if ((f - f0) // step) % 2 == 0 else -1
        key(p["hips"][0], "rotation_euler", f, (swing * s, 0, 0)); key(p["hips"][1], "rotation_euler", f, (-swing * s, 0, 0))
        key(p["arms"][0], "rotation_euler", f, (-swing * 0.8 * s, 0, 0)); key(p["arms"][1], "rotation_euler", f, (swing * 0.8 * s, 0, 0))
        key(p["body"], "location", f, (0, 0, 0.0)); key(p["body"], "location", f + step // 2, (0, 0, 0.05))

def bob(o, f0, f1, period=12, amount=0.12, path="location", axis=2, base=None):
    base = list(getattr(o, path)) if base is None else list(base)
    for f in range(f0, f1 + 1, period):
        v = list(base); v[axis] += amount; key(o, path, f + period // 2, tuple(v)); key(o, path, f, tuple(base))

def wave_arm(p, f0, f1, period=10, side=1):
    a = p["arms"][0 if side < 0 else 1]
    for f in range(f0, f1 + 1, period):
        key(a, "rotation_euler", f, (0, R(-150) * side, 0)); key(a, "rotation_euler", f + period // 2, (0, R(-120) * side, 0))

# ---------------- animals and vehicles ----------------
def cow(name, loc, color="white", patch="black", rot=0):
    c = E(name, loc, rot=(0, 0, R(rot)))
    add("ball", name + "_body", color, c, (0, 0, 1.0), scale=(1.0, 0.5, 0.48))
    add("ball", name + "_patch", patch, c, (0.2, -0.38, 1.1), scale=(0.3, 0.15, 0.22))
    for sx in (-1, 1):
        for sy in (-1, 1): add("cyl", f"{name}_leg{sx}{sy}", color, c, (0.6 * sx, 0.22 * sy, 0.4), radius=0.08, depth=0.8, vertices=10)
    head = E(name + "_neck", (1.05, 0, 1.2), c)
    add("ball", name + "_head", color, head, (0.25, 0, 0.1), scale=(0.33, 0.24, 0.24))
    add("ball", name + "_snout", "pink", head, (0.52, 0, 0.0), scale=(0.12, 0.15, 0.12))
    for sy in (-1, 1):
        add("cone", f"{name}_horn{sy}", "cream", head, (0.2, 0.16 * sy, 0.38), rot=(R(-25 * sy), 0, 0), radius1=0.05, radius2=0.0, depth=0.25, vertices=8)
        add("ball", f"{name}_eye{sy}", "black", head, (0.45, 0.17 * sy, 0.14), scale=(0.04, 0.04, 0.04))
    tail = E(name + "_tailpiv", (-1.0, 0, 1.15), c)
    add("cyl", name + "_tail", color, tail, (0, 0, -0.35), radius=0.03, depth=0.7, vertices=8)
    return c, head, tail

def bullock_cart(name, loc, rot=0):
    cart = E(name, loc, rot=(0, 0, R(rot)))
    add("box", name + "_bed", "wood", cart, (-1.2, 0, 1.0), scale=(2.2, 1.6, 0.15))
    for sy in (-1, 1): add("box", f"{name}_side{sy}", "wood", cart, (-1.2, 0.8 * sy, 1.25), scale=(2.2, 0.08, 0.4))
    add("box", name + "_yoke", "darkwood", cart, (1.2, 0, 1.1), scale=(2.6, 0.12, 0.1))
    wheels = []
    for sy in (-1, 1):
        wp = E(f"{name}_wheelpiv{sy}", (-1.2, 0.9 * sy, 0.7), cart)
        add("torus", f"{name}_wheel{sy}", "darkwood", wp, (0, 0, 0), rot=(R(90), 0, 0), major_radius=0.62, minor_radius=0.06)
        for k in range(3): add("box", f"{name}_spoke{sy}{k}", "darkwood", wp, (0, 0, 0), rot=(0, R(60 * k), 0), scale=(1.2, 0.04, 0.05))
        wheels.append(wp)
    oxen = [cow(f"{name}_ox{sy}", (2.4, 0.55 * sy, 0), color="cream", patch="wood")[0] for sy in (-1, 1)]
    for o in oxen: o.parent = cart; o.scale = (0.85, 0.85, 0.85)
    hay = add("cyl", name + "_hay", "thatch", cart, (-1.4, 0, 1.5), scale=(0.9, 0.6, 0.45), radius=1, depth=1)
    return cart, wheels

def bicycle(name, loc, rot=0):
    b = E(name, loc, rot=(0, 0, R(rot)))
    wheels = []
    for i, x in enumerate((-0.55, 0.55)):
        wp = E(f"{name}_wp{i}", (x, 0, 0.36), b)
        add("torus", f"{name}_wheel{i}", "black", wp, (0, 0, 0), rot=(R(90), 0, 0), major_radius=0.34, minor_radius=0.03)
        wheels.append(wp)
    add("box", name + "_frame", "red", b, (0, 0, 0.6), rot=(0, R(10), 0), scale=(1.1, 0.04, 0.05))
    add("box", name + "_post", "red", b, (-0.15, 0, 0.75), rot=(0, R(-15), 0), scale=(0.05, 0.04, 0.5))
    add("box", name + "_bar", "grey", b, (0.5, 0, 1.0), scale=(0.05, 0.5, 0.04))
    return b, wheels

def bird(name, loc):
    b = E(name, loc)
    wings = []
    for sx in (-1, 1):
        wp = E(f"{name}_wp{sx}", (0, 0, 0), b)
        add("box", f"{name}_wing{sx}", "black", wp, (0.22 * sx, 0, 0), scale=(0.45, 0.08, 0.03)); wings.append(wp)
    return b, wings

def hen(name, loc):
    h = E(name, loc)
    add("ball", name + "_body", "white", h, (0, 0, 0.25), scale=(0.22, 0.16, 0.18))
    head = E(name + "_neck", (0.17, 0, 0.38), h)
    add("ball", name + "_head", "white", head, (0, 0, 0), scale=(0.09, 0.09, 0.09))
    add("box", name + "_comb", "red", head, (0, 0, 0.09), scale=(0.08, 0.02, 0.05))
    add("cone", name + "_beak", "yellow", head, (0.1, 0, 0), rot=(0, R(90), 0), radius1=0.03, radius2=0, depth=0.07, vertices=6)
    return h, head

# ---------------- the village layout ----------------
def build_village(frames=240):
    """Lays out the whole village and its idle life. Returns a dict of named things stories can use."""
    v = {}
    add("plane", "ground", "grass", None, (0, 0, 0), size=120)
    add("box", "road", "road", None, (0, -3.2, 0.01), scale=(80, 3.2, 0.02))
    for i in range(6):                                   # paddy fields behind the village
        add("box", f"paddy{i}", "field" if i % 2 else "field2", None, (-18 + 7.5 * i, 16, 0.02), scale=(7.2, 7, 0.03))
    add("cyl", "pond", "water", None, (12, 6, 0.02), scale=(2.6, 1.8, 0.02), radius=1, depth=1)
    for i in range(4): add("ball", f"lotus{i}", "pink", None, (11 + 0.7 * i, 5.6 + 0.4 * (i % 2), 0.06), scale=(0.15, 0.15, 0.06))
    for i, (x, s) in enumerate([(-30, 9), (-12, 12), (8, 10), (26, 11)]):   # hills far away
        add("ball", f"hill{i}", "hill", None, (x, 60, -2), scale=(s * 1.6, 4, s * 0.6))
    add("ball", "sun", "sun", None, (18, 58, 14), scale=(2.2, 0.2, 2.2))
    clouds = []
    for i, (x, z) in enumerate([(-22, 13), (-4, 15), (14, 12.5), (30, 14.5)]):
        cl = E(f"cloud{i}", (x, 50, z))
        for j, (dx, s) in enumerate([(-1.1, 1.1), (0, 1.5), (1.2, 1.0)]): add("ball", f"cloud{i}_{j}", "cloud", cl, (dx, 0, 0), scale=(s * 1.3, 0.3, s * 0.8))
        key(cl, "location", 1, (x, 50, z)); key(cl, "location", frames, (x + 4, 50, z)); linear(cl); clouds.append(cl)

    hut("hut1", (-15, 4, 0), rot=-10); hut("hut2", (-11, 7, 0), wall="wallyellow", rot=5); hut("hut3", (9, 9, 0), rot=12)
    house("house1", (-4, 5, 0), wall="wallblue"); house("house2", (16, 3.5, 0), wall="wallpink", rot=-8)
    v["temple"], flag = temple("temple", (4, 11, 0))
    for f in range(1, frames + 1, 8): key(flag, "rotation_euler", f, (0, 0, R(12 if (f // 8) % 2 else -12)))
    v["banyan"], canopy = banyan("banyan", (-6, 0.8, 0))
    for i, (x, y, lean) in enumerate([(-20, 9, 6), (-17.5, 11, -8), (20, 8, 10), (22.5, 10, -5), (6, 2, 7)]):
        p, top = palm(f"palm{i}", (x, y, 0), lean)
        for f in range(1, frames + 1, 30): key(top, "rotation_euler", f, (0, R(4 if (f // 30) % 2 else -4), 0))
    v["well"], bucket = well("well", (2, 1.5, 0))
    v["stall"] = tea_stall("stall", (10, 0.2, 0))
    charpai("charpai1", (-13, 1.3, 0), rot=8); haystack("hay1", (-19, 2, 0)); haystack("hay2", (18.5, 0.8, 0), 0.8)
    line, cloths = clothesline("line1", (-9.5, 4.8, 0))
    for i, c in enumerate(cloths):
        for f in range(1 + i * 3, frames + 1, 24): key(c, "rotation_euler", f, (R(10), 0, 0)); key(c, "rotation_euler", f + 12, (R(-6), 0, 0))

    # foreground on the near side of the road: bamboo fence, bushes, marigolds, banana plants, a sleeping dog
    rnd = random.Random(7)
    for i, x in enumerate(range(-30, 31, 2)):
        add("cyl", f"fencepost{i}", "wood", None, (x, -6.6, 0.55), radius=0.07, depth=1.1, vertices=8)
    for z in (0.45, 0.85): add("box", f"fencerail{z}", "wood", None, (0, -6.6, z), scale=(60, 0.06, 0.07))
    for i in range(16):
        x = -30 + i * 4 + rnd.uniform(-1, 1)
        add("ball", f"bush{i}", "leaf" if i % 2 else "leaf2", None, (x, -7.8, 0.2), scale=(rnd.uniform(0.6, 0.9), 0.45, rnd.uniform(0.3, 0.42)))
        for j in range(3):
            add("ball", f"marigold{i}_{j}", "saffron" if j % 2 else "yellow", None, (x + rnd.uniform(-0.6, 0.6), -7.5, rnd.uniform(0.42, 0.55)), scale=(0.11, 0.11, 0.11))
    for i, x in enumerate((-21, 3.5, 19)):
        bp = E(f"banana{i}", (x, -8.0, 0))
        add("cyl", f"banana{i}_trunk", "palm", bp, (0, 0, 0.9), radius=0.16, depth=1.8, vertices=10)
        for k in range(5):
            a = 2 * math.pi * k / 5
            add("ball", f"banana{i}_leaf{k}", "leaf", bp, (0.7 * math.cos(a), 0.7 * math.sin(a), 1.9), rot=(0, R(-25), a), scale=(0.9, 0.3, 0.05))
    dog = E("dog", (-2.5, -5.4, 0), rot=(0, 0, R(20)))
    add("ball", "dog_body", "road", dog, (0, 0, 0.22), scale=(0.55, 0.32, 0.22))
    dhead = E("dog_headpiv", (0.5, -0.05, 0.25), dog)
    add("ball", "dog_head", "road", dhead, (0.12, 0, 0), scale=(0.2, 0.18, 0.16))
    for sy in (-1, 1): add("ball", f"dog_ear{sy}", "darkwood", dhead, (0.05, 0.13 * sy, 0.12), scale=(0.08, 0.05, 0.1))
    add("ball", "dog_eye", "black", dhead, (0.28, -0.08, 0.05), scale=(0.05, 0.02, 0.012))
    for f in range(1, frames + 1, 48): key(dhead, "rotation_euler", f, (0, 0, 0)); key(dhead, "rotation_euler", f + 24, (0, R(-12), 0))

    # people and animals living their day
    ppl = {}
    ppl["water_woman"] = person("water_woman", (-24, -3.4, 0), top="green", bottom="magenta", kind="woman", head_item="pot", rot=90)
    walk(ppl["water_woman"], [(-24, -3.4, 0), (2, -3.4, 0)], 1, frames, step=7, swing=0.25)
    ppl["farmer"] = person("farmer", (-1, -0.6, 0), top="white", bottom="white", kind="man", head_item="turban", skin="skin2")
    wave_arm(ppl["farmer"], 1, frames, side=1)
    ppl["tea_man"] = person("tea_man", (10, 0.9, 0), top="white", bottom="teal", kind="man", skin="skin")
    for f in range(1, frames + 1, 16):
        key(ppl["tea_man"]["arms"][0], "rotation_euler", f, (R(-70), 0, 0)); key(ppl["tea_man"]["arms"][0], "rotation_euler", f + 8, (R(-100), 0, 0))
    ppl["elder1"] = person("elder1", (-6.6, -1.3, 0.5), top="white", bottom="white", kind="man", hair="grey", head_item="cap", skin="skin3", size=0.95)
    ppl["elder2"] = person("elder2", (-5.2, -1.4, 0.5), top="cream", bottom="white", kind="man", hair="grey", skin="skin2", size=0.95)
    for p_, off in ((ppl["elder1"], 0), (ppl["elder2"], 6)):
        for f in range(1 + off, frames + 1, 24):
            key(p_["head"], "rotation_euler", f, (0, 0, R(15))); key(p_["head"], "rotation_euler", f + 12, (0, 0, R(-15)))
    add("cyl", "elder1_stick", "darkwood", ppl["elder1"]["arms"][1], (0, -0.1, -0.5), radius=0.025, depth=1.2)
    ppl["well_woman"] = person("well_woman", (2, 0.4, 0), top="red", bottom="yellow", kind="woman")
    for f in range(1, frames + 1, 20):
        for a in ppl["well_woman"]["arms"]: key(a, "rotation_euler", f, (R(-160), 0, 0)); key(a, "rotation_euler", f + 10, (R(-110), 0, 0))
        key(bucket, "location", f, (0, 0, 1.4)); key(bucket, "location", f + 10, (0, 0, 1.75))
    kids = []
    for i, (x, top, bottom, phase) in enumerate([(-8.5, "red", "blue", 0), (-7.4, "yellow", "darkwood", 5), (-3.6, "teal", "blue", 9)]):
        k = person(f"kid{i}", (x, -1.6, 0), top=top, bottom=bottom, kind="kid", size=0.62, skin="skin" if i % 2 else "skin2")
        for f in range(1 + phase, frames + 1, 14):
            key(k["root"], "location", f, (x, -1.6, 0)); key(k["root"], "location", f + 7, (x, -1.6, 0.6))
            key(k["arms"][0], "rotation_euler", f + 7, (0, R(140), 0)); key(k["arms"][1], "rotation_euler", f + 7, (0, R(-140), 0))
            key(k["arms"][0], "rotation_euler", f, (0, 0, 0)); key(k["arms"][1], "rotation_euler", f, (0, 0, 0))
        kids.append(k)
    ball = add("ball", "kidsball", "red", None, (-7.95, -1.9, 0.2), scale=(0.18, 0.18, 0.18))
    for f in range(1, frames + 1, 14): key(ball, "location", f, (-7.95, -1.9, 0.2)); key(ball, "location", f + 7, (-7.95, -1.9, 1.6))
    ppl["school1"] = person("school1", (26, -2.6, 0), top="white", bottom="blue", kind="kid", size=0.65, rot=-90)
    walk(ppl["school1"], [(26, -2.6, 0), (-6, -2.6, 0)], 1, frames, step=5, swing=0.45)
    add("box", "school1_bag", "red", ppl["school1"]["body"], (0, 0.3, 1.2), scale=(0.36, 0.2, 0.45))

    cow1, cow1_head, cow1_tail = cow("cow1", (-16.5, -0.2, 0), rot=-15)
    for f in range(1, frames + 1, 16):
        key(cow1_head, "rotation_euler", f, (0, R(30), 0)); key(cow1_head, "rotation_euler", f + 8, (0, R(5), 0))
        key(cow1_tail, "rotation_euler", f, (R(25), 0, 0)); key(cow1_tail, "rotation_euler", f + 8, (R(-25), 0, 0))
    cow2, _, cow2_tail = cow("cow2", (13.5, 4.6, 0), color="cream", patch="wood", rot=160)
    for f in range(1, frames + 1, 18): key(cow2_tail, "rotation_euler", f, (R(30), 0, 0)); key(cow2_tail, "rotation_euler", f + 9, (R(-30), 0, 0))
    for i, (x, y) in enumerate([(-12, -0.6), (-11.3, -1.0), (6.5, -0.4)]):
        h, hh = hen(f"hen{i}", (x, y, 0))
        for f in range(1 + 3 * i, frames + 1, 10): key(hh, "rotation_euler", f, (0, R(60), 0)); key(hh, "rotation_euler", f + 5, (0, 0, 0))

    cart, wheels = bullock_cart("cart", (-34, -3.0, 0), rot=0)
    key(cart, "location", 1, (-26, -3.0, 0)); key(cart, "location", frames, (12, -3.0, 0)); linear(cart)
    driver = person("cart_driver", (-0.2, 0, 0.85), top="white", bottom="white", kind="man", head_item="turban", skin="skin2", size=0.9)
    driver["root"].parent = cart
    for wpv in wheels: key(wpv, "rotation_euler", 1, (0, 0, 0)); key(wpv, "rotation_euler", frames, (0, R(360 * 38 / (2 * math.pi * 0.62)), 0)); linear(wpv)
    bike, bwheels = bicycle("bike", (30, -4.1, 0), rot=180)
    rider = person("bike_rider", (0, 0, 0.35), top="blue", bottom="darkwood", kind="man", size=0.85); rider["root"].parent = bike
    for hp in rider["hips"]: hp.rotation_euler = (R(-70), 0, 0)
    for a in rider["arms"]: a.rotation_euler = (R(-70), 0, 0)
    key(bike, "location", 1, (6, -4.1, 0)); key(bike, "location", frames, (-14, -4.1, 0)); linear(bike)
    for wpv in bwheels: key(wpv, "rotation_euler", 1, (0, 0, 0)); key(wpv, "rotation_euler", frames, (0, R(360 * 20 / (2 * math.pi * 0.34)), 0)); linear(wpv)
    for i in range(4):                                     # birds crossing the sky
        b, wings = bird(f"bird{i}", (-30 - 2 * i, 25, 9 + 0.6 * i))
        key(b, "location", 1, (-30 - 2 * i, 25, 9 + 0.6 * i)); key(b, "location", frames, (25 - 2 * i, 25, 10 + 0.6 * i)); linear(b)
        for f in range(1 + i, frames + 1, 6):
            for sx, wp in zip((-1, 1), wings): key(wp, "rotation_euler", f, (0, R(30 * sx), 0)); key(wp, "rotation_euler", f + 3, (0, R(-25 * sx), 0))
    smoke = []
    for i in range(4):                                     # chai stall smoke
        s = add("ball", f"smoke{i}", "cloud", None, (9.4, 0.2, 1.6), scale=(0.15, 0.15, 0.15))
        for f in range(1 + 8 * i, frames + 1, 32):
            key(s, "location", f, (9.4, 0.2, 1.6)); key(s, "scale", f, (0.1, 0.1, 0.1))
            key(s, "location", f + 31, (9.0 + 0.3 * math.sin(i), 0.2, 2.9)); key(s, "scale", f + 31, (0.24, 0.24, 0.24))
        smoke.append(s)
    v.update(people=ppl, kids=kids, cart=cart, bike=bike, clouds=clouds)
    return v

def camera_pan(x0=-16, x1=16, frames=240, y=-20, z=4.6, look_z=2.3, lens=30):
    tgt = E("cam_target", (x0, 4, look_z))
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); cam.data.lens = lens
    bpy.context.scene.collection.objects.link(cam); bpy.context.scene.camera = cam
    c = cam.constraints.new("TRACK_TO"); c.target = tgt; c.track_axis = "TRACK_NEGATIVE_Z"; c.up_axis = "UP_Y"
    key(cam, "location", 1, (x0, y, z)); key(cam, "location", frames, (x1, y, z))
    key(tgt, "location", 1, (x0, 4, look_z)); key(tgt, "location", frames, (x1, 4, look_z))
    return cam
