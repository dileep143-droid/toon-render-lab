"""lib_camera.py - time-of-day lighting presets, practical lights (lantern, torch, diya rows, festival bulbs) and camera
rigs (shot framing, dolly push-in, orbit, follow, whip-pan, shaky cam, dream look, freeze-frame) for the village cartoon.
Blender 4.2 LTS + 5.x. No compositor (its API changed in 5.x): the dream vignette is a camera-parented plane.

    import lib_camera as CAM
    CAM.light_preset("golden")                    # morning / noon / golden / night / rainy / festival_night / dream
    cam = CAM.camera((0, -8, 2), target=(0, 0, 1))
    CAM.dolly_push(cam, 1, 72, amount=0.35)       # slow push-in
    CAM.follow(cam, rig.arm, 1, 200)              # keeps a character framed (smoothed)
"""
import bpy, math, random
from mathutils import Vector, Euler
import lib_fx as FX

R = math.radians

# preset: sky colour, sky strength, sun colour, sun energy, sun elevation, sun azimuth, exposure
PRESETS = {
    "morning":        dict(sky=(0.62, 0.78, 1.0), sky_k=0.8, sun=(1.0, 0.86, 0.68), sun_e=3.2, elev=18, az=-60, expo=0.0),
    "noon":           dict(sky=(0.55, 0.75, 1.0), sky_k=1.0, sun=(1.0, 0.97, 0.90), sun_e=5.0, elev=70, az=20, expo=-0.2),
    "golden":         dict(sky=(0.80, 0.78, 0.85), sky_k=0.55, sun=(1.0, 0.74, 0.48), sun_e=3.2, elev=14, az=110, expo=0.0),
    "dusk":           dict(sky=(0.55, 0.42, 0.62), sky_k=0.45, sun=(1.0, 0.45, 0.25), sun_e=1.6, elev=3, az=115, expo=0.2),
    "night":          dict(sky=(0.06, 0.09, 0.22), sky_k=0.35, sun=(0.55, 0.65, 1.0), sun_e=0.35, elev=40, az=-30, expo=0.6),
    "rainy":          dict(sky=(0.52, 0.56, 0.62), sky_k=0.9, sun=(0.80, 0.84, 0.90), sun_e=0.9, elev=50, az=0, expo=0.2),
    "festival_night": dict(sky=(0.08, 0.06, 0.20), sky_k=0.3, sun=(0.6, 0.6, 1.0), sun_e=0.25, elev=40, az=-30, expo=0.7),
    "dream":          dict(sky=(0.75, 0.55, 1.0), sky_k=1.1, sun=(1.0, 0.80, 1.0), sun_e=2.5, elev=45, az=30, expo=0.3),
    "summer_noon":    dict(sky=(0.85, 0.85, 0.80), sky_k=1.2, sun=(1.0, 0.95, 0.80), sun_e=6.0, elev=80, az=0, expo=-0.4),
    "winter":         dict(sky=(0.75, 0.80, 0.88), sky_k=0.9, sun=(0.95, 0.95, 1.0), sun_e=2.0, elev=25, az=-40, expo=0.0),
}


def _sun():
    o = bpy.data.objects.get("sun_light") or bpy.data.objects.get("sun")
    if o is None or o.type != "LIGHT":
        d = bpy.data.lights.new("sun", "SUN"); o = bpy.data.objects.new("sun_light", d); bpy.context.scene.collection.objects.link(o)
    o.data.type = "SUN"
    return o


def _world():
    sc = bpy.context.scene
    if sc.world is None:
        sc.world = bpy.data.worlds.new("sky")
    w = sc.world; w.use_nodes = True
    bg = w.node_tree.nodes.get("Background") or w.node_tree.nodes.new("ShaderNodeBackground")
    return w, bg


