# -*- coding: utf-8 -*-
# Generated by Django 1.11.2 on 2017-10-04 21:54
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('django_celery_beat', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='periodictask',
            name='name',
            field=models.CharField(help_text='Useful description', max_length=200, unique=True, verbose_name='name'),
        ),
    ]
