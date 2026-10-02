"""Friendly CARTOON look for MPFB / MakeHuman characters (Infobells / kids-3D-rhymes style), so the cast matches the
clean cartoon props of lib_props.py instead of looking photo-real.

    h, rig = mpfb_child.make_child(...)          # 1. build the character (faces=True is fine)
    lib_toon.toonify(h, rig, skin_rgb=...)       # 2. toon proportions + shading  (BEFORE dress)
    G = lib_outfits.dress(h, rig, outfit)        # 3. clothes are built on the toon body, so they fit
    lib_toon.toonify_scene()                     # 4. flatten the cloth shading (+ outline if toonify(outline=True))

CALL ORDER: toonify() changes the body SHAPE, so call it BEFORE lib_outfits.dress(). dress() measures the body with its
shape keys applied (lib_outfits._rest_mesh), so every garment, accessory and the footwear is fitted to the toon body.
Proportions are NOT done with pose-bone scaling (lib_outfits.set_pose() and animation reset pose bones, and dress() works
in the rest pose). They are done with ONE smooth spatial warp that is applied consistently to
  * the basemesh, as an extra shape key "toon_proportions" (MPFB targets and the ARKit face units keep working on top),
  * every proxy mesh of the character (eyes, eyebrows, eyelashes, hair, teeth, ...), so nothing floats or pokes through,
  * the rig's REST bones (edit bones), so joints stay inside the warped mesh and animation deforms correctly.
If toonify() is called AFTER dress() anyway, the garments (children of the rig) are warped with the same function, so
they still fit; lib_outfits' body cache is cleared.

The warp: head scaled ~15 % about the top of the neck (smooth ramp up the neck), eyes (eyeball + socket + lids) ~20 %
about each eyeball centre, slightly narrower lower jaw (softer, younger face), and for children slightly shorter lower
legs (the ground stays at the feet). Adults (Dadi etc.) get a gentler version.
Shading: flat wheatish skin (a little of the original albedo kept for lips), low specular, subtle subsurface, soft warm
rim, a touch of self-emission to lift the shadows (flatter, cartoon-like); glossy enlarged-iris eyes; darker, slightly
bigger eyebrows; flat dark-brown hair with a soft specular band (hair alpha is kept). Optional inverted-hull outline.
"""
import bpy, math, sys
from mathutils import Vector

STYLES = {
    "infobells": dict(head=0.20, eyes=0.25, jaw=0.05, legs=0.07, adult=0.6,
                      tex_mix=0.22, rim=0.15, emit=0.06, skin_gain=0.9, rough=0.6, spec=0.22, sss=0.12,
                      iris=1.2, brow_x=1.08, brow_z=1.35,
                      hair_rgb=(0.09, 0.06, 0.045), hair_fac=0.92, brow_rgb=(0.035, 0.025, 0.02),
                      outline_rgb=(0.16, 0.09, 0.05), outline_body=0.0022, outline_cloth=0.003),
}
OUTLINE_MOD = "toon_outline"


# ----------------------------------------------------------------------------------------------- helpers
def _lin(c):
    return tuple((x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4) for x in c[:3])


def _inp(node, names):
    for n in names:
        if n in node.inputs: return node.inputs[n]
    return None


def _set(node, names, v):
    s = _inp(node, names if isinstance(names, (tuple, list)) else (names,))
    if s is not None and not s.is_linked:
        try: s.default_value = v
        except Exception: pass
    return s


def _smooth(a, b, x):
    t = max(0.0, min(1.0, (x - a) / (b - a))) if b != a else (1.0 if x >= b else 0.0)
    return t * t * (3 - 2 * t)


def _rest_coords(o):
    """local rest coordinates (shape keys mixed, no modifiers) - same vertex order as o.data"""
    saved = [(m, m.show_viewport) for m in o.modifiers]
    for m in o.modifiers: m.show_viewport = False
    bpy.context.view_layer.update()
    try:
        dg = bpy.context.evaluated_depsgraph_get(); ev = o.evaluated_get(dg); me = ev.to_mesh()
        co = [v.co.copy() for v in me.vertices]; ev.to_mesh_clear()
    finally:
        for m, s in saved: m.show_viewport = s
        bpy.context.view_layer.update()
    if len(co) != len(o.data.vertices): co = [v.co.copy() for v in o.data.vertices]
    return co


