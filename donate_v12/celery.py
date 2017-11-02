from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from django.conf import settings

# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'donate_v12.settings')


class SDCelery(Celery):
    pass

    def gen_task_name(self, name, module):
        print "Name: %s, Module: %s" % (name, module)
        if module.endswith('.tasks'):
            module = module[:-6]
        return super(SDCelery, self).gen_task_name(name, module)


app = Celery(settings.PROJECT_NAME)
# app = SDCelery(settings.PROJECT_NAME)

# Using a string here means the worker don't have to serialize the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')
# Optional configuration, see the application user guide.
# app.conf.update(
    # timezone='Africa/Lagos',
    # result_expires=3600,
# )

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print('Request: {0!r}'.format(self.request))