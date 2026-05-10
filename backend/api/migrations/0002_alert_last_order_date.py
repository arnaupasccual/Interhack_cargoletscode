from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='alert',
            name='last_order_date',
            field=models.DateField(
                blank=True,
                null=True,
                help_text='Date of the last order placed by the client for this family',
            ),
        ),
    ]
