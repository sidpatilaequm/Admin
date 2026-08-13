import fitz  # PyMuPDF
from PIL import Image
import math
import io
import os
import hashlib
from typing import List, Dict, Iterator


# Default extraction parameters; callers can override via function args
DEFAULTS = {
    "min_drawn_width_pt": 150,
    "min_drawn_height_pt": 100,
    "min_drawn_area_pt2": 19000,
    "aspect_min": 0.9,
    "aspect_max": 2.6,
    "min_effective_dpi": 45,
    "top_k_per_page": None,
    "merge_tol_pt": 18,
    "crop_margin_pt": 8,
    "crop_scale": 10,
    # When enabled, also crop each occurrence rectangle on the page (useful for tiny thumbs)
    "save_all_occurrences": False,
    "occurrence_min_width_pt": 60,
    "occurrence_min_height_pt": 60,
    "occurrence_min_area_pt2": 5000,
    # Skip near-uniform (single-color) images like full-black/white bars
    "skip_uniform": True,
    "uniform_range_threshold": 8,     # grayscale range (0-255); <= means uniform
    "uniform_dominant_ratio": 0.985,  # if a single gray level dominates >= this ratio → uniform
    # Skip images that cover (nearly) a full page
    "skip_full_page_images": True,
    "full_page_area_ratio": 0.6,      # area(image)/area(page) ≥ threshold → treated as full page
    "full_page_side_ratio": 0.9,      # width or height covers ≥90% of page → treated as full page
    # Skip small corner/edge fragments that touch page borders
    "skip_edge_fragments": True,
    "edge_margin_pt": 24,             # within 24pt of an edge counts as touching the edge
    "edge_small_ratio": 0.35,         # fragment width or height must be <= 35% of page to qualify for skip
    "edge_area_ratio": 0.08,          # OR area <= 8% of page area
    # Skip crops where the foreground object is cut off by the image borders
    "skip_border_touching": True,
    "border_gray_threshold": 245,     # grayscale threshold for foreground vs background
    "border_margin_px": 2,            # consider touching if within N pixels from an edge
    # If foreground touches an image edge and its bbox area is below this fraction of image area → skip
    "border_touching_area_ratio": 0.6,
    # Additionally, if white background is very high and object touches edge, skip
    "border_touching_min_white_ratio": 0.80,
    # Low-information filters (remove gradient squares, blurry circles, dark patches)
    "skip_low_info": True,
    "low_info_entropy_bits": 3.0,     # Shannon entropy threshold (0-8 for 8-bit gray)
    "low_info_stddev": 12.0,          # stddev of gray; small => flat/low-contrast
    "low_info_white_bg_ratio": 0.70,  # if white bg is high and foreground is small, skip
    "low_info_fg_area_max": 0.50,     # foreground bbox area <= this fraction → skip (when bg is white)
}


def _effective_dpi(px_w: int, px_h: int, w_pt: float, h_pt: float):
    w_in = max(w_pt, 1e-6) / 72.0
    h_in = max(h_pt, 1e-6) / 72.0
    return (px_w / w_in, px_h / h_in)


def _rect_ok(r: fitz.Rect, cfg: Dict) -> bool:
    w_pt, h_pt = r.width, r.height
    area = w_pt * h_pt
    if h_pt <= 0:
        return False
    aspect = w_pt / h_pt
    return (((w_pt >= cfg["min_drawn_width_pt"] and h_pt >= cfg["min_drawn_height_pt"]) or
             area >= cfg["min_drawn_area_pt2"]) and
            (cfg["aspect_min"] <= aspect <= cfg["aspect_max"]))


def _close_or_overlap(a: fitz.Rect, b: fitz.Rect, tol: float) -> bool:
    if (a & b).get_area() > 0:
        return True
    a_exp = fitz.Rect(a.x0 - tol, a.y0 - tol, a.x1 + tol, a.y1 + tol)
    return (a_exp & b).get_area() > 0


def _merge_rects(rects: List[fitz.Rect], tol_pt: float = 10) -> List[fitz.Rect]:
    rects = [fitz.Rect(r) for r in rects]
    changed = True
    while changed and len(rects) > 1:
        changed = False
        new_rects = []
        while rects:
            r = rects.pop()
            i = 0
            while i < len(rects):
                if _close_or_overlap(r, rects[i], tol_pt):
                    r = r | rects[i]
                    rects.pop(i)
                    changed = True
                else:
                    i += 1
            new_rects.append(r)
        rects = new_rects
    return rects


