# The `subject` field is already created by 0003, so this unconditional AddField
# failed on fresh databases. The later 0007 migration still adjusts the field.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("predictor", "0005_add_syllabus_subject"),
    ]

    operations = []
