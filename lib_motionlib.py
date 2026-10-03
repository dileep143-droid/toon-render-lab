"""lib_motionlib - the Sonpur ready-made motion library (CMU, 100STYLE, Quaternius UAL, Bandai, LAFAN1, ZeroEGGS, Motorica,
InterAct) retargeted onto MPFB "default" rigs (any body: toddler, child, adult, elder).

    import lib_motionlib as ML
    info = ML.load_motion("walk", rig, start=1)                    # tag query or exact catalogue name
    info = ML.load_motion("cmu_016_15", rig, start=40, in_place=True, loop=3)
    info = ML.load_motion("old walk", rig, final=True)             # final render: prefers commercial_ok motions
    ML.find("sit ground", final=True)                              # -> catalogue rows, best first

HOW IT WORKS (numpy only, no Blender needed for the heavy part)
 1. a source take (BVH, or a glTF action sampled in Blender) -> world joint positions + joint rotations, resampled to 30 fps;
 2. it is turned into a RIG-INDEPENDENT "motion description" (md): for 18 body segments a (direction, reference) vector pair per
    frame in a canonical frame (Z up, character faces -Y at frame 0, starts at the origin) + hip-centre path in leg lengths +
    foot contacts. Torso frames come from joint positions; limb twist comes from the knee/elbow hinge (calibrated per take),
    the palm from finger joints - so odd rest poses (Bandai's all-along-X, Geno's arms-up) do not matter;
 3. load_motion() solves that description for THE rig it is given (its own bone lengths and rest pose), grounds it (no feet
    through the floor), pins planted feet with a 2-bone IK (no sliding) and writes one Blender action.
Data lives in private Kaggle datasets (mani7673/sonpur-motion-packs = commercial-OK, mani7673/sonpur-motion-nc = NON-COMMERCIAL);
each has motion_catalogue.json + md/<pack>/<name>.npz. Set SONPUR_MOTION_DIR (os.pathsep-separated) or mount them on Kaggle."""
import os, re, json, math, glob, io, zipfile
import numpy as np

FPS = 30
SEGS = ["hips", "chest", "neck", "head",
        "clav_L", "arm_L", "forearm_L", "hand_L", "thigh_L", "shin_L", "foot_L",
        "clav_R", "arm_R", "forearm_R", "hand_R", "thigh_R", "shin_R", "foot_R"]
SI = {s: i for i, s in enumerate(SEGS)}
# how the 'ref' vector of each segment behaves under a left/right mirror: -1 = axial (hinge / 'left' axis), +1 = polar
_REF_PARITY = {"hips": -1, "chest": -1, "neck": -1, "head": -1, "clav": 1, "arm": -1, "forearm": -1, "hand": -1, "thigh": -1, "shin": -1, "foot": -1}
DOWN, UP, FWD, BACK, LEFT = (np.array(v, float) for v in ((0, 0, -1), (0, 0, 1), (0, -1, 0), (0, 1, 0), (1, 0, 0)))

# ---------------------------------------------------------------------------------------------------------------------
# small vector / rotation helpers (all vectorised over leading axes)
# ---------------------------------------------------------------------------------------------------------------------
def _n(v, eps=1e-9):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), eps)

def _rot_axes(axis, ang):
    c, s = np.cos(ang), np.sin(ang); o, z = np.ones_like(ang), np.zeros_like(ang)
    if axis == "X": m = [[o, z, z], [z, c, -s], [z, s, c]]
    elif axis == "Y": m = [[c, z, s], [z, o, z], [-s, z, c]]
    else: m = [[c, -s, z], [s, c, z], [z, z, o]]
    return np.moveaxis(np.array(m), (0, 1), (-2, -1))

def frame(d, r):
    """columns [d, r_perp, d x r_perp]"""
    d = _n(d); r = r - np.sum(r * d, -1, keepdims=True) * d; r = _n(r)
    return np.stack([d, r, np.cross(d, r)], -1)

def avg_rot(Ms):
    Ms = Ms[np.isfinite(Ms).all(axis=(-2, -1))]
    if len(Ms) == 0: return np.eye(3)
    U, S, Vt = np.linalg.svd(np.sum(Ms, 0)); D = np.eye(3); D[2, 2] = np.sign(np.linalg.det(U @ Vt))
    return U @ D @ Vt

def m2q(M):
    """(...,3,3) -> (...,4) w,x,y,z"""
    M = np.asarray(M, float); sh = M.shape[:-2]; m = M.reshape(-1, 3, 3)
    m00, m01, m02, m10, m11, m12, m20, m21, m22 = (m[:, i, j] for i in range(3) for j in range(3))
    t = m00 + m11 + m22
    c = np.argmax(np.stack([t, m00, m11, m22], -1), -1)
    s0 = np.sqrt(np.maximum(t + 1, 1e-12)) * 2; s1 = np.sqrt(np.maximum(1 + m00 - m11 - m22, 1e-12)) * 2
    s2 = np.sqrt(np.maximum(1 + m11 - m00 - m22, 1e-12)) * 2; s3 = np.sqrt(np.maximum(1 + m22 - m00 - m11, 1e-12)) * 2
    q0 = np.stack([0.25 * s0, (m21 - m12) / s0, (m02 - m20) / s0, (m10 - m01) / s0], -1)
    q1 = np.stack([(m21 - m12) / s1, 0.25 * s1, (m01 + m10) / s1, (m02 + m20) / s1], -1)
    q2 = np.stack([(m02 - m20) / s2, (m01 + m10) / s2, 0.25 * s2, (m12 + m21) / s2], -1)
    q3 = np.stack([(m10 - m01) / s3, (m02 + m20) / s3, (m12 + m21) / s3, 0.25 * s3], -1)
    q = np.choose(c[:, None], [q0, q1, q2, q3])
    return _n(q).reshape(*sh, 4)

