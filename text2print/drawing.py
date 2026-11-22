"""A dimensioned drawing of a part, measured off the meshes that go in the project. Make one for anything that has to
fit something: it shows the person the numbers as built (and which were theirs), before anything is printed. A U band
went through six rebuilds on a wrong measurement that one drawing exposed (Nov 2026)."""
import numpy as np

INK, RED, PAPER = "#1A1A1A", "#C0392B", "#FAF9F5"


def dimension_sheet(parts, path, dims=(), title=None, dpi=110):
    """parts: [(mesh, '#hex')] in the pose they print. Draws a top view (x right, y up) and a front view (x right,
    z up) with the overall length, width and height. dims adds your own: (view, (a0, b0), (a1, b1), label) with
    view "top" (a, b = x, y) or "front" (a, b = x, z), e.g. ("top", (-25, 0), (25, 0), "50.0 hole").
    -> the three overall sizes (x, y, z) in mm."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    V = np.vstack([np.asarray(m.vertices) for m, _ in parts]); lo, hi = V.min(0), V.max(0); L, W, H = hi - lo
    pad = 0.09 * max(L, W, H) + 4
    fig, ax = plt.subplots(2, 1, figsize=(11, 11 * (W + H + 6 * pad) / (L + 4 * pad) + 0.6), facecolor=PAPER,
                           gridspec_kw={"height_ratios": [W + 3 * pad, H + 3 * pad]})

    def draw(a, i, j, order):
        for mesh, col in order:
            a.add_collection(PolyCollection(np.asarray(mesh.vertices)[np.asarray(mesh.faces)][:, :, [i, j]],
                                            facecolors=_soft(col), edgecolors="none"))
        a.set_aspect("equal"); a.axis("off")

    def dim(a, p, q, text):
        a.annotate("", xy=p, xytext=q, arrowprops=dict(arrowstyle="<->", color=RED, lw=1.4))
        a.text((p[0] + q[0]) / 2, (p[1] + q[1]) / 2, text, color=RED, fontsize=12, ha="center", va="center",
               bbox=dict(fc=PAPER, ec="none", pad=1.5))

    top, front = ax
    by_height = sorted(parts, key=lambda mc: float(np.asarray(mc[0].vertices)[:, 2].max()))      # painter: tallest last
    draw(top, 0, 1, by_height); draw(front, 0, 2, parts)
    top.set_title((title + "  ·  " if title else "") + "top view", fontsize=12, loc="left", color=INK)
    front.set_title("front view, as it prints", fontsize=12, loc="left", color=INK)
    top.set_xlim(lo[0] - 2 * pad, hi[0] + 2 * pad); top.set_ylim(lo[1] - 2 * pad, hi[1] + pad)
    front.set_xlim(lo[0] - 2 * pad, hi[0] + 2 * pad); front.set_ylim(lo[2] - 2 * pad, hi[2] + pad)
    dim(top, (lo[0], lo[1] - pad), (hi[0], lo[1] - pad), f"{L:.1f}")
    dim(top, (hi[0] + pad, lo[1]), (hi[0] + pad, hi[1]), f"{W:.1f}")
    dim(front, (hi[0] + pad, lo[2]), (hi[0] + pad, hi[2]), f"{H:.1f}")
    for view, p, q, label in dims:
        dim(top if view == "top" else front, tuple(p), tuple(q), label)
    fig.tight_layout(); fig.savefig(path, dpi=dpi, facecolor=PAPER); plt.close(fig)
    return float(L), float(W), float(H)


def _soft(col):
    """White parts would vanish on the paper: draw them a shade darker."""
    c = col.lstrip("#"); r, g, b = (int(c[k:k + 2], 16) for k in (0, 2, 4))
    return "#DDD9CE" if min(r, g, b) > 225 else col
