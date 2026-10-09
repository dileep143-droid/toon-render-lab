"""2D cut-out PUPPET animation in Blender (headless):  blender -b -P puppet_scene.py -- <char_dir> <plate.png> <out.mp4>
Pieces from make_parts.py share one canvas, so each is a full-canvas plane parented to an Empty at its joint (shoulder, elbow, hip,
neck); rotating the Empty swings the limb. Heads are swapped (closed/half/open/o/blink) from Rhubarb cues. Walk-in, wave, talk."""
import bpy, json, math, os, sys
argv = sys.argv[sys.argv.index("--") + 1:]; D, PLATE, OUT = argv[0], argv[1], argv[2]
P = os.path.join(D, "parts"); rig = json.load(open(os.path.join(P, "rig.json"))); W, H = rig["canvas"]
cues = json.load(open(os.path.join(D, "line_rhubarb.json")))["mouthCues"]; TALK = cues[-1]["end"]
FPS = 24; T0 = 5.8; END = T0 + TALK + 1.0; NF = int(END * FPS)
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene; sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 8; sc.cycles.use_denoising = False; sc.cycles.filter_width = 1.0
sc.cycles.transparent_max_bounces = 32; sc.cycles.max_bounces = 2
if os.environ.get("PUPPET_GPU"):                     # Kaggle / any NVIDIA box: Cycles on CUDA, more samples
    pr = bpy.context.preferences.addons["cycles"].preferences; pr.compute_device_type = "CUDA"; pr.get_devices()
    for dv in pr.devices: dv.use = dv.type == "CUDA"
    sc.cycles.device = "GPU"; sc.cycles.samples = int(os.environ.get("PUPPET_SAMPLES", "32"))
sc.render.resolution_x, sc.render.resolution_y = 1920, 1080; sc.render.fps = FPS; sc.frame_start, sc.frame_end = 1, NF
sc.view_settings.view_transform = "Standard"
CH = 6.4; S = CH / H                                   # character canvas height in scene units


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


plate = plane("plate", PLATE, 16.0, 9.0, -1.0)
GROUND = -4.2                                          # canvas bottom sits here
root = empty("root", (0, GROUND + CH / 2, 0))
to_world = lambda px, py: (root.location.x + (px - W / 2) * S, root.location.y + (H / 2 - py) * S, 0)
E = {}
order = sorted(rig["pieces"].items(), key=lambda kv: (kv[1]["parent"] is not None, kv[1]["parent"] == "body", kv[0]))
for name, p in [kv for kv in rig["pieces"].items() if kv[0] == "body"] + [kv for kv in rig["pieces"].items() if kv[0] != "body" and not kv[0].startswith("arm_lower") and not kv[0].startswith("head_")] + [kv for kv in rig["pieces"].items() if kv[0].startswith("arm_lower")]:
    par = root if p["parent"] is None else E[p["parent"]]
    E[name] = empty("E_" + name, to_world(*p["pivot"]), par)
headE = empty("E_head", to_world(*rig["pieces"]["head_closed"]["pivot"]), E["body"])
planes = {}
for name, p in rig["pieces"].items():
    ob = plane(name, os.path.join(P, name + ".png"), W * S, H * S, 0.02 * p["z"] + (0.001 if name.startswith("head_") else 0))
    ob.location = (root.location.x, root.location.y, 0.02 * p["z"]); bpy.context.view_layer.update()
    par = headE if name.startswith("head_") else E[name]
    ob.parent = par; ob.matrix_parent_inverse = par.matrix_world.inverted(); planes[name] = ob


def key_rot(e, f, deg): e.rotation_euler = (0, 0, math.radians(deg)); e.keyframe_insert("rotation_euler", frame=f)
def key_loc(e, f, x=None, y=None):
    if x is not None: e.location.x = x
    if y is not None: e.location.y = y
    e.keyframe_insert("location", frame=f)


bx, by = root.location.x, root.location.y
# --- walk in (0 .. 3.0 s): from off-screen left to centre, legs/arms swing, body bobs
WALK_END = int(3.0 * FPS)
for f in range(1, WALK_END + 1):
    t = (f - 1) / FPS; ph = 2 * math.pi * t / 0.62
    key_loc(root, f, x=-9.5 + 9.5 * min(1, t / 3.0), y=by + 0.07 * abs(math.sin(ph)))
    key_rot(E["leg_L"], f, 16 * math.sin(ph)); key_rot(E["leg_R"], f, -16 * math.sin(ph))
    key_rot(E["arm_upper_L"], f, -10 * math.sin(ph)); key_rot(E["arm_upper_R"], f, 10 * math.sin(ph))
    key_rot(headE, f, 1.5 * math.sin(ph))
