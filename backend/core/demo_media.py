"""Demo photos and facilities for the seeded packages.

The photos are simple drawn scenes (no stock photos are bundled) so the gallery works out of the box.
"""
import io
import shutil
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image, ImageDraw, ImageFont

from catalog.models import PackageFacility, PackageImage

# theme, then facilities: meals, accommodation, transport, activities, places, other
DEMO = {
    "PK201": ("mountain", ["Breakfast", "Dinner"], ["Hotel"], ["AC bus (Volvo)"], ["Sightseeing tour", "Bonfire"],
              ["Solang Valley", "Old Manali", "Hadimba Temple", "Vashisht hot springs"], ["Trip captain"]),
    "PK202": ("river", ["Lunch", "Dinner", "Breakfast"], ["Camp / tent"], ["Tempo Traveller"], ["Rafting", "Bonfire", "Camping"],
              ["Shivpuri", "Laxman Jhula", "Triveni Ghat"], ["Trip captain", "First aid kit"]),
    "PK203": ("mountain", ["Breakfast", "Dinner"], ["Camp / tent"], ["AC bus (Volvo)", "Cab"], ["Trekking", "Camping"],
              ["Kasol", "Kheerganga", "Manikaran Sahib"], ["Trip captain"]),
    "PK204": ("lake", ["Breakfast", "Dinner"], ["Hotel"], ["Non-AC bus"], ["Boating", "Sightseeing tour"],
              ["City Palace", "Lake Pichola", "Bagore ki Haveli", "Fateh Sagar"], ["Entry tickets"]),
    "PK205": ("mountain", ["Breakfast", "Dinner"], ["Hotel"], ["Tempo Traveller"], ["Sightseeing tour"],
              ["The Ridge", "Mall Road", "Kufri", "Green Valley"], []),
    "PK206": ("temple", ["Breakfast", "Dinner"], ["Hotel"], ["Tempo Traveller"], ["Boating", "Sightseeing tour"],
              ["Kashi Vishwanath", "Dashashwamedh Ghat", "Sarnath"], ["Trip captain"]),
    "PK207": ("forest", ["Breakfast", "Lunch", "Dinner"], ["Resort"], ["Tempo Traveller"], ["Jeep safari", "Bonfire"],
              ["Jhirna zone", "Corbett Falls", "Kosi river"], ["Entry tickets"]),
    "PK208": ("beach", ["Breakfast", "Dinner"], ["Resort"], ["Non-AC bus"], ["Boating", "Sightseeing tour"],
              ["Baga & Calangute", "Fort Aguada", "Old Goa churches", "Anjuna market"], []),
    "PK209": ("mountain", ["Breakfast", "Dinner"], ["Hotel"], ["Tempo Traveller"], ["Sightseeing tour"],
              ["Kempty Falls", "Mall Road", "Gun Hill", "Company Garden"], []),
    "PK210": ("temple", ["Breakfast", "Lunch", "Dinner"], ["Hotel", "Camp / tent"], ["Tempo Traveller"], ["Trekking"],
              ["Guptkashi", "Gaurikund", "Kedarnath Temple"], ["Trip captain", "First aid kit"]),
    "PK211": ("mountain", ["Breakfast", "Dinner"], ["Homestay"], ["AC bus (Volvo)", "Tempo Traveller"], ["Sightseeing tour"],
              ["Sangla", "Chitkul", "Kamru Fort"], ["Trip captain"]),
    "PK212": ("city", ["Breakfast", "Dinner"], ["Hotel"], ["Tempo Traveller"], ["Sightseeing tour"],
              ["Amber Fort", "Hawa Mahal", "City Palace", "Chokhi Dhani"], ["Entry tickets"]),
    "PK213": ("mountain", ["Breakfast", "Dinner"], ["Hotel"], ["AC bus (Volvo)"], ["Sightseeing tour"],
              ["Dalai Lama Temple", "Bhagsu waterfall", "HPCA stadium", "Norbulingka"], []),
    "PK214": ("mountain", ["Breakfast", "Dinner"], ["Hotel"], ["AC bus (Volvo)"], ["Sightseeing tour", "Paragliding"],
              ["Atal Tunnel", "Sissu", "Mall Road", "Club House"], []),
    "PK215": ("river", ["Breakfast", "Dinner"], ["Hotel"], ["AC bus (Volvo)", "Tempo Traveller"], ["Sightseeing tour", "Bonfire"],
              ["Solang Valley", "Atal Tunnel", "Kasol", "Manikaran Sahib"], ["Trip captain"]),
    "PK216": ("city", ["Breakfast", "Dinner"], ["Camp / tent"], ["Tempo Traveller"], ["Camping"], ["Brahma Temple", "Pushkar Lake"], []),
    "PK217": ("beach", ["Breakfast", "Dinner"], ["Resort"], ["Non-AC bus"], ["Jeep safari"], ["Dudhsagar Falls", "Palolem", "Colva"], []),
}

