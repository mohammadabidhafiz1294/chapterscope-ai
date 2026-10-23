# Originally MySQL-only patches that added columns already created by 0001/0003.
# They were redundant and contained vendor-specific SQL that could not run on
# SQLite or PostgreSQL. Kept as a no-op to preserve the migration graph.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("predictor", "0007_alter_syllabus_subject"),
    ]

    operations = []
