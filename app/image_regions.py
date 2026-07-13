from PIL import Image, ImageStat


def _box_px(image: Image.Image, region_fraction: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    x0f, y0f, x1f, y1f = region_fraction
    w, h = image.size
    return int(x0f * w), int(y0f * h), int(x1f * w), int(y1f * h)


def crop_plate_region(image: Image.Image, region_fraction: tuple[float, float, float, float]) -> Image.Image:
    """Crop down to just the VIN-plate inset, so OCR reads a small focused image
    instead of scanning the whole damage photo for text."""
    return image.crop(_box_px(image, region_fraction))


def mask_plate_region(image: Image.Image, region_fraction: tuple[float, float, float, float]) -> Image.Image:
    """Return a copy of image with the VIN-plate inset flattened to the image's mean
    color, so its sharp rectangular edges don't inflate the edge-density prefilter or
    distract the damage classifier/detector."""
    out = image.copy()
    box = _box_px(image, region_fraction)
    fill = tuple(int(c) for c in ImageStat.Stat(out).mean[:3])
    out.paste(Image.new("RGB", (box[2] - box[0], box[3] - box[1]), fill), box)
    return out
