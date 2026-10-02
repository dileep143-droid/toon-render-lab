import bpy, sys
bpy.ops.wm.open_mainfile(filepath=sys.argv[sys.argv.index("--") + 1])
print("SCENES", [s.name for s in bpy.data.scenes], "ENGINE", bpy.context.scene.render.engine)
print("COLLECTIONS", [(c.name, len(c.all_objects)) for c in bpy.data.collections])
for o in bpy.data.objects:
    print("OBJ", o.type, o.name, "parent=", o.parent.name if o.parent else "-", "mats=", [m.name for m in o.data.materials] if o.type == "MESH" else "", "dims=", tuple(round(d, 2) for d in o.dimensions))
for m in bpy.data.materials:
    nodes = [n.bl_idname for n in m.node_tree.nodes] if m.use_nodes else []
    print("MAT", m.name, nodes[:12])
arm = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
if arm:
    names = [b.name for b in arm.pose.bones]
    print("BONES", len(names)); print("SOMEBONES", [n for n in names if any(k in n.lower() for k in ("root", "torso", "chest", "head", "neck", "hand_ik", "upper_arm", "forearm", "properties", "jaw", "mouth", "eye", "smile", "brow"))][:120])
    print("RIG PROPS", [k for k in arm.pose.bones[0].keys()][:40] if names else [])
    for b in arm.pose.bones:
        ks = list(b.keys())
        if ks and len(ks) < 40: print("PROPS on", b.name, ks)