def light_preset(name="noon", frame=None, moon=None, lanterns=(), diyas=(), stars=False):
    """set sky + sun for a time of day. frame: keyframe it (so you can cross-fade presets over a shot).
    night extras: moon=(x,y,z) adds a glowing moon disc; lanterns / diyas = lists of world points for practicals;
    stars=True scatters emissive star dots on a far dome."""
    p = PRESETS[name]; sc = bpy.context.scene; w, bg = _world(); sun = _sun()
    bg.inputs[0].default_value = (*FX.lin(p["sky"]), 1); bg.inputs[1].default_value = p["sky_k"]
    sun.data.color = FX.lin(p["sun"]); sun.data.energy = p["sun_e"]
    try: sun.data.angle = R(4 if name not in ("rainy",) else 25)
    except Exception: pass
    sun.rotation_euler = Euler((R(90 - p["elev"]), 0, R(p["az"])))
    try: sc.view_settings.exposure = p["expo"]
    except Exception: pass
    if frame is not None:
        bg.inputs[0].keyframe_insert("default_value", frame=frame); bg.inputs[1].keyframe_insert("default_value", frame=frame)
        sun.data.keyframe_insert("energy", frame=frame); sun.data.keyframe_insert("color", frame=frame); sun.keyframe_insert("rotation_euler", frame=frame)
        try: sc.view_settings.keyframe_insert("exposure", frame=frame)
        except Exception: pass
    out = {"sun": sun}
    if moon is not None:
        m = FX.new_obj("moon", FX.mesh_sphere(1.0, 24, 12, "fx_unit_sphere"), FX.collection("CAM_sky"), moon, FX.fxmat("moon", (1.0, 0.97, 0.85), emit=6.0, fade=False))
        m.scale = (2.0, 0.2, 2.0); out["moon"] = m
    if stars:
        rnd = random.Random(7); col = FX.collection("CAM_sky"); mat = FX.fxmat("star_dot", (1, 1, 0.9), emit=8.0, fade=False)
        for i in range(120):
            a = rnd.uniform(-1.2, 1.2); e = rnd.uniform(0.15, 1.2); r = 80
            s = FX.new_obj(f"stardot_{i}", FX.mesh_ico(1.0, 1, "fx_unit_ico"), col, (r * math.sin(a) * math.cos(e), r * math.cos(a) * math.cos(e), r * math.sin(e)), mat)
            s.scale = (rnd.uniform(0.08, 0.2),) * 3
    out["lanterns"] = [lantern(q) for q in lanterns]
    out["diyas"] = [FX.flame(q, 1, sc.frame_end, size=1.0, seed=i, diya=True) for i, q in enumerate(diyas)]
    return out


def crossfade(name_a, name_b, f0, f1, **kw):
    """keyframed change of light from one preset to another (sunset in a single shot)"""
    light_preset(name_a, f0, **kw); light_preset(name_b, f1)


def lantern(loc, c=(1.0, 0.72, 0.35), energy=25.0, flicker=True, seed=0, body=True):
    """hurricane lantern: warm point light (+ simple lantern body) with a gentle seeded flicker"""
    col = FX.collection("CAM_practicals"); out = {}
    if body:
        g = FX.new_obj(f"lantern_glass_{seed}", FX.mesh_cyl(0.06, 0.14, 16, name="fx_lantern_glass"), col, Vector(loc), FX.fxmat("lantern_glass", c, emit=4.0, fade=False))
        FX.new_obj(f"lantern_top_{seed}", FX.mesh_cyl(0.07, 0.04, 16, r2=0.02, name="fx_lantern_top"), col, (0, 0, 0.09), FX.fxmat("lantern_metal", (0.25, 0.25, 0.28), fade=False), g)
        FX.new_obj(f"lantern_base_{seed}", FX.mesh_cyl(0.075, 0.04, 16, name="fx_lantern_base"), col, (0, 0, -0.09), FX.fxmat("lantern_metal", (0.25, 0.25, 0.28), fade=False), g)
        out["body"] = g
    ld = bpy.data.lights.new(f"lantern_light_{seed}", "POINT"); ld.color = FX.lin(c); ld.energy = energy; ld.shadow_soft_size = 0.05
    lo = FX.new_obj(f"lantern_light_{seed}", ld, col, Vector(loc)); out["light"] = lo
    if flicker:
        rnd = random.Random(seed)
        for f in range(bpy.context.scene.frame_start, bpy.context.scene.frame_end + 1, 3):
            ld.energy = energy * rnd.uniform(0.85, 1.1); ld.keyframe_insert("energy", frame=f)
    return out


def torch(holder, energy=60.0, angle=30, c=(1.0, 0.95, 0.8), offset=(0, -0.05, 0)):
    """hand torch: a spot light cone attached to a hand follower / object, pointing along the holder's -Y (forward).
    Gives the long torch shadow in night scenes."""
    ld = bpy.data.lights.new("torch", "SPOT"); ld.energy = energy; ld.spot_size = R(angle); ld.spot_blend = 0.35; ld.color = FX.lin(c)
    ld.shadow_soft_size = 0.02
    lo = FX.new_obj("torch_light", ld, FX.collection("CAM_practicals"), offset, parent=holder)
    lo.rotation_euler = (R(-90), 0, 0)                                  # spot shines along -Z -> point it along -Y
    return lo