PALETTES = {  # sky top, sky bottom, far, near
    "mountain": ((141, 184, 232), (255, 217, 168), (127, 157, 201), (47, 78, 126)),
    "river": ((247, 178, 103), (255, 227, 179), (111, 156, 126), (46, 94, 78)),
    "lake": ((233, 138, 91), (250, 212, 166), (122, 62, 46), (62, 109, 156)),
    "beach": ((190, 227, 248), (255, 232, 194), (43, 140, 196), (243, 215, 161)),
    "forest": ((159, 203, 138), (231, 243, 216), (123, 174, 107), (36, 86, 58)),
    "temple": ((242, 140, 40), (255, 211, 155), (91, 42, 26), (196, 106, 43)),
    "city": ((244, 154, 106), (255, 207, 158), (201, 123, 74), (126, 63, 31)),
}


def _scene(theme, variant, caption):
    w, h = 1200, 800
    top, bottom, far, near = PALETTES[theme]
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):   # sky gradient
        t = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    shift = variant * 140
    d.ellipse([820 - shift, 120, 940 - shift, 240], fill=(255, 243, 214))
    far_pts = [(0, 470)] + [(x, 300 + ((x * 7 + shift) % 230)) for x in range(0, w + 1, 150)] + [(w, h), (0, h)]
    d.polygon(far_pts, fill=far)
    near_pts = [(0, 600)] + [(x, 520 + ((x * 13 + shift * 2) % 160)) for x in range(0, w + 1, 200)] + [(w, h), (0, h)]
    d.polygon(near_pts, fill=near)
    try:
        font = ImageFont.truetype("arial.ttf", 44)
    except OSError:
        font = ImageFont.load_default()
    d.rectangle([0, h - 90, w, h], fill=(11, 46, 89))
    d.text((w / 2, h - 45), caption, fill=(255, 255, 255), font=font, anchor="mm")   # centred, so cropping keeps it readable
    out = io.BytesIO()
    img.save(out, "JPEG", quality=80)
    return out.getvalue()


def wipe_media():
    folder = Path(settings.MEDIA_ROOT) / "packages"
    if folder.is_dir():
        shutil.rmtree(folder)


def add_demo_media(pkgs):
    """pkgs: {"PK201": Package, …}"""
    for key, pkg in pkgs.items():
        theme, *sections = DEMO[key]
        places = sections[4]
        for i in range(4):
            caption = f"{pkg.title} · {places[i % len(places)]}"
            PackageImage.objects.create(package=pkg, sort_order=i, is_cover=i == 0,
                                        image=ContentFile(_scene(theme, i, caption), name=f"demo-{i + 1}.jpg"))
        cats = ["meals", "accommodation", "transport", "activities", "places", "other"]
        PackageFacility.objects.bulk_create([
            PackageFacility(package=pkg, category=cat, label=label, sort_order=j)
            for cat, labels in zip(cats, sections) for j, label in enumerate(labels)
        ])
