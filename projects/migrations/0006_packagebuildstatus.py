# Generated by Django 4.1.2 on 2022-11-05 10:20

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0005_project_git_private_token'),
    ]

    operations = [
        migrations.CreateModel(
            name='PackageBuildStatus',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('branchname', models.CharField(max_length=250)),
                ('sourcehash', models.CharField(max_length=250)),
                ('dirty', models.BooleanField(default=False)),
                ('package', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='projects.package')),
            ],
        ),
    ]
