"""Traditional Indian look for the Rain rig: langa-voni (half saree), jewellery, jasmine, warm wheatish skin, brown eyes.
Call dress(rig) while the rig is at the origin with scale 1 and the pose already set; the clothes are parented to bones and follow."""
import bpy, bmesh, math
from mathutils import Matrix, Vector

def pmat(name, rgb, rough=0.55, sheen=0.0, metal=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name); m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (*[c ** 2.2 for c in rgb], 1); b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    try: b.inputs["Sheen Weight"].default_value = sheen
    except Exception: pass
    return m

def bone_world(rig, bone):
    return rig.matrix_world @ rig.pose.bones[bone].matrix

def attach(obj, rig, bone):
    """parent obj to a bone without moving it"""
    mw = obj.matrix_world.copy()
    obj.parent = rig; obj.parent_type = "BONE"; obj.parent_bone = bone
    bpy.context.view_layer.update(); obj.matrix_world = mw

def new_obj(name, me, mat):
    o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o)
    me.materials.append(mat); return o

def lathe(name, rings, segs=72, pleat=0.0, mat=None):
    """surface of revolution from rings [(z, rx, ry)], optional pleats (folds) that grow towards the hem"""
    me = bpy.data.meshes.new(name); bm = bmesh.new(); grid = []
    zt, zb = rings[0][0], rings[-1][0]
    for z, rx, ry in rings:
        depth = (zt - z) / max(1e-6, zt - zb)
        row = []
        for i in range(segs):
            a = 2 * math.pi * i / segs
            k = 1 + (pleat * depth * (1 if i % 2 == 0 else -1))
            row.append(bm.verts.new((rx * k * math.cos(a), ry * k * math.sin(a), z)))
        grid.append(row)
    for r in range(len(grid) - 1):
        for i in range(segs):
            j = (i + 1) % segs
            bm.faces.new((grid[r][i], grid[r][j], grid[r + 1][j], grid[r + 1][i]))
    bm.to_mesh(me); bm.free()
    for p in me.polygons: p.use_smooth = True
    return new_obj(name, me, mat)

def strip(name, pts, width, mat, normal_hint=Vector((0, -1, 0))):
    """a cloth band following points pts (list of Vector), width across"""
    me = bpy.data.meshes.new(name); bm = bmesh.new(); L, Rt = [], []
    for i, p in enumerate(pts):
        d = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
        side = d.cross(normal_hint).normalized() * (width / 2)
        L.append(bm.verts.new(p + side)); Rt.append(bm.verts.new(p - side))
    for i in range(len(pts) - 1): bm.faces.new((L[i], L[i + 1], Rt[i + 1], Rt[i]))
    bm.to_mesh(me); bm.free()
    for p in me.polygons: p.use_smooth = True
    o = new_obj(name, me, mat)
    s = o.modifiers.new("thick", "SOLIDIFY"); s.thickness = 0.003
    return o

def smooth_path(pts, n=6):
    """Catmull-Rom style resample so the cloth curves smoothly instead of bending sharply"""
    out = []
    P = [pts[0]] + pts + [pts[-1]]
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for k in range(n):
            t = k / n
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(pts[-1]); return out

def ring_on_bone(name, rig, bone, at_tail, major, minor, mat):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, major_segments=32, minor_segments=8)
    o = bpy.context.active_object; o.name = name; o.data.materials.append(mat); bpy.ops.object.shade_smooth()
    bw = bone_world(rig, bone)
    pos = bw @ Vector((0, rig.pose.bones[bone].length if at_tail else 0, 0))
    o.matrix_world = Matrix.Translation(pos) @ bw.to_3x3().to_4x4() @ Matrix.Rotation(math.radians(90), 4, "X")
    attach(o, rig, bone); return o

def hue_shift(mat_name, hue, sat=1.0, val=1.0):
    m = bpy.data.materials.get(mat_name)
    if not m: return
    nt = m.node_tree; b = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"); inp = b.inputs["Base Color"]
    hs = nt.nodes.new("ShaderNodeHueSaturation"); hs.inputs["Hue"].default_value = hue; hs.inputs["Saturation"].default_value = sat; hs.inputs["Value"].default_value = val
    if inp.is_linked:
        src = inp.links[0].from_socket; nt.links.remove(inp.links[0]); nt.links.new(src, hs.inputs["Color"])
    else: hs.inputs["Color"].default_value = inp.default_value
    nt.links.new(hs.outputs["Color"], inp)