def _char_meshes(h, rig):
    out = []
    for o in [h] + list(set(rig.children_recursive) | set(h.children_recursive)):
        if o.type == "MESH" and o not in out: out.append(o)
    return out


def _kind(o, h):
    n = o.name.lower()
    if o == h: return "body"
    if o.get("outfit_piece") or o.get("outfit_foot"): return "cloth"
    if "eyebrow" in n: return "brow"
    if "eyelash" in n: return "lash"
    if "high-poly" in n or "low-poly" in n or (("eye" in n) and "brow" not in n and "lash" not in n): return "eyes"
    if "teeth" in n or "tongue" in n: return "mouth"
    try:
        t = sys.modules.get("lib_outfits") and sys.modules["lib_outfits"]._otype(o)
        if t: t = str(t).lower()
        if t == "hair": return "hair"
        if t == "clothes": return "cloth"
    except Exception: pass
    if "hair" in n or any(w in n for w in ("braid", "ponytail", "bob0", "short0", "long0", "afro")): return "hair"
    return "other"


# ----------------------------------------------------------------------------------------------- the warp
class _Warp:
    """one smooth spatial warp in RIG space (z up, x left-right); applied to meshes, proxies and rest bones alike"""

    def __init__(self, h, rig, st, strength, kid):
        self.Mr = rig.matrix_world.copy(); self.Mri = self.Mr.inverted()
        B = rig.data.bones
        def bh(n): return B[n].head_local.copy() if n in B else None
        head, neck = bh("head"), bh("neck01") or bh("neck02")
        hq = [self.Mri @ (h.matrix_world @ c) for c in _rest_coords(h)]
        bg = h.vertex_groups.get("body")
        if bg is not None:
            idx = {v.index for v in h.data.vertices for g in v.groups if g.group == bg.index and g.weight > 0.5}
            body = [hq[i] for i in idx] or hq
        else: body = hq
        self.ground = min(p.z for p in body); top = max(p.z for p in body)
        if head is None:   # no named bones: estimate from the body bbox
            head = Vector((0, 0, self.ground + 0.87 * (top - self.ground)))
        if neck is None: neck = Vector((head.x, head.y, head.z - 0.06 * (top - self.ground)))
        adult = 1.0 if kid else st["adult"]
        self.sh = 1 + st["head"] * strength * adult
        self.se = 1 + st["eyes"] * strength * (1.0 if kid else 0.75)
        self.jaw = st["jaw"] * strength * adult
        self.legk = 1 - st["legs"] * strength if kid else 1.0
        self.pivot = head; dz = max(1e-4, head.z - neck.z)
        self.z0, self.z1 = neck.z + 0.45 * dz, head.z + 0.05 * dz
        # eye centres: centroid of each half of the eyes proxy, else eye bones
        eyes = [o for o in _char_meshes(h, rig) if _kind(o, h) == "eyes"]
        cs = []
        if eyes:
            pts = [self.Mri @ (eyes[0].matrix_world @ c) for c in _rest_coords(eyes[0])]
            for side in (1, -1):
                s_ = [p for p in pts if (p.x - head.x) * side > 0]
                if s_: cs.append(sum(s_, Vector()) / len(s_))
        if len(cs) != 2:
            cs = [c for c in (bh("eye.L"), bh("eye.R")) if c is not None]
        self.eyes = [self._head(c) for c in cs] if len(cs) == 2 else []
        self.d = (self.eyes[0] - self.eyes[1]).length if self.eyes else 0.06 * self.sh
        self.eye_z = sum(c.z for c in self.eyes) / 2 if self.eyes else head.z + 0.5 * dz
        knees = [c for c in (bh("lowerleg01.L"), bh("lowerleg01.R")) if c is not None]
        self.knee = sum(c.z for c in knees) / len(knees) if knees else self.ground + 0.28 * (top - self.ground)
        self.info = dict(kid=kid, head_scale=round(self.sh, 3), eye_scale=round(self.se, 3), leg_k=round(self.legk, 3),
                         ipd=round(self.d, 4), height=round(top - self.ground, 3), knee=round(self.knee - self.ground, 3))

    def _head(self, p):
        w = _smooth(self.z0, self.z1, p.z)
        return self.pivot + (p - self.pivot) * (1 + (self.sh - 1) * w) if w > 0 else p.copy()

    def __call__(self, p):
        p = self._head(p)
        if self.eyes and self.se != 1:
            for c in self.eyes:
                r = (p - c).length
                w = 1 - _smooth(0.24 * self.d, 0.46 * self.d, r)
                if w > 0: p = c + (p - c) * (1 + (self.se - 1) * w)
        if self.jaw:
            z = p.z; e = self.eye_z; d = self.d
            w = _smooth(e - 2.1 * d, e - 1.6 * d, z) * (1 - _smooth(e - 1.0 * d, e - 0.55 * d, z))
            if w > 0: p = Vector((self.pivot.x + (p.x - self.pivot.x) * (1 - self.jaw * w), p.y, p.z))
        if self.legk != 1:
            g, k = self.ground, self.knee
            p = Vector((p.x, p.y, g + (p.z - g) * self.legk if p.z < k else p.z - (1 - self.legk) * (k - g)))
        return p

    def apply_mesh(self, o):
        Mo = o.matrix_world; R = self.Mri @ Mo; Ri = R.inverted()
        q = _rest_coords(o)
        new = [Ri @ self(R @ c) for c in q]
        if o.data.shape_keys:
            kb = o.data.shape_keys.key_blocks
            basis = o.data.shape_keys.reference_key
            k = kb.get("toon_proportions") or o.shape_key_add(name="toon_proportions", from_mix=False)
            k.relative_key = basis
            for i, (a, b) in enumerate(zip(q, new)): k.data[i].co = basis.data[i].co + (b - a)
            k.slider_min = 0.0; k.value = 1.0
        else:
            for v, b in zip(o.data.vertices, new): v.co = b
            o.data.update()

    def apply_bones(self, rig):
        vl = bpy.context.view_layer; prev = vl.objects.active
        hid = rig.hide_get(); rig.hide_set(False); vl.objects.active = rig
        try:
            bpy.ops.object.mode_set(mode="EDIT")
            pts = {eb.name: (self(eb.head.copy()), self(eb.tail.copy())) for eb in rig.data.edit_bones}   # armature space == rig space
            for eb in rig.data.edit_bones:
                hd, tl = pts[eb.name]
                if eb.use_connect and eb.parent: tl = tl
                eb.head = hd; eb.tail = tl
            bpy.ops.object.mode_set(mode="OBJECT")
            return True
        except Exception as ex:
            print("TOON bones not warped:", repr(ex)[:200])
            try: bpy.ops.object.mode_set(mode="OBJECT")
            except Exception: pass
            return False
        finally:
            rig.hide_set(hid); vl.objects.active = prev