def phone_glow(face_anchor, energy=4.0):
    """blue phone-screen glow lighting a face from below"""
    ld = bpy.data.lights.new("phone_glow", "AREA"); ld.energy = energy; ld.color = (0.55, 0.75, 1.0); ld.size = 0.08
    lo = FX.new_obj("phone_glow", ld, FX.collection("CAM_practicals"), (0, -0.25, -0.2), parent=face_anchor)
    lo.rotation_euler = (R(-120), 0, 0)
    return lo


def power_cut(frame, lights=None, sky_to=0.05):
    """everything goes dark at `frame` (keys light energies + sky strength to ~0)"""
    w, bg = _world()
    bg.inputs[1].keyframe_insert("default_value", frame=frame - 1); s = bg.inputs[1].default_value
    bg.inputs[1].default_value = sky_to; bg.inputs[1].keyframe_insert("default_value", frame=frame); bg.inputs[1].default_value = s
    for o in (lights or [o for o in bpy.data.objects if o.type == "LIGHT"]):
        e = o.data.energy; o.data.keyframe_insert("energy", frame=frame - 1); o.data.energy = 0.0; o.data.keyframe_insert("energy", frame=frame); o.data.energy = e


def festival_bulbs(points, colors=("yellow", "red", "green", "blue", "saffron"), chase=True, every=0.25):
    """string of coloured bulbs (mela / festival night) along a list of points; chase=True blinks them in sequence"""
    vs, L = FX.polyline(points); n = max(2, int(L[-1] / every)); out = []
    col = FX.collection("CAM_bulbs")
    for i in range(n):
        p, _ = FX.along(vs, L, L[-1] * i / (n - 1)); c = colors[i % len(colors)]
        b = FX.new_obj(f"bulb_{i}", FX.mesh_sphere(1.0, 10, 6, "fx_unit_sphere_lo"), col, p, FX.fxmat("bulb_" + c, c, emit=6.0, fade=False)); b.scale = (0.03,) * 3
        if chase:
            for f in range(bpy.context.scene.frame_start + i % 3 * 6, bpy.context.scene.frame_end, 18):
                FX.key(b, "scale", f, (0.03,) * 3); FX.key(b, "scale", f + 6, (0.018,) * 3)
        out.append(b)
    cu = bpy.data.curves.new("bulb_wire", "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = 0.004
    sp = cu.splines.new("POLY"); sp.points.add(len(vs) - 1)
    for i, v in enumerate(vs): sp.points[i].co = (*v, 1)
    FX.new_obj("bulb_wire", cu, col, (0, 0, 0), FX.fxmat("wire", (0.1, 0.1, 0.1), fade=False))
    return out


# ---------------------------------------------------------------------------------------------------------------------
# cameras
# ---------------------------------------------------------------------------------------------------------------------
def look_at(cam, target, frame=None):
    t = FX.target_point(target) if hasattr(target, "matrix_world") else Vector(target)
    cam.rotation_euler = (t - cam.location).to_track_quat("-Z", "Y").to_euler()
    if frame is not None: cam.keyframe_insert("rotation_euler", frame=frame)


def camera(loc, target=(0, 0, 1), lens=35, name="cam", make_active=True):
    cam = bpy.data.objects.new(name, bpy.data.cameras.new(name)); bpy.context.scene.collection.objects.link(cam)
    cam.location = loc; cam.data.lens = lens; look_at(cam, target)
    try: cam.data.clip_end = 500
    except Exception: pass
    if make_active: bpy.context.scene.camera = cam
    return cam


SHOTS = {  # kind: (distance in subject-heights, height factor, lens)
    "wide": (9.0, 0.9, 24), "full": (3.2, 0.55, 35), "medium": (1.8, 0.75, 45), "closeup": (0.9, 0.88, 60), "insert": (0.45, 0.5, 70),
    "low": (2.4, 0.15, 30), "high": (2.6, 2.2, 30), "overhead": (0.01, 4.0, 28),
}


def shot(target, kind="medium", height=1.1, side=0.0, cam=None, frame=None, aim_z=None):
    """frame a subject (object or point): wide / full / medium / closeup / insert / low (hero angle) / high / overhead.
    side = degrees around the subject (0 = from the front, the -Y side)."""
    p = FX.target_point(target) if hasattr(target, "matrix_world") else Vector(target)
    d, hk, lens = SHOTS[kind]
    a = R(side - 90)
    loc = p + Vector((math.cos(a) * d * height, math.sin(a) * d * height, hk * height))
    cam = cam or camera(loc, lens=lens)
    cam.location = loc; cam.data.lens = lens
    aim = p + Vector((0, 0, (aim_z if aim_z is not None else {"closeup": 0.88, "insert": 0.3, "low": 0.7, "overhead": 0.0}.get(kind, 0.55)) * height))
    look_at(cam, aim)
    if frame is not None:
        cam.keyframe_insert("location", frame=frame); cam.keyframe_insert("rotation_euler", frame=frame); cam.data.keyframe_insert("lens", frame=frame)
    return cam


def dolly_push(cam, f0, f1, amount=0.3, target=None):
    """move the camera `amount` (fraction of its distance to target) toward the target, eased"""
    t = FX.target_point(target) if target is not None and hasattr(target, "matrix_world") else (Vector(target) if target is not None else None)
    if t is None:
        t = cam.location + cam.matrix_world.to_3x3() @ Vector((0, 0, -5))
    p0 = cam.location.copy(); p1 = p0.lerp(t, amount)
    FX.key(cam, "location", f0, tuple(p0)); FX.key(cam, "location", f1, tuple(p1))
    return cam


def orbit(cam, target, f0, f1, degrees=90, radius=None, height=None):
    """circle the camera around a target (keys every 2 frames, always looking at it)"""
    t = FX.target_point(target) if hasattr(target, "matrix_world") else Vector(target)
    v = cam.location - t; r = radius or Vector((v.x, v.y)).length; h = height if height is not None else v.z
    a0 = math.atan2(v.y, v.x)
    for f in range(f0, f1 + 1, 2):
        a = a0 + R(degrees) * (f - f0) / max(1, f1 - f0)
        cam.location = t + Vector((r * math.cos(a), r * math.sin(a), h)); cam.keyframe_insert("location", frame=f)
        look_at(cam, t, f)
    return cam


def follow(cam, obj, f0, f1, offset=None, smooth=0.15, aim_z=0.6, step=2):
    """keep a moving character framed: camera keeps its current offset from obj, lagging smoothly (no constraint;
    keyed so it renders the same everywhere)"""
    sc = bpy.context.scene; fnow = sc.frame_current
    sc.frame_set(f0); bpy.context.view_layer.update()
    p0 = obj.matrix_world.translation.copy(); off = Vector(offset) if offset is not None else cam.location - p0
    cur = p0 + off; aim = p0.copy()
    for f in range(f0, f1 + 1, step):
        sc.frame_set(f); bpy.context.view_layer.update(); p = obj.matrix_world.translation.copy()
        cur = cur.lerp(p + off, min(1.0, smooth * step * 2)); aim = aim.lerp(p, min(1.0, smooth * step * 3))
        cam.location = cur; cam.keyframe_insert("location", frame=f)
        look_at(cam, aim + Vector((0, 0, aim_z)), f)
    sc.frame_set(fnow)
    return cam


def whip_pan(cam, frame, degrees=70, dur=6, blur=True):
    """fast whip-pan (transition): yaw swings by `degrees` over dur frames with motion blur on"""
    r0 = cam.rotation_euler.copy()
    cam.keyframe_insert("rotation_euler", frame=frame)
    cam.rotation_euler = (r0.x, r0.y, r0.z + R(degrees)); cam.keyframe_insert("rotation_euler", frame=frame + dur)
    if blur:
        sc = bpy.context.scene
        try: sc.render.use_motion_blur = True; sc.render.motion_blur_shutter = 1.0
        except Exception: pass
    return cam


def shaky_cam(cam, f0, f1, amp=0.015, rot_amp=0.6, seed=5):
    """handheld feel (low, continuous) - FX.camera_shake without decay, slower"""
    return FX.camera_shake(cam, f0, f1, amp=amp, rot_amp=rot_amp, freq=4, seed=seed, decay=False)


def dream_look(cam=None, f0=None, f1=None, tint=(0.75, 0.5, 1.0), vignette=0.65, soft=True, wobble=True):
    """dream / imagination look: purple-tinted soft vignette (camera-parented plane, no compositor), shallow depth of
    field and a gentle wobble. f0/f1 = only during those frames (fades in/out)."""
    cam = cam or bpy.context.scene.camera
    import bmesh
    bm = bmesh.new(); bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1.0)
    me = bpy.data.meshes.new("vignette"); bm.to_mesh(me); bm.free()
    m = bpy.data.materials.new("dream_vignette"); m.use_nodes = True; nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial"); em = nt.nodes.new("ShaderNodeEmission"); em.inputs[0].default_value = (*FX.lin(tint), 1)
    tr = nt.nodes.new("ShaderNodeBsdfTransparent"); mix = nt.nodes.new("ShaderNodeMixShader")
    tc = nt.nodes.new("ShaderNodeTexCoord"); gr = nt.nodes.new("ShaderNodeTexGradient"); gr.gradient_type = "SPHERICAL"
    mp = nt.nodes.new("ShaderNodeMapping"); mp.inputs["Scale"].default_value = (1.1, 1.8, 1)
    rmp = nt.nodes.new("ShaderNodeMapRange"); rmp.inputs[1].default_value = 0.0; rmp.inputs[2].default_value = 0.55
    inv = nt.nodes.new("ShaderNodeMath"); inv.operation = "SUBTRACT"; inv.inputs[0].default_value = 1.0
    k = nt.nodes.new("ShaderNodeMath"); k.operation = "MULTIPLY"; k.inputs[1].default_value = vignette
    nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
    sub = nt.nodes.new("ShaderNodeVectorMath"); sub.operation = "SUBTRACT"; sub.inputs[1].default_value = (0.5, 0.5, 0)
    nt.links.new(tc.outputs["Generated"], sub.inputs[0]); nt.links.new(sub.outputs[0], mp.inputs["Vector"]); nt.links.new(mp.outputs[0], gr.inputs[0])
    nt.links.new(gr.outputs["Fac"], rmp.inputs[0]); nt.links.new(rmp.outputs[0], inv.inputs[1]); nt.links.new(inv.outputs[0], k.inputs[0])
    nt.links.new(k.outputs[0], mix.inputs[0]); nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(em.outputs[0], mix.inputs[2]); nt.links.new(mix.outputs[0], out.inputs[0])
    for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
        try: setattr(m, attr, val)
        except Exception: pass
    me.materials.append(m)
    d = 0.2; w = d * 36 / cam.data.lens
    v = bpy.data.objects.new("dream_vignette", me); FX.collection("CAM_fx").objects.link(v); v.parent = cam; v.location = (0, 0, -d); v.scale = (w * 0.6, w * 0.6 * 0.5625 * 1.2, 1)
    try: v.visible_shadow = False
    except Exception: pass
    if f0 is not None:
        FX.life(v, f0, f1)
        k.inputs[1].default_value = 0.0; k.inputs[1].keyframe_insert("default_value", frame=f0)
        k.inputs[1].default_value = vignette; k.inputs[1].keyframe_insert("default_value", frame=f0 + 8)
        if f1:
            k.inputs[1].keyframe_insert("default_value", frame=f1 - 8); k.inputs[1].default_value = 0.0; k.inputs[1].keyframe_insert("default_value", frame=f1)
    if soft:
        cam.data.dof.use_dof = True; cam.data.dof.aperture_fstop = 1.2
    if wobble and f0 is not None:
        r0 = cam.rotation_euler.copy()
        for f in range(f0, (f1 or f0 + 48), 6):
            cam.rotation_euler = (r0.x, r0.y + R(1.5) * math.sin(f * 0.4), r0.z); cam.keyframe_insert("rotation_euler", frame=f)
    return v


def slow_motion(f0, f1, factor=0.5):
    """slow-motion section via the scene time-remap is global; instead return a render plan that repeats frames
    (use with FX.render_plan). For real slow-mo, key the action at half speed."""
    plan = []
    for f in range(f0, f1 + 1):
        for _ in range(int(round(1 / factor))): plan.append((f, 1.0))
    return plan


def freeze_frame(start, end, at, hold=24, zoom=1.15):
    """end-of-episode freeze on the laugh (with a little zoom): render plan for FX.render_plan()"""
    return FX.freeze_plan(start, end, {at: hold}, {at: zoom})


__all__ = [n for n in dir() if not n.startswith("_")]
