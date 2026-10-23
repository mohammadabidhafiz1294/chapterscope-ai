# Originally a MySQL-only repair that ensured the syllabus columns introduced by
# 0003 existed. The declarative operations in 0003 already create this schema, so
# the raw information_schema/PREPARE SQL was redundant and blocked SQLite and
# PostgreSQL. Kept as a no-op to preserve the migration graph.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("predictor", "0003_syllabus_alter_topic_unique_together_and_more"),
    ]

    operations = []