# ----------------------------------------------------------------------------------------------- materials
def _out(nt):
    return next((n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial" and n.is_active_output), None) or \
        next((n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial"), None)


def _find_albedo(nt, seen=None):
    seen = seen or set()
    if nt.name in seen: return None
    seen.add(nt.name); best = None
    for n in nt.nodes:
        if n.bl_idname == "ShaderNodeGroup" and n.node_tree:
            r = _find_albedo(n.node_tree, seen)
            if r and (best is None or "diffuse" in r.name.lower()): best = r
        if n.bl_idname == "ShaderNodeTexImage" and n.image:
            nm = n.image.name.lower()
            if any(w in nm for w in ("normal", "_nor", "rough", "spec", "bump", "sss", "_ao", "alpha", "trans", "displ")) \
                    and not any(w in nm for w in ("diffuse", "albedo", "color", "colour")): continue
            if best is None or "diffuse" in nm or "albedo" in nm: best = n.image
    return best


def _principleds(nt, seen=None):
    seen = seen or set()
    if nt.name in seen: return []
    seen.add(nt.name); out = []
    for n in nt.nodes:
        if n.bl_idname == "ShaderNodeBsdfPrincipled": out.append(n)
        if n.bl_idname == "ShaderNodeGroup" and n.node_tree: out += _principleds(n.node_tree, seen)
    return out


