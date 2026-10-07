from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class City(models.Model):
    name = models.CharField(max_length=80)
    state = models.CharField(max_length=60, blank=True, default="")
    slug = models.SlugField(max_length=90, unique=True)
    is_popular = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "cities"
        ordering = ["name"]

    @classmethod
    def by_name(cls, name):
        """Find a city case-insensitively, or create it (admins and operators type city names freely)."""
        name = " ".join(name.split())
        city = cls.objects.filter(name__iexact=name).first()
        return city or cls.objects.create(name=name, slug=unique_slug(cls, name))

    def __str__(self):
        return self.name


def unique_slug(model, text, max_len=140):
    base = slugify(text)[: max_len - 6] or "item"
    slug, n = base, 2
    while model.objects.filter(slug=slug).exists():
        slug, n = f"{base}-{n}", n + 1
    return slug


class ActivePackageManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class Package(models.Model):
    """A trip product an operator sells, e.g. Manali Weekend Escape."""

    class Status(models.TextChoices):
        DRAFT = "draft"
        PENDING_REVIEW = "pending_review"
        APPROVED = "approved"
        REJECTED = "rejected"
        UNLISTED = "unlisted"

    operator = models.ForeignKey("operators.Operator", on_delete=models.PROTECT, related_name="packages")
    title = models.CharField(max_length=120)
    slug = models.SlugField(max_length=160, unique=True)
    from_city = models.ForeignKey(City, on_delete=models.PROTECT, related_name="+")
    to_city = models.ForeignKey(City, on_delete=models.PROTECT, related_name="+")
    nights = models.PositiveSmallIntegerField()
    price_per_person = models.DecimalField(max_digits=10, decimal_places=2)
    default_seats = models.PositiveSmallIntegerField(default=20)
    summary = models.TextField(blank=True, default="")
    pickup_point = models.CharField(max_length=160, blank=True, default="")   # e.g. "Majnu ka Tilla, Delhi · 7:30 PM"
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING_REVIEW, db_index=True)
    rejection_reason = models.TextField(blank=True, default="")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)
    rating_avg = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    rating_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)   # soft delete keeps booking history intact

    objects = ActivePackageManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "packages"
        ordering = ["-created_at"]
        base_manager_name = "all_objects"   # related lookups (booking.package) still see soft-deleted rows
        indexes = [models.Index(fields=["from_city", "to_city", "status"])]
        constraints = [
            models.CheckConstraint(condition=models.Q(nights__lte=15), name="nights_0_15"),
            models.CheckConstraint(condition=models.Q(price_per_person__gt=0), name="price_positive"),
            models.CheckConstraint(condition=models.Q(default_seats__gte=1, default_seats__lte=80), name="default_seats_1_80"),
        ]

    def __str__(self):
        return self.title


def package_image_path(instance, filename):
    return f"packages/{instance.package_id}/{filename}"


class PackageImage(models.Model):
    """Photos for a package. Files live in MEDIA_ROOT/packages/<package id>/."""
    MIN, MAX = 1, 8

    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to=package_image_path)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_cover = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "package_images"
        ordering = ["sort_order", "id"]
        constraints = [models.UniqueConstraint(fields=["package"], condition=models.Q(is_cover=True), name="one_cover_per_package")]

    def delete(self, *args, **kwargs):
        storage, name = self.image.storage, self.image.name
        super().delete(*args, **kwargs)
        if name:
            storage.delete(name)


class PackageItineraryDay(models.Model):
    """Day-wise plan shown on the trip page."""
    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name="itinerary")
    day_number = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=140)
    description = models.TextField(blank=True, default="")

    class Meta:
        db_table = "package_itinerary_days"
        ordering = ["day_number"]
        constraints = [models.UniqueConstraint(fields=["package", "day_number"], name="one_row_per_day")]


class PackageFacility(models.Model):
    """What's included: meals, stay, transport, activities, places visited, other."""

    class Category(models.TextChoices):
        MEALS = "meals", "Meals"
        ACCOMMODATION = "accommodation", "Accommodation"
        TRANSPORT = "transport", "Transport"
        ACTIVITIES = "activities", "Activities"
        PLACES = "places", "Visiting places"
        OTHER = "other", "Other"

    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name="facilities")
    category = models.CharField(max_length=15, choices=Category.choices)
    label = models.CharField(max_length=80)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "package_facilities"
        ordering = ["category", "sort_order", "id"]
        constraints = [models.UniqueConstraint(fields=["package", "category", "label"], name="unique_facility_per_package")]


# Standard choices shown as checkboxes in the operator form (places and custom "other" items are free text).
STANDARD_FACILITIES = {
    "meals": ["Breakfast", "Lunch", "Dinner", "Evening snacks", "Welcome drink"],
    "accommodation": ["Hotel", "Homestay", "Resort", "Camp / tent", "Dormitory"],
    "transport": ["AC bus (Volvo)", "Non-AC bus", "Tempo Traveller", "Cab", "Train tickets", "Pickup & drop"],
    "activities": ["Trekking", "Rafting", "Paragliding", "Bonfire", "Camping", "Jeep safari", "Boating", "Sightseeing tour"],
    "places": [],
    "other": ["Trip captain", "First aid kit", "Entry tickets", "Travel insurance"],
}