def q2m(q):
    q = _n(np.asarray(q, float)); w, x, y, z = np.moveaxis(q, -1, 0)
    m = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
         [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
         [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    return np.moveaxis(np.array(m), (0, 1), (-2, -1))

def slerp_m(A, B, t):
    """rotation matrices (F,3,3) -> slerp(A, B, t)"""
    qa, qb = m2q(A), m2q(B)
    d = np.sum(qa * qb, -1); qb = np.where(d[:, None] < 0, -qb, qb); d = np.abs(d)
    th = np.arccos(np.clip(d, -1, 1)); s = np.sin(th)
    wa = np.where(s > 1e-6, np.sin((1 - t) * th) / np.maximum(s, 1e-9), 1 - t); wb = np.where(s > 1e-6, np.sin(t * th) / np.maximum(s, 1e-9), t)
    return q2m(wa[:, None] * qa + wb[:, None] * qb)

def rot_between(a, b):
    """minimal rotation matrices taking unit vectors a -> b (F,3)"""
    a, b = _n(a), _n(b); v = np.cross(a, b); c = np.sum(a * b, -1); s = np.linalg.norm(v, axis=-1)
    k = _n(np.where(s[:, None] > 1e-8, v, np.cross(a, np.where(np.abs(a[:, :1]) < 0.9, LEFT, BACK))))
    ang = np.arctan2(s, c); K = np.zeros(a.shape[:-1] + (3, 3))
    K[..., 0, 1], K[..., 0, 2], K[..., 1, 0], K[..., 1, 2], K[..., 2, 0], K[..., 2, 1] = -k[..., 2], k[..., 1], k[..., 2], -k[..., 0], -k[..., 1], k[..., 0]
    return np.eye(3) + np.sin(ang)[:, None, None] * K + (1 - np.cos(ang))[:, None, None] * (K @ K)

def _ffill(v, ok):
    """forward/back fill rows of v where ok is False"""
    v = v.copy(); idx = np.where(ok, np.arange(len(ok)), 0); np.maximum.accumulate(idx, out=idx)
    if ok.any():
        first = np.argmax(ok); idx[:first] = first
    return v[idx]

# ---------------------------------------------------------------------------------------------------------------------
# 1. SOURCES -> joint positions + rotations
# ---------------------------------------------------------------------------------------------------------------------
def parse_bvh(text, fps=FPS, skip_first=False, t0=None, t1=None):
    """-> dict(names, parents, P (F,J,3), B (F,J,3,3) world rotations (identity at rest), rest (J,3), fps, up='Y', src_fps, src_frames)
    End Sites become joints named '<parent>__end'. Resampled to `fps` (nearest frame). t0/t1 in seconds cut a window."""
    names, parents, offs, chans = [], [], [], []
    stack = []; pos = 0; lines = text.split("\n")
    i = 0
    while i < len(lines):
        s = lines[i].strip(); i += 1
        if not s: continue
        tok = s.split()
        if tok[0] in ("ROOT", "JOINT"):
            names.append(tok[1]); parents.append(stack[-1] if stack else -1); offs.append((0, 0, 0)); chans.append([]); cur = len(names) - 1; pending = cur
        elif tok[0] == "End":
            names.append(names[stack[-1]] + "__end"); parents.append(stack[-1]); offs.append((0, 0, 0)); chans.append([]); pending = len(names) - 1
        elif tok[0] == "{": stack.append(pending)
        elif tok[0] == "}": stack.pop()
        elif tok[0] == "OFFSET": offs[pending] = tuple(float(x) for x in tok[1:4])
        elif tok[0] == "CHANNELS": chans[pending] = tok[2:]
        elif tok[0] == "MOTION": break
    nf = int(lines[i].split()[-1]); ft = float(lines[i + 1].split()[-1]); i += 2
    ncol = sum(len(c) for c in chans)
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        data = np.fromstring(" ".join(lines[i:]), dtype=np.float64, sep=" ")
    nf = min(nf, len(data) // ncol); data = data[: nf * ncol].reshape(nf, ncol)
    src_fps = 1.0 / ft if ft > 0 else 30.0
    first = 1 if (skip_first and nf > 2) else 0
    dur = (nf - first) / src_fps
    a = max(0.0, t0 or 0.0); b = min(dur, t1 if t1 else dur)
    tt = np.arange(a, b, 1.0 / fps)
    idx = np.clip(np.round(tt * src_fps).astype(int) + first, 0, nf - 1)
    data = data[idx].astype(np.float64); F = len(idx); J = len(names)
    good = np.isfinite(data).all(1) & (np.abs(data).max(1) < 1e6)
    if not good.all():
        if not good.any(): raise ValueError("no finite frames")
        data = _ffill(data, good)
    P = np.zeros((F, J, 3)); B = np.zeros((F, J, 3, 3)); rest = np.zeros((J, 3))
    col = 0
    for j in range(J):
        p = parents[j]; off = np.array(offs[j]); L = np.broadcast_to(np.eye(3), (F, 3, 3)).copy(); t = np.broadcast_to(off, (F, 3)).copy()
        pc = {}
        for c in chans[j]:
            pc[c] = data[:, col]; col += 1
        if all(k in pc for k in ("Xposition", "Yposition", "Zposition")):
            t = np.stack([pc["Xposition"], pc["Yposition"], pc["Zposition"]], -1)
        for c in chans[j]:
            if c.endswith("rotation"):
                L = L @ _rot_axes(c[0].upper(), np.radians(pc[c]))
        rest[j] = (rest[p] if p >= 0 else 0) + off
        if p < 0: B[:, j] = L; P[:, j] = t
        else: B[:, j] = B[:, p] @ L; P[:, j] = P[:, p] + np.einsum("fij,fj->fi", B[:, p], t)
    return dict(names=names, parents=parents, P=P, B=B, rest=rest, fps=fps, up="Y", src_fps=src_fps, src_frames=nf - first)

# ---------------------------------------------------------------------------------------------------------------------
# 2. skeleton roles (name based, works for CMU/cgspeed, Geno, Bandai, Holden/100STYLE-original, UE/Quaternius, Mixamo, MPFB)
# ---------------------------------------------------------------------------------------------------------------------
def _side(n):
    lo = n.lower()
    if "left" in lo: return "L"
    if "right" in lo: return "R"
    if re.search(r"(^|[_.\-\s:])l($|[_.\-\s])", lo) or re.match(r"^L[A-Z]", n) or re.search(r"[a-z0-9]_?L$", n) and not n.endswith("ALL"): return "L"
    if re.search(r"(^|[_.\-\s:])r($|[_.\-\s])", lo) or re.match(r"^R[A-Z]", n) or re.search(r"[a-z0-9]_?R$", n): return "R"
    return None

def _core(n):
    c = n.split(":")[-1]
    c = re.sub(r"^(DEF|ORG|MCH|mixamorig)[-_]", "", c, flags=re.I)
    c = re.sub(r"(?i)left|right", "", c)
    c = re.sub(r"^[LR](?=[A-Z])", "", c)
    c = re.sub(r"([_.\-])[lLrR]$", "", c); c = re.sub(r"(?<=[a-z0-9])[LR]$", "", c)
    c = re.sub(r"^([_.\-])[lLrR]([_.\-])", "", c)
    return c.lower().strip("_.-")

_ROLE_PATS = [  # role, pattern on the core name (full match), sided?
    ("hips", r"hips?|pelvis|root_?hips?", False), ("head", r"head", False), ("head_end", r"head_?(end|top)|head__end", False),
    ("upleg", r"up_?leg|upper_?leg|thigh", True), ("knee", r"leg|lower_?leg|calf|shin|knee", True),
    ("ankle", r"foot|ankle", True), ("toe", r"toes?(_?base)?|ball|toe_?0?1", True),
    ("collar", r"collar|clavicle", True), ("shoulder", r"shoulder", True), ("uparm", r"arm|upper_?arm|up_?arm", True),
    ("forearm", r"fore_?arm|lower_?arm|elbow", True), ("wrist", r"hand|wrist", True),
    ("index1", r"(hand_?|f_)?index[._]?0?1|finger_?2-?1|index_?finger_?1", True), ("middle1", r"(hand_?|f_)?middle[._]?0?1|finger_?3-?1", True),
    ("pinky1", r"(hand_?|f_)?(pinky|little)[._]?0?1|finger_?5-?1", True), ("thumb1", r"(hand_?|f_)?thumb[._]?0?1|thumb|finger_?1-?1", True),
    ("hipjoint_holden", r"hip", True), ("knee_h", r"knee", True),
]

def skeleton_roles(names, parents):
    """-> {role: joint index}; sided roles get '_L'/'_R'"""
    out = {}
    cores = [_core(n) for n in names]; sides = [_side(n) for n in names]
    def find(pat, side, sided):
        for j, c in enumerate(cores):
            if names[j].endswith("__end"): continue
            if (sides[j] == side) if sided else (sides[j] is None):
                if re.fullmatch(pat, c): return j
        return None
    for role, pat, sided in _ROLE_PATS:
        for s in (("L", "R") if sided else (None,)):
            k = role + ("_" + s if s else "")
            if k not in out:
                j = find(pat, s, sided)
                if j is not None: out[k] = j
    for s in ("L", "R"):
        if f"upleg_{s}" not in out and f"hipjoint_holden_{s}" in out: out[f"upleg_{s}"] = out[f"hipjoint_holden_{s}"]
        if f"collar_{s}" in out and f"shoulder_{s}" in out and f"uparm_{s}" not in out: out[f"uparm_{s}"] = out[f"shoulder_{s}"]
        if f"collar_{s}" in out: out[f"clav_{s}"] = out[f"collar_{s}"]
        elif f"shoulder_{s}" in out and f"uparm_{s}" in out: out[f"clav_{s}"] = out[f"shoulder_{s}"]
        elif f"shoulder_{s}" in out: out[f"uparm_{s}"] = out[f"shoulder_{s}"]
        for k in ("collar", "shoulder", "hipjoint_holden", "knee_h"): out.pop(f"{k}_{s}", None)
        # the knee must be a descendant of the upper leg; CMU 'LeftLeg' vs Holden 'LeftKnee'
        if f"knee_{s}" not in out and f"upleg_{s}" in out:
            ch = [j for j, p in enumerate(parents) if p == out[f"upleg_{s}"] and not names[j].endswith("__end")]
            if ch: out[f"knee_{s}"] = ch[0]
    if "hips" not in out:
        out["hips"] = next((j for j, p in enumerate(parents) if p < 0), 0)
    # chest = lowest common ancestor of the two upper arms (or clavicles)
    def chain(j):
        c = []
        while j >= 0: c.append(j); j = parents[j]
        return c
    a, b = out.get("clav_L", out.get("uparm_L")), out.get("clav_R", out.get("uparm_R"))
    if a is not None and b is not None:
        ca, cb = chain(a), set(chain(b))
        out["chest"] = next(j for j in ca[1:] if j in cb)
    if "head" in out and "chest" in out:          # neck = the head's parent (CMU Neck1, Geno Neck1, Bandai Neck, UE neck_01)
        j = parents[out["head"]]
        if j != out["chest"] and j >= 0: out["neck"] = j
    # hand end / toe end from end sites when there is no finger / toe joint
    for s in ("L", "R"):
        w = out.get(f"wrist_{s}")
        if w is not None:
            ends = [j for j, p in enumerate(parents) if p == w and names[j].endswith("__end")]
            if ends: out[f"hand_end_{s}"] = ends[0]
        t = out.get(f"toe_{s}", out.get(f"ankle_{s}"))
        if t is not None:
            ends = [j for j, p in enumerate(parents) if p == t and names[j].endswith("__end")]
            if ends: out[f"toe_end_{s}"] = ends[0]
    if "head_end" not in out and "head" in out:
        ends = [j for j, p in enumerate(parents) if p == out["head"]]
        if ends: out["head_end"] = ends[0]
    return out

# ---------------------------------------------------------------------------------------------------------------------
# 3. source -> rig-independent motion description (md)
# ---------------------------------------------------------------------------------------------------------------------
def describe(src, roles=None, meta=None, skip_tpose=False):
    """src: dict from parse_bvh (or the Blender sampler). Returns md dict (D (F,18,2,3), root (F,3), contact (F,2), meta)."""
    names, P, B = src["names"], src["P"].copy(), src["B"].copy(); F = len(P)
    R = roles or skeleton_roles(names, src["parents"])
    need = ["hips", "upleg_L", "upleg_R", "knee_L", "knee_R", "ankle_L", "ankle_R", "uparm_L", "uparm_R", "forearm_L", "forearm_R", "wrist_L", "wrist_R", "head", "chest"]
    miss = [k for k in need if k not in R]
    if miss: raise ValueError(f"skeleton roles missing {miss}; names: {names[:60]}")
    if src.get("up", "Y") == "Y":
        C = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], float)
        P = P @ C.T; B = C @ B @ C.T
    J = lambda k: P[:, R[k]]
    if skip_tpose and F > 6:      # cgspeed CMU files start with 1-3 added T-pose frames: drop them
        zl = np.abs(_n(J("forearm_L") - J("uparm_L"))[:, 2]); zr = np.abs(_n(J("forearm_R") - J("uparm_R"))[:, 2])
        k = 0
        while k < 3 and any(z[k] < 0.4 and z[k + 3] > 0.7 for z in (zl, zr)): k += 1
        if k:
            P, B = P[k:], B[k:]; F = len(P)
    # yaw: character's left (+X) and start at the origin
    hipmid = 0.5 * (J("upleg_L") + J("upleg_R"))
    l0 = np.median((J("upleg_L") - J("upleg_R"))[: max(1, min(F, 10))], 0); l0[2] = 0
    yaw = -math.atan2(l0[1], l0[0]); Rz = _rot_axes("Z", np.array(yaw))
    o = hipmid[0].copy(); o[2] = 0
    P = (P - o) @ Rz.T; B = Rz @ B
    hipmid = 0.5 * (J("upleg_L") + J("upleg_R"))
    Ls = float(np.median(np.linalg.norm(J("knee_L") - J("upleg_L"), axis=-1) + np.linalg.norm(J("ankle_L") - J("knee_L"), axis=-1)))
    toe = {s: J(f"toe_{s}") if f"toe_{s}" in R else J(f"ankle_{s}") for s in "LR"}
    lowest = np.minimum(np.minimum(toe["L"][:, 2], toe["R"][:, 2]), np.minimum(J("ankle_L")[:, 2], J("ankle_R")[:, 2]))
    floor = float(np.percentile(lowest, 2))
    D = np.full((F, len(SEGS), 2, 3), np.nan)
    Bj = lambda k: B[:, R[k]]
    def cal(Bk, target):              # constant joint-local vector so that Bk @ v ~ target (averaged)
        v = _n(np.einsum("fji,fj->fi", Bk, target)); m = np.isfinite(v).all(-1)
        return _n(np.sum(v[m], 0)) if m.any() else np.array([1.0, 0, 0])
    # --- torso frames: O = B @ K, K calibrated from positions
    upv = J("head") - J("chest")
    shl = J("uparm_L") - J("uparm_R")
    if "clav_L" in R and "clav_R" in R and np.median(np.linalg.norm(J("clav_L") - J("clav_R"), axis=-1)) > 0.1 * float(
            np.median(np.linalg.norm(J("knee_L") - J("upleg_L"), axis=-1))):
        shl = J("clav_L") - J("clav_R")           # clavicle roots are rigid with the chest joint (when they are apart)
    O_est_ch = frame(upv, shl)             # columns: up, left, back(=up x left)... (we store dir=up, ref=left)
    K_ch = avg_rot(np.einsum("fji,fjk->fik", Bj("chest"), O_est_ch))
    O_ch = Bj("chest") @ K_ch
    O_est_h = frame(J("chest") - hipmid, J("upleg_L") - J("upleg_R"))
    K_h = avg_rot(np.einsum("fji,fjk->fik", Bj("hips"), O_est_h))
    O_h = Bj("hips") @ K_h
    O_hd = Bj("head") @ K_ch
    O_nk = Bj("neck") @ K_ch if "neck" in R else None
    for seg, O in (("hips", O_h), ("chest", O_ch), ("head", O_hd), ("neck", O_nk)):
        if O is None: continue
        D[:, SI[seg], 0] = O[..., 0]; D[:, SI[seg], 1] = O[..., 1]
    chest_back = np.cross(O_ch[..., 0], O_ch[..., 1])          # up x left = back
    hip_back = np.cross(O_h[..., 0], O_h[..., 1])
    palm = "none"
    for s in "LR":
        sh, el, wr = J(f"uparm_{s}"), J(f"forearm_{s}"), J(f"wrist_{s}")
        d_arm, d_fa = _n(el - sh), _n(wr - el)
        # hand end
        he = None
        for k in (f"middle1_{s}",):
            if k in R: he = J(k)
        if he is None and f"index1_{s}" in R and f"pinky1_{s}" in R: he = 0.5 * (J(f"index1_{s}") + J(f"pinky1_{s}"))
        if he is None and f"index1_{s}" in R: he = J(f"index1_{s}")
        if he is None and f"hand_end_{s}" in R:
            he = J(f"hand_end_{s}")
            if np.median(np.linalg.norm(he - wr, axis=-1)) < 0.03 * Ls: he = None
        d_hand = _n(he - wr) if he is not None else d_fa
        # elbow hinge
        n = np.cross(d_arm, d_fa); bent = np.linalg.norm(n, axis=-1); n = _n(n)
        ok = bent > 0.35
        ref_arm, ref_fa = _hinge_refs(Bj(f"uparm_{s}"), Bj(f"forearm_{s}"), n, bent, ok, d_arm, d_fa, -chest_back)
        # palm side
        if f"index1_{s}" in R and f"pinky1_{s}" in R:
            side_v = J(f"index1_{s}") - J(f"pinky1_{s}"); palm = "ip"
        elif f"thumb1_{s}" in R and np.median(np.linalg.norm(J(f"thumb1_{s}") - wr, axis=-1)) > 0.02 * Ls:
            side_v = J(f"thumb1_{s}") - wr; palm = "thumb" if palm == "none" else palm
        else:
            side_v = None
        if side_v is not None:
            ref_hand = side_v; ref_fa = side_v if palm == "ip" else ref_fa
        else:
            ref_hand = np.einsum("fij,j->fi", Bj(f"wrist_{s}"), cal(Bj(f"wrist_{s}"), ref_fa))
        D[:, SI[f"arm_{s}"]] = np.stack([d_arm, ref_arm], 1)
        D[:, SI[f"forearm_{s}"]] = np.stack([d_fa, ref_fa], 1)
        D[:, SI[f"hand_{s}"]] = np.stack([d_hand, ref_hand], 1)
        if f"clav_{s}" in R:
            d_cl = _n(sh - J(f"clav_{s}"))
            ref_cl = np.einsum("fij,j->fi", Bj(f"clav_{s}"), cal(Bj(f"clav_{s}"), chest_back))
            D[:, SI[f"clav_{s}"]] = np.stack([d_cl, ref_cl], 1)
        # legs
        hp, kn, an = J(f"upleg_{s}"), J(f"knee_{s}"), J(f"ankle_{s}")
        d_th, d_sh = _n(kn - hp), _n(an - kn)
        n = np.cross(d_th, d_sh); bent = np.linalg.norm(n, axis=-1); n = _n(n); ok = bent > 0.3
        ref_th, ref_sh = _hinge_refs(Bj(f"upleg_{s}"), Bj(f"knee_{s}"), n, bent, ok, d_th, d_sh, hip_back)
        if f"toe_{s}" in R and np.median(np.linalg.norm(J(f"toe_{s}") - an, axis=-1)) > 0.03 * Ls: d_ft = _n(J(f"toe_{s}") - an)
        elif f"toe_end_{s}" in R: d_ft = _n(J(f"toe_end_{s}") - an)
        else: d_ft = _n(np.cross(ref_sh, d_sh))
        ref_ft = np.einsum("fij,j->fi", Bj(f"ankle_{s}"), cal(Bj(f"ankle_{s}"), ref_sh))
        D[:, SI[f"thigh_{s}"]] = np.stack([d_th, ref_th], 1)
        D[:, SI[f"shin_{s}"]] = np.stack([d_sh, ref_sh], 1)
        D[:, SI[f"foot_{s}"]] = np.stack([d_ft, ref_ft], 1)
    root = np.stack([hipmid[:, 0], hipmid[:, 1], hipmid[:, 2] - floor], -1) / Ls
    # foot contacts (source): low and slow
    con = np.zeros((F, 2), np.uint8)
    dt = 1.0 / src["fps"]
    for k, s in enumerate("LR"):           # heel (ankle) planted: low relative to its own standing height, and nearly still
        a = J(f"ankle_{s}")
        a_low = float(np.percentile(a[:, 2], 3))
        h = a[:, 2] - a_low
        v = np.zeros(F); v[1:] = np.linalg.norm(np.diff(a, axis=0), axis=-1) / dt / Ls; v[0] = v[1] if F > 1 else 0
        c = (h < 0.05 * Ls) & (v < 0.25) & (a_low - floor < 0.25 * Ls)
        c = _clean_bool(c, 3)
        con[:, k] = c
    md = dict(D=D.astype(np.float32), root=root.astype(np.float32), contact=con, fps=src["fps"],
              meta=dict(meta or {}, palm=palm, src_leg=Ls, frames=F, roles={k: names[v] for k, v in R.items()},
                        origin_legs=[round(float(x) / Ls, 4) for x in o[:2]], yaw_deg=round(math.degrees(yaw), 2)))
    return md

def _hinge_refs(B_up, B_lo, n, bent, ok, d_up, d_lo, body_bend):
    """upper and lower limb reference vectors: the hinge normal where the limb is bent, a per-take calibrated
    joint-local hinge elsewhere; geometric fallback (body-relative) when the take is never bent."""
    F = len(n)
    if ok.sum() >= 5:
        vu = _n(np.sum(_n(np.einsum("fji,fj->fi", B_up[ok], n[ok])), 0)); vl = _n(np.sum(_n(np.einsum("fji,fj->fi", B_lo[ok], n[ok])), 0))
        cu = np.einsum("fij,j->fi", B_up, vu); cl = np.einsum("fij,j->fi", B_lo, vl)
    else:
        cu = _n(np.cross(d_up, body_bend)); cl = _n(np.cross(d_lo, body_bend))
    w = np.clip((bent - 0.25) / 0.3, 0, 1)[:, None]
    # keep the measured normal's sign consistent with the calibrated one
    nn = np.where(np.sum(n * cu, -1, keepdims=True) < 0, -n, n)
    return _n(w * nn + (1 - w) * cu), _n(w * nn + (1 - w) * cl)

def _clean_bool(c, minlen):
    c = c.copy(); n = len(c); i = 0
    while i < n:
        j = i
        while j < n and c[j] == c[i]: j += 1
        if c[i] and j - i < minlen: c[i:j] = False
        i = j
    i = 0
    while i < n:                                # fill tiny gaps
        j = i
        while j < n and c[j] == c[i]: j += 1
        if not c[i] and 0 < i and j < n and j - i < 2: c[i:j] = True
        i = j
    return c

def save_md(path, md):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    np.savez_compressed(path, D=md["D"].astype(np.float16), root=md["root"].astype(np.float32), contact=md["contact"],
                        fps=np.array(md["fps"]), meta=np.array(json.dumps(md["meta"])))

def load_md(path_or_file):
    z = np.load(path_or_file, allow_pickle=False)
    return dict(D=z["D"].astype(np.float64), root=z["root"].astype(np.float64), contact=z["contact"].astype(bool), fps=float(z["fps"]),
                meta=json.loads(str(z["meta"])))

def mirror_md(md):
    D = md["D"].copy(); S = np.array([-1.0, 1, 1])
    out = D.copy()
    for seg in SEGS:
        base = seg.split("_")[0]; src = seg
        if seg.endswith("_L"): src = seg[:-2] + "_R"
        elif seg.endswith("_R"): src = seg[:-2] + "_L"
        out[:, SI[seg], 0] = D[:, SI[src], 0] * S
        out[:, SI[seg], 1] = D[:, SI[src], 1] * S * _REF_PARITY[base]
    r = md["root"].copy(); r[:, 0] *= -1
    return dict(md, D=out, root=r, contact=md["contact"][:, ::-1].copy())

def resample_md(md, fps, speed=1.0, t0=0.0, t1=None):
    src_fps = md["fps"]; F = len(md["root"]); dur = (F - 1) / src_fps
    t1 = dur if t1 is None else min(t1, dur)
    tt = np.arange(t0, t1 + 1e-9, speed / fps) * src_fps
    i0 = np.clip(np.floor(tt).astype(int), 0, F - 1); i1 = np.clip(i0 + 1, 0, F - 1); w = (tt - i0)
    lerp = lambda a: a[i0] * (1 - w.reshape((-1,) + (1,) * (a.ndim - 1))) + a[i1] * w.reshape((-1,) + (1,) * (a.ndim - 1))
    return dict(md, D=lerp(md["D"]), root=lerp(md["root"]), contact=md["contact"][np.round(tt).astype(int).clip(0, F - 1)], fps=fps)

# ---------------------------------------------------------------------------------------------------------------------
# 4. TARGET (MPFB default rig) - rest data, solve, ground, foot lock, QC
# ---------------------------------------------------------------------------------------------------------------------
_T_PATS = {   # segment -> (first bone, last bone) regexes for the MPFB default rig (plus generic fallbacks)
    "hips": (r"root|hips?|pelvis", None), "head": (r"head", None),
    "clav": (r"clavicle", r"shoulder0?1"), "arm": (r"upperarm0?1|upper_?arm", r"upperarm0?2"), "forearm": (r"lowerarm0?1|fore_?arm|lower_?arm", r"lowerarm0?2"),
    "hand": (r"wrist|hand", None), "thigh": (r"upperleg0?1|thigh|up_?leg", r"upperleg0?2"), "shin": (r"lowerleg0?1|shin|calf", r"lowerleg0?2"),
    "foot": (r"foot", None),
}

def rig_rest_from_bones(bones):
    """bones: list of (name, parent_name|None, head(3), tail(3), matrix_local 3x3) in armature space -> rig dict"""
    names = [b[0] for b in bones]; ix = {n: i for i, n in enumerate(names)}
    rig = dict(names=names, parents=[ix.get(b[1], -1) if b[1] else -1 for b in bones],
               head=np.array([b[2] for b in bones], float), tail=np.array([b[3] for b in bones], float), R=np.array([b[4] for b in bones], float))
    rig["order"] = _topo(rig["parents"]); rig.update(_target_map(rig))
    return rig

def _topo(parents):
    depth = []
    for j in range(len(parents)):
        d, p = 0, parents[j]
        while p >= 0: d += 1; p = parents[p]
        depth.append(d)
    return sorted(range(len(parents)), key=lambda j: depth[j])

def _target_map(rig):
    names, par = rig["names"], rig["parents"]
    def find(pat, side):
        for j, n in enumerate(names):
            s = _side(n); c = _core(n)
            if (s == side) and re.fullmatch(pat, c): return j
        return None
    seg = {}
    for k, (fp, lp) in _T_PATS.items():
        for s in (("L", "R") if k not in ("hips", "head") else (None,)):
            f = find(fp, s)
            if f is None: continue
            ch = [f]
            if lp:
                l = find(lp, s)
                if l is not None and l != f:
                    c = []; j = l
                    while j >= 0 and j != f: c.append(j); j = par[j]
                    if j == f: ch = [f] + c[::-1]
            seg[k + ("_" + s if s else "")] = ch
    # spine chain hips..chest and neck chain
    sp = sorted([j for j, n in enumerate(names) if re.fullmatch(r"spine0?\d", n.lower())], key=lambda j: -int(re.sub(r"\D", "", names[j]) or 0))
    nk = sorted([j for j, n in enumerate(names) if re.fullmatch(r"neck0?\d", n.lower())], key=lambda j: int(re.sub(r"\D", "", names[j]) or 0))
    fingers = {}
    for s in "LR":
        for key, pat in (("index1", r"finger2-1"), ("pinky1", r"finger5-1"), ("thumb1", r"finger1-1"), ("middle1", r"finger3-1")):
            j = find(pat, s)
            if j is not None: fingers[f"{key}_{s}"] = j
    return dict(seg=seg, spine=sp, necks=nk, fingers=fingers)

def rest_vectors(rig, palm="none"):
    """target rest (dir, ref) for each segment, armature space (MPFB: Z up, faces -Y)"""
    H, T, seg = rig["head"], rig["tail"], rig["seg"]; out = {}
    out["hips"] = out["chest"] = out["neck"] = out["head"] = (UP, LEFT)
    for s in "LR":
        g = lambda k: seg.get(f"{k}_{s}")
        if g("arm"): d = _n(T[g("arm")[-1]] - H[g("arm")[0]]); out[f"arm_{s}"] = (d, _n(np.cross(d, FWD)))
        if g("forearm"):
            d = _n(T[g("forearm")[-1]] - H[g("forearm")[0]]); r = _n(np.cross(d, FWD))
            fi = rig["fingers"]
            if palm == "ip" and f"index1_{s}" in fi and f"pinky1_{s}" in fi: r = H[fi[f"index1_{s}"]] - H[fi[f"pinky1_{s}"]]
            out[f"forearm_{s}"] = (d, r)
        if g("hand"):
            w = H[g("hand")[0]]; fi = rig["fingers"]
            if f"middle1_{s}" in fi: e = H[fi[f"middle1_{s}"]]
            elif f"index1_{s}" in fi and f"pinky1_{s}" in fi: e = 0.5 * (H[fi[f"index1_{s}"]] + H[fi[f"pinky1_{s}"]])
            else: e = T[g("hand")[0]]
            d = _n(e - w)
            if palm == "ip" and f"index1_{s}" in fi and f"pinky1_{s}" in fi: r = H[fi[f"index1_{s}"]] - H[fi[f"pinky1_{s}"]]
            elif palm == "thumb" and f"thumb1_{s}" in fi: r = H[fi[f"thumb1_{s}"]] - w
            else: r = out.get(f"forearm_{s}", (None, _n(np.cross(d, FWD))))[1]
            out[f"hand_{s}"] = (d, r)
        if g("clav"): d = _n(T[g("clav")[-1]] - H[g("clav")[0]]); out[f"clav_{s}"] = (d, BACK)
        if g("thigh"): d = _n(T[g("thigh")[-1]] - H[g("thigh")[0]]); out[f"thigh_{s}"] = (d, _n(np.cross(d, BACK)))
        if g("shin"): d = _n(T[g("shin")[-1]] - H[g("shin")[0]]); out[f"shin_{s}"] = (d, _n(np.cross(d, BACK)))
        if g("foot"): d = _n(T[g("foot")[0]] - H[g("foot")[0]]); out[f"foot_{s}"] = (d, out.get(f"shin_{s}", (None, LEFT))[1])
    return out

def leg_geometry(rig):
    H, seg = rig["head"], rig["seg"]; g = {}
    for s in "LR":
        th, sh, ft = seg[f"thigh_{s}"], seg[f"shin_{s}"], seg[f"foot_{s}"]
        g[s] = dict(hip=th[0], knee=sh[0], ankle=ft[0], L1=float(np.linalg.norm(H[sh[0]] - H[th[0]])), L2=float(np.linalg.norm(H[ft[0]] - H[sh[0]])))
    g["leg"] = g["L"]["L1"] + g["L"]["L2"]
    return g

def solve(md, rig, ground=True, foot_lock=True, in_place=False, lock_blend=2):
    """md (already resampled) + rig rest -> dict(q (F,N,4) local basis quaternions, loc (F,3) root bone location, P heads, qc)"""
    D, root, con = md["D"], md["root"], md["contact"]; F = len(root); N = len(rig["names"])
    Rr, H, Tl, par = rig["R"], rig["head"], rig["tail"], rig["parents"]
    rv = rest_vectors(rig, md["meta"].get("palm", "none"))
    seg = rig["seg"]; LG = leg_geometry(rig)
    W = np.zeros((F, len(SEGS), 3, 3)); have = np.zeros(len(SEGS), bool)
    for i, s in enumerate(SEGS):
        if s not in rv: continue
        d, r = D[:, i, 0], D[:, i, 1]
        ok = np.isfinite(d).all(-1) & np.isfinite(r).all(-1)
        if not ok.any(): continue
        d = _ffill(d, ok); r = _ffill(r, ok)
        r = np.where((np.linalg.norm(np.cross(_n(d), r), axis=-1) < 1e-4)[:, None], np.cross(_n(d), FWD if s[:2] in ("ar", "fo", "ha") else BACK), r)
        Mr = frame(rv[s][0][None], np.asarray(rv[s][1], float)[None])[0]
        W[:, i] = frame(d, r) @ Mr.T; have[i] = True
    if not have[SI["neck"]] and have[SI["head"]] and have[SI["chest"]]: W[:, SI["neck"]] = slerp_m(W[:, SI["chest"]], W[:, SI["head"]], 0.5); have[SI["neck"]] = True
    # per-bone world delta
    Wb = np.zeros((F, N, 3, 3)); assigned = {}
    for s, ch in seg.items():
        if s in SI and have[SI[s]]:
            for j in ch: assigned[j] = W[:, SI[s]]
    sp = rig["spine"]
    for k, j in enumerate(sp):
        assigned[j] = slerp_m(W[:, SI["hips"]], W[:, SI["chest"]], (k + 1) / len(sp))
    nk = rig["necks"]
    for k, j in enumerate(nk):
        t = (k + 1) / (len(nk) + 1)
        assigned[j] = slerp_m(W[:, SI["chest"]], W[:, SI["neck"]], t * 2) if t <= 0.5 else slerp_m(W[:, SI["neck"]], W[:, SI["head"]], (t - 0.5) * 2)
    for j in rig["order"]:
        Wb[:, j] = assigned[j] if j in assigned else (Wb[:, par[j]] if par[j] >= 0 else np.eye(3))
    # root path: hip-joint midpoint
    rootj = seg["hips"][0]
    Lt = LG["leg"]
    hm_rest = 0.5 * (H[LG["L"]["hip"]] + H[LG["R"]["hip"]])
    want = np.stack([hm_rest[0] + root[:, 0] * Lt, hm_rest[1] + root[:, 1] * Lt, root[:, 2] * Lt], -1)
    if in_place:
        k = max(1, int(md["fps"]))
        for a in (0, 1):
            sm = np.convolve(np.pad(want[:, a], (k // 2, k - 1 - k // 2), mode="edge"), np.ones(k) / k, mode="valid")
            want[:, a] = want[:, a] - sm + hm_rest[a]
    rh = want - np.einsum("fij,j->fi", Wb[:, rootj], hm_rest - H[rootj])
    Ph = _fk_heads(Wb, rh, rig)
    qc = {}
    # ground: the lowest sole point (ankle above its rest height, toe base) sits on z=0
    def soles(Ph, Wb):
        out = []
        for s in "LR":
            a = LG[s]["ankle"]; toe = Ph[:, a] + np.einsum("fij,j->fi", Wb[:, a], Tl[a] - H[a])
            out.append(np.minimum(Ph[:, a, 2] - H[a, 2], toe[:, 2] - Tl[a, 2]))
        return np.minimum(out[0], out[1]), out
    sole, per = soles(Ph, Wb)
    if ground:
        off = -float(np.percentile(sole, 3)); rh[:, 2] += off; Ph[..., 2] += off; sole = sole + off
    qc["floor_pen_cm"] = round(float(max(0.0, -sole.min())) * 100 / max(Lt, 1e-6) * 0.8, 1)    # cm on a 0.8 m leg
    # foot slide before locking (in contact frames), in cm on a 0.8 m leg
    slide = []
    for k, s in enumerate("LR"):
        a = LG[s]["ankle"]; c = con[:, k]
        for i0, i1 in _runs(c):
            p = Ph[i0:i1, a, :2]; slide.append(float(np.max(np.linalg.norm(p - p.mean(0), axis=-1))) * 2)
    qc["foot_slide_cm"] = round(float(np.median(slide)) * 100 / Lt * 0.8, 1) if slide else 0.0
    qc["foot_slide95_cm"] = round(float(np.percentile(slide, 95)) * 100 / Lt * 0.8, 1) if slide else 0.0
    reach_fail = 0
    if foot_lock and not in_place:
        for k, s in enumerate("LR"):
            reach_fail += _lock_leg(Wb, Ph, rig, LG[s], con[:, k], seg[f"thigh_{s}"], seg[f"shin_{s}"], lock_blend)
        Ph = _fk_heads(Wb, rh, rig)
        if ground:
            sole, per = soles(Ph, Wb); pen = -min(0.0, float(np.percentile(sole, 1)))
            if pen > 0.005 * Lt: rh[:, 2] += pen; Ph[..., 2] += pen
    qc["reach_fail_frames"] = int(reach_fail)
    # knee / elbow bending backwards, extreme twist
    bad_knee = bad_elbow = 0
    for s in "LR":
        for up, lo, cnt in (("thigh", "shin", "k"), ("arm", "forearm", "e")):
            if f"{up}_{s}" not in seg or f"{lo}_{s}" not in seg: continue
            j1, j2 = seg[f"{up}_{s}"][0], seg[f"{lo}_{s}"][0]
            du = _n(np.einsum("fij,j->fi", Wb[:, j1], rv[f"{up}_{s}"][0])); dl = _n(np.einsum("fij,j->fi", Wb[:, j2], rv[f"{lo}_{s}"][0]))
            hinge = np.einsum("fij,j->fi", Wb[:, j1], rv[f"{up}_{s}"][1])
            c = np.cross(du, dl); ang = np.degrees(np.arcsin(np.clip(np.linalg.norm(c, axis=-1), 0, 1)))
            back = (np.sum(c * hinge, -1) < 0) & (ang > 20)
            if cnt == "k": bad_knee += int(back.sum())
            else: bad_elbow += int(back.sum())
    qc["knee_backwards_frames"] = bad_knee; qc["elbow_backwards_frames"] = bad_elbow
    # local basis
    q = np.zeros((F, N, 4)); q[..., 0] = 1
    tw = 0
    for j in range(N):
        p = par[j]
        Wp = Wb[:, p] if p >= 0 else np.broadcast_to(np.eye(3), (F, 3, 3))
        M = np.einsum("ji,fjk->fik", Rr[j], np.einsum("fji,fjk->fik", Wp, Wb[:, j])) @ Rr[j]
        if np.allclose(M, np.eye(3), atol=1e-7): continue
        qq = m2q(M)
        s = np.sign(np.sum(qq[1:] * qq[:-1], -1)); s = np.concatenate([[1], np.cumprod(np.where(s == 0, 1, s))]); qq = qq * s[:, None]
        if qq[0, 0] < 0: qq = -qq
        q[:, j] = qq
        tw = max(tw, float(np.degrees(np.max(np.abs(2 * np.arctan2(qq[:, 2], qq[:, 0]))))) if rig["names"][j][:5] in ("lower", "upper", "wrist") else 0)
    qc["max_limb_twist_deg"] = round(min(tw, 360 - tw), 0)
    loc = np.einsum("ji,fj->fi", Rr[rootj], rh - H[rootj])
    qc["flagged"] = bool(qc["floor_pen_cm"] > 4 or qc["knee_backwards_frames"] > 0.05 * F or qc["elbow_backwards_frames"] > 0.1 * F
                         or qc["max_limb_twist_deg"] > 150 or qc["reach_fail_frames"] > 0.1 * F)
    return dict(q=q, loc=loc, root_bone=rootj, P=Ph, W=Wb, qc=qc)

def _runs(c):
    out = []; n = len(c); i = 0
    while i < n:
        if c[i]:
            j = i
            while j < n and c[j]: j += 1
            out.append((i, j)); i = j
        else: i += 1
    return out

def _fk_heads(Wb, rh, rig):
    F, N = Wb.shape[:2]; H, par = rig["head"], rig["parents"]; P = np.zeros((F, N, 3))
    for j in rig["order"]:
        p = par[j]
        P[:, j] = rh if p < 0 else P[:, p] + np.einsum("fij,j->fi", Wb[:, p], H[j] - H[p])
    return P

def _lock_leg(Wb, Ph, rig, g, c, thigh, shin, blend):
    """pin the ankle during contact runs with an analytic 2-bone IK on (thigh, shin); returns frames that could not reach"""
    F = len(c); hipj, kj, aj = g["hip"], g["knee"], g["ankle"]; L1, L2 = g["L1"], g["L2"]
    target = Ph[:, aj].copy(); w = np.zeros(F)
    runs = []
    for i0, i1 in _runs(c):                     # split a long contact where the planted foot really shuffles (> 4 % of the leg)
        a = i0
        for i in range(i0 + 1, i1 + 1):
            if i == i1 or np.linalg.norm(Ph[i, aj, :2] - Ph[a:i, aj, :2].mean(0)) > 0.04 * (L1 + L2):
                runs.append((a, i)); a = i
    for i0, i1 in runs:
        pin = Ph[i0:i1, aj].mean(0)
        target[i0:i1] = pin; w[i0:i1] = 1
        for k in range(1, blend + 1):           # ease in/out
            if i0 - k >= 0 and w[i0 - k] < 1 - k / (blend + 1): w[i0 - k] = 1 - k / (blend + 1); target[i0 - k] = pin
            if i1 - 1 + k < F and w[i1 - 1 + k] < 1 - k / (blend + 1): w[i1 - 1 + k] = 1 - k / (blend + 1); target[i1 - 1 + k] = pin
    m = w > 0
    if not m.any(): return 0
    Hp, K, A = Ph[m, hipj], Ph[m, kj], Ph[m, aj]
    At = A + (target[m] - A) * w[m, None]
    d = At - Hp; dl = np.linalg.norm(d, axis=-1); fail = int((dl > (L1 + L2) * 0.999).sum())
    dl = np.clip(dl, abs(L1 - L2) + 1e-4, (L1 + L2) * 0.999); u = _n(d)
    pole = K - Hp; v = _n(pole - np.sum(pole * u, -1, keepdims=True) * u)
    ca = (L1 ** 2 + dl ** 2 - L2 ** 2) / (2 * L1 * dl); sa = np.sqrt(np.clip(1 - ca ** 2, 0, 1))
    Kn = Hp + L1 * (ca[:, None] * u + sa[:, None] * v)
    Q1 = rot_between(K - Hp, Kn - Hp)
    old_shin = np.einsum("fij,fj->fi", Q1, A - K)
    Q2 = rot_between(old_shin, At - Kn) @ Q1
    for j in thigh: Wb[m, j] = Q1 @ Wb[m, j]
    for j in shin: Wb[m, j] = Q2 @ Wb[m, j]
    return fail

# ---------------------------------------------------------------------------------------------------------------------
# 5. CATALOGUE + lookup
# ---------------------------------------------------------------------------------------------------------------------
_CAT = None
def data_dirs():
    out = []
    for d in os.environ.get("SONPUR_MOTION_DIR", "").split(os.pathsep):
        if d: out.append(d)
    here = os.path.dirname(os.path.abspath(__file__))
    out += [os.path.join(here, "motion_packs"), "/kaggle/input/sonpur-motion-packs", "/kaggle/input/sonpur-motion-nc"]
    out += glob.glob("/kaggle/input/sonpur-motion*") + glob.glob("/kaggle/input/datasets/*/sonpur-motion*")
    seen = []
    for d in out:
        if os.path.isdir(d) and os.path.abspath(d) not in seen: seen.append(os.path.abspath(d))
    return seen

def catalogue(reload=False):
    """merged motion catalogue {name: row} from every mounted pack (row['_dir'] = where it came from)"""
    global _CAT
    if _CAT is not None and not reload: return _CAT
    _CAT = {}
    for d in data_dirs():
        for p in glob.glob(os.path.join(d, "**", "motion_catalogue.json"), recursive=True):
            base = os.path.dirname(p)
            for row in json.load(open(p, encoding="utf-8"))["motions"]:
                row = dict(row, _dir=base); _CAT.setdefault(row["name"], row)
    return _CAT

def find(query, final=False, limit=20, cat=None, require_all=False):
    """rank catalogue rows for a tag/word query ('old walk', 'sit ground', 'cmu_016_15'). Rows matching more words rank first;
    require_all=True keeps only rows that contain every word (in tags, description or name)."""
    cat = cat or catalogue()
    if query in cat: return [cat[query]]
    words = [w for w in re.split(r"[\s,]+", query.lower()) if w]
    scored = []
    for r in cat.values():
        hay = set(r.get("tags", [])) | set(re.split(r"[^a-z0-9]+", (r.get("desc", "") + " " + r["name"] + " " + " ".join(r.get("tags", []))).lower()))
        hit = sum(1 for w in words if w in hay)
        if hit == 0 or (require_all and hit < len(words)): continue
        s = hit * 10 + (5 if r.get("category") in words else 0) - (8 if r.get("flagged") else 0)
        s += (20 if r.get("commercial_ok") else 0) if final else 0
        s += {"style100": 1.5, "cmu": 1, "quaternius": 1, "bandai": 0.5}.get(r.get("pack", "").split("_")[0], 0)
        s -= 0.002 * abs(r.get("seconds", 8) - 8)
        scored.append((s, r))
    scored.sort(key=lambda x: -x[0])
    return [r for s, r in scored[:limit]]

def _md_file(row):
    p = os.path.join(row["_dir"], row["file"])
    if os.path.exists(p): return p
    z = os.path.join(row["_dir"], row["file"].split("/")[0] + ".zip")
    if os.path.exists(z):
        return io.BytesIO(zipfile.ZipFile(z).read("/".join(row["file"].split("/")[1:])))
    raise FileNotFoundError(p)

# ---------------------------------------------------------------------------------------------------------------------
# 6. BLENDER side
# ---------------------------------------------------------------------------------------------------------------------
def rig_rest(arm_obj):
    """rest data of a Blender armature object (armature space)"""
    bones = [(b.name, b.parent.name if b.parent else None, tuple(b.head_local), tuple(b.tail_local), [list(r) for r in b.matrix_local.to_3x3()])
             for b in arm_obj.data.bones]
    return rig_rest_from_bones(bones)

def _arm(rig):
    return getattr(rig, "arm", rig)

def load_motion(name, rig, start=1, final=False, in_place=False, root_motion=True, foot_lock=True, speed=1.0, mirror=False,
                loop=1, t0=0.0, t1=None, fps=None, action_name=None, ground=True, verbose=True):
    """Apply a library motion to an MPFB rig (armature object or lib_anim.Rig). `name` = exact catalogue name or a tag query.
    final=True: prefer commercial_ok motions with the same tags; NC-only motions still load, with a loud warning.
    in_place: hip path removed (for loops/treadmill shots; feet then slide by design, so no foot lock).
    root_motion=False: same as in_place. loop>1 repeats the take (use with in_place, or with catalogue 'cycle').
    Returns info dict (name, licence, commercial_ok, frames, f_end, qc, warning)."""
    import bpy
    arm = _arm(rig); cat = catalogue()
    if not cat: raise RuntimeError("no motion catalogue found: set SONPUR_MOTION_DIR to the unpacked sonpur-motion-packs / sonpur-motion-nc datasets")
    rows = find(name, final=final, cat=cat)
    if not rows: raise KeyError(f"no motion matches {name!r}")
    row = rows[0]; warning = None
    if final and not row.get("commercial_ok"):
        alts = [r for r in rows if r.get("commercial_ok")]
        if alts: row = alts[0]
        else:
            warning = f"NON-COMMERCIAL MOTION IN A FINAL RENDER: {row['name']} ({row.get('licence')}) - no commercial_ok motion matches {name!r}"
            print("!" * 100 + "\n" + warning + "\n" + "!" * 100)
    md = load_md(_md_file(row))
    if mirror: md = mirror_md(md)
    sc = bpy.context.scene; fps = fps or sc.render.fps / max(1e-6, sc.render.fps_base)
    if row.get("cycle") and loop > 1 and t1 is None:
        t0, t1 = row["cycle"]
    md = resample_md(md, fps, speed=speed, t0=t0, t1=t1)
    if loop > 1:
        for k in ("D", "root", "contact"):
            reps = [md[k]] * loop
            if k == "root":
                step = md["root"][-1] - md["root"][0]; step[2] = 0
                reps = [md["root"] + step * i for i in range(loop)]
            md[k] = np.concatenate(reps, 0)
    R = rig_rest(arm)
    sol = solve(md, R, ground=ground, foot_lock=foot_lock and root_motion and not in_place, in_place=in_place or not root_motion)
    act = write_action(arm, sol, R, start, action_name or f"ML_{row['name']}")
    F = len(sol["loc"])
    info = dict(name=row["name"], licence=row.get("licence"), commercial_ok=row.get("commercial_ok"), credit=row.get("credit"),
                frames=F, f_start=start, f_end=start + F - 1, qc=sol["qc"], action=act.name, warning=warning, tags=row.get("tags"))
    if verbose: print("MOTION", json.dumps({k: v for k, v in info.items() if k != "credit"})[:600])
    return info

def write_action(arm, sol, R, start, name):
    import bpy
    q, loc = sol["q"], sol["loc"]; F, N = q.shape[:2]
    act = bpy.data.actions.new(name); act.use_fake_user = True
    if arm.animation_data is None: arm.animation_data_create()
    arm.animation_data.action = act
    slot_api = not hasattr(act, "fcurves")
    if slot_api:
        try:
            slot = act.slots.new(id_type="OBJECT", name=arm.name); arm.animation_data.action_slot = slot
        except Exception: pass
    frames = np.arange(start, start + F, dtype=np.float32)
    def fc(path, idx, group):
        if not slot_api: return act.fcurves.new(path, index=idx, action_group=group)
        return act.fcurve_ensure_for_datablock(arm, path, index=idx, group_name=group)
    def put(curve, vals):
        curve.keyframe_points.add(F)
        co = np.empty(F * 2, np.float32); co[0::2] = frames; co[1::2] = vals
        curve.keyframe_points.foreach_set("co", co)
        curve.keyframe_points.foreach_set("interpolation", np.full(F, 1, np.int32))   # LINEAR
        curve.update()
    names = R["names"]
    for j in range(N):
        if np.allclose(q[:, j], [1, 0, 0, 0], atol=1e-6): continue
        pb = arm.pose.bones[names[j]]; pb.rotation_mode = "QUATERNION"
        for i in range(4): put(fc(f'pose.bones["{names[j]}"].rotation_quaternion', i, names[j]), q[:, j, i])
    rb = names[sol["root_bone"]]
    for i in range(3): put(fc(f'pose.bones["{rb}"].location', i, rb), loc[:, i])
    return act

def bake_library(names, arm, out_blend, prefix=""):
    """bake catalogue motions onto this armature as fake-user actions and save ONLY the armature + actions (no meshes)."""
    import bpy
    done = []
    for n in names:
        try:
            info = load_motion(n, arm, start=1, action_name=prefix + n, verbose=False); done.append(info["action"])
        except Exception as ex: print("BAKE FAIL", n, ex)
    arm.animation_data.action = None
    bpy.data.libraries.write(out_blend, {arm, arm.data} | {bpy.data.actions[a] for a in done}, fake_user=True)
    return done