def toon_skin_material(name, skin_rgb, st, albedo=None):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; N, L = nt.nodes, nt.links; N.clear()
    out = N.new("ShaderNodeOutputMaterial"); out.location = (900, 0)
    b = N.new("ShaderNodeBsdfPrincipled"); b.location = (600, 0)
    flat = (*_lin(tuple(c * st.get("skin_gain", 1.0) for c in skin_rgb)), 1.0)
    m.diffuse_color = flat
    col = None
    if albedo is not None and st["tex_mix"] > 0:
        tx = N.new("ShaderNodeTexImage"); tx.image = albedo; tx.location = (-600, 200)
        mul = N.new("ShaderNodeMix"); mul.data_type = "RGBA"; mul.blend_type = "MULTIPLY"; mul.inputs[0].default_value = 1.0
        L.new(tx.outputs["Color"], mul.inputs[6]); mul.inputs[7].default_value = tuple(min(1.0, c * 1.25) for c in flat[:3]) + (1,)
        mx = N.new("ShaderNodeMix"); mx.data_type = "RGBA"; mx.inputs[0].default_value = st["tex_mix"]
        mx.inputs[6].default_value = flat; L.new(mul.outputs[2], mx.inputs[7]); col = mx.outputs[2]
    # soft warm rim: Layer Weight facing -> ramp -> lighten
    lw = N.new("ShaderNodeLayerWeight"); lw.inputs["Blend"].default_value = 0.35; lw.location = (-300, -250)
    cr = N.new("ShaderNodeValToRGB"); cr.location = (-100, -250)
    cr.color_ramp.elements[0].position = 0.45; cr.color_ramp.elements[1].position = 0.95
    L.new(lw.outputs["Facing"], cr.inputs["Fac"])
    rimf = N.new("ShaderNodeMath"); rimf.operation = "MULTIPLY"; rimf.inputs[1].default_value = st["rim"]
    L.new(cr.outputs["Color"], rimf.inputs[0])
    rim = N.new("ShaderNodeMix"); rim.data_type = "RGBA"; rim.blend_type = "SCREEN"; rim.location = (300, 0)
    L.new(rimf.outputs[0], rim.inputs[0])
    if col is not None: L.new(col, rim.inputs[6])
    else: rim.inputs[6].default_value = flat
    rim.inputs[7].default_value = (*_lin((1.0, 0.88, 0.74)), 1)
    L.new(rim.outputs[2], b.inputs["Base Color"])
    _set(b, "Roughness", st["rough"]); _set(b, ("Specular IOR Level", "Specular"), st["spec"])
    _set(b, ("Subsurface Weight", "Subsurface"), st["sss"])
    _set(b, "Subsurface Radius", (1.0, 0.45, 0.28)); _set(b, "Subsurface Scale", 0.012)
    _set(b, ("Coat Weight",), 0.0); _set(b, ("Sheen Weight",), 0.0)
    e = _inp(b, ("Emission Color", "Emission"))
    if e is not None and st["emit"] > 0:
        L.new(rim.outputs[2], e); _set(b, "Emission Strength", st["emit"])
    L.new(b.outputs[0], out.inputs["Surface"])
    return m


def _tint(nt, rgb, fac, mode="MIX", seen=None):
    """re-colour every albedo texture in the tree in place (alpha links untouched)"""
    seen = seen if seen is not None else set()
    if nt.name in seen: return 0
    seen.add(nt.name); n_ = 0
    for n in list(nt.nodes):
        if n.bl_idname == "ShaderNodeGroup" and n.node_tree: n_ += _tint(n.node_tree, rgb, fac, mode, seen)
        if n.bl_idname == "ShaderNodeTexImage" and n.image:
            nm = n.image.name.lower()
            if any(w in nm for w in ("normal", "_nor", "rough", "spec", "bump", "alpha", "trans")) and not any(w in nm for w in ("diffuse", "albedo", "color", "colour")): continue
            links = list(n.outputs["Color"].links)
            if not links: continue
            mx = nt.nodes.new("ShaderNodeMix"); mx.data_type = "RGBA"; mx.blend_type = mode; mx.inputs[0].default_value = fac
            mx.inputs[7].default_value = (*_lin(rgb), 1)
            nt.links.new(n.outputs["Color"], mx.inputs[6])
            for l in links:
                to = l.to_socket; nt.links.remove(l); nt.links.new(mx.outputs[2], to)
            n_ += 1
    for b in [x for x in nt.nodes if x.bl_idname == "ShaderNodeBsdfPrincipled"]:
        bc = b.inputs["Base Color"]
        if not bc.is_linked: bc.default_value = (*_lin(rgb), 1); n_ += 1
    return n_


