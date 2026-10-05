"""Blender 2D cut-out scene, rendered headless:  blender -b -P blender2d/scene.py -- <assets_dir> <out.mp4>
Layers are textured planes in front of an orthographic camera:
  plate.png (set)  <  <char>_body.png  <  <char>_mouth_half.png / <char>_mouth_open.png  (same canvas as the body -> no placement)
Mouth visibility is keyframed from Rhubarb cues (X/A = closed, B/C/D/G/H = half, E/F = open), held >= 2 frames.
A slow eased camera push and a gentle idle sway keep the shot alive (shot grammar: locked/eased camera, readable face)."""
import bpy, json, os, sys

argv = sys.argv[sys.argv.index("--") + 1:]
A, OUT = argv[0], argv[1]
FPS = 24
cues = json.load(open(os.path.join(A, "line_rhubarb.json")))["mouthCues"]
dur = cues[-1]["end"]; NF = int(dur * FPS) + 12

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE"
sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
sc.render.fps = FPS; sc.frame_start, sc.frame_end = 1, NF
sc.render.film_transparent = False
sc.view_settings.view_transform = "Standard"


def plane(name, png, z, width):
    img = bpy.data.images.load(os.path.join(A, png))
    w, h = img.size
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, z))
    ob = bpy.context.active_object; ob.name = name
    ob.scale = (width, width * h / w, 1)
    mat = bpy.data.materials.new(name); mat.use_nodes = True
    nt = mat.node_tree; nt.nodes.clear()
    tex = nt.nodes.new("ShaderNodeTexImage"); tex.image = img; tex.interpolation = "Smart"
    emi = nt.nodes.new("ShaderNodeEmission"); tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader"); out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(tex.outputs["Color"], emi.inputs["Color"]); nt.links.new(tex.outputs["Alpha"], mix.inputs["Fac"])
    nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(emi.outputs[0], mix.inputs[2]); nt.links.new(mix.outputs[0], out.inputs[0])
    if hasattr(mat, "blend_method"): mat.blend_method = "BLEND"
    if hasattr(mat, "surface_render_method"): mat.surface_render_method = "BLENDED"
    ob.data.materials.append(mat)
    return ob


plate = plane("plate", "plate.png", 0.0, 16.0)
body = plane("body", "dadi_body.png", 0.1, 5.2); body.location = (1.2, -1.0, 0.1)
mouths = {}
for st in ("half", "open"):
    m = plane("mouth_" + st, f"dadi_mouth_{st}.png", 0.2, 5.2); m.location = (1.2, -1.0, 0.2 + (0.01 if st == "open" else 0)); m.parent = body
    m.location = (0, 0, 0.1 + (0.01 if st == "open" else 0)); m.scale = (1, 1, 1); mouths[st] = m
# parenting keeps the mouth glued to the body: one canvas, one transform

SHAPE = {"X": None, "A": None, "B": "half", "C": "half", "D": "open", "E": "open", "F": "half", "G": "half", "H": "half"}
track = [None] * (NF + 1)
for c in cues:
    for f in range(int(c["start"] * FPS) + 1, int(c["end"] * FPS) + 1):
        if f <= NF: track[f] = SHAPE.get(c["value"])
for f in range(2, NF + 1):          # hold every shape >= 2 frames (limited animation, no jitter)
    if track[f] != track[f - 1] and f + 1 <= NF and track[f + 1] != track[f]: track[f] = track[f - 1]
for st, ob in mouths.items():
    for f in range(1, NF + 1):
        vis = track[f] == st
        ob.hide_render = not vis; ob.keyframe_insert("hide_render", frame=f)
        ob.hide_viewport = not vis; ob.keyframe_insert("hide_viewport", frame=f)

cam_data = bpy.data.cameras.new("cam"); cam_data.type = "ORTHO"; cam_data.ortho_scale = 16.0
cam = bpy.data.objects.new("cam", cam_data); sc.collection.objects.link(cam); sc.camera = cam
cam.location = (0, 0, 10)
cam_data.keyframe_insert("ortho_scale", frame=1)
cam_data.ortho_scale = 11.0; cam.location = (1.0, 0.6, 10)   # slow push towards Dadi's face
cam_data.keyframe_insert("ortho_scale", frame=NF); cam.keyframe_insert("location", frame=NF)
cam.location = (0, 0, 10); cam.keyframe_insert("location", frame=1)
for fc in (cam.animation_data.action.fcurves if cam.animation_data and cam.animation_data.action else []):
    for k in fc.keyframe_points: k.interpolation = "SINE"
body.rotation_euler = (0, 0, 0); body.keyframe_insert("rotation_euler", frame=1)
body.rotation_euler = (0, 0, 0.012); body.keyframe_insert("rotation_euler", frame=NF // 2)
body.rotation_euler = (0, 0, 0); body.keyframe_insert("rotation_euler", frame=NF)

sc.sequence_editor_create()
sc.sequence_editor.sequences.new_sound("line", os.path.join(A, "line.wav"), 1, 1) if hasattr(sc.sequence_editor, "sequences") else sc.sequence_editor.strips.new_sound("line", os.path.join(A, "line.wav"), 1, 1)
r = sc.render; r.image_settings.file_format = "FFMPEG"; r.ffmpeg.format = "MPEG4"; r.ffmpeg.codec = "H264"
r.ffmpeg.audio_codec = "AAC"; r.ffmpeg.constant_rate_factor = "MEDIUM"; r.filepath = OUT
bpy.ops.render.render(animation=True)
print("RENDERED", OUT, NF, "frames")
