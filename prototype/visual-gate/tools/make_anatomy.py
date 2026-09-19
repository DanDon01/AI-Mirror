"""Generate the biometric object's geometry.

Produces, for both the heart and the brain:

  *.mesh  an indexed triangle mesh with normals, for the shaded solid
          that sits under the particles
  *.pts   a point cloud sampled on that same surface, carrying a normal,
          an ambient-occlusion term and a vessel/activity term

Both forms are signed distance fields, surfaced with marching cubes and
decimated by vertex clustering. The clouds share a point count and are
ordered consistently, so particle i morphs from heart to brain directly.

The occlusion term is what lets a viewer read topology in a point cloud:
without it every particle is equally lit and the form collapses into a
silhouette. The vessel term drives emissive coronary arteries on the
heart and activity regions in the brain.

    python tools/make_anatomy.py
"""

import os
import struct

import numpy as np
from skimage import measure

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "assets", "anatomy"))
POINTS = 52000
RNG = np.random.default_rng(20260919)


# ----------------------------------------------------------------------
# SDF primitives, vectorised over (N,3)
# ----------------------------------------------------------------------

def sd_ellipsoid(p, c, r):
    q = (p - np.asarray(c)) / np.asarray(r)
    k0 = np.linalg.norm(q, axis=1)
    k1 = np.linalg.norm(q / np.asarray(r), axis=1)
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-6)


def sd_capsule(p, a, b, r):
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    pa = p - a
    ba = b - a
    h = np.clip((pa @ ba) / (ba @ ba), 0.0, 1.0)[:, None]
    return np.linalg.norm(pa - ba * h, axis=1) - r


def sd_chain(p, nodes, k=0.04, subdiv=5):
    d = None
    for i in range(len(nodes) - 1):
        (a, ra), (b, rb) = nodes[i], nodes[i + 1]
        a = np.asarray(a, float)
        b = np.asarray(b, float)
        for s in range(subdiv):
            t0, t1 = s / subdiv, (s + 1) / subdiv
            seg = sd_capsule(p, a + (b - a) * t0, a + (b - a) * t1,
                             ra + (rb - ra) * (t0 + t1) * 0.5)
            d = seg if d is None else smin(d, seg, k)
    return d


def smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1 - h) + a * h - k * h * (1 - h)


def smax(a, b, k):
    h = np.clip(0.5 - 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1 - h) + a * h + k * h * (1 - h)


def ssub(d, cut, k):
    """Smooth subtraction: carve `cut` out of `d`."""
    return smax(d, -cut, k)


def gyroid(p, freq):
    x, y, z = (p * freq).T
    return np.sin(x) * np.cos(y) + np.sin(y) * np.cos(z) + np.sin(z) * np.cos(x)


def polyline_distance(p, pts):
    """Min distance from each point to a polyline."""
    best = None
    for i in range(len(pts) - 1):
        d = sd_capsule(p, pts[i], pts[i + 1], 0.0)
        best = d if best is None else np.minimum(best, d)
    return best


# ----------------------------------------------------------------------
# Heart
# ----------------------------------------------------------------------

# The anterior interventricular groove, which separates the ventricles
# and carries the left anterior descending artery. Carving it is most of
# what makes a heart read as a heart rather than a lumpy cone.
LAD = [(0.075, 0.215, 0.235), (0.025, 0.09, 0.245), (-0.02, -0.06, 0.225),
       (-0.07, -0.22, 0.185), (-0.115, -0.37, 0.135)]

# Right coronary artery, around the right atrioventricular groove.
RCA = [(0.125, 0.245, 0.135), (0.225, 0.215, 0.045), (0.265, 0.155, -0.075),
       (0.205, 0.085, -0.185), (0.075, 0.035, -0.235)]

# Circumflex, around the left atrioventricular groove.
CFX = [(-0.02, 0.255, 0.115), (-0.145, 0.235, 0.045), (-0.225, 0.175, -0.075),
       (-0.215, 0.105, -0.175)]


