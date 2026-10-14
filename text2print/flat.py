"""Flat lithophane tiles, printed face-down and lit from behind.

  litho      one colour (white/natural): thickness 0.8 mm (light) to 3.0 mm (dark) per pixel
  cmyk       full colour on 4 AMS slots (Bambu's CMYK bundle: cyan, magenta, yellow + white). From the face up each
             pixel stacks cyan, magenta and yellow layers as thick as that ink is needed (0 - 0.6 mm), then white
             as thick as the pixel is dark (0.6 - 2.4 mm). Light through the stack mixes the colours.

Geometry is voxel columns quantised to the print layer (pixels ~ one line wide), so every colour boundary sits on
a layer and each colour is a watertight part. A 3 mm white frame keeps the tile flat and strong."""
import math

import numpy as np
import trimesh

STYLES = {
    "litho": dict(name="Lithophane", blurb="One colour; the picture appears when it's backlit"),
    "cmyk":  dict(name="Colour lithophane", blurb="Cyan, magenta, yellow and white mix into a full-colour image"),
}
CMYK = ["#0086D6", "#EC008C", "#F4EE2A", "#FFFFFF"]


def _image(path, w_px, h_px, picture):
    from PIL import Image
    if path:
        im = Image.open(path).convert("RGB")
    else:
        im = _builtin(picture)
    im = im.resize((w_px, h_px), Image.LANCZOS)
    return np.asarray(im, float) / 255.0                          # rows top -> bottom


def _builtin(picture):
    """Built-in colour picture: a sunset over hills, or a two-tone flame."""
    from PIL import Image
    W, H = 400, 300
    y, x = np.mgrid[0:H, 0:W].astype(float); y /= H; x /= W
    sky = np.stack([0.98 - 0.2 * y, 0.55 + 0.3 * y, 0.35 + 0.55 * y], -1)          # warm top -> cool horizon
    sun = np.hypot(x - 0.62, (y - 0.55) * 0.75) < 0.13
    sky[sun] = [1.0, 0.86, 0.35]
    hills = y > 0.62 + 0.08 * np.sin(x * 9) + 0.04 * np.sin(x * 23)
    sky[hills] = np.stack([0.15 + 0.1 * x, 0.32 + 0.2 * (1 - y), 0.22 + 0.05 * x], -1)[hills]
    return Image.fromarray((np.clip(sky, 0, 1) * 255).astype(np.uint8))


def _slab(z_lo, z_hi, px, x0, y0):
    """Closed solid between two height fields given per pixel ([ix, iy]); vertex heights average the 4 pixels
    around each grid corner. Zero thickness becomes a 0.002 mm hairline the slicer never samples."""
    def corners(a):
        p = np.pad(a, 1, mode="edge")
        return 0.25 * (p[:-1, :-1] + p[1:, :-1] + p[:-1, 1:] + p[1:, 1:])
    lo, hi = corners(z_lo), corners(z_hi)
    hi = np.maximum(hi, lo + 0.002)
    nx1, ny1 = lo.shape
    xs = x0 + np.arange(nx1) * px; ys = y0 + np.arange(ny1) * px
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    top = np.column_stack([X.ravel(), Y.ravel(), hi.ravel()]); bot = np.column_stack([X.ravel(), Y.ravel(), lo.ravel()])
    V = np.vstack([top, bot]); off = len(top)
    ii, jj = np.meshgrid(np.arange(nx1 - 1), np.arange(ny1 - 1), indexing="ij"); ii, jj = ii.ravel(), jj.ravel()
    a_ = ii * ny1 + jj; b_ = (ii + 1) * ny1 + jj; c_ = (ii + 1) * ny1 + jj + 1; d_ = ii * ny1 + jj + 1
    F = [np.column_stack([a_, b_, c_]), np.column_stack([a_, c_, d_]),                    # top
         np.column_stack([a_ + off, c_ + off, b_ + off]), np.column_stack([a_ + off, d_ + off, c_ + off])]   # bottom
    ring = ([(i, 0) for i in range(nx1)] + [(nx1 - 1, j) for j in range(1, ny1)] +
            [(i, ny1 - 1) for i in range(nx1 - 2, -1, -1)] + [(0, j) for j in range(ny1 - 2, 0, -1)])
    ids = [i * ny1 + j for i, j in ring]
    for k in range(len(ids)):
        p_, q_ = ids[k], ids[(k + 1) % len(ids)]
        F.append(np.array([[p_, q_ + off, q_], [p_, p_ + off, q_ + off]]))
    m = trimesh.Trimesh(V, np.vstack(F), process=True)
    trimesh.repair.fix_normals(m)
    if m.volume < 0:
        m.invert()
    return m


def _trim(mesh, fp_poly, h):
    import manifold3d as m3d
    from .meshops import manifold_to_trimesh
    cs = m3d.CrossSection([np.asarray(fp_poly.exterior.coords[:-1]).tolist()])
    prism = m3d.Manifold.extrude(cs, h + 2).translate([0, 0, -1])
    body = m3d.Manifold(m3d.Mesh(vert_properties=np.asarray(mesh.vertices, np.float32), tri_verts=np.asarray(mesh.faces, np.int32)))
    return manifold_to_trimesh(body ^ prism, min_volume=0.0)


