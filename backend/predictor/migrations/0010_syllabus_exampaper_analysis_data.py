import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("predictor", "0009_alter_exampaper_year"),
    ]

    operations = [
        migrations.AddField(
            model_name="syllabus",
            name="analysis_data",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="exampaper",
            name="analysis_data",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name="exampaper",
            name="year",
            field=models.PositiveIntegerField(
                help_text="Year of the exam paper",
                validators=[
                    django.core.validators.MinValueValidator(1900),
                    django.core.validators.MaxValueValidator(2100),
                ],
            ),
        ),
    ]