def sdf_heart(p):
    # Ventricular mass: a cone tapering to the apex, tilted down and to
    # the left the way a real heart sits in the chest.
    vent = sd_chain(p, [
        ((0.045, 0.235, -0.015), 0.255),
        ((0.025, 0.115, 0.010), 0.278),
        ((-0.005, -0.030, 0.030), 0.262),
        ((-0.050, -0.175, 0.045), 0.210),
        ((-0.095, -0.310, 0.055), 0.138),
        ((-0.140, -0.425, 0.060), 0.062),
        ((-0.170, -0.495, 0.062), 0.016),
    ], k=0.05)

    # Right ventricle bulging across the anterior surface.
    rv = sd_ellipsoid(p, (0.175, 0.055, 0.135), (0.225, 0.255, 0.200))
    d = smin(vent, rv, 0.075)

    # Atria above the atrioventricular junction.
    ra = sd_ellipsoid(p, (0.215, 0.335, -0.010), (0.170, 0.135, 0.180))
    d = smin(d, ra, 0.055)
    la = sd_ellipsoid(p, (-0.165, 0.330, -0.115), (0.160, 0.125, 0.165))
    d = smin(d, la, 0.055)

    # Auricles: the two ear-like flaps. Small, but very recognisable.
    r_aur = sd_ellipsoid(p, (0.165, 0.395, 0.135), (0.105, 0.070, 0.095))
    d = smin(d, r_aur, 0.035)
    l_aur = sd_ellipsoid(p, (-0.190, 0.360, 0.075), (0.090, 0.060, 0.080))
    d = smin(d, l_aur, 0.035)

    # Aorta: rises, arches back and left, gives off three branches, then
    # descends. The arch is the single most identifiable feature.
    aorta = sd_chain(p, [
        ((0.030, 0.290, -0.020), 0.088),
        ((0.045, 0.430, -0.030), 0.080),
        ((0.030, 0.545, -0.070), 0.075),
        ((-0.055, 0.625, -0.130), 0.068),
        ((-0.150, 0.590, -0.190), 0.062),
        ((-0.165, 0.440, -0.225), 0.056),
        ((-0.160, 0.300, -0.240), 0.050),
    ], k=0.025)
    d = smin(d, aorta, 0.030)

    for base, tip, r in (((0.010, 0.575, -0.085), (0.035, 0.700, -0.085), 0.030),
                         ((-0.045, 0.615, -0.120), (-0.055, 0.725, -0.130), 0.025),
                         ((-0.100, 0.615, -0.155), (-0.135, 0.715, -0.170), 0.025)):
        d = smin(d, sd_capsule(p, base, tip, r), 0.020)

    # Pulmonary trunk: rises in front of the aorta, then bifurcates.
    trunk = sd_chain(p, [
        ((0.140, 0.300, 0.140), 0.082),
        ((0.105, 0.430, 0.130), 0.076),
        ((0.045, 0.520, 0.085), 0.070),
    ], k=0.025)
    d = smin(d, trunk, 0.030)
    d = smin(d, sd_capsule(p, (0.045, 0.520, 0.085), (-0.135, 0.545, 0.000), 0.048), 0.022)
    d = smin(d, sd_capsule(p, (0.045, 0.520, 0.085), (0.205, 0.505, 0.010), 0.044), 0.022)

    # Venae cavae entering the right atrium.
    d = smin(d, sd_capsule(p, (0.250, 0.360, -0.055), (0.265, 0.585, -0.080), 0.055), 0.028)
    d = smin(d, sd_capsule(p, (0.235, 0.215, -0.105), (0.250, 0.060, -0.145), 0.052), 0.028)

    # Carve the grooves. Everything above is mass; these are what give
    # the surface its structure.
    lad_groove = polyline_distance(p, LAD) - 0.032
    d = ssub(d, lad_groove, 0.022)
    rca_groove = polyline_distance(p, RCA) - 0.030
    d = ssub(d, rca_groove, 0.022)
    cfx_groove = polyline_distance(p, CFX) - 0.028
    d = ssub(d, cfx_groove, 0.022)

    # Fine muscular surface texture.
    d -= 0.004 * np.abs(gyroid(p, 26.0))
    return d


def heart_vessel_field(p):
    """Emissive coronary tree: proximity to the artery polylines."""
    d = np.minimum(np.minimum(polyline_distance(p, LAD),
                              polyline_distance(p, RCA)),
                   polyline_distance(p, CFX))
    return np.exp(-np.maximum(d - 0.018, 0.0) / 0.030)


# ----------------------------------------------------------------------
# Brain
# ----------------------------------------------------------------------