def dress(rig, skin_value=2.1):
    bpy.context.view_layer.update()
    # ---- skin: warm wheatish, like the kids in Indian 3D rhymes ----
    for mn in ("MAT-rain.body", "MAT-rain.hands"):
        m = bpy.data.materials.get(mn)
        if not m: continue
        for n in m.node_tree.nodes:
            if n.bl_idname == "ShaderNodeHueSaturation": n.inputs["Saturation"].default_value = 1.0
        hue_shift(mn, 0.505, 0.9, skin_value)            # brighten to a warm wheatish tone
        _mult(m, (1.0, 0.86, 0.74), linked_only=True)   # gentle warm peach
    # ---- eyes: blue irises -> dark brown (white stays white) ----
    hue_shift("MAT-rain.eyes", 0.92, 1.6, 0.55)
    # ---- hide modern clothes ----
    try: rig.pose.bones["Properties_Character_Rain"]["Scarf"] = False
    except Exception: pass
    for n in ("GEO-rain-jeans", "GEO-rain-scarf"):
        o = bpy.data.objects.get(n)
        if o: o.hide_render = True; o.hide_viewport = True
    green, gold = pmat("langa_green", (0.10, 0.55, 0.30), 0.45, sheen=0.6), pmat("zari_gold", (1.0, 0.76, 0.25), 0.3, metal=0.9)
    voni_c, blouse = pmat("voni_orange", (1.0, 0.55, 0.12), 0.5, sheen=0.8), (1.0, 0.25, 0.45)
    # blouse colour on her top
    top = bpy.data.materials.get("MAT-rain.top")
    if top: hue_shift("MAT-rain.top", 0.5, 0.0, 1.0); _mult(top, blouse)
    # ---- langa: long pleated skirt from waist to ankle, with a gold zari border ----
    skirt = lathe("langa", [(0.99, 0.135, 0.105), (0.90, 0.175, 0.13), (0.76, 0.215, 0.15), (0.45, 0.25, 0.20), (0.07, 0.33, 0.29)], pleat=0.07, mat=green)
    attach(skirt, rig, "DEF-Pelvis")
    hem = lathe("langa_border", [(0.17, 0.317, 0.278), (0.06, 0.34, 0.30)], pleat=0.07, mat=gold); attach(hem, rig, "DEF-Pelvis")
    belt = lathe("waist_border", [(1.0, 0.139, 0.109), (0.965, 0.149, 0.115)], segs=48, mat=gold); attach(belt, rig, "DEF-Spine1")
    # ---- voni: draped from the right waist across the chest, over the left shoulder, down the back ----
    pts = smooth_path([Vector(p) for p in [(-0.13, -0.112, 0.96), (-0.075, -0.13, 1.05), (-0.005, -0.142, 1.13), (0.06, -0.128, 1.205), (0.105, -0.085, 1.265),
                                           (0.12, -0.01, 1.29), (0.12, 0.06, 1.265), (0.115, 0.1, 1.15), (0.11, 0.105, 0.98)]])
    voni = strip("voni", pts, 0.11, voni_c); attach(voni, rig, "DEF-Spine3")
    edge = [p + (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized().cross(Vector((0, -1, 0))).normalized() * 0.05 + Vector((0, -0.003, 0)) for i, p in enumerate(pts)]
    vb = strip("voni_border", edge, 0.018, gold); attach(vb, rig, "DEF-Spine3")
    # ---- long braid (jada) down the back, jasmine woven at the top ----
    hair = pmat("braid_hair", (0.07, 0.05, 0.045), 0.45)
    for i in range(16):
        t = i / 15
        x = 0.012 * (1 if i % 2 else -1); y = 0.085 + 0.045 * t; z = 1.45 - 0.55 * t; r = 0.032 - 0.016 * t
        bpy.ops.mesh.primitive_uv_sphere_add(radius=1, segments=16, ring_count=8, location=(x, y, z))
        b = bpy.context.active_object; b.name = f"braid{i}"; b.scale = (r, r * 0.85, r * 1.35); b.rotation_euler = (0, math.radians(25 if i % 2 else -25), 0)
        b.data.materials.append(hair); bpy.ops.object.shade_smooth(); attach(b, rig, "DEF-Head" if i < 3 else "DEF-Spine3")
    bpy.ops.mesh.primitive_cylinder_add(radius=0.012, depth=0.05, location=(0, 0.13, 0.88))
    tassel = bpy.context.active_object; tassel.name = "braid_tassel"; tassel.data.materials.append(pmat("tassel_red", (0.9, 0.12, 0.2))); attach(tassel, rig, "DEF-Spine3")
    # ---- jewellery: necklace, bangles, jhumkas; jasmine in the hair ----
    neck = ring_on_bone("necklace", rig, "DEF-Neck", False, 0.075, 0.006, gold)
    for side in ("L", "R"):
        for k, off in enumerate((0.0, 0.012, 0.024)):
            b = ring_on_bone(f"bangle{side}{k}", rig, f"DEF-Forearm2.{side}", True, 0.034, 0.005, gold if k != 1 else pmat("bangle_red", (0.9, 0.1, 0.15), 0.3))
            bpy.context.view_layer.update(); b.matrix_world = b.matrix_world @ Matrix.Translation((0, 0, -off - 0.01))
        ear = bone_world(rig, f"DEF-Ear_Bot.{side}")
        tip = ear @ Vector((0, rig.pose.bones[f"DEF-Ear_Bot.{side}"].length, 0))
        bpy.ops.mesh.primitive_cone_add(radius1=0.012, radius2=0.002, depth=0.02, vertices=16, location=tip - Vector((0, 0, 0.018)))
        j = bpy.context.active_object; j.name = f"jhumka{side}"; j.data.materials.append(gold); bpy.ops.object.shade_smooth(); attach(j, rig, "DEF-Head")
    jas = pmat("jasmine", (0.98, 0.98, 0.94), 0.6)
    for i in range(9):
        a = math.radians(-70 + i * 17.5)
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.011, segments=10, ring_count=6, location=(0.085 * math.sin(a), 0.07 + 0.03 * math.cos(a), 1.47 + 0.01 * math.cos(a)))
        f = bpy.context.active_object; f.name = f"jasmine{i}"; f.data.materials.append(jas); attach(f, rig, "DEF-Head")

def _mult(mat, rgb, linked_only=False):
    nt = mat.node_tree; b = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"); inp = b.inputs["Base Color"]
    if not inp.is_linked:
        if linked_only: return
        inp.default_value = (*[c ** 2.2 for c in rgb], 1); return
    mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.blend_type = "MULTIPLY"; mix.inputs[0].default_value = 1.0
    mix.inputs[7].default_value = (*[c ** 2.2 for c in rgb], 1)
    src = inp.links[0].from_socket; nt.links.remove(inp.links[0]); nt.links.new(src, mix.inputs[6]); nt.links.new(mix.outputs[2], inp)