def _grow_rect(r: fitz.Rect, m: float) -> fitz.Rect:
    return fitz.Rect(r.x0 - m, r.y0 - m, r.x1 + m, r.y1 + m)


def extract_images_to_dir(
    pdf_path: str,
    output_dir: str,
    *,
    params: Dict = None,
) -> List[Dict]:
    """
    Extract images from a PDF and save them under output_dir.

    Returns a list of metadata dicts:
      {
        "page": int (1-based),
        "index": int (1-based, within job),
        "kind": "embed" | "crop-merged",
        "drawn_width_pt": int,
        "drawn_height_pt": int,
        "path": absolute file path,
        "relpath": path relative to the output_dir,
        "ext": file extension (without dot),
        "hash": md5 hex of file bytes
      }
    """
    cfg = {**DEFAULTS, **(params or {})}
    os.makedirs(output_dir, exist_ok=True)

    doc = fitz.open(pdf_path)
    seen_hashes = set()
    saved: List[Dict] = []
    saved_count = 0

    for pno in range(len(doc)):
        page = doc[pno]
        saved_rects: List[fitz.Rect] = []

        def _is_full_page_rect(r: fitz.Rect) -> bool:
            if not cfg.get("skip_full_page_images"):
                return False
            try:
                page_rect = page.rect
                page_area = max(page_rect.get_area(), 1.0)
                img_area = r.get_area()
                area_ratio = img_area / page_area
                width_ratio = r.width / page_rect.width
                height_ratio = r.height / page_rect.height
                if area_ratio >= float(cfg.get("full_page_area_ratio", 0.6)):
                    return True
                if width_ratio >= float(cfg.get("full_page_side_ratio", 0.9)) and height_ratio >= 0.6:
                    return True
                if height_ratio >= float(cfg.get("full_page_side_ratio", 0.9)) and width_ratio >= 0.6:
                    return True
            except Exception:
                return False
            return False

        def _is_edge_fragment_rect(r: fitz.Rect) -> bool:
            if not cfg.get("skip_edge_fragments"):
                return False
            try:
                page_rect = page.rect
                page_area = max(page_rect.get_area(), 1.0)
                # touching edge?
                margin = float(cfg.get("edge_margin_pt", 24))
                touches_edge = (
                    r.x0 <= page_rect.x0 + margin or
                    r.y0 <= page_rect.y0 + margin or
                    r.x1 >= page_rect.x1 - margin or
                    r.y1 >= page_rect.y1 - margin
                )
                if not touches_edge:
                    return False
                # small enough to be a fragment
                small_side = (r.width <= page_rect.width * float(cfg.get("edge_small_ratio", 0.35)) or
                              r.height <= page_rect.height * float(cfg.get("edge_small_ratio", 0.35)))
                small_area = (r.get_area() <= page_area * float(cfg.get("edge_area_ratio", 0.08)))
                return small_side or small_area
            except Exception:
                return False

        # Helper: detect near-uniform images
        def _bytes_is_uniform(img_bytes: bytes) -> bool:
            if not cfg.get("skip_uniform"):
                return False
            try:
                with Image.open(io.BytesIO(img_bytes)) as im:
                    g = im.convert("L")
                    g = g.resize((64, 64))
                    minv, maxv = g.getextrema()
                    if (maxv - minv) <= int(cfg.get("uniform_range_threshold", 8)):
                        return True
                    hist = g.histogram()
                    total = sum(hist) or 1
                    if (max(hist) / total) >= float(cfg.get("uniform_dominant_ratio", 0.985)):
                        return True
            except Exception:
                return False
            return False

        # Helper: detect if significant foreground touches image border (cut-off pieces)
        def _bytes_object_touches_border(img_bytes: bytes) -> bool:
            if not cfg.get("skip_border_touching"):
                return False
            try:
                with Image.open(io.BytesIO(img_bytes)) as im:
                    g = im.convert("L")
                    w, h = g.size
                    # limit size for speed while preserving edges reasonably
                    max_side = max(w, h)
                    if max_side > 512:
                        scale = 512.0 / max_side
                        g = g.resize((max(1, int(w * scale)), max(1, int(h * scale))))
                        w, h = g.size
                    thresh = int(cfg.get("border_gray_threshold", 245))
                    # build a binary mask of likely foreground (darker than near-white)
                    bw = g.point(lambda x: 255 if x < thresh else 0, mode='1')
                    bbox = bw.getbbox()
                    if not bbox:
                        return False
                    x0, y0, x1, y1 = bbox
                    margin = int(cfg.get("border_margin_px", 2))
                    touches = (x0 <= margin or y0 <= margin or (w - x1) <= margin or (h - y1) <= margin)
                    if not touches:
                        return False
                    area_ratio = (max(1, (x1 - x0) * (y1 - y0))) / float(w * h)
                    if area_ratio <= float(cfg.get("border_touching_area_ratio", 0.6)):
                        return True
                    # also consider overall whiteness; if page is very white and object touches edge, skip
                    white_ratio = float(sum(1 for px in g.getdata() if px >= thresh)) / float(w * h)
                    if white_ratio >= float(cfg.get("border_touching_min_white_ratio", 0.80)):
                        return True
                    return False
            except Exception:
                return False
            
            return False

        # Low-information detector: low entropy/contrast or tiny foreground on white
        def _bytes_is_low_info(img_bytes: bytes) -> bool:
            if not cfg.get("skip_low_info"):
                return False
            try:
                with Image.open(io.BytesIO(img_bytes)) as im:
                    g = im.convert("L")
                    w, h = g.size
                    # cap size for speed
                    max_side = max(w, h)
                    if max_side > 512:
                        scale = 512.0 / max_side
                        g = g.resize((max(1, int(w * scale)), max(1, int(h * scale))))
                        w, h = g.size
                    hist = g.histogram()
                    total = float(sum(hist)) or 1.0
                    probs = [h_ / total for h_ in hist]
                    entropy = -sum(p * math.log(p + 1e-12, 2) for p in probs if p > 0)
                    # stddev
                    mean = sum(i * hist[i] for i in range(256)) / total
                    var = sum(((i - mean) ** 2) * hist[i] for i in range(256)) / total
                    std = math.sqrt(var)
                    if entropy <= float(cfg.get("low_info_entropy_bits", 3.0)) or std <= float(cfg.get("low_info_stddev", 12.0)):
                        return True
                    # white background with small foreground
                    thresh = int(cfg.get("border_gray_threshold", 245))
                    white_ratio = float(sum(1 for px in g.getdata() if px >= thresh)) / float(w * h)
                    if white_ratio >= float(cfg.get("low_info_white_bg_ratio", 0.70)):
                        bw = g.point(lambda x: 255 if x < thresh else 0, mode='1')
                        bbox = bw.getbbox()
                        if bbox:
                            x0, y0, x1, y1 = bbox
                            fg_area_ratio = (max(1, (x1 - x0) * (y1 - y0))) / float(w * h)
                            if fg_area_ratio <= float(cfg.get("low_info_fg_area_max", 0.50)):
                                return True
            except Exception:
                return False
            return False

        # PASS 1: embedded images by xref
        xrefs = [t[0] for t in page.get_images(full=True)]
        candidates = []
        for xref in xrefs:
            rects = page.get_image_rects(xref)
            if not rects:
                continue
            r = max(rects, key=lambda R: R.width * R.height)
            if not _rect_ok(r, cfg):
                continue

            try:
                base = doc.extract_image(xref)
                img_bytes = base.get("image")
                if not img_bytes:
                    continue
                with Image.open(io.BytesIO(img_bytes)) as im:
                    px_w, px_h = im.size
            except Exception:
                continue

            w_dpi, h_dpi = _effective_dpi(px_w, px_h, r.width, r.height)
            if min(w_dpi, h_dpi) < cfg["min_effective_dpi"]:
                continue

            ext = (base.get("ext") or "png").lower()
            if ext in {"jpx", "jp2"}:
                ext = "jpg"

            candidates.append({
                "rect": r,
                "area": r.width * r.height,
                "bytes": img_bytes,
                "ext": ext,
            })

        candidates.sort(key=lambda c: c["area"], reverse=True)
        if cfg["top_k_per_page"]:
            candidates = candidates[: cfg["top_k_per_page"]]

        for c in candidates:
            b = c["bytes"]
            if _bytes_is_uniform(b) or _bytes_object_touches_border(b) or _bytes_is_low_info(b):
                continue
            h = hashlib.md5(b).hexdigest()
            if h in seen_hashes:
                continue
            seen_hashes.add(h)

            if _is_full_page_rect(c["rect"]) or _is_edge_fragment_rect(c["rect"]):
                continue
            saved_count += 1
            filename = f"page_{pno+1}_img_{saved_count}.{c['ext']}"
            out_path = os.path.join(output_dir, filename)
            with open(out_path, "wb") as f:
                f.write(b)

            saved_rects.append(c["rect"])
            saved.append({
                "page": pno + 1,
                "index": saved_count,
                "kind": "embed",
                "drawn_width_pt": int(c["rect"].width),
                "drawn_height_pt": int(c["rect"].height),
                "path": out_path,
                "relpath": filename,
                "ext": c["ext"],
                "hash": h,
            })

        # PASS 1b: optionally crop every occurrence rectangle (captures tiny placed images)
        if cfg.get("save_all_occurrences"):
            for xref in xrefs:
                try:
                    occ_rects = page.get_image_rects(xref)
                except Exception:
                    occ_rects = []
                for r in occ_rects:
                    if r.width < cfg["occurrence_min_width_pt"] and r.height < cfg["occurrence_min_height_pt"] \
                       and (r.width * r.height) < cfg["occurrence_min_area_pt2"]:
                        continue
                    # avoid duplicates with already-saved embeds
                    skip = False
                    for s in saved:
                        if s["page"] == pno + 1 and abs(s.get("drawn_width_pt", 0) - int(r.width)) < 1 and abs(s.get("drawn_height_pt", 0) - int(r.height)) < 1:
                            # likely same occurrence already captured
                            skip = True
                            break
                    if skip:
                        continue
                    if _is_full_page_rect(r) or _is_edge_fragment_rect(r):
                        continue
                    try:
                        mat = fitz.Matrix(cfg["crop_scale"], cfg["crop_scale"])
                        pix = page.get_pixmap(matrix=mat, clip=r, alpha=False)
                        b = pix.tobytes("png")
                    except Exception:
                        continue
                    if _bytes_is_uniform(b) or _bytes_object_touches_border(b) or _bytes_is_low_info(b):
                        continue
                    h = hashlib.md5(b).hexdigest()
                    if h in seen_hashes:
                        continue
                    seen_hashes.add(h)
                    saved_count += 1
                    filename = f"page_{pno+1}_img_{saved_count}.png"
                    out_path = os.path.join(output_dir, filename)
                    with open(out_path, "wb") as f:
                        f.write(b)
                    saved.append({
                        "page": pno + 1,
                        "index": saved_count,
                        "kind": "occurrence-crop",
                        "drawn_width_pt": int(r.width),
                        "drawn_height_pt": int(r.height),
                        "path": out_path,
                        "relpath": filename,
                        "ext": "png",
                        "hash": h,
                    })

        # PASS 2: fallback crop of image blocks
        layout = page.get_text("rawdict")
        crop_rects = []
        for blk in layout.get("blocks", []):
            if blk.get("type") == 1 and "bbox" in blk:
                r = fitz.Rect(blk["bbox"])
                if _rect_ok(r, cfg):
                    crop_rects.append(r)

        merged = _merge_rects(crop_rects, tol_pt=cfg["merge_tol_pt"])
        merged = [_grow_rect(r, cfg["crop_margin_pt"]) for r in merged if _rect_ok(r, cfg)]

        # filter ones overlapping already-saved embeds
        def _iou(a: fitz.Rect, b: fitz.Rect) -> float:
            inter = a & b
            if inter.is_empty:
                return 0.0
            return inter.get_area() / (a.get_area() + b.get_area() - inter.get_area())

        merged = [r for r in merged if all(_iou(r, s) < 0.6 for s in saved_rects)]

        merged.sort(key=lambda R: R.width * R.height, reverse=True)
        if cfg["top_k_per_page"]:
            remaining = max(cfg["top_k_per_page"] - len([m for m in saved if m["page"] == pno + 1]), 0)
            merged = merged[:remaining] if remaining else []

        for r in merged:
            if _is_full_page_rect(r) or _is_edge_fragment_rect(r):
                continue
            mat = fitz.Matrix(cfg["crop_scale"], cfg["crop_scale"])
            pix = page.get_pixmap(matrix=mat, clip=r, alpha=False)
            b = pix.tobytes("png")
            if _bytes_is_uniform(b) or _bytes_object_touches_border(b) or _bytes_is_low_info(b):
                continue
            h = hashlib.md5(b).hexdigest()
            if h in seen_hashes:
                continue
            seen_hashes.add(h)

            saved_count += 1
            filename = f"page_{pno+1}_img_{saved_count}.png"
            out_path = os.path.join(output_dir, filename)
            with open(out_path, "wb") as f:
                f.write(b)

            saved_rects.append(r)
            saved.append({
                "page": pno + 1,
                "index": saved_count,
                "kind": "crop-merged",
                "drawn_width_pt": int(r.width),
                "drawn_height_pt": int(r.height),
                "path": out_path,
                "relpath": filename,
                "ext": "png",
                "hash": h,
            })

    doc.close()
    return saved