def _pupil_uv(nt, seen=None):
    """UV of the pupil = centroid of the darkest pixels of the eye's colour texture"""
    import numpy as np
    seen = seen if seen is not None else set()
    if nt.name in seen: return None
    seen.add(nt.name)
    for n in nt.nodes:
        if n.bl_idname == "ShaderNodeGroup" and n.node_tree:
            r = _pupil_uv(n.node_tree, seen)
            if r is not None: return r
        if n.bl_idname == "ShaderNodeTexImage" and n.image and n.image.size[0] > 8:
            nm = n.image.name.lower()
            if any(w in nm for w in ("normal", "_nor", "bump", "rough", "spec")): continue
            w, h = n.image.size
            px = np.empty(w * h * 4, dtype=np.float32); n.image.pixels.foreach_get(px); px = px.reshape(h, w, 4)
            lum = px[..., 0] * 0.3 + px[..., 1] * 0.59 + px[..., 2] * 0.11
            thr = np.percentile(lum, 0.4)
            ys, xs = np.nonzero(lum <= thr)
            if len(xs) < 4: continue
            if xs.std() > 0.08 * w or ys.std() > 0.08 * h:
                print("TOON pupil not one dark spot", n.image.name, round(float(xs.std()) / w, 3), round(float(ys.std()) / h, 3)); return None
            return (float(xs.mean() + 0.5) / w, float(ys.mean() + 0.5) / h)
    return None


def _iris_centre(o, rig):
    """UV of the pupil = UV of the front-most vertex of each eyeball (the character faces -Y in rig space)"""
    me = o.data
    if not me.uv_layers: return None
    uv = me.uv_layers.active.data; vuv = {}
    for lp in me.loops:
        if lp.vertex_index not in vuv: vuv[lp.vertex_index] = uv[lp.index].uv.copy()
    M = rig.matrix_world.inverted() @ o.matrix_world
    co = [M @ v.co for v in me.vertices]; cx = sum(p.x for p in co) / len(co); out = []
    for side in (1, -1):
        idx = [i for i, p in enumerate(co) if (p.x - cx) * side > 0 and i in vuv]
        if not idx: return None
        out.append(vuv[min(idx, key=lambda i: co[i].y)])
    if (out[0] - out[1]).length > 0.05: print("TOON iris: eyes use different UV islands", out); return None
    return (out[0] + out[1]) / 2


def _iris(nt, scale, centre=None, seen=None):
    """enlarge the iris: scale the eye texture's UVs about the pupil's UV"""
    seen = seen if seen is not None else set()
    if nt.name in seen or scale == 1 or centre is None: return
    seen.add(nt.name)
    for n in list(nt.nodes):
        if n.bl_idname == "ShaderNodeGroup" and n.node_tree: _iris(n.node_tree, scale, centre, seen)
        if n.bl_idname == "ShaderNodeTexImage" and n.image and not n.inputs["Vector"].is_linked:
            nm = n.image.name.lower()
            if any(w in nm for w in ("normal", "_nor", "bump")): continue
            tc = nt.nodes.new("ShaderNodeTexCoord"); mp = nt.nodes.new("ShaderNodeMapping"); mp.vector_type = "POINT"
            s = 1.0 / scale; u, v = centre
            mp.inputs["Scale"].default_value = (s, s, 1); mp.inputs["Location"].default_value = (u - u * s, v - v * s, 0)
            nt.links.new(tc.outputs["UV"], mp.inputs["Vector"]); nt.links.new(mp.outputs["Vector"], n.inputs["Vector"])


