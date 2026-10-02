"""Gudu and the Apple: an 8-second sample cartoon built and rendered entirely by script (Blender, no screen needed).
Run:  blender -b -noaudio --python render_scene.py -- <output_folder>
Original character (not based on any existing show). Flat cartoon colours (emission shaders) + Freestyle ink outlines."""
import bpy, math, os, sys

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(argv[0] if argv else "frames")
FAST = "--fast" in argv          # quick preview: half resolution, every 2nd frame

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 8
scene.cycles.use_denoising = False
scene.render.resolution_x, scene.render.resolution_y = (640, 360) if FAST else (1280, 720)
scene.render.fps = 24
scene.frame_start, scene.frame_end = 1, 192
scene.frame_step = 2 if FAST else 1
scene.view_settings.view_transform = "Standard"      # keep cartoon colours bright, no film look
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = os.path.join(OUT, "frame_")

# ink outlines
scene.render.use_freestyle = True
scene.render.line_thickness_mode = "ABSOLUTE"
scene.render.line_thickness = 2.6
vl = scene.view_layers[0]
fs = vl.freestyle_settings
ls = fs.linesets[0] if len(fs.linesets) else fs.linesets.new("ink")
ls.select_silhouette = ls.select_border = ls.select_crease = True
if ls.linestyle is None:
    ls.linestyle = bpy.data.linestyles.new("ink")
ls.linestyle.color = (0.06, 0.05, 0.07)
ls.linestyle.thickness = 3.0

# sky
world = bpy.data.worlds.new("sky"); scene.world = world; world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs[0].default_value = (0.52, 0.80, 1.0, 1.0); bg.inputs[1].default_value = 1.0

def mat(name, rgb):
    m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree; nt.nodes.clear()
    e = nt.nodes.new("ShaderNodeEmission"); e.inputs["Color"].default_value = (*rgb, 1.0); e.inputs["Strength"].default_value = 1.0
    o = nt.nodes.new("ShaderNodeOutputMaterial"); nt.links.new(e.outputs["Emission"], o.inputs["Surface"])
    return m

ORANGE, DARKOR, WHITE, BLACK = mat("orange", (1.0, 0.55, 0.12)), mat("darkorange", (0.85, 0.36, 0.06)), mat("white", (1, 1, 1)), mat("black", (0.04, 0.04, 0.05))
PINK, GREEN, RED, BROWN, YELLOW = mat("pink", (1.0, 0.55, 0.6)), mat("grass", (0.35, 0.78, 0.32)), mat("red", (0.9, 0.12, 0.12)), mat("brown", (0.42, 0.25, 0.1)), mat("yellow", (1.0, 0.88, 0.15))

def empty(name, loc=(0, 0, 0)):
    o = bpy.data.objects.new(name, None); o.location = loc; scene.collection.objects.link(o); return o

def sphere(name, loc, scale, m, parent=None, ico=False):
    if ico: bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, location=loc)
    else:   bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, location=loc)
    o = bpy.context.active_object; o.name = name; o.scale = scale; o.data.materials.append(m)
    if not ico: bpy.ops.object.shade_smooth()
    if parent: o.parent = parent
    return o

def key(o, path, frame, value):
    setattr(o, path, value); o.keyframe_insert(data_path=path, frame=frame)

def fcurves(o):
    """F-curves of an object's action, on Blender 4.2 (legacy actions) and 4.4+/5.x (slotted, layered actions)."""
    a = o.animation_data.action
    try:
        return list(a.fcurves)
    except AttributeError:
        out = []
        for layer in a.layers:
            for strip in layer.strips:
                for slot in a.slots:
                    cb = strip.channelbag(slot)
                    if cb: out += list(cb.fcurves)
        return out

# ground
bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, 0)); g = bpy.context.active_object; g.data.materials.append(GREEN)

# Gudu: everything parented to one empty at his feet, so squash/stretch happens from the ground up
gudu = empty("Gudu")
body = sphere("body", (0, 0, 1.2), (1.0, 1.0, 1.05), ORANGE, gudu)
for sx in (-1, 1):
    sphere(f"foot{sx}", (0.45 * sx, -0.1, 0.16), (0.32, 0.38, 0.16), DARKOR, gudu)
    sphere(f"cheek{sx}", (0.62 * sx, -0.72, 1.02), (0.15, 0.05, 0.1), PINK, gudu)
eyes = [sphere(f"eye{sx}", (0.34 * sx, -0.86, 1.55), (0.27, 0.12, 0.33), WHITE, gudu) for sx in (-1, 1)]
pupils = [sphere(f"pupil{sx}", (0.31 * sx, -0.98, 1.5), (0.11, 0.05, 0.14), BLACK, gudu) for sx in (-1, 1)]
mouth = sphere("mouth", (0, -1.0, 0.92), (0.24, 0.05, 0.07), BLACK, gudu)

# hop in from the left (lands on 16, 32, 48), squash on each landing, stretch in the air
hops = [(1, -6.0, 0.0), (8, -4.5, 1.4), (16, -3.0, 0.0), (24, -1.8, 1.1), (32, -1.0, 0.0), (40, -0.4, 0.7), (48, 0.0, 0.0)]
for f, x, z in hops:
    key(gudu, "location", f, (x, 0, z))
for f in (16, 32, 48): key(gudu, "scale", f, (1.18, 1.18, 0.78))
for f in (8, 24, 40):  key(gudu, "scale", f, (0.9, 0.9, 1.14))
key(gudu, "scale", 1, (1, 1, 1)); key(gudu, "scale", 54, (0.97, 0.97, 1.04)); key(gudu, "scale", 60, (1, 1, 1))

