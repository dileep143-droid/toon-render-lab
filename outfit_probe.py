"""Probe (temporary): print MPFB basemesh vertex groups, modifiers, bones for an 8y girl and a man."""
import bpy, sys, os, math
from mathutils import Vector
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
PACK, FUNC = sys.argv[sys.argv.index("--") + 1:][:2]
import mpfb_child as MC
MC.install_packs(PACK, FUNC)
import inspect
print("PROBE SIG create_human", inspect.signature(MC.HS.create_human))
for age, g in ((0.13125, 0.0), (0.55, 1.0)):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    macros = {"gender": g, "age": age, "muscle": 0.5, "weight": 0.55, "proportions": 0.5, "height": 0.5, "cupsize": 0.5, "firmness": 0.5,
              "race": {"african": 0.15, "asian": 0.55, "caucasian": 0.30}}
    h = MC.HS.create_human(macro_detail_dict=macros, feet_on_ground=True, scale=0.1)
    rig = MC.HS.add_builtin_rig(h, "default")
    bpy.context.view_layer.update()
    print("PROBE age", age, "dims", tuple(round(x, 3) for x in h.dimensions), "verts", len(h.data.vertices), "loc", tuple(h.location), "parent", h.parent)
    print("PROBE mods", [(m.type, m.name, getattr(m, "vertex_group", None)) for m in h.modifiers])
    vg = {g.index: g.name for g in h.vertex_groups}
    cnt = {}
    for v in h.data.vertices:
        for ge in v.groups:
            if ge.weight > 0.05: cnt[vg[ge.group]] = cnt.get(vg[ge.group], 0) + 1
    print("PROBE vgroups", len(vg), sorted(cnt.items()))
    print("PROBE bones", [b.name for b in rig.data.bones])
    for b in rig.data.bones:
        if b.name in ("root", "pelvis.L", "spine05", "spine03", "spine01", "neck01", "head", "clavicle.L", "upperarm01.L", "lowerarm01.L", "wrist.L", "upperleg01.L", "upperleg02.L", "lowerleg01.L", "lowerleg02.L", "foot.L", "toe1-1.L"):
            print("PROBE bone", b.name, tuple(round(x, 3) for x in (rig.matrix_world @ b.head_local)), tuple(round(x, 3) for x in (rig.matrix_world @ b.tail_local)), "parent", b.parent.name if b.parent else None)
    print("PROBE children", [(o.name, o.type) for o in rig.children_recursive])
print("PROBE DONE")
