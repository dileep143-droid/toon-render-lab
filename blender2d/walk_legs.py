"""WALK with DRAWN legs (the RubberHose idea): every frame the pyjama legs are drawn fresh as clean outlined tubes from hip -> knee ->
ankle, and the character's own drawn foot is attached at the ankle. Leg shape therefore never distorts (stretched-drawing walks
looked 'worst' - owner, 9 Oct). Foot targets follow the spine_anim_mcp foot-plant idea (MIT): planted on the ground for 60 % of the
cycle (slides back under the body while the body moves forward), lifted on an arc for 40 %; the knee is solved by 2-bone IK.
Body + arm come from the side-view puppet (SidePuppet), legs are drawn behind the kurta.
  python walk_legs.py <char_side_dir> <out_preview.jpg>"""
import json, math, os, sys
import cv2, numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from side_puppet import SidePuppet

PYJ, PYJ_SHADE, INK = np.array([242, 242, 244]), np.array([206, 207, 214]), np.array([28, 24, 24])


class DrawnLegs:
    def __init__(self, D, sp, style="normal"):
        """style 'normal': straight legs, the stance leg works like a pendulum (hips rise over each step, lowest at contact);
        style 'sneak': hips low, knees bent all the time (creeping - e.g. sneaking off with the laddoos). Owner-approved 9 Oct."""
        self.sp = sp; J = sp.J; self.J = J; self.style = style
        self.hip = J["hip"].copy(); self.ground = float(J["ankle_front"][1]) + 2
        Dv = self.ground - float(self.hip[1]); self.Dv = Dv
        self.w_top, self.w_knee, self.w_ank = 96.0, 74.0, 66.0                          # pyjama widths measured on the drawing
        if style == "sneak":
            self.l1 = self.l2 = 0.54 * Dv; self.drop = 0.12 * Dv; Dw = Dv - self.drop
            reach = self.l1 + self.l2; self.stride = 2 * math.sqrt(max(10.0, (0.97 * reach) ** 2 - Dw ** 2)); self.lift = 0.16 * Dv
        else:
            self.l1 = self.l2 = 0.506 * Dv; self.drop = 0.0                             # legs straight when standing
            self.reach = (self.l1 + self.l2) * 0.996; self.stride = 0.74 * Dv; self.lift = 0.075 * Dv
        # the character's own FOOT: skin + outline pixels of the near leg below the pyjama hem, anchored at the ankle
        P = os.path.join(D, "parts"); leg = np.asarray(Image.open(os.path.join(P, "leg_front.png")).convert("RGBA"))
        a = leg[..., 3] > 40; rgb = leg[..., :3].astype(int); y = np.arange(leg.shape[0])[:, None]
        skin = (rgb[..., 0] - rgb[..., 2] > 35) & (rgb[..., 0] > 120)                    # warm skin only (no grey pyjama hem)
        skin = cv2.morphologyEx(skin.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)) > 0
        dark = rgb.max(2) < 90                                                           # the foot's own outline next to the skin
        foot = a & (skin | (dark & cv2.dilate(skin.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool))) & (y > J["ankle_front"][1] - 30)
        n, lab, st, _ = cv2.connectedComponentsWithStats(foot.astype(np.uint8)); foot = lab == 1 + int(np.argmax(st[1:, 4])) if n > 1 else foot
        ys, xs = np.nonzero(foot); x0, x1, y0, y1 = xs.min() - 4, xs.max() + 5, ys.min() - 4, ys.max() + 5
        crop = leg[y0:y1, x0:x1].copy(); crop[..., 3] = np.where(foot[y0:y1, x0:x1], crop[..., 3], 0)
        self.foot = crop.astype(np.float32) / 255; self.foot_anchor = np.array([J["ankle_front"][0] - x0, J["ankle_front"][1] - y0], np.float32)

    def foot_target(self, t_norm, phase, hip_x):
        u = (t_norm + phase) % 1.0; S = self.stride
        if u < 0.6:                                                                   # STANCE: planted, slides back relative to the hip
            return np.array([hip_x + S / 2 - S * (u / 0.6), self.ground]), 0.0
        v = (u - 0.6) / 0.4                                                           # SWING: arc forward, toes point down a little
        return np.array([hip_x - S / 2 + S * v, self.ground - self.lift * math.sin(math.pi * v)]), 18.0 * math.sin(math.pi * v)

    def knee(self, H, A):
        d = A - H; dist = float(np.clip(np.linalg.norm(d), abs(self.l1 - self.l2) + 1e-3, self.l1 + self.l2 - 1e-3))
        u = d / (np.linalg.norm(d) + 1e-6); a = (self.l1 ** 2 - self.l2 ** 2 + dist ** 2) / (2 * dist)
        h = math.sqrt(max(0.0, self.l1 ** 2 - a ** 2)); base = H + u * a
        perp = np.array([u[1], -u[0]])                                                # knee bends FORWARD (+x, the way he faces)
        if perp[0] < 0: perp = -perp
        return base + perp * h, H + u * dist

    def draw_leg(self, canvas, H, A, toe_deg, dark, ss=2):
        """Draw one pyjama leg (two tapered capsules + knee disc) with ink outline and back-side shading, then the foot."""
        K, A = self.knee(H, A); A_ank = A; Hh, Wd = canvas.shape[:2]
        # foot: rotate the drawn foot about its ankle anchor, paste at the ankle
        f = self.foot.copy()
        if dark: f[..., :3] *= 0.9
        fh, fw = f.shape[:2]; M = cv2.getRotationMatrix2D(tuple(self.foot_anchor.tolist()), -toe_deg, 1.0)
        M[:, 2] += A_ank - self.foot_anchor; M *= ss; M[:, :2] /= 1; M2 = M.copy()
        pm = f.copy(); pm[..., :3] *= pm[..., 3:]
        warped = cv2.warpAffine(pm, M2, (Wd, Hh), flags=cv2.INTER_LINEAR, borderValue=0)
        canvas[:] = warped + canvas * (1 - warped[..., 3:])
        Hc, Kc, Ac = H * ss, K * ss, A * ss; Hh, Wd = canvas.shape[:2]
        m = np.zeros((Hh, Wd), np.uint8)
        def capsule(p, q, wp, wq):
            d = q - p; n = np.array([-d[1], d[0]]) / (np.linalg.norm(d) + 1e-6)
            poly = np.array([p + n * wp / 2 * ss, q + n * wq / 2 * ss, q - n * wq / 2 * ss, p - n * wp / 2 * ss]).astype(np.int32)
            cv2.fillPoly(m, [poly], 255)
        capsule(Hc + (Hc - Kc) * 0.25, Kc, self.w_top, self.w_knee); capsule(Kc, Ac, self.w_knee, self.w_ank)
        cv2.circle(m, tuple(Kc.astype(int)), int(self.w_knee / 2 * ss), 255, -1)
        k = int(15 * ss); sh = m.copy(); sh[:, k:] &= ~m[:, :-k]                    # back-edge band that follows the leg's shape
        ink = cv2.morphologyEx(m, cv2.MORPH_GRADIENT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (int(5 * ss), int(5 * ss))))
        col = np.zeros((Hh, Wd, 3), np.float32); col[:] = PYJ; col[sh > 0] = PYJ_SHADE; col[ink > 0] = INK
        if dark: col *= 0.9
        a = (m > 0).astype(np.float32)[..., None]
        canvas[..., :3] = col / 255 * a + canvas[..., :3] * (1 - a); canvas[..., 3:] = a + canvas[..., 3:] * (1 - a)
        return canvas