def build(shape, v, nz, style="litho", image=None, picture="sunset", draft=False, options=None):
    W = v["width"]; D = v.get("depth", v["width"] * 1.1547)
    fp = shape.footprint(v)
    lh = 0.12 if nz.size <= 0.4 else round(nz.size * 0.3, 2)
    px = max(nz.line_w, 0.45) * (2.5 if draft else 1.0)
    nx, ny = int(W / px), int(D / px)
    x0, y0 = -nx * px / 2, -ny * px / 2
    xc = x0 + (np.arange(nx) + 0.5) * px; yc = y0 + (np.arange(ny) + 0.5) * px
    X, Y = np.meshgrid(xc, yc, indexing="ij")
    inside = fp(X, Y) <= 0
    frame = fp(X, Y) > -3.0                                       # 3 mm solid frame
    use_lib = bool(options) and bool(options.get("image") or (options.get("picture") or "sunset") != "sunset")
    if use_lib:
        from PIL import Image
        from . import pictures
        im = pictures.colour_image(options, W / D).resize((nx, ny), Image.LANCZOS)
        img = (np.asarray(im, float) / 255.0)[::-1].transpose(1, 0, 2)
    else:
        img = _image(image, nx, ny, picture)[::-1].transpose(1, 0, 2)  # -> [ix, iy, rgb], y up
    lum = img.mean(axis=2)
    q = lambda t: np.round(t / lh).astype(int)                     # thickness -> whole layers
    from shapely.geometry import Polygon
    from shapely.geometry.polygon import orient
    import skimage.measure as skm
    # footprint outline polygon (for the trim): contour of the sdf at 0 on a fine grid
    fx = np.linspace(x0 - 2, -x0 + 2, 400); fy = np.linspace(y0 - 2, -y0 + 2, 400)
    FX, FY = np.meshgrid(fx, fy, indexing="ij")
    cont = max(skm.find_contours(fp(FX, FY), 0.0), key=len)
    poly = orient(Polygon(np.column_stack([np.interp(cont[:, 0], np.arange(400), fx), np.interp(cont[:, 1], np.arange(400), fy)])).buffer(0), 1.0)
    if style == "litho":
        t = np.where(frame, 3.0, 3.0 - 2.2 * lum)
        hi = q(t) * lh
        m = _trim(_slab(np.zeros_like(hi), hi, px, x0, y0), poly, 4.0)
        light = np.exp(-1.1 * hi)[..., None] * np.array([1.0, 0.93, 0.80])   # warm lamp through white PLA
        return {3: m}, dict(layer_h=lh, pixel=px, layers=int(q(t).max()), swaps=0, transitions=[],
                            backlit=_backlit(light / light.max(), inside))
    # CMYK: subtractive ink per channel from RGB, under a white body
    c, m_, y_ = 1 - img[:, :, 0], 1 - img[:, :, 1], 1 - img[:, :, 2]
    k_ = np.minimum(np.minimum(c, m_), y_)
    ink = lambda a: q(0.6 * np.clip(a - 0.6 * k_, 0, 1))
    tc, tm, ty = ink(c), ink(m_), ink(y_)
    tw = q(0.6 + 1.8 * (1 - lum))
    zero = np.zeros_like(tc)
    tc, tm, ty = (np.where(frame, zero, t) for t in (tc, tm, ty)); tw = np.where(frame, q(3.0), tw)
    stack = [tc, tm, ty, tw]; base = zero.copy(); parts = {}; spans = []
    for slot, t in enumerate(stack):
        if (t > 0).any():
            parts[slot] = _trim(_slab(base * lh, (base + t) * lh, px, x0, y0), poly, (base + t).max() * lh + 1)
        spans.append((base.copy(), t)); base = base + t
    nzl = int(base.max()); seq = []
    for k in range(nzl):                                           # colours present in each layer; like the slicer,
        here = [slot for slot, (b0, t) in enumerate(spans) if (inside & (b0 <= k) & (k < b0 + t)).any()]
        if seq and seq[-1] in here:                                # start with the colour already loaded
            here.remove(seq[-1]); here.insert(0, seq[-1])
        seq.extend(here)
    transitions = [(a, b) for a, b in zip(seq, seq[1:]) if a != b]
    # backlit estimate: each ink passes its own colour per 0.4 mm, the white body dims evenly
    light = np.ones(tc.shape + (3,))
    for col, t in zip(CMYK[:3], (tc, tm, ty)):
        rgb = np.array([int(col[i:i + 2], 16) for i in (1, 3, 5)]) / 255.0
        light *= np.clip(rgb, 0.05, 1.0)[None, None, :] ** (t[..., None] * lh / 0.4)
    light *= np.exp(-0.9 * tw * lh)[..., None]
    return parts, dict(layer_h=lh, pixel=px, layers=nzl, swaps=len(transitions), transitions=transitions,
                       backlit=_backlit(light / max(light.max(), 1e-6), inside))


def _backlit(light, inside):
    """[ix, iy, rgb] light -> uint8 image rows top-down, outside the footprint transparent."""
    a = np.where(inside, 255, 0).astype(np.uint8)
    rgb = (np.clip(light, 0, 1) * 255).astype(np.uint8)
    return np.dstack([rgb, a])[:, ::-1].transpose(1, 0, 2)
