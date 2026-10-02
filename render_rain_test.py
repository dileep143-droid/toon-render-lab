"""Test: Infobells-style shot. Blender Studio's 'Rain' rig (CC-BY 4.0, credit: Blender Studio) restyled as an Indian village girl,
standing in our village with soft sunlight and a blurred background.
Run:  blender -b --python render_rain_test.py -- <out_folder> [--fast]"""
import bpy, os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import village as V
R = math.radians

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(argv[0] if argv else "rain_test"); FAST = "--fast" in argv
HERE = os.path.dirname(os.path.abspath(__file__))
RAIN = os.path.join(HERE, "assets", "rain", "Rain v3.3", "rain_v3.2.blend")

sc = V.setup_shaded(fast=FAST, frames=120)
V.build_village(120)
# the old block-built villagers don't fit this style: remove them (cows, carts and the village itself stay)
def drop(o):
    for ch in list(o.children): drop(ch)
    bpy.data.objects.remove(o, do_unlink=True)
for n in ("water_woman", "farmer", "tea_man", "elder1", "elder2", "well_woman", "kid0", "kid1", "kid2", "school1", "cart_driver", "bike_rider", "kidsball"):
    o = bpy.data.objects.get(n)
    if o: drop(o)
w = sc.world.node_tree.nodes["Background"]; w.inputs[0].default_value = (0.30, 0.55, 1.0, 1); w.inputs[1].default_value = 0.9
bpy.data.lights["sun"].energy = 3.6
sc.view_settings.view_transform = "Standard"; sc.view_settings.look = "None"; sc.view_settings.exposure = 0.0

# ---- bring in Rain ----
with bpy.data.libraries.load(RAIN, link=False) as (src, dst):
    dst.collections = ["CH-rain"]
col = dst.collections[0]; sc.collection.children.link(col)
for name in ("rain-rig-widgets", "rain-eyes-viewport", "rain-rig-helpers"):
    c = bpy.data.collections.get(name)
    if c: c.hide_render = True
cornea = bpy.data.objects.get("GEO-rain-eye_cornea")
if cornea: cornea.hide_render = True          # the glassy eye layer renders as solid white here; the eyes underneath have the irises
rig = bpy.data.objects["RIG-rain"]
import rain_dress

def tint(mat_name, rgb, strength=1.0, recolour=False):
    """multiply a material's base colour by an (sRGB) tint, keeping its textures and shading detail.
    recolour=True first turns the original colour to grey, so the new colour comes out true (yellow stays yellow)."""
    m = bpy.data.materials.get(mat_name)
    if not m: return
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    inp = bsdf.inputs["Base Color"]
    mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.blend_type = "MULTIPLY"
    mix.inputs[0].default_value = strength
    mix.inputs[7].default_value = (*[c ** 2.2 for c in rgb], 1)          # B colour
    src_sock = None
    if inp.is_linked:
        src_sock = inp.links[0].from_socket; nt.links.remove(inp.links[0])
    if recolour and src_sock is not None:
        grey = nt.nodes.new("ShaderNodeHueSaturation"); grey.inputs["Saturation"].default_value = 0.0; grey.inputs["Value"].default_value = 1.6
        nt.links.new(src_sock, grey.inputs["Color"]); src_sock = grey.outputs["Color"]
    if src_sock is not None: nt.links.new(src_sock, mix.inputs[6])        # A colour
    else: mix.inputs[6].default_value = inp.default_value
    nt.links.new(mix.outputs[2], inp)

# hair black; the rest of the look (skin, eyes, langa-voni, jewellery) is done by rain_dress after posing
tint("MAT-rain.hair", (0.22, 0.16, 0.13))
tint("MAT-rain.hairband", (1.0, 0.45, 0.1))

# ---- pose: arms down, right hand waving (axes measured with pose_test.py: left arm down = -Z, right arm down = +Z) ----
pb = rig.pose.bones
try:
    pb["Properties_IKFK"]["ik_arm_right"] = 0.0; pb["Properties_IKFK"]["ik_arm_left"] = 0.0
    pb["Properties_Character_Rain"]["Eye_Dots"] = False        # full eyes with irises, not dot eyes
except Exception as ex: print("prop warning", ex)
def rot(bone, x=0, y=0, z=0):
    b = pb.get(bone)
    if b: b.rotation_mode = "XYZ"; b.rotation_euler = (R(x), R(y), R(z))
rot("FK-Upperarm.L", 0, 0, -72); rot("FK-Forearm.L", 0, 0, -12)
rot("FK-Upperarm.R", 0, 0, 12); rot("FK-Forearm.R", 0, 0, -100); rot("FK-Hand.R", 0, 0, -10)
rot("FK-Head", 4, 0, -6)
for c in ("ACT-Cheek_Outer.L", "ACT-Cheek_Outer.R"):
    b = pb.get(c)
    if b: b.location = (0, 0, 0.012)
bpy.context.view_layer.update()
rain_dress.dress(rig)                       # traditional clothes, built at the origin and attached to bones
rig.location = (-1.2, -1.0, 0); rig.scale = (0.82, 0.82, 0.82); rig.rotation_euler = (0, 0, R(-8))
bpy.context.view_layer.update()

# ---- bindi: small red dot on the forehead, found from the head mesh ----
dg = bpy.context.evaluated_depsgraph_get()
head = bpy.data.objects["GEO-rain-head"].evaluated_get(dg); mw = head.matrix_world
vs = [mw @ v.co for v in head.data.vertices]
cx = sum(v.x for v in vs) / len(vs)
zmin, zmax = min(v.z for v in vs), max(v.z for v in vs)
band = [v for v in vs if abs(v.x - cx) < 0.012 * 0.82 and zmin + 0.62 * (zmax - zmin) < v.z < zmin + 0.70 * (zmax - zmin)]
if band:
    f = min(band, key=lambda v: v.y)
    V.add("ball", "bindi", "red", None, (f.x, f.y - 0.004, f.z), scale=(0.009, 0.004, 0.009))

# ---- camera: medium shot like a kids' show, background softly out of focus ----
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.lens = 50; cam.location = (-0.75, -4.4, 1.12); cam.rotation_euler = (R(88), 0, R(6))
cam.data.dof.use_dof = True
foc = V.E("focus", (-1.2, -1.0, 1.15)); cam.data.dof.focus_object = foc; cam.data.dof.aperture_fstop = 1.2

os.makedirs(OUT, exist_ok=True)
sc.frame_set(1); sc.render.filepath = os.path.join(OUT, "rain_village_still.png"); bpy.ops.render.render(write_still=True)
print("STILL DONE ->", OUT)
