#!/usr/bin/env python3
"""Image -> XY waveform with path optimization (not row-by-row).

This script generates stipple points from image darkness, then finds a short
continuous draw path (nearest-neighbor style) to reduce travel scratches when
you only have 2-channel XY output and no laser blanking channel.
"""

from __future__ import annotations

import argparse
import wave
from pathlib import Path

import numpy as np

try:
    from PIL import Image
except ModuleNotFoundError as exc:
    raise SystemExit(
        "Missing dependency: Pillow. Install with `python3 -m pip install -r python/requirements.txt`."
    ) from exc

try:
    from scipy.spatial import cKDTree as _SciPyKDTree
except Exception:
    _SciPyKDTree = None


class _NumpyKDTree:
    def __init__(self, points: np.ndarray):
        self.points = np.asarray(points, dtype=np.float32)

    def query(self, points: np.ndarray, k: int = 1, workers: int | None = None):
        del workers
        pts = np.asarray(points, dtype=np.float32)
        single = pts.ndim == 1
        if single:
            pts = pts[None, :]

        diff = self.points[None, :, :] - pts[:, None, :]
        dist2 = np.sum(diff * diff, axis=2)

        if k <= 1:
            idx = np.argmin(dist2, axis=1)
            dist = np.sqrt(dist2[np.arange(pts.shape[0]), idx])
        else:
            kk = min(int(k), self.points.shape[0])
            part = np.argpartition(dist2, kth=kk - 1, axis=1)[:, :kk]
            part_dist2 = np.take_along_axis(dist2, part, axis=1)
            order = np.argsort(part_dist2, axis=1)
            idx = np.take_along_axis(part, order, axis=1)
            dist = np.sqrt(np.take_along_axis(dist2, idx, axis=1))

        if single:
            return dist[0], idx[0]
        return dist, idx


def _make_kdtree(points: np.ndarray):
    if _SciPyKDTree is not None:
        return _SciPyKDTree(points)
    return _NumpyKDTree(points)


def _guard_large_numpy_kdtree(sample_count: int, point_count: int, context: str) -> None:
    if _SciPyKDTree is not None:
        return
    work = int(sample_count) * int(point_count)
    if work <= 2_000_000:
        return
    raise RuntimeError(
        f"{context} needs fast nearest-neighbor search for this image size. "
        "Install SciPy with `python3 -m pip install -r python/requirements.txt`, "
        "or reduce image size / increase pixel step / enable downsample."
    )


def tone_map_weights(ink_values: np.ndarray, density: float, gamma: float, floor: float) -> np.ndarray:
    g = max(1e-6, float(gamma))
    f = float(np.clip(floor, 0.0, 1.0))
    mapped = np.power(np.clip(ink_values, 0.0, 1.0), g)
    mapped = f + (1.0 - f) * mapped
    return np.clip(mapped * max(0.0, density), 0.0, 1.0)


def load_ink(image_path: Path, max_size: int | None, downsample_step: int) -> np.ndarray:
    img = Image.open(image_path).convert("L")
    w, h = img.size
    if max_size is not None and max_size > 0:
        scale = min(1.0, float(max_size) / float(max(w, h)))
        if scale < 1.0:
            img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)

    arr = np.asarray(img, dtype=np.float32) / 255.0
    step = max(1, int(downsample_step))
    if step > 1:
        arr = arr[::step, ::step]
    return 1.0 - arr


def sample_weighted_dots(
    ink: np.ndarray,
    dots_number: int,
    density: float,
    tone_gamma: float,
    tone_floor: float,
    seed: int,
    pixel_step: int,
) -> np.ndarray:
    h, w = ink.shape
    s = max(1, int(pixel_step))
    ys = np.arange(0, h, s, dtype=np.int32)
    xs = np.arange(0, w, s, dtype=np.int32)
    yy, xx = np.meshgrid(ys, xs, indexing="ij")
    rows = yy.ravel()
    cols = xx.ravel()

    weights = tone_map_weights(ink[rows, cols], density, tone_gamma, tone_floor)
    valid = np.flatnonzero(weights > 1e-6)
    if valid.size == 0:
        t = np.linspace(0.0, 2.0 * np.pi, 2000, endpoint=False)
        return np.column_stack((0.5 * (np.cos(t) + 1) * (w - 1), 0.5 * (np.sin(t) + 1) * (h - 1)))

    rng = np.random.default_rng(seed)
    k = min(int(dots_number), valid.size)
    probs = weights[valid]
    probs = probs / probs.sum()
    chosen = rng.choice(valid, size=k, replace=False, p=probs)
    pts = np.column_stack((cols[chosen].astype(np.float32), rows[chosen].astype(np.float32)))
    return pts