def render_walk(sp, legs, t, period=0.8, ss=2, hip_dx=0.0):
    """One walk frame on the character canvas. hip_dx shifts the body (the scene supplies forward travel)."""
    tn = (t / period) % 1.0; bob = 6.0 * abs(math.sin(2 * math.pi * tn))             # up at passing, down at contact (x2 per cycle)
    w = 2 * math.pi / period
    if legs.style == "sneak": dy = legs.drop - bob + 6.0
    else:
        # pendulum: hip height set by the planted (stance) leg kept straight -> lowest at contact, highest at passing
        dys = []
        for ph in (0.0, 0.5):
            u = (tn + ph) % 1.0
            if u < 0.6:
                dx = legs.stride / 2 - legs.stride * (u / 0.6)
                dys.append(legs.Dv - math.sqrt(max(1.0, legs.reach ** 2 - dx ** 2)))
        dy = max(dys) if dys else 0.0
    pose = {"dy": dy, "body": 1.2 * math.sin(2 * w * t), "arm_u": -18 * math.sin(w * t) - 0.0, "arm_l": 6 + 6 * math.sin(w * t + math.pi)}
    # body + arm from the puppet (legs drawn separately)
    keep = [L for L in sp.layers if L["name"] in ("body", "arm")]; saved = sp.layers; sp.layers = keep
    top = np.asarray(sp.render(pose, ss=ss)).astype(np.float32) / 255; sp.layers = saved
    Hh, Wd = sp.H * ss, sp.W * ss; canvas = np.zeros((Hh, Wd, 4), np.float32)
    H = np.array([legs.hip[0], legs.hip[1] + pose["dy"]])
    for phase, dark in ((0.5, True), (0.0, False)):                                   # far leg first (darker), then near leg
        A, toe = legs.foot_target(tn, phase, H[0]); legs.draw_leg(canvas, H, A, toe, dark, ss)
    canvas = cv2.resize(canvas, (sp.W, sp.H), interpolation=cv2.INTER_AREA)
    a = top[..., 3:]; out = top[..., :3] * a + canvas[..., :3] * (1 - a)                # body over the premultiplied legs
    alpha = a + canvas[..., 3:] * (1 - a)
    rgb = np.where(alpha > 1e-4, out / np.maximum(alpha, 1e-4), 0)
    return Image.fromarray((np.dstack([np.clip(rgb, 0, 1), np.clip(alpha, 0, 1)]) * 255).astype(np.uint8)), legs.stride / (0.6 * period)


if __name__ == "__main__":
    D, OUT = sys.argv[1], sys.argv[2]
    sp = SidePuppet(D); legs = DrawnLegs(D, sp)
    print("stride px", round(legs.stride, 1), "lift", round(legs.lift, 1), "l1/l2", round(legs.l1, 1))
    ims = [render_walk(sp, legs, t)[0] for t in np.linspace(0, 0.8, 8, endpoint=False)]
    W, H = ims[0].size; sheet = Image.new("RGB", (W * 8, H), (205, 230, 255))
    for i, im in enumerate(ims): sheet.paste(im, (i * W, 0), im)
    sheet.crop((0, 700, W * 8, H)).resize((W * 8 * 2 // 3, (H - 700) * 2 // 3)).save(OUT); print("saved", OUT)
