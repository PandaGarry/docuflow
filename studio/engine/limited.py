"""Limited-animation cutout actor: rigid head/forearm layers + local deformations.

No crossfades between different body drawings, no generated video, no 3D rig.
The inverse deformation is deliberately small; large gestures use drawn keys.
All landmarks and foreground masks are explicit production data in rigs.json.
"""
from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw


def cut_green(image: Image.Image) -> Image.Image:
    """Keep authored alpha. Only key raw chroma-green plates; never recolor skin."""
    rgba = np.array(image.convert('RGBA'))
    if image.mode == 'RGBA' and np.any(rgba[..., 3] < 10):
        return image.copy()
    rgb = rgba[..., :3].astype(np.float32)
    r, g, b = rgb.transpose(2, 0, 1)
    green = np.minimum(g - r, g - b)
    alpha = np.clip((62 - green) / 24, 0, 1)
    alpha[g < 75] = 1
    # Despill only the keyed edge. Cap/denim/gray sweater keep their colors.
    edge = (alpha > 0) & (alpha < 1)
    rgb[..., 1][edge] = np.minimum(g[edge], np.maximum(r, b)[edge] + 5)
    rgba[..., :3] = rgb.astype(np.uint8)
    rgba[..., 3] = np.minimum(rgba[..., 3], (alpha * 255).astype(np.uint8))
    return Image.fromarray(rgba)


def smooth(x):
    x = min(1., max(0., x))
    return x * x * (3 - 2 * x)


def blink_at(t: float, phase: float) -> float:
    """Finite close/hold/open, not a constant sinusoidal eyelid flutter."""
    out = 0.
    for start in (2.1 + phase, 6.6 + phase, 11.3 + phase, 17.7 + phase,
                  23.1 + phase, 29.2 + phase, 34.6 + phase):
        u = t - start
        if 0 <= u < .24:
            out = max(out, smooth(u / .075) if u < .075 else
                      1. if u < .125 else 1 - smooth((u - .125) / .115))
    return out


def premult_warp(image, matrix):
    """Transform premultiplied color to avoid dark/green interpolation fringes."""
    arr = np.asarray(image).astype(np.float32) / 255
    arr[..., :3] *= arr[..., 3:4]
    out = cv2.warpAffine(arr, matrix, image.size, flags=cv2.INTER_CUBIC,
                         borderMode=cv2.BORDER_CONSTANT)
    a = np.clip(out[..., 3:4], 0, 1)
    rgb = np.divide(out[..., :3], np.maximum(a, .001))
    return Image.fromarray((np.clip(np.concatenate((rgb, a), -1), 0, 1) * 255).astype(np.uint8))


