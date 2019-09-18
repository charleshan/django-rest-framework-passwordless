# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import drfpasswordless.models


class Migration(migrations.Migration):

    dependencies = [
        ('drfpasswordless', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='callbacktoken',
            name='key',
            field=models.CharField(default=drfpasswordless.models.generate_numeric_token, max_length=6),
        ),
    ]
