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
        d = smin(d, sd_ellipsoid(p, (sx * 0.225, -0.135, 0.065),
                                 (0.135, 0.115, 0.215)), 0.050)

    # Frontal pole slightly narrower, occipital slightly broader.
    d = smax(d, sd_ellipsoid(p, (0.0, 0.03, 0.02), (0.44, 0.40, 0.44)) - 0.02, 0.06)

    # Lateral (Sylvian) sulcus: the deep cleft above each temporal lobe.
    for sx in (-1.0, 1.0):
        d = ssub(d, sd_chain(p, [
            ((sx * 0.300, -0.020, 0.185), 0.040),
            ((sx * 0.330, -0.045, 0.030), 0.045),
            ((sx * 0.290, -0.055, -0.135), 0.038),
        ], k=0.02), 0.030)

    # Central sulcus, running down and forward across each hemisphere.
    # It is the landmark that separates frontal from parietal lobe and
    # the one a viewer reads as "brain" fastest after the fissure.
    for sx in (-1.0, 1.0):
        d = ssub(d, sd_chain(p, [
            ((sx * 0.050, 0.325, -0.020), 0.028),
            ((sx * 0.155, 0.255, 0.030), 0.030),
            ((sx * 0.245, 0.135, 0.080), 0.028),
            ((sx * 0.285, 0.025, 0.105), 0.024),
        ], k=0.018), 0.024)

    # Parieto-occipital sulcus, at the back.
    for sx in (-1.0, 1.0):
        d = ssub(d, sd_chain(p, [
            ((sx * 0.035, 0.295, -0.235), 0.025),
            ((sx * 0.125, 0.195, -0.290), 0.025),
            ((sx * 0.175, 0.080, -0.300), 0.023),
        ], k=0.018), 0.022)

    # Longitudinal fissure between the hemispheres.
    fissure = np.maximum(np.abs(p[:, 0]) - 0.022, -(p[:, 1] - 0.02))
    d = ssub(d, fissure, 0.028)

    # Cerebellum. Its folia are fine parallel transverse ridges, not the
    # branching convolution of cortex, and reproducing that difference is
    # most of what distinguishes it at a glance.
    cb = sd_ellipsoid(p, (0.0, -0.235, -0.250), (0.235, 0.130, 0.145))
    cb -= 0.014 * np.abs(np.sin(p[:, 1] * 105.0))
    d = smin(d, cb, 0.045)

    # Brainstem.
    d = smin(d, sd_chain(p, [
        ((0.0, -0.140, -0.075), 0.072),
        ((0.0, -0.290, -0.055), 0.060),
        ((0.0, -0.430, -0.030), 0.048),
    ], k=0.03), 0.040)

    # Cortical folding. Stretched along the anterior-posterior axis so
    # the gyri elongate into ridges rather than reading as isotropic
    # lumps, and deeper than before so the occlusion term has something
    # to bite on.
    q = p * np.array([1.0, 1.30, 0.72])
    d -= 0.033 * np.abs(gyroid(q, 10.5))
    d -= 0.011 * np.abs(gyroid(p, 22.0))
    return d


# White-matter bundles. Not a literal tractogram, but built from the
# real routes: commissural fibres crossing the midline, projection
# fibres fanning up from the brainstem, and association fibres running
# front to back within a hemisphere.

