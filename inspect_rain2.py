import bpy, sys
bpy.ops.wm.open_mainfile(filepath=sys.argv[sys.argv.index("--") + 1])
arm = bpy.data.objects["RIG-rain"]
ctrl = [b.name for b in arm.pose.bones if not b.name.split("-")[0] in ("DEF", "ORG", "MCH", "TAN", "BB", "N", "P", "AIM", "STR", "TGT", "ROT", "IK_POLE_HELP") and not b.name.startswith(("DEF", "ORG", "MCH", "TAN", "AIM", "N-", "P-", "BB-"))]
print("CONTROLS", len(ctrl)); print("CTRL", ctrl[:400])
for n in ("Properties_IKFK", "Properties_Character_Rain", "Properties_Face"):
    b = arm.pose.bones.get(n)
    if b: print("PROPS", n, {k: (b[k] if isinstance(b[k], (int, float, str)) else type(b[k]).__name__) for k in b.keys()})
for k in arm.keys(): print("ARMPROP", k)
head = bpy.data.objects["GEO-rain-head"]
mw = head.matrix_world
vs = [mw @ v.co for v in head.data.vertices]
print("HEAD bounds x", round(min(v.x for v in vs), 3), round(max(v.x for v in vs), 3), "y", round(min(v.y for v in vs), 3), round(max(v.y for v in vs), 3), "z", round(min(v.z for v in vs), 3), round(max(v.z for v in vs), 3))
mat = bpy.data.materials["MAT-rain.body"]
for n in mat.node_tree.nodes: print("BODYNODE", n.bl_idname, n.name, [(i.name, i.default_value[:] if hasattr(i.default_value, "__len__") else i.default_value) for i in n.inputs if hasattr(i, "default_value") and not i.is_linked][:6])
for mn in ("MAT-rain.top", "MAT-rain.jeans", "MAT-rain.scarf", "MAT-rain.hair"):
    m = bpy.data.materials[mn]
    for n in m.node_tree.nodes:
        if n.bl_idname == "ShaderNodeValToRGB": print("RAMP", mn, n.name, [tuple(round(c, 2) for c in e.color) for e in n.color_ramp.elements])
        if n.bl_idname == "ShaderNodeBsdfPrincipled": print("BSDF", mn, "base linked:", n.inputs["Base Color"].is_linked, tuple(round(c, 2) for c in n.inputs["Base Color"].default_value))