def sdf_brain(p):
    # Cerebral hemispheres, longer front-to-back than they are wide.
    lh = sd_ellipsoid(p, (-0.150, 0.070, 0.010), (0.255, 0.275, 0.365))
    rh = sd_ellipsoid(p, (0.150, 0.070, 0.010), (0.255, 0.275, 0.365))
    d = smin(lh, rh, 0.045)

    # Temporal lobes. Without them the brain is an ovoid; with them, and
    # with the lateral sulcus below, the side profile is unmistakable.
    for sx in (-1.0, 1.0):
        temporal = sd_ellipsoid(p, (sx * 0.225, -0.135, 0.065),
                                (0.135, 0.115, 0.215))
        d = smin(d, temporal, 0.050)

    # Frontal pole slightly narrower, occipital slightly broader.
    d = smax(d, sd_ellipsoid(p, (0.0, 0.03, 0.02), (0.44, 0.40, 0.44)) - 0.02, 0.06)

    # Lateral (Sylvian) sulcus: the deep cleft above each temporal lobe.
    for sx in (-1.0, 1.0):
        sulcus = sd_chain(p, [
            ((sx * 0.300, -0.020, 0.185), 0.040),
            ((sx * 0.330, -0.045, 0.030), 0.045),
            ((sx * 0.290, -0.055, -0.135), 0.038),
        ], k=0.02)
        d = ssub(d, sulcus, 0.030)

    # Longitudinal fissure between the hemispheres.
    fissure = np.maximum(np.abs(p[:, 0]) - 0.022, -(p[:, 1] - 0.02))
    d = ssub(d, fissure, 0.028)

    # Cerebellum, tucked under the occipital lobes.
    cb = sd_ellipsoid(p, (0.0, -0.235, -0.250), (0.235, 0.130, 0.145))
    cb -= 0.020 * np.abs(gyroid(p, 30.0))   # finer foliation than cortex
    d = smin(d, cb, 0.045)

    # Brainstem.
    stem = sd_chain(p, [
        ((0.0, -0.140, -0.075), 0.072),
        ((0.0, -0.290, -0.055), 0.060),
        ((0.0, -0.430, -0.030), 0.048),
    ], k=0.03)
    d = smin(d, stem, 0.040)

    # Cortical folding.
    d -= 0.026 * np.abs(gyroid(p, 11.0))
    d -= 0.009 * np.abs(gyroid(p, 23.0))
    return d


def brain_vessel_field(p):
    """Activity regions: broad, smooth, used for gentle illumination."""
    f = 0.5 + 0.5 * np.sin(p[:, 2] * 7.0 + p[:, 1] * 4.0)
    g = 0.5 + 0.5 * np.sin(p[:, 0] * 9.0 - p[:, 2] * 5.0 + 1.7)
    return np.clip(f * 0.6 + g * 0.6, 0.0, 1.0)


# ----------------------------------------------------------------------
# Surfacing
# ----------------------------------------------------------------------

def eval_grid(fn, res, extent):
    """Evaluate an SDF over a grid, in slabs to bound peak memory."""
    axis = np.linspace(-extent, extent, res, dtype=np.float32)
    field = np.empty((res, res, res), dtype=np.float32)
    ys, zs = np.meshgrid(axis, axis, indexing="ij")
    flat = np.stack([np.zeros(ys.size, np.float32), ys.ravel(), zs.ravel()], 1)
    for i, x in enumerate(axis):
        flat[:, 0] = x
        field[i] = fn(flat).reshape(res, res).astype(np.float32)
    return field, axis


def cluster_decimate(verts, faces, cell):
    """Vertex-clustering decimation: snap to a grid, weld, drop slivers."""
    keys = np.floor(verts / cell).astype(np.int64)
    _, inverse, counts = np.unique(keys, axis=0, return_inverse=True,
                                   return_counts=True)
    n = counts.shape[0]
    summed = np.zeros((n, 3))
    np.add.at(summed, inverse, verts)
    new_verts = summed / counts[:, None]
    new_faces = inverse[faces]
    ok = ((new_faces[:, 0] != new_faces[:, 1]) &
          (new_faces[:, 1] != new_faces[:, 2]) &
          (new_faces[:, 0] != new_faces[:, 2]))
    return new_verts, new_faces[ok]


def vertex_normals(verts, faces):
    normals = np.zeros_like(verts)
    tri = verts[faces]
    face_n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    for col in range(3):
        np.add.at(normals, faces[:, col], face_n)
    length = np.linalg.norm(normals, axis=1, keepdims=True)
    return normals / np.maximum(length, 1e-9)


def surface(fn, res, extent, cell):
    field, axis = eval_grid(fn, res, extent)
    verts, faces, _, _ = measure.marching_cubes(field, 0.0)
    step = axis[1] - axis[0]
    verts = verts * step - extent
    verts, faces = cluster_decimate(verts, faces, cell)
    return verts, faces, vertex_normals(verts, faces)


def sdf_normals(fn, p, eps=1.5e-3):
    g = np.empty_like(p)
    for axis in range(3):
        step = np.zeros(3)
        step[axis] = eps
        g[:, axis] = fn(p + step) - fn(p - step)
    return g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-9)


def occlusion(fn, p, n):
    """Cheap ambient occlusion straight off the field: on a flat surface
    the distance at offset d is d, and in a crevice it is less."""
    total = np.zeros(len(p))
    weight = 0.0
    for dist in (0.012, 0.028, 0.055, 0.095):
        sampled = fn(p + n * dist)
        total += (sampled / dist) * (1.0 / dist)
        weight += 1.0 / dist
    return np.clip(total / weight, 0.0, 1.0) ** 1.3


