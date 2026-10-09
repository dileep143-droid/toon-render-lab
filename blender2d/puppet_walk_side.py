"""SIDE-VIEW walk-in (profile puppet from make_parts_side.py), headless:  blender -b -P puppet_walk_side.py -- <char_dir> <plate.png> <out.mp4>
Legs swing about one hip, the near arm swings opposite the front leg. Root motion is computed from the STANCE leg so the planted
foot never slides; the body rises at the passing position. Walks from off-screen left to centre, settles to a standing pose."""
import bpy, json, math, os, sys
argv = sys.argv[sys.argv.index("--") + 1:]; D, PLATE, OUT = argv[0], argv[1], argv[2]
P = os.path.join(D, "parts"); rig = json.load(open(os.path.join(P, "rig.json"))); W, H = rig["canvas"]; pcs = rig["pieces"]
FPS = 24; AMP = 20.0; PERIOD = 0.72
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene; sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 8; sc.cycles.use_denoising = False
sc.cycles.transparent_max_bounces = 32; sc.cycles.max_bounces = 2; sc.cycles.filter_width = 1.0
if os.environ.get("PUPPET_GPU"):                     # Kaggle / any NVIDIA box: Cycles on CUDA, more samples
    pr = bpy.context.preferences.addons["cycles"].preferences; pr.compute_device_type = "CUDA"; pr.get_devices()
    for dv in pr.devices: dv.use = dv.type == "CUDA"
    sc.cycles.device = "GPU"; sc.cycles.samples = int(os.environ.get("PUPPET_SAMPLES", "32"))
sc.render.resolution_x, sc.render.resolution_y = 1920, 1080; sc.render.fps = FPS; sc.view_settings.view_transform = "Standard"
CH = 6.4; S = CH / H


def plane(name, img_path, width, height, z):
    img = bpy.data.images.load(img_path); img.alpha_mode = "STRAIGHT"
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, z)); ob = bpy.context.active_object; ob.name = name; ob.scale = (width, height, 1)
    bpy.ops.object.transform_apply(scale=True)
    mat = bpy.data.materials.new(name); mat.use_nodes = True; nt = mat.node_tree; nt.nodes.clear()
    tex = nt.nodes.new("ShaderNodeTexImage"); tex.image = img; tex.interpolation = "Cubic"; tex.extension = "CLIP"
    emi = nt.nodes.new("ShaderNodeEmission"); tr = nt.nodes.new("ShaderNodeBsdfTransparent"); mix = nt.nodes.new("ShaderNodeMixShader"); out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(tex.outputs["Color"], emi.inputs["Color"]); nt.links.new(tex.outputs["Alpha"], mix.inputs["Fac"])
    nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(emi.outputs[0], mix.inputs[2]); nt.links.new(mix.outputs[0], out.inputs[0])
    if hasattr(mat, "blend_method"): mat.blend_method = "BLEND"
    ob.data.materials.append(mat); return ob


def empty(name, loc, parent=None):
    e = bpy.data.objects.new(name, None); sc.collection.objects.link(e); e.location = loc
    if parent: e.parent = parent; e.matrix_parent_inverse = parent.matrix_world.inverted()
    bpy.context.view_layer.update(); return e


plane("plate", PLATE, 16.0, 9.0, -1.0)
GROUND = -4.2; X0 = -10.5
root = empty("root", (X0, GROUND + CH / 2, 0)); by = root.location.y
to_world = lambda px, py: (root.location.x + (px - W / 2) * S, root.location.y + (H / 2 - py) * S, 0)
E = {"body": empty("E_body", to_world(*pcs["body"]["pivot"]), root)}
for n in ("leg_back", "leg_front", "arm"): E[n] = empty("E_" + n, to_world(*pcs[n]["pivot"]), E["body"])
for n, p in pcs.items():
    ob = plane(n, os.path.join(P, n + ".png"), W * S, H * S, 0.02 * p["z"]); ob.location = (root.location.x, root.location.y, 0.02 * p["z"])
    bpy.context.view_layer.update(); ob.parent = E[n]; ob.matrix_parent_inverse = E[n].matrix_world.inverted()


def key(e, f, deg=None, x=None, y=None):
    if deg is not None: e.rotation_euler = (0, 0, math.radians(deg)); e.keyframe_insert("rotation_euler", frame=f)
    if x is not None or y is not None:
        if x is not None: e.location.x = x
        if y is not None: e.location.y = y
        e.keyframe_insert("location", frame=f)


L = 0.5 * (pcs["leg_front"]["length"] + pcs["leg_back"]["length"]) * S
phi = lambda t: AMP * math.sin(2 * math.pi * t / PERIOD + math.pi / 2)       # front leg angle (+ = forward); starts at full stride
x, f, dt = X0, 1, 1.0 / FPS
while True:
    t = (f - 1) * dt; pf, pb = phi(t), -phi(t)
    stance = pf if phi(t + dt) < pf else pb                                     # the leg moving backward carries the body
    nf, nb = phi(t + dt), -phi(t + dt); st_next = nf if stance == pf else nb
    y = by + 0.5 * L * (math.cos(math.radians(stance)) - math.cos(math.radians(AMP)))
    key(root, f, x=x, y=y)
    key(E["leg_front"], f, pf - pcs["leg_front"]["rest"]); key(E["leg_back"], f, pb - pcs["leg_back"]["rest"])
    key(E["arm"], f, -0.75 * pf - pcs["arm"]["rest"]); key(E["body"], f, -1.5)          # slight forward lean while walking
    x += L * abs(math.sin(math.radians(stance)) - math.sin(math.radians(st_next)))
    if x >= 0 and abs(pf) < 3: break
    f += 1
f_stop = f + 8
key(root, f_stop, x=x + 0.08, y=by); key(E["body"], f_stop, 0)
for n in ("leg_front", "leg_back", "arm"): key(E[n], f_stop, -pcs[n]["rest"] + (2 if n == "leg_front" else -2 if n == "leg_back" else 0))
for ob in bpy.data.objects:
    if ob.animation_data and ob.animation_data.action:
        for fc in ob.animation_data.action.fcurves:
            for k in fc.keyframe_points: k.interpolation = "LINEAR" if k.co[0] < f else "BEZIER"
NF = f_stop + int(0.5 * FPS); sc.frame_start, sc.frame_end = 1, NF
cam_d = bpy.data.cameras.new("cam"); cam_d.type = "ORTHO"; cam_d.ortho_scale = 16.0
cam = bpy.data.objects.new("cam", cam_d); sc.collection.objects.link(cam); sc.camera = cam; cam.location = (0, 0, 20)
r = sc.render; r.image_settings.file_format = "FFMPEG"; r.ffmpeg.format = "MPEG4"; r.ffmpeg.codec = "H264"
r.ffmpeg.constant_rate_factor = "PERC_LOSSLESS"; r.filepath = OUT
bpy.ops.render.render(animation=True); print("RENDERED", OUT, NF, "frames, walk frames", f)
