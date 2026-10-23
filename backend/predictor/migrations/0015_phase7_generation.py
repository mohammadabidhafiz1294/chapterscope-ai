"""Phase 7 practice-question generation: requests + generated-question provenance.

Additive only. Creates ``GenerationRequest`` (one generated paper) and adds
Phase 7 provenance/validation columns to the pre-existing
``GeneratedQuestion`` table. Every new column carries a default that keeps
the meaning of existing rows: ``request`` is NULL and ``validation_status``
starts at ``NEEDS_REVIEW`` for any legacy generated question, and all the
new JSON/text fields default to empty. No backfill is run and no existing
column is altered.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("predictor", "0014_phase5_analytics"),
    ]

    operations = [
        migrations.CreateModel(
            name="GenerationRequest",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("topic_ids", models.JSONField(blank=True, default=list)),
                ("question_count", models.PositiveIntegerField(default=5)),
                ("question_types", models.JSONField(blank=True, default=list)),
                (
                    "difficulty",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("easy", "Easy"),
                            ("medium", "Medium"),
                            ("hard", "Hard"),
                            ("", "Unspecified"),
                        ],
                        default="",
                        max_length=10,
                    ),
                ),
                ("marks", models.PositiveIntegerField(blank=True, null=True)),
                ("language", models.CharField(blank=True, default="en", max_length=20)),
                ("include_answers", models.BooleanField(default=True)),
                ("year_from", models.PositiveIntegerField(blank=True, null=True)),
                ("year_to", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("PROCESSING", "Processing"),
                            ("COMPLETED", "Completed"),
                            ("PARTIAL", "Partial"),
                            ("FAILED", "Failed"),
                        ],
                        default="PENDING",
                        max_length=12,
                    ),
                ),
                ("questions_created", models.PositiveIntegerField(default=0)),
                ("questions_validated", models.PositiveIntegerField(default=0)),
                ("questions_needs_review", models.PositiveIntegerField(default=0)),
                (
                    "generation_model",
                    models.CharField(blank=True, default="", max_length=100),
                ),
                (
                    "generation_version",
                    models.CharField(blank=True, default="", max_length=100),
                ),
                ("request_meta", models.JSONField(blank=True, default=dict)),
                ("error_code", models.CharField(blank=True, default="", max_length=64)),
                ("error_message", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddField(
            model_name="generatedquestion",
            name="answer_confidence",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="generatedquestion",
            name="generation_model",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="generatedquestion",
            name="generation_version",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="generatedquestion",
            name="language",
            field=models.CharField(blank=True, default="en", max_length=20),
        ),
        migrations.AddField(
            model_name="generatedquestion",
            name="marking_rubric",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="generatedquestion",
            name="numeric_report",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="generatedquestion",
            name="options",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="generatedquestion",
            name="topic_ids",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="generatedquestion",
            name="validation_report",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="generatedquestion",
            name="validation_status",
            field=models.CharField(
                choices=[("VALIDATED", "Validated"), ("NEEDS_REVIEW", "Needs review")],
                default="NEEDS_REVIEW",
                max_length=16,
            ),
        ),
        migrations.AddIndex(
            model_name="generatedquestion",
            index=models.Index(
                fields=["notebook", "validation_status"],
                name="genq_notebook_validation_idx",
            ),
        ),
        migrations.AddField(
            model_name="generationrequest",
            name="creator",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="generation_requests",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="generationrequest",
            name="notebook",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="generation_requests",
                to="predictor.coursenotebook",
            ),
        ),
        migrations.AddField(
            model_name="generationrequest",
            name="topic",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="generation_requests",
                to="predictor.notebooktopic",
            ),
        ),
        migrations.AddField(
            model_name="generatedquestion",
            name="request",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="questions",
                to="predictor.generationrequest",
            ),
        ),
        migrations.AddIndex(
            model_name="generationrequest",
            index=models.Index(
                fields=["notebook", "creator"], name="genreq_notebook_creator_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="generationrequest",
            index=models.Index(
                fields=["notebook", "status"], name="genreq_notebook_status_idx"
            ),
        ),
    ]
