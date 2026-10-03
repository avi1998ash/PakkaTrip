"""Package photos and facilities — validation and saving.

Images arrive as multipart files. Each one is opened with Pillow, checked, resized to at most
1600px and re-encoded as JPEG. Re-encoding also strips EXIF data, which on phone photos often
includes the GPS location of the operator's home or office.
"""
import io
import json
import uuid

from django.core.files.base import ContentFile
from django.db import transaction
from PIL import Image, UnidentifiedImageError

from .models import STANDARD_FACILITIES, PackageFacility, PackageImage, PackageItineraryDay

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_SIDE = 1600
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


class MediaError(Exception):
    """Shown to the operator as-is."""


def _process_upload(f):
    if f.size > MAX_UPLOAD_BYTES:
        raise MediaError(f"“{f.name}” is larger than 5 MB.")
    try:
        img = Image.open(f)
        img.verify()            # cheap integrity check…
        f.seek(0)
        img = Image.open(f)     # …then reopen to actually decode
        if img.format not in ALLOWED_FORMATS:
            raise MediaError(f"“{f.name}” must be a JPG, PNG or WebP image.")
        img.load()
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise MediaError(f"“{f.name}” is not a valid image.")
    if min(img.size) < 300:
        raise MediaError(f"“{f.name}” is too small — use photos at least 300px on each side.")
    img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=85, optimize=True)
    return ContentFile(out.getvalue(), name=f"{uuid.uuid4().hex}.jpg")


def parse_json(value, default):
    if value in (None, ""):
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        raise MediaError("Malformed form data — please reload the page and try again.")


def clean_facilities(raw):
    """{category: [labels]} → validated, de-duplicated dict."""
    if not isinstance(raw, dict):
        raise MediaError("Malformed facilities.")
    out = {}
    for cat, labels in raw.items():
        if cat not in STANDARD_FACILITIES or not isinstance(labels, list):
            continue
        seen, clean = set(), []
        for label in labels:
            label = " ".join(str(label).split())[:80]
            if label and label.lower() not in seen:
                seen.add(label.lower())
                clean.append(label)
        if len(clean) > 30:
            raise MediaError("Too many items in one facilities section (max 30).")
        out[cat] = clean
    return out


@transaction.atomic
def save_images(package, order, cover, new_files):
    """order: tokens in display order — "e:<id>" (existing image) or "n:<i>" (i-th uploaded file)."""
    if not isinstance(order, list):
        raise MediaError("Malformed image list.")
    if not PackageImage.MIN <= len(order) <= PackageImage.MAX:
        raise MediaError(f"Add between {PackageImage.MIN} and {PackageImage.MAX} photos (you have {len(order)}).")
    if cover not in order:
        cover = order[0]
    existing = {f"e:{img.id}": img for img in package.images.all()}
    processed = {}
    for token in order:   # validate everything before touching the database or disk
        kind, _, ref = str(token).partition(":")
        if kind == "e" and token not in existing:
            raise MediaError("One of the photos no longer exists — please reload the page.")
        if kind == "n":
            try:
                processed[token] = _process_upload(new_files[int(ref)])
            except (ValueError, IndexError):
                raise MediaError("A photo upload went missing — please try again.")
        elif kind != "e":
            raise MediaError("Malformed image list.")

    for token, img in existing.items():
        if token not in order:
            img.delete()
    package.images.update(is_cover=False)
    for i, token in enumerate(order):
        if token in existing:
            img = existing[token]
            img.sort_order, img.is_cover = i, token == cover
            img.save(update_fields=["sort_order", "is_cover"])
        else:
            PackageImage.objects.create(package=package, image=processed[token], sort_order=i, is_cover=token == cover)


@transaction.atomic
def save_facilities(package, facilities):
    package.facilities.all().delete()
    PackageFacility.objects.bulk_create([
        PackageFacility(package=package, category=cat, label=label, sort_order=i)
        for cat, labels in facilities.items() for i, label in enumerate(labels)
    ])


def clean_itinerary(raw, nights):
    """[{title, text}] → at most nights+1 days; blank days are dropped."""
    if not isinstance(raw, list):
        raise MediaError("Malformed itinerary.")
    days = []
    for d in raw[: int(nights) + 1]:
        title = " ".join(str((d or {}).get("title", "")).split())[:140]
        text = str((d or {}).get("text", "")).strip()[:1500]
        if title:
            days.append((title, text))
    return days


@transaction.atomic
def save_itinerary(package, days):
    package.itinerary.all().delete()
    PackageItineraryDay.objects.bulk_create([PackageItineraryDay(package=package, day_number=i + 1, title=t, description=x)
                                             for i, (t, x) in enumerate(days)])


def itinerary_out(package):
    return [{"day": d.day_number, "title": d.title, "text": d.description} for d in package.itinerary.all()]


def images_out(package, request=None):
    return [{"id": img.id, "url": img.image.url, "is_cover": img.is_cover} for img in package.images.all()]


def facilities_out(package):
    out = {cat: [] for cat in STANDARD_FACILITIES}
    for f in package.facilities.all():
        out[f.category].append(f.label)
    return out
