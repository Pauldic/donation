import logging

from django.conf import settings
from django.core.exceptions import SuspiciousOperation
from django.core.urlresolvers import reverse
from django.template import loader

from social_core.exceptions import InvalidEmail, AuthCanceled
from social_core.pipeline.partial import partial
from social_core.backends.google import GooglePlusAuth
from social_core.backends.utils import load_backends
from social_django.middleware import SocialAuthExceptionMiddleware
from social_django.models import UserSocialAuth
from social_django.utils import psa, load_strategy

from core.models import EmailCycler, Member
from core.utils import get_str_conf, get_bool_conf

log = logging.getLogger(settings.PROJECT_NAME+"*")
log.setLevel(settings.DEBUG)


def get_profile_picture(backend, strategy, details, response, user=None, *args, **kwargs):
    url = None
    try:
        if backend.name == 'facebook':
            url = "https://graph.facebook.com/%s/picture?type=large"%response['id']
            # print "Gender: "+response.get('gender')
            # print "Link: "+response.get('link')
            # print "Timezone: "+response.get('timezone')
        elif backend.name == 'twitter':
            url = response.get('profile_image_url', '').replace('_normal','')
        elif backend.name == 'google-oauth2':
            url = response['image'].get('url')
            size = url.split('=')[-1]
            url = url.replace(size, '240')
        elif backend.name == 'github':
            url = response['avatar_url']

        if url:
            user.avatar_url = url
            user.save()
    except:
        print "error....."



@partial
def require_email(strategy, details, user=None, is_new=False, *args, **kwargs):
    if kwargs.get('ajax') or user and user.email:
        return
    elif is_new and not details.get('email'):
        email = strategy.request_data().get('email')
        if email:
            details['email'] = email
        else:
            current_partial = kwargs.get('current_partial')
            # return strategy.redirect('/email?partial_token={0}'.format(current_partial.token))
            # details['force_mail_validation']=True
            # strategy.REQUIRES_EMAIL_VALIDATION = True
            return strategy.redirect('/Email Required?partial_token={0}'.format(current_partial.token))
            # return {strategy: strategy.redirect('/Email Required?partial_token={0}'.format(current_partial.token)), force_mail_validation: True}


@partial
def force_mail_validation(backend, details, user=None, is_new=False, *args, **kwargs):
    # usa = UserSocialAuth(provider=backend.name, uid=2)
    existing_usa = UserSocialAuth.objects.filter(provider=backend.name, uid=kwargs.get('uid')).count()
    new_association = kwargs.get('new_association')
    data = backend.strategy.request_data()
    if new_association and 'verification_code' not in data and existing_usa == 0:
        current_partial = kwargs.get('current_partial')
        backend.strategy.send_email_validation(backend, details['email'], current_partial.token)
        backend.strategy.session_set('email_validation_address', details['email'])
        url = "{0}?email={1}".format(backend.strategy.setting('EMAIL_VALIDATION_URL'), details['email'])
        return backend.strategy.redirect(backend.strategy.request.build_absolute_uri(url))
    elif new_association and 'verification_code' in data:
        backend.REQUIRES_EMAIL_VALIDATION = True
    return


def send_validation(strategy, backend, code, partial_token):
    url = '{0}?verification_code={1}&partial_token={2}'.format(reverse('social:complete', args=(backend.name,)), code.code, partial_token)
    url = strategy.request.build_absolute_uri(url)
    print url
    html_message = loader.render_to_string('core/mail_templates/activation.html',  {'firstName': "", 'lastName': "", 'email': code.email, 'username': "",
                                                                                    'token': code.code, 'sponsor': settings.DEFAULT_SPONSOR, 'url': url})
    from core.tasks import sendMail
    sendMail.apply_async(
        kwargs={'subject': get_str_conf(22, None, default="Account Activation"), 'message': "Hello,\n this is your token xyz", 'recipients': [{"Email": code.email, "Name": ""}],
                'fail_silently': False, 'html_message': html_message, 'connection_label': EmailCycler.get_email_label()})


@partial
def mail_validation_member(backend, details, is_new=False, *args, **kwargs):
    requires_validation = backend.REQUIRES_EMAIL_VALIDATION or backend.setting('FORCE_EMAIL_VALIDATION', False)
    send_validation = details.get('email') and (is_new or backend.setting('PASSWORDLESS', False))
    data = backend.strategy.request_data()
    if requires_validation and send_validation:
        data = backend.strategy.request_data()
        if 'verification_code' in data:
            backend.strategy.session_pop('email_validation_address')
            if not backend.strategy.validate_email(details['email'], data['verification_code']):
                raise InvalidEmail(backend)
            else:
                try:
                    me = Member.objects.filter(email=details['email']).first()
                    me.is_email_verified = True
                    if get_bool_conf(1020, me.country, False):
                        if me.is_phone_verified:
                            me.is_phone_verified = True
                            me.status = "Active"
                    else:
                        me.status = "Active"
                    me.save()
                except:
                    pass
        else:
            current_partial = kwargs.get('current_partial')
            backend.strategy.send_email_validation(backend, details['email'], current_partial.token)
            backend.strategy.session_set('email_validation_address', details['email'])
            return backend.strategy.redirect(backend.strategy.setting('EMAIL_VALIDATION_URL'))


def is_authenticated(user):
    if callable(user.is_authenticated):
        return user.is_authenticated()
    else:
        return user.is_authenticated


def associations(user, strategy):
    user_associations = strategy.storage.user.get_social_auth_for_user(user)
    if hasattr(user_associations, 'all'):
        user_associations = user_associations.all()
    return list(user_associations)


def common_context(authentication_backends, strategy, user=None, plus_id=None, **extra):
    """Common view context"""
    context = {
        'user': user,
        'available_backends': load_backends(authentication_backends),
        'associated': {}
    }

    if user and is_authenticated(user):
        context['associated'] = dict((association.provider, association)
                                     for association in associations(user, strategy))

    if plus_id:
        context['plus_id'] = plus_id
        context['plus_scope'] = ' '.join(GooglePlusAuth.DEFAULT_SCOPE)

    return dict(context, **extra)


def url_for(name, **kwargs):
    if name == 'social:begin':
        url = '/login/{backend}/'
    elif name == 'social:complete':
        url = '/complete/{backend}/'
    elif name == 'social:disconnect':
        url = '/disconnect/{backend}/'
    elif name == 'social:disconnect_individual':
        url = '/disconnect/{backend}/{association_id}/'
    else:
        url = name
    return url.format(**kwargs)


def get_username_lower(strategy, details, backend, user=None, *args, **kwargs):
    from social_core.pipeline.user import get_username
    return {'username': get_username(strategy, details, backend, user=None, *args, **kwargs)['username'].lower()}