def sample_points(fn, verts, faces, count):
    """Area-weighted sampling over the mesh, then projected back onto the
    exact isosurface so points sit on the surface, not the decimation."""
    tri = verts[faces]
    area = 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0],
                                         tri[:, 2] - tri[:, 0]), axis=1)
    pick = RNG.choice(len(faces), size=count, p=area / area.sum())
    u = RNG.random((count, 1))
    v = RNG.random((count, 1))
    over = (u + v) > 1
    u[over] = 1 - u[over]
    v[over] = 1 - v[over]
    a, b, c = tri[pick, 0], tri[pick, 1], tri[pick, 2]
    p = a + (b - a) * u + (c - a) * v
    for _ in range(4):
        p -= sdf_normals(fn, p) * fn(p)[:, None]
    return p


def order_for_morph(points, extra):
    """Sort both clouds the same way so particle i is in a comparable
    place on each form. Unsorted, the morph reads as static."""
    v = points - points.mean(axis=0)
    theta = np.arctan2(v[:, 0], v[:, 2])
    phi = np.arctan2(v[:, 1], np.linalg.norm(v[:, [0, 2]], axis=1))
    key = np.round(phi * 26).astype(int) * 100000 + np.round(theta * 26).astype(int)
    order = np.argsort(key, kind="stable")
    return points[order], [e[order] for e in extra]


def normalise(points, height=1.0, centre=None):
    centre = points.mean(axis=0) if centre is None else centre
    scale = height / (points[:, 1].max() - points[:, 1].min())
    return (points - centre) * scale, centre, scale


# ----------------------------------------------------------------------
# Output
# ----------------------------------------------------------------------

def write_mesh(path, verts, normals, faces):
    with open(path, "wb") as fh:
        fh.write(struct.pack("<II", len(verts), len(faces)))
        inter = np.concatenate([verts, normals], axis=1).astype("<f4")
        fh.write(inter.tobytes())
        fh.write(faces.astype("<u4").tobytes())
    print(f"  {os.path.basename(path):12s} {len(verts):6d} verts  "
          f"{len(faces):6d} tris  {os.path.getsize(path)//1024:5d} KB")


def write_points(path, pos, nrm, ao, vessel):
    with open(path, "wb") as fh:
        fh.write(struct.pack("<I", len(pos)))
        payload = np.concatenate(
            [pos, nrm, ao[:, None], vessel[:, None]], axis=1).astype("<f4")
        fh.write(payload.tobytes())
    print(f"  {os.path.basename(path):12s} {len(pos):6d} pts   "
          f"{os.path.getsize(path)//1024:5d} KB")


def preview(name, points, shade, size=430):
    from PIL import Image
    img = Image.new("L", (size * 2, size), 0)
    px = img.load()
    for ax, off in ((0, 0), (2, size)):
        a, b = points[:, ax], points[:, 1]
        sx = ((a - a.min()) / np.ptp(a) * (size - 40) + 20 + off).astype(int)
        sy = ((1 - (b - b.min()) / np.ptp(b)) * (size - 40) + 20).astype(int)
        val = (shade * 165 + 18).astype(int)
        for x, y, v in zip(sx, sy, val):
            if 0 <= x < size * 2 and 0 <= y < size:
                px[x, y] = min(255, px[x, y] + int(v))
    img.save(os.path.join(OUT, f"_preview_{name}.png"))


def build(name, fn, vessel_fn, res, extent, cell):
    print(f"{name}: surfacing at {res}^3")
    verts, faces, normals = surface(fn, res, extent, cell)
    print(f"  marching cubes -> {len(verts)} verts, {len(faces)} tris")

    pts = sample_points(fn, verts, faces, POINTS)
    nrm = sdf_normals(fn, pts)
    ao = occlusion(fn, pts, nrm)
    ves = vessel_fn(pts)

    # One normalisation for both mesh and cloud, or they will not align.
    pts, centre, scale = normalise(pts)
    verts = (verts - centre) * scale

    pts, (nrm, ao, ves) = order_for_morph(pts, [nrm, ao, ves])

    write_mesh(os.path.join(OUT, f"{name}.mesh"), verts, normals, faces)
    write_points(os.path.join(OUT, f"{name}.pts"), pts, nrm, ao, ves)
    preview(name, pts, ao)
    return pts.shape[0]


def main():
    os.makedirs(OUT, exist_ok=True)
    build("heart", sdf_heart, heart_vessel_field, res=176, extent=0.86, cell=0.0105)
    build("brain", sdf_brain, brain_vessel_field, res=176, extent=0.80, cell=0.0105)
    print(f"previews in {OUT}")


if __name__ == "__main__":
    main()
