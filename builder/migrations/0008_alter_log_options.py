# Generated by Django 4.1.2 on 2022-11-14 05:14

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('builder', '0007_alter_build_table_alter_log_table'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='log',
            options={'ordering': ('id',)},
        ),
    ]
