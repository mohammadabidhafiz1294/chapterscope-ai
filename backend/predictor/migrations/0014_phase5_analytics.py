"""Phase 5 analytics: aliases, review status, label provenance, paper totals.

Additive only. Every new column carries a model default that preserves the
meaning of existing rows: topic/question links created before this phase keep
``CONFIRMED`` with ``classification_source=MANUAL`` and are therefore counted
by analytics exactly as before; type labels are left ``type_review_status=""``
(nothing pending) so pre-existing ``question_type`` values keep counting;
``ExamPaper.total_marks`` starts ``NULL`` for every paper and is derived at
read time until an operator sets it. No backfill is run and no existing
column is altered.
"""

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("predictor", "0013_phase4_rag"),
    ]

    operations = [
        migrations.AddField(
            model_name="exampaper",
            name="total_marks",
            field=models.PositiveIntegerField(
                blank=True,
                help_text=(
                    "Total marks of the paper. When blank, analytics "
                    "derives it from the sum of parsed question marks "
                    "and flags it as derived."
                ),
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="notebooktopic",
            name="aliases",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="notebooktopic",
            name="review_status",
            field=models.CharField(
                choices=[("CONFIRMED", "Confirmed"), ("NEEDS_REVIEW", "Needs review")],
                db_index=True,
                default="CONFIRMED",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="question",
            name="type_classifier_version",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="question",
            name="type_confidence",
            field=models.FloatField(
                blank=True,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(0.0),
                    django.core.validators.MaxValueValidator(1.0),
                ],
            ),
        ),
        migrations.AddField(
            model_name="question",
            name="type_review_status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "None"),
                    ("NEEDS_REVIEW", "Needs review"),
                    ("CONFIRMED", "Confirmed"),
                ],
                db_index=True,
                default="",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="question",
            name="type_source",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "Unset"),
                    ("RULE", "Rule-based"),
                    ("LLM", "LLM"),
                    ("MANUAL", "Manual"),
                ],
                default="",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="questiontopic",
            name="classification_source",
            field=models.CharField(
                choices=[
                    ("MANUAL", "Manual"),
                    ("RULE", "Rule-based"),
                    ("ALIAS", "Alias match"),
                    ("LLM", "LLM"),
                ],
                default="MANUAL",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="questiontopic",
            name="classifier_version",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="questiontopic",
            name="review_status",
            field=models.CharField(
                choices=[
                    ("CONFIRMED", "Confirmed"),
                    ("NEEDS_REVIEW", "Needs review"),
                    ("REJECTED", "Rejected"),
                ],
                db_index=True,
                default="CONFIRMED",
                max_length=16,
            ),
        ),
    ]