def outline_material(rgb):
    name = "toon_outline_%02x%02x%02x" % tuple(int(c * 255) for c in rgb)
    m = bpy.data.materials.get(name)
    if m: return m
    m = bpy.data.materials.new(name); m.use_nodes = True; m.diffuse_color = (*_lin(rgb), 1)
    nt = m.node_tree; N, L = nt.nodes, nt.links; N.clear()
    out = N.new("ShaderNodeOutputMaterial")
    geo = N.new("ShaderNodeNewGeometry"); lp = N.new("ShaderNodeLightPath")
    inv = N.new("ShaderNodeMath"); inv.operation = "SUBTRACT"; inv.inputs[0].default_value = 1.0
    L.new(geo.outputs["Backfacing"], inv.inputs[1])   # flipped hull: its FAR side faces the camera = the visible rim
    mul = N.new("ShaderNodeMath"); mul.operation = "MULTIPLY"
    L.new(inv.outputs[0], mul.inputs[0]); L.new(lp.outputs["Is Camera Ray"], mul.inputs[1])
    tr = N.new("ShaderNodeBsdfTransparent"); em = N.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*_lin(rgb), 1); em.inputs["Strength"].default_value = 1.0
    mix = N.new("ShaderNodeMixShader")
    L.new(mul.outputs[0], mix.inputs[0]); L.new(tr.outputs[0], mix.inputs[1]); L.new(em.outputs[0], mix.inputs[2])
    L.new(mix.outputs[0], out.inputs["Surface"])
    try: m.blend_method = "HASHED"
    except Exception: pass
    return m


def add_outline(o, thickness, rgb):
    """inverted-hull outline (render only; viewport off so coverage / posed_coords never see the extra vertices)"""
    if o.modifiers.get(OUTLINE_MOD): return
    mat = outline_material(rgb)
    o.data.materials.append(mat)
    so = o.modifiers.new(OUTLINE_MOD, "SOLIDIFY")
    so.thickness = thickness; so.offset = 1.0; so.use_flip_normals = True; so.use_rim = False
    so.use_quality_normals = True; so.material_offset = len(o.data.materials) - 1
    so.show_viewport = False; so.show_render = True
    so.show_in_editmode = False


# ----------------------------------------------------------------------------------------------- public
def toonify(basemesh, rig, strength=1.0, style="infobells", skin_rgb=(0.86, 0.64, 0.48), kid=None, proportions=True,
            shading=True, outline=False):
    """Give an MPFB character the friendly cartoon look. Call AFTER mpfb_child.make_child and BEFORE lib_outfits.dress.
    strength scales the proportion changes (0 = none). kid=None decides from the height (< 1.5 m).
    Returns a dict with what was done (for logs)."""
    st = STYLES[style]; h = basemesh; info = {"style": style}
    pp = rig.data.pose_position; rig.data.pose_position = "REST"; bpy.context.view_layer.update()
    try:
        if proportions and strength > 0 and not h.get("toon_proportions"):
            if kid is None:
                z = [c.z for c in _rest_coords(h)]; kid = (max(z) - min(z)) * rig.matrix_world.to_scale().z < 1.5
            W = _Warp(h, rig, st, strength, kid); info.update(W.info)
            before = h.dimensions.z
            meshes = _char_meshes(h, rig)
            for o in meshes:
                try: W.apply_mesh(o)
                except Exception as ex: print("TOON warp fail", o.name, repr(ex)[:200])
            info["bones"] = W.apply_bones(rig)
            bpy.context.view_layer.update()
            info["warped"] = [o.name for o in meshes]; info["height_before"] = round(before, 3); info["height_after"] = round(h.dimensions.z, 3)
            h["toon_proportions"] = 1.0
            LO = sys.modules.get("lib_outfits")
            if LO is not None and hasattr(LO, "_BODIES"): LO._BODIES.pop(h.name, None)
        if shading:
            albedo = None
            for s in h.material_slots:
                if s.material and s.material.use_nodes and not s.material.name.startswith("toon_"):
                    albedo = albedo or _find_albedo(s.material.node_tree)
            sk = toon_skin_material("toon_skin_" + h.name, skin_rgb, st, albedo)
            for s in h.material_slots:
                if s.material and not s.material.name.startswith("toon_outline"): s.material = sk
            if not h.material_slots: h.data.materials.append(sk)
            info["albedo"] = albedo.name if albedo else None
            for o in _char_meshes(h, rig):
                k = _kind(o, h)
                mats = [s.material for s in o.material_slots if s.material and s.material.use_nodes]
                if k == "eyes":
                    for m in mats:
                        try: ctr = _pupil_uv(m.node_tree)
                        except Exception as ex: ctr = None; print("TOON pupil fail", repr(ex)[:150])
                        info.setdefault("pupil_uv", []).append(tuple(round(x, 3) for x in ctr) if ctr else None)
                        _iris(m.node_tree, st["iris"], ctr)
                        for b in _principleds(m.node_tree):
                            _set(b, "Roughness", 0.04); _set(b, ("Coat Weight",), 0.8); _set(b, ("Coat Roughness",), 0.03)
                            _set(b, ("Specular IOR Level", "Specular"), 0.6)
                elif k in ("brow", "lash"):
                    for m in mats:
                        _tint(m.node_tree, st["brow_rgb"], 1.0)
                        for b in _principleds(m.node_tree): _set(b, "Roughness", 0.8); _set(b, ("Specular IOR Level", "Specular"), 0.1)
                    if k == "brow" and o.data.vertices:
                        cx = sum(v.co.x for v in o.data.vertices) / len(o.data.vertices)
                        for side in (1, -1):
                            vs = [v for v in o.data.vertices if (v.co.x - cx) * side > 0]
                            if not vs: continue
                            c = sum((v.co for v in vs), Vector()) / len(vs)
                            # local axes of an MPFB proxy: x = left/right, y or z = up (MakeHuman meshes are Y-up before rotation)
                            up = 2 if o.dimensions.z >= o.dimensions.y else 1
                            for v in vs:
                                d = v.co - c; d.x *= st["brow_x"]; d[up] *= st["brow_z"]; v.co = c + d
                        o.data.update()
                elif k == "hair":
                    for m in mats:
                        _tint(m.node_tree, st["hair_rgb"], st["hair_fac"])
                        for b in _principleds(m.node_tree):
                            _set(b, "Roughness", 0.5); _set(b, ("Specular IOR Level", "Specular"), 0.35)
                            _set(b, ("Sheen Weight",), 0.0); _set(b, ("Coat Weight",), 0.0)
        if outline:
            add_outline(h, st["outline_body"], st["outline_rgb"])
        h["toon"] = style; h["toon_outline"] = bool(outline)
    finally:
        rig.data.pose_position = pp; bpy.context.view_layer.update()
    print("TOON", h.name, info)
    return info


