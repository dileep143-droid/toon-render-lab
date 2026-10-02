import bpy, sys
bpy.ops.wm.open_mainfile(filepath=sys.argv[sys.argv.index("--") + 1])
arm = bpy.data.objects["RIG-rain"]
want = ("Pelvis", "Hips", "Spine", "Chest", "Ribcage", "Neck", "Head", "Hand", "Forearm", "Shoulder", "Clavicle", "Ear")
for b in arm.data.bones:
    if b.name.startswith("DEF-") and any(w in b.name for w in want) and b.use_deform:
        h = arm.matrix_world @ b.head_local; t = arm.matrix_world @ b.tail_local
        print("DEF", b.name, "head", tuple(round(v, 3) for v in h), "tail", tuple(round(v, 3) for v in t))
for mn in ("MAT-rain.eyes",):
    m = bpy.data.materials[mn]
    for n in m.node_tree.nodes: print("EYENODE", n.bl_idname, n.name, n.image.name if getattr(n, "image", None) else "")