def weighted_voronoi_stipple_points(
    ink: np.ndarray,
    dots_number: int,
    density: float,
    tone_gamma: float,
    tone_floor: float,
    seed: int,
    pixel_step: int,
    iterations: int,
    lerp: float,
) -> np.ndarray:
    h, w = ink.shape
    s = max(1, int(pixel_step))
    ys = np.arange(0, h, s, dtype=np.int32)
    xs = np.arange(0, w, s, dtype=np.int32)
    yy, xx = np.meshgrid(ys, xs, indexing="ij")
    rows = yy.ravel()
    cols = xx.ravel()

    weights = tone_map_weights(ink[rows, cols], density, tone_gamma, tone_floor)
    valid = np.flatnonzero(weights > 1e-6)
    if valid.size == 0:
        return sample_weighted_dots(
            ink, dots_number, density, tone_gamma, tone_floor, seed, pixel_step
        )

    rng = np.random.default_rng(seed)
    k = min(int(dots_number), valid.size)
    probs = weights[valid]
    probs = probs / probs.sum()
    chosen = rng.choice(valid, size=k, replace=False, p=probs)
    points = np.column_stack((cols[chosen].astype(np.float32), rows[chosen].astype(np.float32)))

    samples = np.column_stack((cols[valid].astype(np.float32), rows[valid].astype(np.float32)))
    sample_w = weights[valid]
    l = float(np.clip(lerp, 0.0, 1.0))
    _guard_large_numpy_kdtree(samples.shape[0], k, "Voronoi stippling")

    for _ in range(max(1, int(iterations))):
        tree = _make_kdtree(points)
        owners = tree.query(samples, workers=-1)[1]

        wsum = np.bincount(owners, weights=sample_w, minlength=k)
        cx = np.bincount(owners, weights=sample_w * samples[:, 0], minlength=k)
        cy = np.bincount(owners, weights=sample_w * samples[:, 1], minlength=k)

        new_points = points.copy()
        nz = wsum > 0
        new_points[nz, 0] = cx[nz] / wsum[nz]
        new_points[nz, 1] = cy[nz] / wsum[nz]

        points += l * (new_points - points)
        points[:, 0] = np.clip(points[:, 0], 0, w - 1)
        points[:, 1] = np.clip(points[:, 1], 0, h - 1)

    return points


def poisson_disk_stipple_points(
    ink: np.ndarray,
    dots_number: int,
    density: float,
    tone_gamma: float,
    tone_floor: float,
    seed: int,
    min_dist: float,
    attempts: int,
) -> np.ndarray:
    """Global weighted Poisson-disk sampling (avoids local growth trapping)."""
    h, w = ink.shape
    rng = np.random.default_rng(seed)

    r = max(1.0, float(min_dist))
    cell = r / np.sqrt(2.0)
    gw = int(np.ceil(w / cell))
    gh = int(np.ceil(h / cell))
    grid = np.full((gh, gw), -1, dtype=np.int32)


    ys = np.arange(0, h, dtype=np.int32)
    xs = np.arange(0, w, dtype=np.int32)
    yy, xx = np.meshgrid(ys, xs, indexing="ij")
    rows = yy.ravel()
    cols = xx.ravel()
    weights = tone_map_weights(ink[rows, cols], density, tone_gamma, tone_floor)
    valid = np.flatnonzero(weights > 1e-6)
    if valid.size == 0:
        return sample_weighted_dots(
            ink, dots_number, density, tone_gamma, tone_floor, seed, pixel_step=1
        )

    # Draw a large global candidate set by darkness weights.
    target = max(1, int(dots_number))
    candidate_n = min(valid.size, max(target * max(4, int(attempts)), target))
    probs = weights[valid]
    probs = probs / probs.sum()
    cand_idx = rng.choice(valid, size=candidate_n, replace=False, p=probs)
    rng.shuffle(cand_idx)

    def far_enough(px: float, py: float) -> bool:
        gx = int(px / cell)
        gy = int(py / cell)
        y0 = max(0, gy - 2)
        y1 = min(gh - 1, gy + 2)
        x0 = max(0, gx - 2)
        x1 = min(gw - 1, gx + 2)
        for yy in range(y0, y1 + 1):
            for xx in range(x0, x1 + 1):
                idx = grid[yy, xx]
                if idx >= 0:
                    qx, qy = points[idx]
                    if (px - qx) * (px - qx) + (py - qy) * (py - qy) < r * r:
                        return False
        return True

    points: list[np.ndarray] = []
    for idx0 in cand_idx:
        px = float(cols[idx0])
        py = float(rows[idx0])
        if far_enough(px, py):
            idx = len(points)
            points.append(np.array([px, py], dtype=np.float32))
            grid[int(py / cell), int(px / cell)] = idx
            if len(points) >= target:
                break

    if len(points) == 0:
        return sample_weighted_dots(
            ink, dots_number, density, tone_gamma, tone_floor, seed, pixel_step=1
        )

    pts = np.vstack(points)

    # If Poisson cannot reach target due high min_dist, top up with weighted random.
    if pts.shape[0] < target:
        extra = sample_weighted_dots(
            ink,
            dots_number=target - pts.shape[0],
            density=density,
            tone_gamma=tone_gamma,
            tone_floor=tone_floor,
            seed=seed + 101,
            pixel_step=1,
        )
        pts = np.vstack([pts, extra])

    # Guard: if coverage is too local, fallback to weighted random globally.
    xmin, ymin = pts[:, 0].min(), pts[:, 1].min()
    xmax, ymax = pts[:, 0].max(), pts[:, 1].max()
    bbox_ratio = ((xmax - xmin + 1) * (ymax - ymin + 1)) / float(max(1, w * h))
    if bbox_ratio < 0.3:
        return sample_weighted_dots(
            ink,
            dots_number,
            density,
            tone_gamma,
            tone_floor,
            seed + 202,
            pixel_step=1,
        )

    return pts[:target]