# smile, blink
key(mouth, "scale", 66, (0.24, 0.05, 0.07)); key(mouth, "scale", 72, (0.34, 0.05, 0.12))
for o in eyes + pupils:
    s = tuple(o.scale)
    key(o, "scale", 78, s); key(o, "scale", 82, (s[0], s[1], s[2] * 0.08)); key(o, "scale", 86, s)

# look up as the apple falls
for p in pupils:
    l = tuple(p.location)
    key(p, "location", 98, l); key(p, "location", 106, (l[0], l[1], l[2] + 0.14)); key(p, "location", 118, (l[0], l[1], l[2] + 0.14))

# the apple: falls (accelerating), bonks his head on frame 120, bounces away, lands
apple = sphere("apple", (0, -0.2, 9), (0.32, 0.32, 0.3), RED)
bpy.ops.mesh.primitive_cylinder_add(radius=0.04, depth=0.25, location=(0, -0.2, 9.35)); stem = bpy.context.active_object
stem.data.materials.append(BROWN); stem.parent = apple; stem.location = (0, 0, 0.35 / 0.3)
for f, loc in [(1, (0, -0.2, 9)), (96, (0, -0.2, 9)), (120, (0, -0.2, 2.55)), (122, (0.15, -0.2, 2.05)), (134, (1.6, -0.2, 3.6)), (152, (3.4, -0.2, 0.3)), (192, (3.6, -0.2, 0.3))]:
    key(apple, "location", f, loc)
for fc in fcurves(apple):
    for kp in fc.keyframe_points:
        if int(kp.co[0]) == 96: kp.interpolation = "QUAD"; kp.easing = "EASE_IN"

# bonk: big squash, shocked "O" mouth, eyes pop
key(gudu, "scale", 120, (1, 1, 1)); key(gudu, "scale", 122, (1.18, 1.18, 0.78)); key(gudu, "scale", 127, (0.95, 0.95, 1.08)); key(gudu, "scale", 133, (1, 1, 1))
key(mouth, "scale", 119, (0.34, 0.05, 0.12)); key(mouth, "scale", 121, (0.16, 0.05, 0.22)); key(mouth, "scale", 170, (0.16, 0.05, 0.22)); key(mouth, "scale", 182, (0.3, 0.05, 0.06))
for o in eyes:
    s = tuple(o.scale); key(o, "scale", 119, s); key(o, "scale", 121, (s[0] * 1.3, s[1], s[2] * 1.3)); key(o, "scale", 170, (s[0] * 1.3, s[1], s[2] * 1.3)); key(o, "scale", 180, s)

# stars circling his head
stars = empty("stars", (0, -0.2, 2.75))
for i in range(3):
    a = 2 * math.pi * i / 3
    sphere(f"star{i}", (0.85 * math.cos(a), 0.85 * math.sin(a), 2.75), (0.15, 0.15, 0.15), YELLOW, None).parent = stars
for o in stars.children: o.location = (o.location[0], o.location[1], 0)
key(stars, "scale", 1, (0, 0, 0)); key(stars, "scale", 121, (0, 0, 0)); key(stars, "scale", 125, (1, 1, 1)); key(stars, "scale", 176, (1, 1, 1)); key(stars, "scale", 182, (0, 0, 0))
key(stars, "rotation_euler", 121, (0, 0, 0)); key(stars, "rotation_euler", 182, (0, 0, 4 * math.pi))
for fc in fcurves(stars):
    if fc.data_path == "rotation_euler":
        for kp in fc.keyframe_points: kp.interpolation = "LINEAR"

# caption
bpy.ops.object.text_add(location=(0, -3.0, 3.55), rotation=(math.radians(90), 0, 0))
cap = bpy.context.active_object; cap.data.body = "GRAVITY 1 : GUDU 0"; cap.data.align_x = "CENTER"; cap.data.size = 0.5; cap.data.extrude = 0.0
cap.data.materials.append(mat("navy", (0.08, 0.1, 0.32)))
# keep the caption out of the ink-outline pass so the letters stay crisp
nolines = bpy.data.collections.new("no_outline"); scene.collection.children.link(nolines)
for c_ in list(cap.users_collection): c_.objects.unlink(cap)
nolines.objects.link(cap)
ls.select_by_collection = True; ls.collection = nolines; ls.collection_negation = "EXCLUSIVE"
key(cap, "scale", 1, (0, 0, 0)); key(cap, "scale", 150, (0, 0, 0)); key(cap, "scale", 156, (1.15, 1.15, 1.15)); key(cap, "scale", 160, (1, 1, 1))

# camera
target = empty("look", (0, 0, 1.6))
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); cam.data.lens = 32
cam.location = (0, -11.5, 2.3); scene.collection.objects.link(cam); scene.camera = cam
c = cam.constraints.new("TRACK_TO"); c.target = target; c.track_axis = "TRACK_NEGATIVE_Z"; c.up_axis = "UP_Y"

os.makedirs(OUT, exist_ok=True)
only = [int(x) for a in argv if a.startswith("--frames=") for x in a.split("=", 1)[1].split(",") if x.strip()]
if only:                             # test mode: render a few single stills, e.g. --frames=48,84,121,158
    for f in only:
        scene.frame_set(f); scene.render.filepath = os.path.join(OUT, f"still_{f:04d}.png"); bpy.ops.render.render(write_still=True)
    print("STILLS DONE ->", OUT); raise SystemExit
bpy.ops.render.render(animation=True)
print("RENDER DONE ->", OUT)