for e in (E["leg_L"], E["leg_R"], E["arm_upper_L"], E["arm_upper_R"], headE): key_rot(e, WALK_END + 6, 0)
key_loc(root, WALK_END + 6, x=0, y=by)
# --- wave (3.6 .. 5.4 s) with his left arm (viewer's right): raise, forearm waves, lower
w0, w1 = int(3.6 * FPS), int(5.4 * FPS)
key_rot(E["arm_upper_L"], w0, 0); key_rot(E["arm_upper_L"], w0 + 8, 140); key_rot(E["arm_upper_L"], w1 - 8, 140); key_rot(E["arm_upper_L"], w1, 0)
for f in range(w0, w1 + 1): key_rot(E["arm_lower_L"], f, (25 * math.sin(2 * math.pi * 3 * (f - w0) / FPS)) if w0 + 8 < f < w1 - 8 else 0)
key_rot(headE, w0 + 8, 4); key_rot(headE, w1, 0)
# --- talk (T0 .. ): head swaps from Rhubarb, gentle head tilt + body sway, one gesture with the right arm
SHAPE = {"X": "closed", "A": "closed", "B": "mouth_half", "C": "mouth_half", "D": "mouth_open", "E": "mouth_o", "F": "mouth_o", "G": "mouth_half", "H": "mouth_half"}
track = ["closed"] * (NF + 2)
for c in cues:
    for f in range(int((T0 + c["start"]) * FPS) + 1, int((T0 + c["end"]) * FPS) + 1):
        if f <= NF: track[f] = SHAPE.get(c["value"], "closed")
for f in range(2, NF):                       # never hold a mouth for a single frame
    if track[f] != track[f - 1] and track[f + 1] != track[f]: track[f] = track[f - 1]
blinks = [int(1.2 * FPS), int(4.0 * FPS)] + [f for f in range(int(T0 * FPS), NF, int(3.1 * FPS))]
for b in blinks:
    if all(track[x] == "closed" for x in range(b, min(b + 3, NF))):
        for x in range(b, min(b + 3, NF)): track[x] = "blink"
for name in ("closed", "mouth_half", "mouth_open", "mouth_o", "blink"):
    ob = planes["head_" + name]; last = None
    for f in range(1, NF + 1):
        vis = track[f] == name
        if vis != last:
            ob.hide_render = not vis; ob.keyframe_insert("hide_render", frame=f); last = vis
t_talk = int(T0 * FPS)
for f in range(t_talk, NF + 1, 6):
    t = (f - t_talk) / FPS
    key_rot(headE, f, 3 * math.sin(2 * math.pi * t / 2.3)); key_loc(root, f, x=0.05 * math.sin(2 * math.pi * t / 3.1), y=by)
g0 = t_talk + int(4.5 * FPS)
key_rot(E["arm_upper_R"], g0, 0); key_rot(E["arm_upper_R"], g0 + 10, -55); key_rot(E["arm_lower_R"], g0 + 10, -35)
key_rot(E["arm_upper_R"], g0 + 40, -55); key_rot(E["arm_upper_R"], g0 + 52, 0); key_rot(E["arm_lower_R"], g0 + 52, 0)
for ob in bpy.data.objects:
    if ob.animation_data and ob.animation_data.action:
        for fc in ob.animation_data.action.fcurves:
            for k in fc.keyframe_points:
                if fc.data_path != "hide_render": k.interpolation = "BEZIER"
cam_d = bpy.data.cameras.new("cam"); cam_d.type = "ORTHO"; cam_d.ortho_scale = 16.0
cam = bpy.data.objects.new("cam", cam_d); sc.collection.objects.link(cam); sc.camera = cam; cam.location = (0, 0, 20)
cam_d.keyframe_insert("ortho_scale", frame=t_talk); cam.keyframe_insert("location", frame=t_talk)
cam_d.ortho_scale = 10.5; cam.location = (0, -0.6, 20); cam_d.keyframe_insert("ortho_scale", frame=t_talk + 30); cam.keyframe_insert("location", frame=t_talk + 30)
sc.sequence_editor_create()
seq = sc.sequence_editor.sequences if hasattr(sc.sequence_editor, "sequences") else sc.sequence_editor.strips
seq.new_sound("line", os.path.join(D, "line.wav"), 1, int(T0 * FPS))
r = sc.render; r.image_settings.file_format = "FFMPEG"; r.ffmpeg.format = "MPEG4"; r.ffmpeg.codec = "H264"; r.ffmpeg.audio_codec = "AAC"
r.ffmpeg.constant_rate_factor = "PERC_LOSSLESS"; r.filepath = OUT
bpy.ops.render.render(animation=True); print("RENDERED", OUT, NF, "frames")
