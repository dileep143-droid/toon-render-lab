import bpy, sys
bpy.ops.wm.open_mainfile(filepath=sys.argv[sys.argv.index("--") + 1])
print("COLLECTIONS", [(c.name, len(c.all_objects)) for c in bpy.data.collections][:20])
for o in bpy.data.objects:
    if o.type in ("MESH", "ARMATURE") and o.data is not None and not o.name.startswith("WGT"):
        print("OBJ", o.type, o.name, [m.name for m in o.data.materials if m] if o.type == "MESH" else "", tuple(round(d, 2) for d in o.dimensions))
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
pb = arm.pose.bones
for n in [b.name for b in pb if b.name.startswith("Properties")]:
    print("PROPS", n, {k: (pb[n][k] if isinstance(pb[n][k], (int, float, str)) else "grp") for k in pb[n].keys()})
print("HAS", [n for n in ("FK-Upperarm.L", "FK-Upperarm.R", "FK-Forearm.L", "FK-Forearm.R", "FK-Hand.R", "FK-Head", "DEF-Pelvis", "DEF-Spine3", "DEF-Neck", "DEF-Head", "DEF-Forearm2.L", "DEF-Ear_Bot.L") if n in pb])
print("FACE", sorted({b.name for b in pb if any(k in b.name for k in ("Mouth", "Lip_Corner", "Corner", "Cheek", "Eyelid", "Jaw", "Smile", "Brow")) and not b.name.startswith(("DEF", "ORG", "MCH", "TAN", "AIM", "N-", "P-", "BB-"))})[:80])
for m in bpy.data.materials:
    if m.use_nodes and any(n.bl_idname == "ShaderNodeHueSaturation" for n in m.node_tree.nodes): print("HSMAT", m.name)
