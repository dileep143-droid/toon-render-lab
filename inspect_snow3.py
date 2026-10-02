import bpy, sys
bpy.ops.wm.open_mainfile(filepath=sys.argv[sys.argv.index("--") + 1])
for mn in ("snow.skin", "snow.shirt", "snow.pants", "snow.skin_darker", "snow.skin_upper_lip"):
    m = bpy.data.materials[mn]; nt = m.node_tree
    print("MAT", mn, "users", m.users)
    for l in nt.links: print("  L", mn, l.from_node.bl_idname, l.from_node.name, l.from_socket.name, "->", l.to_node.bl_idname, l.to_node.name, l.to_socket.name)
    for n in nt.nodes:
        if n.bl_idname == "ShaderNodeGroup": print("  GROUP", n.node_tree.name, [x.bl_idname for x in n.node_tree.nodes])
        if n.bl_idname == "ShaderNodeTexImage" and n.image: print("  IMG", n.name, n.image.name, n.image.filepath)
for o in bpy.data.objects:
    if o.name.startswith("GEO-snow"):
        print("DRV", o.name, [d.data_path for d in (o.animation_data.drivers if o.animation_data else [])][:6], [md.type + ":" + md.name for md in o.modifiers][:10])
