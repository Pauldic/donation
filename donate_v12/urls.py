"""donate_v6 URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.10/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
# import notifications
import notifications.urls
from django.conf.urls import url, include
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import urls
from django.contrib.auth import views
from core import views as core_view

from core.forms import LoginForm
from django.conf import settings

urlpatterns = [
    url(r'^'+settings.ADMIN_URL, admin.site.urls),
    url(r'^', include('core.url')),
    url(r'^captcha/', include('captcha.urls')),
    url(r'^social/auth/', include('social_django.urls', namespace='social')),  #
    # url(r'^support/', include('support.urls')),

    # r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)"

    url(r'^password/reset.jsf$', views.password_reset, {'post_reset_redirect': '/password/reset/done/', 'template_name': 'password/password_reset_form.html'}, name="password_reset"),
    url(r'^password/reset/done/$', views.password_reset_done),
    url(r'^password/reset/(?P<uidb36>[0-9A-Za-z]+)-(?P<token>.+)/$', views.password_reset_confirm, {'post_reset_redirect' : '/password/done/'}),
    url(r'^user/password/done/$', views.password_reset_complete),

    url('^inbox/notifications/', include(notifications.urls, namespace='notifications')),
    url(r'^messages/', include('postman.urls', namespace='postman', app_name='postman')),
]
if settings.DEBUG:
    urlpatterns = urlpatterns + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler400 = core_view.handle400
handler404 = core_view.handle404
handler500 = core_view.handle500

# Change admin site title
# admin.site.site_header = _("Site Administration")
# admin.site.site_title = _("My Site Admin")

admin.site.site_header = "Administration"
admin.site.site_title = "%s Admin" %settings.COY_NAME