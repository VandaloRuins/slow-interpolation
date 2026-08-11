"""Measurement core for render quality: speed, smoothness, focus, artefact candidates.

Imported by `tools/analyse_render.py` (report one clip) and
`tools/detector_bench.py` (sweep candidates against synthetic ground truth). It
lives in `src/` rather than `tools/` so the tests can reach it.

DESIGN NOTES worth keeping, each one bought by a failure on 2026-08-11.

*Measure at native resolution.* `tools/pulse_plot.py` scales to 448x256 before
measuring sharpness, which destroys the frequencies it is trying to report.

*Report the trough, not just the swing.* A normalised swing hides whether the
floor moved: one config read as a 21% regression on swing while its softest
moment was 6.8% SHARPER.

*Flow, not frame differencing, for speed.* A frame difference cannot separate a
light change from a movement, and this pipeline's whole subject is a light change.

*Everything here is a CANDIDATE until `detector_bench.py` says otherwise.* Six
border features are computed and not one of them is known to work; they are
carried so the bench can test them against known amplitudes rather than against
somebody's eye. Do not promote one to a verdict without a sensitivity curve.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

# Flow working size and sampling step, both CHOSEN BY MEASUREMENT rather than by
# argument. Against a known morph amplitude ladder (0 to 4 px injected), 864x270
# at step 3 gives Spearman +1.00 on warp_resid, -1.00 on rigid and +1.00 on
# coherence. The intuition that a 0.13 px/frame drift needs a LONGER baseline is
# wrong: at step 10 coherence collapses to rho +0.09, because the flow field
# decorrelates faster than the motion accumulates.
FLOW_W, FLOW_H = 864, 270
FLOW_STEP = 3
BORDER_PX = 64
BORDER_EVERY = 6               # frames between border samples


# ------------------------------------------------------------------ io

def probe(path: Path) -> tuple[int, int, int, float]:
    o = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,nb_frames,r_frame_rate", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True).stdout.strip().split(",")
    rate = next(f for f in o if "/" in f)
    num, den = rate.split("/")
    ints = [int(f) for f in o if f.isdigit()]
    return ints[0], ints[1], ints[2], float(num) / float(den)


def gray_frames(path: Path, w: int, h: int, limit: int | None = None):
    p = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", str(path), "-vf", "format=gray",
         "-f", "rawvideo", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    n, i = w * h, 0
    try:
        while True:
            b = p.stdout.read(n)
            if len(b) < n or (limit is not None and i >= limit):
                break
            yield np.frombuffer(b, np.uint8).reshape(h, w)
            i += 1
    finally:
        p.stdout.close()
        p.terminate()
        p.wait()


# ------------------------------------------------------------------ focus

def hf_ratio(a: np.ndarray, cutoff: float = 0.25) -> float:
    """Share of spectral energy above `cutoff` of Nyquist, contrast-normalised.

    A RATIO, so it is comparable between configs of one composition and NOT
    between compositions: a high-contrast subject carries more low-frequency
    energy and therefore reads as less sharp than it is.
    """
    g = a.astype(np.float32)
    g = g - g.mean()
    s = g.std()
    if s < 1e-6:
        return 0.0
    F = np.fft.rfft2(g / s)
    P = F.real ** 2 + F.imag ** 2
    fy = np.fft.fftfreq(g.shape[0])[:, None] / .5
    fx = np.fft.rfftfreq(g.shape[1])[None, :] / .5
    t = P.sum()
    return float(P[np.sqrt(fy ** 2 + fx ** 2) > cutoff].sum() / t) if t else 0.0


# ------------------------------------------------------------------ border candidates
# All six of these were tried on 2026-08-11 and all six overlapped between four
# hand-verified dirty clips and four clean ones. They are kept as FEATURES, not
# verdicts, so the bench can retest them where amplitude is known.

def border_features(f: np.ndarray) -> dict:
    import cv2
    h, w = f.shape
    a = f.astype(np.float32)
    band_l, band_r = a[:, :BORDER_PX], a[:, -BORDER_PX:]
    inter = a[:, 3 * BORDER_PX:-3 * BORDER_PX]
    if inter.shape[1] < 32:
        inter = a
    out = {}

    # 1. plain high-frequency energy in the band vs the interior
    hi = hf_ratio(inter) or 1e-9
    out["b_hf"] = min(hf_ratio(band_l), hf_ratio(band_r)) / hi

    # 2/3. streak direction. Sum-over-bucket is BIASED by crop width (a 64px band
    # has 33 x-bins, a 1344px interior has 673), so the mean per bin is the honest
    # version; both are kept to show the bug does not come back.
    def streak(x, use_mean):
        g = x - x.mean()
        s = g.std()
        if s < 1e-6:
            return 1.0
        P = np.abs(np.fft.rfft2(g / s)) ** 2
        fy = np.abs(np.fft.fftfreq(x.shape[0]))[:, None] / .5
        fx = np.abs(np.fft.rfftfreq(x.shape[1]))[None, :] / .5
        hz, vt = P[(fy > .25) & (fx < .08)], P[(fx > .25) & (fy < .08)]
        if hz.size == 0 or vt.size == 0:
            return 1.0
        num, den = (hz.mean(), vt.mean()) if use_mean else (hz.sum(), vt.sum())
        return float(num / den) if den > 0 else 999.0
    for key, um in (("b_streak_sum", False), ("b_streak_mean", True)):
        base = streak(inter, um) or 1e-9
        out[key] = max(streak(band_l, um), streak(band_r, um)) / base

    # 4. strongest vertical discontinuity near either border
    d = np.abs(np.diff(a, axis=1)).mean(axis=0)
    # the margin has to leave an interior to compare against, or the median is
    # taken over an empty slice and every downstream number becomes nan
    m = min(max(110, BORDER_PX + 8), max(1, (len(d) - 8) // 3))
    base = float(np.median(d[m:-m])) if len(d) > 2 * m else float(np.median(d))
    base = base or 1e-9
    out["b_edgepeak"] = max(float(d[:m].max()), float(d[-m:].max())) / base

    # 5. local tile detail
    def tile(x, t=16):
        H, W = (x.shape[0] // t) * t, (x.shape[1] // t) * t
        if H < t or W < t:
            return 0.0
        b = x[:H, :W].reshape(H // t, t, W // t, t).transpose(0, 2, 1, 3).reshape(-1, t * t)
        return float(np.median(b.std(axis=1)))
    ti = tile(inter) or 1e-9
    out["b_detail"] = min(tile(band_l), tile(band_r)) / ti

    # 6. gradient-orientation concentration. A smear is one direction; paint is
    # broad. Chi-squared distance between the band's orientation histogram and
    # the interior's. This one is NEW and untested, hence the bench.
    def orient(x):
        gx = cv2.Sobel(x, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(x, cv2.CV_32F, 0, 1, ksize=3)
        mag = np.sqrt(gx ** 2 + gy ** 2)
        ang = np.arctan2(gy, gx) % np.pi
        hgram, _ = np.histogram(ang, bins=12, range=(0, np.pi), weights=mag)
        s = hgram.sum()
        return hgram / s if s > 0 else hgram
    hi_o, lo_o, ro_o = orient(inter), orient(band_l), orient(band_r)
    def chi2(p, q):
        return float(0.5 * np.sum((p - q) ** 2 / (p + q + 1e-9)))
    out["b_orient"] = max(chi2(lo_o, hi_o), chi2(ro_o, hi_o))
    return out


# ------------------------------------------------------------------ flow

def flow_features(small: list[np.ndarray], step: int) -> dict:
    """Speed, how much of the motion is a coherent global move, and warping error."""
    import cv2
    if len(small) < 3:
        return dict(speed=0.0, rigid=0.0, warp_resid=0.0, coherence=0.0)
    h, w = small[0].shape
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    A = np.stack([gx.ravel(), gy.ravel(), np.ones(gx.size, np.float32)], 1)
    pinv = np.linalg.pinv(A)
    # Coherence needs consecutive flow fields, so keep ONE, not all of them. The
    # list version held 99 fields of 864x270x2 float32, 185 MB, and ran the machine
    # out of memory at full clip length while passing at --limit 150.
    mags, rigid, resid, coh = [], [], [], []
    prev_fl = None
    for a, b in zip(small, small[1:]):
        fl = cv2.calcOpticalFlowFarneback(a, b, None, 0.5, 3, 15, 3, 5, 1.2, 0)
        u, v = fl[..., 0], fl[..., 1]
        tot = float(np.mean(u ** 2 + v ** 2))
        mags.append(float(np.mean(np.sqrt(u ** 2 + v ** 2))))
        if tot > 1e-12:
            ur = u.ravel() - A @ (pinv @ u.ravel())
            vr = v.ravel() - A @ (pinv @ v.ravel())
            rigid.append(1.0 - float(np.mean(ur ** 2 + vr ** 2)) / tot)
        # WARPING ERROR: the standard temporal-consistency measure. Warp a along
        # the flow and see what is left over, as a fraction of the raw change.
        # Motion that flow explains warps cleanly; deformation in place does not.
        warped = cv2.remap(a.astype(np.float32), (gx + u).astype(np.float32),
                           (gy + v).astype(np.float32), cv2.INTER_LINEAR,
                           borderMode=cv2.BORDER_REFLECT)
        raw = float(np.abs(a.astype(np.float32) - b.astype(np.float32)).mean())
        left = float(np.abs(warped - b.astype(np.float32)).mean())
        resid.append(left / raw if raw > 1e-6 else 0.0)
        if prev_fl is not None:
            num = float((prev_fl[..., 0] * fl[..., 0] + prev_fl[..., 1] * fl[..., 1]).sum())
            den = float(np.sqrt((prev_fl ** 2).sum()) * np.sqrt((fl ** 2).sum())) + 1e-9
            coh.append(num / den)
        prev_fl = fl
    scale = 1728 / FLOW_W
    return dict(
        speed=float(np.median(mags)) * scale / step,
        rigid=float(np.median(rigid)) if rigid else 0.0,
        warp_resid=float(np.median(resid)),
        coherence=float(np.median(coh)) if coh else 0.0,
    )


# ------------------------------------------------------------------ top level

def features(path: Path, K: int = 10, limit: int | None = None,
             flow_step: int = FLOW_STEP) -> dict:
    """One row of numbers for one clip. Single decode pass where possible."""
    import cv2
    path = Path(path)
    w, h, _, fps = probe(path)
    cw, ch = min(1024, w), min(512, h)
    x0, y0 = (w - cw) // 2, (h - ch) // 2

    sharp, step, small, bfeat = [], [], [], []
    prev = None
    for i, f in enumerate(gray_frames(path, w, h, limit=limit)):
        c = f[y0:y0 + ch, x0:x0 + cw]
        sharp.append(hf_ratio(c))
        d = c.astype(np.float32)
        d = d - d.mean()                      # remove the light arc
        if prev is not None:
            step.append(float(np.abs(d - prev).mean()))
        prev = d
        if i % flow_step == 0:
            small.append(cv2.resize(f, (FLOW_W, FLOW_H), interpolation=cv2.INTER_AREA))
        if i % BORDER_EVERY == 0:
            bfeat.append(border_features(f))

    sharp, step = np.array(sharp), np.array(step)
    n = len(sharp)
    if n < 4:
        raise ValueError(f"{path.name}: only {n} frames decoded")

    per = n / K
    bidx = sorted({int(round(k * per)) - 1 for k in range(1, K)} & set(range(len(step))))
    mask = np.zeros(len(step), bool)
    if bidx:
        mask[bidx] = True
    med = float(np.median(step[~mask])) if (~mask).any() else float(np.median(step))
    med = med or 1e-9
    folded = np.array([sharp[(np.arange(n) % per).astype(int) == i].mean()
                       for i in range(max(int(per), 1))])

    out = dict(
        clip=path.name, frames=n,
        lurch=float(step[mask].mean()) / med if mask.any() else float("nan"),
        jitter=float(np.median(np.abs(np.diff(step)))) / med,
        loop=float(np.abs(sharp[-1] - sharp[0])) /
             max(float(np.median(np.abs(np.diff(sharp)))), 1e-9),
        flicker=int((step > 3 * med).sum()),
        focus_mean=float(sharp.mean()),
        focus_trough=float(folded.min()),
        focus_p05=float(np.percentile(sharp, 5)),
        focus_swing=100 * float(folded.max() - folded.min()) / float(folded.mean()),
    )
    out.update(flow_features(small, flow_step))
    for k in bfeat[0]:
        out[k] = float(np.median([b[k] for b in bfeat]))
    return out


# ------------------------------------------------------------------ keyframe reference

def keyframe_features(kf_dir: Path) -> dict:
    """How hard a job RIFE was given, measured on the keyframes it was handed.

    This is the CAUSE, not the symptom. Luca, 2026-08-11: "the interpolation
    smoothness is also given by the detail and composition differences between the
    interpolated frames." Two keyframes that disagree force the interpolator to
    invent, and inventing is what reads as morphing and mid-pair softness.

    Needs `staging/<name>/keyframes/` off the slow-interp-outputs volume, which
    `modal.preserve_staging: true` keeps. Present for led16 onward.
    """
    import cv2
    from skimage.metrics import structural_similarity as ssim
    files = sorted(Path(kf_dir).glob("*.png"))
    if len(files) < 2:
        return {}
    # Stream pairs. Holding ten 1536x896 keyframes while skimage allocates float64
    # temporaries for each of them exhausted memory on a loaded machine.
    sims, flows, hfs = [], [], []
    prev = None
    count = 0
    for p in files:
        im = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
        if im is None:
            continue
        count += 1
        h, w = im.shape
        hfs.append(hf_ratio(im[max(0, h // 2 - 256):h // 2 + 256,
                               max(0, w // 2 - 512):w // 2 + 512]))
        if prev is not None:
            # SSIM at half scale. skimage works in float64 and allocates about ten
            # temporaries, which at 1536x896 is over 100 MB per pair and exhausted
            # memory on a loaded machine. Half scale is also the better measure
            # here: the question is how much COMPOSITION AND DETAIL differ between
            # keyframes, not how much pixel noise does.
            sa = cv2.resize(prev, (prev.shape[1] // 2, prev.shape[0] // 2),
                            interpolation=cv2.INTER_AREA)
            sb = cv2.resize(im, (im.shape[1] // 2, im.shape[0] // 2),
                            interpolation=cv2.INTER_AREA)
            sims.append(float(ssim(sa, sb, data_range=255)))
            sa = cv2.resize(prev, (FLOW_W, FLOW_H), interpolation=cv2.INTER_AREA)
            sb = cv2.resize(im, (FLOW_W, FLOW_H), interpolation=cv2.INTER_AREA)
            fl = cv2.calcOpticalFlowFarneback(sa, sb, None, 0.5, 3, 15, 3, 5, 1.2, 0)
            flows.append(float(np.mean(np.sqrt(fl[..., 0] ** 2 + fl[..., 1] ** 2))))
        prev = im
    if not sims:
        return {}
    imgs = [None] * count
    return dict(
        kf_count=len(imgs),
        kf_ssim=float(np.median(sims)),            # 1.0 = consecutive frames agree
        kf_ssim_worst=float(np.min(sims)),
        kf_flow=float(np.median(flows)),           # how far things travel per pair
        kf_hf=float(np.median(hfs)),               # the sharpness ceiling RIFE was given
    )
