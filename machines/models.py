from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator

from builder.models import Build

class Machine(models.Model):
    host = models.CharField(max_length=250)
    port = models.PositiveIntegerField(validators=[ # not validators -> min_value, max_value
        MinValueValidator(0),
        MaxValueValidator(65535),
    ])
    type = models.CharField(max_length=20, choices=[
        ("incus", "Incus"),
        ("docker", "Docker"),
        ("copr", "Copr"),
    ])
    private_key = models.TextField()
    static = models.BooleanField(default = False)
    local = models.BooleanField(default = False)
    priority = models.IntegerField(default = 1)
    cid = models.IntegerField()
    enabled = models.BooleanField(default = True)

    status = models.CharField(max_length=20, default="AVAILABLE", choices=[
        ("AVAILABLE", "AVAILABLE"),
        ("BUILDING", "BUILDING"),
        ("STOPPING", "STOPPING"),
    ])

    # link to the current build running on this machine
    build = models.ForeignKey(Build, on_delete=models.PROTECT, default=None, null=True, blank=True)

    def __str__(self):
        return self.host

    class Meta:
        db_table = "lbs_machine"
        ordering = ("host",)

        constraints = [
            models.UniqueConstraint(fields=["host"],name="unique_host")
        ]
