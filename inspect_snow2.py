import bpy, sys
bpy.ops.wm.open_mainfile(filepath=sys.argv[sys.argv.index("--") + 1])
for o in bpy.data.objects:
    if o.type == "MESH" and o.name.startswith("GEO-snow") and o.data is not None:
        print("SLOTS", o.name, [(s.link, s.material.name if s.material else None) for s in o.material_slots])
arm = bpy.data.objects["RIG-Snow"]; pb = arm.pose.bones
names = [b.name for b in pb]
print("NBONES", len(names))
print("FK", [n for n in names if n.startswith(("FK-", "IK-")) and any(k in n for k in ("arm", "Arm", "Hand", "Head", "Neck", "Shoulder", "Clav", "Chest", "Spine", "Torso", "Hip"))])
print("DEF", [n for n in names if n.startswith("DEF-") and any(k in n for k in ("elvis", "Spine", "Chest", "Neck", "Head", "Forearm", "Ear", "Hips", "Torso"))])
print("MSTR", [n for n in names if n.startswith(("MSTR-", "ROOT", "root", "P-Torso", "Torso"))][:40])
print("PROPBONES", [n for n in names if "ropert" in n])
for n in [n for n in names if "ropert" in n]:
    print("P", n, {k: (pb[n][k] if isinstance(pb[n][k], (int, float, str)) else "grp") for k in pb[n].keys()})
for m in bpy.data.materials:
    if m.name.startswith("snow"): print("MAT", m.name, [n.bl_idname for n in m.node_tree.nodes][:12] if m.use_nodes else "")
