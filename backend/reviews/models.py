from django.conf import settings
from django.db import models
from django.db.models import Avg, Count
from django.utils import timezone


class Review(models.Model):
    """Traveller review — one per completed booking, which proves a real trip."""
    booking = models.OneToOneField("bookings.Booking", on_delete=models.PROTECT, related_name="review")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    package = models.ForeignKey("catalog.Package", on_delete=models.PROTECT, related_name="reviews")
    operator = models.ForeignKey("operators.Operator", on_delete=models.PROTECT, related_name="reviews")
    reviewer_name = models.CharField(max_length=100)
    rating = models.PositiveSmallIntegerField()
    comment = models.TextField()
    operator_reply = models.TextField(blank=True, default="")
    replied_at = models.DateTimeField(null=True, blank=True)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "reviews"
        ordering = ["-created_at"]
        constraints = [models.CheckConstraint(condition=models.Q(rating__gte=1, rating__lte=5), name="rating_1_5")]


def refresh_ratings(package, operator):
    """Recompute the cached rating on the package and the operator."""
    for obj, qs in ((package, Review.objects.filter(package=package, is_published=True)),
                    (operator, Review.objects.filter(operator=operator, is_published=True))):
        agg = qs.aggregate(avg=Avg("rating"), n=Count("id"))
        obj.rating_avg = round(agg["avg"] or 0, 2)
        obj.rating_count = agg["n"]
        obj.save(update_fields=["rating_avg", "rating_count"])