def _bezier(controls, n):
    t = np.linspace(0.0, 1.0, n)[:, None]
    p0, p1, p2, p3 = controls
    return ((1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1
            + 3 * (1 - t) * t ** 2 * p2 + t ** 3 * p3)


def brain_fibres(count=820, samples=26):
    """Curved bundles, pulled inside the surface so they read as
    interior structure seen through a translucent shell."""
    rng = np.random.default_rng(77)
    paths = np.empty((count, samples, 3))
    bundle = np.empty(count)

    for i in range(count):
        kind = i % 4
        j = rng.normal(0.0, 1.0, 3) * 0.035

        if kind == 0:
            # Corpus callosum: arches from one hemisphere to the other.
            z = rng.uniform(-0.24, 0.26)
            reach = rng.uniform(0.16, 0.27)
            p0 = np.array([-reach, 0.075, z]) + j
            p1 = np.array([-reach * 0.45, 0.235, z * 0.9])
            p2 = np.array([reach * 0.45, 0.235, z * 0.9])
            p3 = np.array([reach, 0.075, z]) + j
        elif kind == 1:
            # Corona radiata: fans up from the stem to the cortex.
            sx = 1.0 if rng.random() > 0.5 else -1.0
            tx = sx * rng.uniform(0.07, 0.30)
            tz = rng.uniform(-0.26, 0.28)
            p0 = np.array([0.0, -0.215, -0.045]) + j * 0.4
            p1 = np.array([sx * 0.05, -0.090, -0.020])
            p2 = np.array([tx * 0.7, 0.110, tz * 0.6])
            p3 = np.array([tx, 0.265, tz]) + j
        elif kind == 2:
            # Association fibres: front to back within one hemisphere.
            sx = 1.0 if rng.random() > 0.5 else -1.0
            y = rng.uniform(-0.09, 0.19)
            x = sx * rng.uniform(0.10, 0.27)
            p0 = np.array([x, y, 0.285]) + j
            p1 = np.array([x * 1.05, y + 0.07, 0.10])
            p2 = np.array([x * 1.05, y + 0.05, -0.12])
            p3 = np.array([x * 0.85, y - 0.02, -0.275]) + j
        else:
            # Cerebellar peduncles.
            sx = 1.0 if rng.random() > 0.5 else -1.0
            p0 = np.array([0.0, -0.250, -0.060]) + j * 0.3
            p1 = np.array([sx * 0.055, -0.235, -0.130])
            p2 = np.array([sx * 0.130, -0.225, -0.200])
            p3 = np.array([sx * rng.uniform(0.06, 0.19), -0.245,
                           -0.285 + rng.normal(0, 0.02)])

        paths[i] = _bezier([p0, p1, p2, p3], samples)
        bundle[i] = kind

    # Pull anything that strayed outside back under the surface.
    flat = paths.reshape(-1, 3)
    for _ in range(3):
        d = sdf_brain(flat)
        outside = d > -0.030
        if not outside.any():
            break
        n = sdf_normals(sdf_brain, flat[outside])
        flat[outside] -= n * (d[outside] + 0.030)[:, None]
    paths = flat.reshape(count, samples, 3)
    return paths, bundle


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


def write_fibres(path, paths, bundle):
    count, samples, _ = paths.shape
    with open(path, "wb") as fh:
        fh.write(struct.pack("<II", count, samples))
        t = np.linspace(0.0, 1.0, samples)[None, :, None].repeat(count, 0)
        b = bundle[:, None, None].repeat(samples, 1)
        payload = np.concatenate([paths, t, b], axis=2).astype("<f4")
        fh.write(payload.tobytes())
    print(f"  {os.path.basename(path):12s} {count:6d} fibres x {samples} "
          f"  {os.path.getsize(path)//1024:5d} KB")


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


def build(name, fn, vessel_fn, res, extent, cell, fibre_fn=None):
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
    if fibre_fn is not None:
        # Same centre and scale as the surface, or the tracts float free
        # of the shell they are supposed to run inside.
        paths, bundle = fibre_fn()
        paths = (paths - centre) * scale
        write_fibres(os.path.join(OUT, f"{name}.fib"), paths, bundle)
    preview(name, pts, ao)
    return pts.shape[0]


def main():
    os.makedirs(OUT, exist_ok=True)
    build("heart", sdf_heart, heart_vessel_field, res=176, extent=0.86, cell=0.0105)
    build("brain", sdf_brain, brain_vessel_field, res=176, extent=0.80,
          cell=0.0105, fibre_fn=brain_fibres)
    print(f"previews in {OUT}")


if __name__ == "__main__":
    main()