def nearest_neighbor_order(points: np.ndarray, start_index: int = 0) -> np.ndarray:
    n = points.shape[0]
    if n <= 2:
        return np.arange(n, dtype=np.int32)

    _guard_large_numpy_kdtree(n, min(8, n), "Path optimization")

    tree = _make_kdtree(points)
    visited = np.zeros(n, dtype=bool)
    order = np.empty(n, dtype=np.int32)
    cur = int(np.clip(start_index, 0, n - 1))

    for i in range(n):
        order[i] = cur
        visited[cur] = True
        if i == n - 1:
            break

        k = 8
        nxt = -1
        while True:
            kk = min(k, n)
            d, idxs = tree.query(points[cur], k=kk)
            idxs = np.atleast_1d(idxs)
            for idx in idxs:
                j = int(idx)
                if j != cur and not visited[j]:
                    nxt = j
                    break
            if nxt >= 0:
                break
            if kk == n:
                unv = np.flatnonzero(~visited)
                d2 = np.sum((points[unv] - points[cur]) ** 2, axis=1)
                nxt = int(unv[np.argmin(d2)])
                break
            k *= 2

        cur = nxt

    return order


def apply_aspect_fit(x: np.ndarray, y: np.ndarray, w: int, h: int, mode: str) -> tuple[np.ndarray, np.ndarray]:
    if mode == "fill":
        return x, y
    if w > h:
        y = y * (h / w)
    elif h > w:
        x = x * (w / h)
    return x, y


