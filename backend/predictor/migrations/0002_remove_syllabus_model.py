# Generated manually for removing syllabus functionality

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('predictor', '0001_initial'),
    ]

    operations = [
        # Update Topic model to reference ExamPaper instead of Syllabus
        migrations.AddField(
            model_name='topic',
            name='exam_paper',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='topics',
                to='predictor.exampaper',
                null=True  # Temporary for migration
            ),
        ),

        # Update Prediction model to reference ExamPaper instead of Syllabus
        migrations.AddField(
            model_name='prediction',
            name='exam_paper',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='predictions',
                to='predictor.exampaper',
                null=True  # Temporary for migration
            ),
        ),

        # Remove unique_together constraint first
        migrations.AlterUniqueTogether(
            name='topic',
            unique_together=set(),
        ),

        # Remove old foreign key fields
        migrations.RemoveField(
            model_name='topic',
            name='syllabus',
        ),
        migrations.RemoveField(
            model_name='prediction',
            name='syllabus',
        ),

        # Make the new fields non-nullable
        migrations.AlterField(
            model_name='topic',
            name='exam_paper',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='topics',
                to='predictor.exampaper',
            ),
        ),
        migrations.AlterField(
            model_name='prediction',
            name='exam_paper',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='predictions',
                to='predictor.exampaper',
            ),
        ),

        # Add new unique constraint
        migrations.AlterUniqueTogether(
            name='topic',
            unique_together={('exam_paper', 'name')},
        ),

        # Remove Syllabus model
        migrations.DeleteModel(
            name='Syllabus',
        ),
    ]