class Actor:
    def __init__(self, root: Path, data: dict):
        self.data = data
        self.root = root
        source = cut_green(Image.open(root / data['source']))
        self.size = source.size
        self.w, self.h = source.size
        self.pad = 48
        self.original = source
        yy, xx = np.where(np.asarray(source)[..., 3] > 128)
        if not len(yy):
            raise ValueError(f"Empty actor: {data['source']}")
        self.top = int(yy.min())
        self.foot = int(yy.max())
        self.height = self.foot - self.top + 1
        self.anchor_x = data['anchor'][0] * self.w
        self.phase = data.get('phase', 0)
        self.head_mask = self.mask(data['head'])
        self.arm_mask = self.mask(data.get('forearm', []))
        self.head_mask[self.arm_mask > 128] = 0
        # Overlap only at the neck joint, not around the face silhouette:
        # moving a retained outline would duplicate ears/cap next to the head.
        hm_inner = self.head_mask.copy()
        neck_row = max(0, round(data['neck'][1] * self.h) - 12)
        hm_inner[neck_row:] = cv2.erode(self.head_mask, np.ones((13, 13), np.uint8))[neck_row:]
        am_inner = cv2.erode(self.arm_mask, np.ones((9, 9), np.uint8))
        body_mask = 255 - np.maximum(hm_inner, am_inner)
        body_source = np.array(source)
        body_source[..., 3] = np.minimum(body_source[..., 3], body_mask)
        self.body_source = Image.fromarray(body_source)
        self.body = self.layer(self.body_source, np.full(self.head_mask.shape, 255, np.uint8))
        self.arm = self.layer(source, self.arm_mask)
        self.head = self.layer(source, self.head_mask)
        self.closed_head = self.closed_eyes(source)
        yy, xx = np.mgrid[:self.h, :self.w].astype(np.float32)
        self.xx, self.yy = xx, yy
        self.fields = []
        for cx, cy, radius, dx, dy in data.get('deform', []):
            weight = np.exp(-((xx - cx * self.w) ** 2 + (yy - cy * self.h) ** 2) /
                            (2 * (radius * self.h) ** 2))
            if data.get('reach'):
                # Restrict this small continuous hand deformation to the left
                # side; the cap/face must not be dragged by the wrist field.
                weight *= np.clip((.29 * self.w - xx) / (.12 * self.w), 0, 1)
            self.fields.append((weight, dx * self.w, dy * self.h))

    def mask(self, polygon):
        im = Image.new('L', self.size)
        if polygon:
            ImageDraw.Draw(im).polygon([(x * self.w, y * self.h) for x, y in polygon], fill=255)
        return np.array(im)

    def layer(self, source, mask):
        layer = np.array(source)
        layer[..., 3] = np.minimum(layer[..., 3], mask)
        out = Image.new('RGBA', (self.w + self.pad * 2, self.h + self.pad * 2))
        out.alpha_composite(Image.fromarray(layer), (self.pad, self.pad))
        return out

    def closed_eyes(self, source):
        rgb = np.array(source.convert('RGB'))
        if self.data.get('closed_reference'):
            reference = self.data['closed_reference']
            closed = np.array(Image.open(self.root / reference['source']).convert('RGB'))
            (ax, ay), (bx, by) = reference['eyes']
            targets = self.data['eyes']
            tx, ty = targets[0][0] * self.w, targets[0][1] * self.h
            ux, uy = targets[1][0] * self.w, targets[1][1] * self.h
            z = complex(ux - tx, uy - ty) / complex(bx - ax, by - ay)
            a, b = z.real, z.imag
            matrix = np.array([[a, -b, tx - a * ax + b * ay],
                               [b, a, ty - b * ax - a * ay]], np.float32)
            aligned = cv2.warpAffine(closed, matrix, self.size)
            patch_mask = np.zeros((self.h, self.w), np.uint8)
            for x, y, rw, rh in targets:
                cv2.ellipse(patch_mask, (round(x * self.w), round(y * self.h)),
                            (round(rw * self.w * 1.25), round(rh * self.h * 1.4)),
                            0, 0, 360, 255, -1)
            weight = cv2.GaussianBlur(patch_mask, (0, 0), 2).astype(float)[..., None] / 255
            fixed = np.clip(rgb * (1 - weight) + aligned * weight, 0, 255).astype(np.uint8)
            out = Image.fromarray(fixed).convert('RGBA')
            out.putalpha(source.getchannel('A'))
            return self.layer(out, self.head_mask)
        mask = np.zeros((self.h, self.w), np.uint8)
        for x, y, rw, rh in self.data.get('eyes', []):
            cv2.ellipse(mask, (round(x * self.w), round(y * self.h)),
                        (round(rw * self.w), round(rh * self.h)), 0, 0, 360, 255, -1)
        if not mask.any():
            return self.head
        # Reconstruct skin under closed lids from the same source, not a new face.
        fixed = cv2.inpaint(rgb, mask, 7, cv2.INPAINT_TELEA)
        out = Image.fromarray(fixed).convert('RGBA')
        out.putalpha(source.getchannel('A'))
        d = ImageDraw.Draw(out)
        for x, y, rw, rh in self.data.get('eyes', []):
            cx, cy, rx, ry = x * self.w, y * self.h, rw * self.w, rh * self.h
            d.arc((cx - rx * .9, cy - ry * .65, cx + rx * .9, cy + ry * .95),
                  190, 350, fill=(91, 51, 36, 255), width=max(2, round(self.w * .004)))
        return self.layer(out, self.head_mask)

    def local_motion(self, source, t, intensity, reach=0.):
        if not self.fields or intensity == 0:
            return source
        arr = np.array(source).astype(np.float32) / 255
        arr[..., :3] *= arr[..., 3:4]
        mx, my = self.xx.copy(), self.yy.copy()
        for i, (weight, dx, dy) in enumerate(self.fields):
            amount = (reach / 15 if self.data.get('reach') else
                      math.sin(t * (3.4 if self.data.get('stroke') else 2.1) + i * 1.4) * intensity)
            mx -= weight * dx * amount
            my -= weight * dy * amount
        warped = cv2.remap(arr, mx, my, cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT)
        a = np.clip(warped[..., 3:4], 0, 1)
        rgb = warped[..., :3] / np.maximum(a, .001)
        return Image.fromarray((np.clip(np.concatenate((rgb, a), -1), 0, 1) * 255).astype(np.uint8))

    def render(self, t, *, head=0., arm=0., gesture=1., blink=True):
        # Character acting on twos, camera/lights on ones: sitcom-style timing.
        qt = math.floor(t * 12 + 1e-6) / 12
        if self.data.get('reach'):
            # The fingertip overlaps the ear in this drawing. Keep one continuous
            # surface here instead of splitting that occlusion into duplicate ears.
            src = self.local_motion(self.original, qt, gesture, reach=arm)
            return self.layer(src, np.full(self.head_mask.shape, 255, np.uint8))
        if self.fields:
            # Separate BEFORE remapping: otherwise displaced ears/head pixels can
            # escape the mask and appear as a duplicate beside the fixed head.
            src = self.local_motion(self.body_source, qt, gesture, reach=arm)
            body = self.layer(src, np.full(self.head_mask.shape, 255, np.uint8))
        else:
            body = self.body.copy()
        amount = blink_at(qt, self.phase) if blink else 0
        # A held closed-lid drawing reads cleanly on twos. Dissolving an open
        # iris into skin makes ghost eyes instead of an occluding eyelid.
        head_img = self.closed_head if amount > .4 else self.head
        nx, ny = self.data['neck']
        angle = head + .45 * math.sin(qt * 1.15 + self.phase)
        pivot = (nx * self.w + self.pad, ny * self.h + self.pad)
        head_img = premult_warp(head_img, cv2.getRotationMatrix2D(pivot, angle, 1.0))
        body.alpha_composite(head_img)
        if self.data.get('forearm'):
            ax, ay = self.data['elbow']
            pivot = (ax * self.w + self.pad, ay * self.h + self.pad)
            arm_img = premult_warp(self.arm, cv2.getRotationMatrix2D(pivot, arm, 1.0))
            # Foreground hand must stay above cap/hair in depth order.
            body.alpha_composite(arm_img)
        return body