def toonify_scene(style="infobells", outline=None, objects=None):
    """Flatten the cloth shading made by lib_outfits (and footwear) to match the toon skin and the lib_props palette:
    low sheen, prop-like roughness/specular, a touch of self-emission from the same colour (patterns and zari borders kept).
    outline=None: add the inverted-hull outline when any toonified character asked for it."""
    st = STYLES[style]
    objs = objects or [o for o in bpy.data.objects if o.type == "MESH" and (o.get("outfit_piece") or o.get("outfit_foot"))]
    if outline is None: outline = any(o.get("toon_outline") for o in bpy.data.objects)
    done = set()
    for o in objs:
        for s in o.material_slots:
            m = s.material
            if not m or not m.use_nodes or m.name in done or m.name.startswith("toon_outline"): continue
            done.add(m.name); nt = m.node_tree
            for b in _principleds(nt):
                metal = b.inputs["Metallic"]
                if metal.is_linked or metal.default_value > 0.3: continue      # zari / gold: keep the shine
                _set(b, ("Sheen Weight", "Sheen"), 0.08)
                _set(b, ("Specular IOR Level", "Specular"), 0.25)
                r = b.inputs["Roughness"]
                if not r.is_linked: r.default_value = max(0.55, min(0.75, r.default_value))
                _set(b, ("Coat Weight",), 0.0)
                e = _inp(b, ("Emission Color", "Emission"))
                if e is not None and not e.is_linked:
                    bc = b.inputs["Base Color"]
                    if bc.is_linked: nt.links.new(bc.links[0].from_socket, e)
                    else: e.default_value = bc.default_value
                    _set(b, "Emission Strength", st["emit"] * 0.8)
        if outline and o.data and len(o.data.vertices) > 8:
            add_outline(o, st["outline_cloth"], st["outline_rgb"])
    print("TOON scene materials", len(done), "outline", bool(outline))
    return len(done)