def upsample_points(x: np.ndarray, y: np.ndarray, sample_rate: int, points_per_second: int) -> tuple[np.ndarray, np.ndarray]:
    repeats = max(1, sample_rate // max(points_per_second, 1))
    return np.repeat(x, repeats), np.repeat(y, repeats)


def resample_to_length(
    x: np.ndarray, y: np.ndarray, target_len: int, mode: str = "hold"
) -> tuple[np.ndarray, np.ndarray]:
    if target_len <= 1 or x.shape[0] == target_len:
        return x, y
    if mode == "hold":
        idx = np.floor(np.linspace(0, x.shape[0] - 1, target_len)).astype(np.int64)
        return x[idx], y[idx]
    src_t = np.linspace(0.0, 1.0, x.shape[0], endpoint=True)
    dst_t = np.linspace(0.0, 1.0, target_len, endpoint=True)
    return np.interp(dst_t, src_t, x), np.interp(dst_t, src_t, y)


def append_return_and_silence(
    x: np.ndarray,
    y: np.ndarray,
    sample_rate: int,
    return_ms: float,
    silence_ms: float,
) -> tuple[np.ndarray, np.ndarray]:
    ret_n = max(0, int(sample_rate * (return_ms / 1000.0)))
    sil_n = max(0, int(sample_rate * (silence_ms / 1000.0)))

    if ret_n > 0 and x.size > 0:
        xr = np.linspace(x[-1], 0.0, ret_n, endpoint=True, dtype=np.float32)
        yr = np.linspace(y[-1], 0.0, ret_n, endpoint=True, dtype=np.float32)
        x = np.concatenate([x, xr])
        y = np.concatenate([y, yr])

    if sil_n > 0:
        x = np.concatenate([x, np.zeros(sil_n, dtype=np.float32)])
        y = np.concatenate([y, np.zeros(sil_n, dtype=np.float32)])

    return x, y


def write_wav(path: Path, x: np.ndarray, y: np.ndarray, sr: int) -> None:
    sig = np.stack([x, y], axis=1)
    sig = np.clip(sig, -1.0, 1.0)
    pcm = (sig * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def main() -> None:
    p = argparse.ArgumentParser(description="2ch XY stipple with shortest-path ordering")
    p.add_argument("image", type=Path)
    p.add_argument("--out", type=Path, default=Path("pathopt_xy.wav"))
    p.add_argument("--sample-rate", type=int, default=44100)
    p.add_argument("--dots-number", type=int, default=10000)
    p.add_argument("--density", type=float, default=1.0)
    p.add_argument("--tone-gamma", type=float, default=1.0, help="<1 boosts mid-tones")
    p.add_argument("--tone-floor", type=float, default=0.0, help="Minimum sampling weight for light areas")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--stipple-method", choices=["voronoi", "poisson", "random"], default="voronoi")
    p.add_argument("--pixel-step", type=int, default=1, help="Sampling stride for dot candidates")
    p.add_argument("--downsample-step", type=int, default=1, help="Image pre-downsample step")
    p.add_argument("--max-size", type=int, default=None)
    p.add_argument("--points-per-second", type=int, default=16000)
    p.add_argument("--dot-dwell", type=int, default=1)
    p.add_argument("--target-seconds", type=float, default=None)
    p.add_argument(
        "--resample-mode",
        choices=["hold", "linear"],
        default="hold",
        help="When target-seconds is used: hold keeps stair steps, linear interpolates",
    )
    p.add_argument("--aspect-mode", choices=["fit", "fill"], default="fit")
    p.add_argument("--voronoi-iterations", type=int, default=12)
    p.add_argument("--voronoi-lerp", type=float, default=0.25)
    p.add_argument("--poisson-min-dist", type=float, default=4.0)
    p.add_argument("--poisson-attempts", type=int, default=30)
    p.add_argument("--return-center-ms", type=float, default=0.0)
    p.add_argument("--end-silence-ms", type=float, default=0.0)
    p.add_argument(
        "--allow-tail",
        action="store_true",
        help="Allow appending return/silence tail; default keeps data length exact",
    )
    args = p.parse_args()

    ink = load_ink(args.image, max_size=args.max_size, downsample_step=args.downsample_step)
    h, w = ink.shape
    if args.stipple_method == "voronoi":
        points = weighted_voronoi_stipple_points(
            ink,
            dots_number=args.dots_number,
            density=args.density,
            tone_gamma=args.tone_gamma,
            tone_floor=args.tone_floor,
            seed=args.seed,
            pixel_step=args.pixel_step,
            iterations=args.voronoi_iterations,
            lerp=args.voronoi_lerp,
        )
    elif args.stipple_method == "poisson":
        points = poisson_disk_stipple_points(
            ink,
            dots_number=args.dots_number,
            density=args.density,
            tone_gamma=args.tone_gamma,
            tone_floor=args.tone_floor,
            seed=args.seed,
            min_dist=args.poisson_min_dist,
            attempts=args.poisson_attempts,
        )
    else:
        points = sample_weighted_dots(
            ink,
            dots_number=args.dots_number,
            density=args.density,
            tone_gamma=args.tone_gamma,
            tone_floor=args.tone_floor,
            seed=args.seed,
            pixel_step=args.pixel_step,
        )

    start = int(np.argmin(points[:, 0] + points[:, 1]))
    order = nearest_neighbor_order(points, start_index=start)
    ordered = points[order]

    if args.dot_dwell > 1:
        ordered = np.repeat(ordered, args.dot_dwell, axis=0)

    x = (2.0 * ordered[:, 0] / max(w - 1, 1)) - 1.0
    y = 1.0 - (2.0 * ordered[:, 1] / max(h - 1, 1))
    x, y = apply_aspect_fit(x, y, w, h, mode=args.aspect_mode)
    x, y = upsample_points(x, y, sample_rate=args.sample_rate, points_per_second=args.points_per_second)

    if args.target_seconds is not None and args.target_seconds > 0:
        x, y = resample_to_length(
            x, y, int(args.target_seconds * args.sample_rate), mode=args.resample_mode
        )

    if (args.return_center_ms > 0 or args.end_silence_ms > 0) and not args.allow_tail:
        raise SystemExit(
            "Tail disabled by default to keep data aligned with total length. "
            "Use --allow-tail if you explicitly want appended return/silence."
        )

    if args.allow_tail:
        x, y = append_return_and_silence(
            x,
            y,
            sample_rate=args.sample_rate,
            return_ms=args.return_center_ms,
            silence_ms=args.end_silence_ms,
        )

    x *= 0.75
    y *= 0.75

    write_wav(args.out, x, y, args.sample_rate)
    np.savez(args.out.with_suffix(".npz"), x=x, y=y, sample_rate=args.sample_rate)
    print(f"Wrote {args.out}")
    print(f"Dots: {points.shape[0]}  Samples: {x.shape[0]} @ {args.sample_rate} Hz")


if __name__ == "__main__":
    main()
