from django.conf.urls import url
from django.contrib import admin

from core import views
from core.forms import LoginForm
from django.contrib.auth import views as auth
from django.contrib import admin

from django.conf import settings

from core.views import BasicVersionCreateView, BasicPlusVersionCreateView, PictureCreateView, PictureListView, PictureDeleteView, jQueryVersionCreateView, AngularVersionCreateView, POPCreateView

app_name = 'core'
urlpatterns = [
    # url(r'^login$', views.login, name='login'),
    #url(r'^(?P<notification>[\w ,"-_$*&@#%]+)/$', views.home, name='home'),
    url(r'^desktop.gmb$', views.dashboard, name='dashboard'),
    # url(r'^desktop.gmb$', views.dashboard, name='dashboard'),
    url(r'^$', views.home, name='index'),
    url(r'^(?P<email>[\w.%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,4})$', views.home, name='index'),
    url(r'^(?P<sid>[0-9]{11})/$', views.home_register, name='index'),
    url(r'^aboutus.gmb$', views.about, name='aboutus'),
    url(r'^faq.gmb$', views.faq, name='faq'),
    url(r'^referals.gmb$', views.referals, name='referals'),
    url(r'^contactus.gmb$', views.contact, name='contact-us'),
    url(r'^warning.gmb$', views.warning, name='warning'),
    url(r'^screen/locked.gmb$', views.locked, name='locked'),
    url(r'^send/my/credentials.gmb$', views.locked, name='locked'),

    url(r'^email/request/(?P<partial_backend_name>[0-9A-Za-z-]+)/(?P<partial_token>[0-9A-Fa-f-]+)/$', views.email_request_form, name='email-request-form'),
    # url(r'^email/request/(?P<partial_backend_name>[0-9A-Za-z-]+)/$', views.email_request_form, name='email-request-form'),
    # url(r'^email/request/$', views.email_request_form, name='email-request-form'),
    url(r'^email/verify/(?P<email>[\w.%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,4})/(?P<token>[\wA-Za-z0-9]{'+settings.EMAIL_TOKEN_LENGTH+'})/$', views.verify_email, name='verify-email'),
    url(r'^email/resend.gmb$', views.resend_email, name='resend-email'),
    url(r'^code/resend.gmb$', views.resend_phone_verification_code, name='resend-code'),
    url(r'^code/verify/code.gmb$', views.verify_phone_code, name='verify-phone-code'),
    url(r'^sms/verify.gmb$', views.sms_verify, name='sms-verify'),
    url(r'^sms/inbound.gmb$', views.sms_inbound, name='sms-inbound'),
    url(r'^call/incoming/verify.gmb$', views.incoming_call_verify, name='incoming-call-verify'),
    url(r'^call/status.gmb$', views.call_status, name='call-status'),
    url(r'^call/answered.gmb$', views.call_answered, name='call-answered'),
    url(r'^verify/status.gmb$', views.call_sms_status, name='call-sms-status'),
    url(r'^call/verify.gmb$', views.verify_by_call, name='verify-call'),

    url(r'^login.gmb$', auth.login, {'template_name': 'registration/login.html', 'authentication_form': LoginForm}, name="login"),
    url(r'^logout.gmb$', auth.logout, {'next_page': 'core:index'}, name='logout'),
    url(r'^password/change.gmb$', auth.password_change, {'post_change_redirect': 'core:password_change_done'}, name='password_change'),
    url(r'^password/change/done.gmb$', auth.password_change_done, name='password_change_done'),
    url(r'^password/reset.gmb$', auth.password_reset, {'post_reset_redirect': 'core:password_reset_done', 'email_template_name': 'core/mail_templates/password_reset_email.html', 'html_email_template_name': 'core/mail_templates/password_reset_email_html.html'}, name='password_reset'),
    url(r'^password/reset/done.gmb$', auth.password_reset_done, name='password_reset_done'),
    url(r'^password/reset/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$', auth.password_reset_confirm, {'post_reset_redirect': 'core:password_reset_complete'}, name='password_reset_confirm'),
    url(r'^password/reset/complete.gmb$', auth.password_reset_complete, name='password_reset_complete'),



    # url(r'^login/$', views.login, name='login'),
    # url(r'^logout/$', views.logout, name='logout'),
    # url(r'^password_change/$', views.password_change, name='password_change'),
    # url(r'^password_change/done/$', views.password_change_done, name='password_change_done'),
    # url(r'^password_reset/$', views.password_reset, name='password_reset'),
    # url(r'^password_reset/done/$', views.password_reset_done, name='password_reset_done'),
    # url(r'^reset/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$',
    #     views.password_reset_confirm, name='password_reset_confirm'),
    # url(r'^reset/done/$', views.password_reset_complete, name='password_reset_complete'),


    url(r'^register.gmb$', views.register, name='register'),
    url(r'^register/admin/(?P<code>[\w{}.-]{4,20})/$', views.register, name='register-coded'),
    url(r'^register/(?P<sponsor>[\w{}.-]{4,20})/$', views.register, name='register'),
    url(r'^register/admin/(?P<sponsor>[\w{}.-]{4,20})/(?P<code>\d+)/$', views.register, name='register-coded'),

    # url(r'^pre-register/$', views.pre_register, name='pre-register-plain'),
    # url(r'^pre-register/(?P<code>\d+)/$', views.pre_register, name='pre-register-plain-coded'),
    # url(r'^pre-register/(?P<sid>[\w{}.-]{4,20})/$', views.pre_register, name='pre-register'),
    # url(r'^pre-register/(?P<sid>[\w{}.-]{4,20})/(?P<code>\d+)/$', views.pre_register, name='pre-register-coded'),

    # url(r'^(?P<sid>0[7-9]{1}[0-1]{1}[0-9]{8})/pre-register.php$', views.pre_register, name='pre-register-admin'),

    # url(r'^registration/fix/(?P<email>[\w.%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,4})/(?P<username>[\w{}.-]{4,20})/(?P<token>[\wA-Za-z0-9]{16})/(?P<sponsor>[\w{}.-]{4,20})/$', views.pre_register_fix, name='pre-register-fix'),
    # url(r'^(?P<phone>0[7-9]{1}[0-1]{1}[0-9]{8})/pre-register.php$', views.pre_register, name='pre-register-sip'),
    # url(r'^resend/email/(?P<email>[\w.%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,4})/pre-register.php$', views.resend_email, name='re-send-email'),
    # url(r'^resend/email/(?P<username>[\w{}.-]{4,20})/pre-register.php$', views.resend_email, name='re-send-email'),

    # url(r'^registration/(?P<email>[\w.%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,4})/(?P<username>[\w{}.-]{4,20})/(?P<token>[\wA-Za-z0-9]{16})/(?P<sponsor>[\w{}.-]{4,20})/redirector.php$', views.register,  name="registration"),
    # url(r'^registration/phone/verification/request/(?P<email>[\w.%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,4})/(?P<token>[\wA-Za-z0-9]{16})/(?P<phone>0[7-9]{1}[0-1]{1}[0-9]{8})/requester.php$', views.send_phone_verification_code,  name="phone-verify-request"),
    # url(r'^registration/phone/verification/request/(?P<email>[\w.%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,4})/(?P<token>[\wA-Za-z0-9]{16})/(?P<phone>0[7-9]{1}[0-1]{1}[0-9]{8})/(?P<code>[0-9]{6})/v.php$', views.verify_code,  name="phone-verify"),
    # url(r'^registration/request/(?P<email>[\w.%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,4})/(?P<username>[\w{}.-]{4,20})/(?P<token>[\wA-Za-z0-9]{16})/(?P<phone>0[7-9]{1}[0-1]{1}[0-9]{8})/(?P<code>[0-9]{6})/submit.php$', views.register_user,  name="registration-submit"),
            # {% url 'core:registration-submit' email token '08000000000' '000000' %}
    url(r'^(?P<notification>[\w \',]+)/$', views.home, name='home'),


    url(r'^market/converter.gmb$', views.coin_convert, name='coin-converter'),
    url(r'^gh/(?P<bank_account_id>\d+)/board.gmb$', views.gh_board, name='gh-board'),
    url(r'^gh/request.gmb$', views.gh_request, name='gh'),
    url(r'^gh/wallet.gmb$', views.gh_wallet, name='gh-wallet'),
    url(r'^gh/ph/wallet.gmb$', views.gh_ph_wallet, name='gh-ph-wallet'),
    url(r'^gh/wallet/bonus.gmb$', views.gh_wallet_bonus, name='gh-wallet-bonus'),

    url(r'^(?P<first>[\w{}.-]{5,6})/ph.gmb$', views.ph_request, name='ph-4-coin'),
    url(r'^ph/request.gmb$', views.phing, name='ph-request'),
    url(r'^ph/cancel.gmb$', views.cancel_ph, name='cancel-ph'),
    url(r'^(?P<amount>[0-9]{4,7})/ph.gmb$', views.ph_request, name='ph'),
    url(r'^ph.gmb$', views.ph_request, name='ph'),

    url(r'^gmbc/market.gmb$', views.market_place, name='market-place'),

    url(r'^(?P<tdid>%s[0-9]{13,20})/extend/time.gmb$' %settings.TRANSACTION_DETAIL_ID_PREFIX, views.extend_time, name='extend-time'),
    url(r'^(?P<tdid>%s[0-9]{13,20})/block.gmb$' %settings.TRANSACTION_DETAIL_ID_PREFIX, views.block_user, name='account-block'),
    url(r'^(?P<tdid>%s[0-9]{13,20})/cant/pay.gmb$' %settings.TRANSACTION_DETAIL_ID_PREFIX, views.cant_pay, name='cant-pay'),
    url(r'^(?P<tdid>%s[0-9]{13,20})/pay/timeout.gmb$' %settings.TRANSACTION_DETAIL_ID_PREFIX, views.pay_timeout, name='pay-timeout'),
    # url(r'^(?P<tdid>%s[0-9]{13,20})/receiver.gmb$' %settings.TRANSACTION_DETAIL_ID_PREFIX, views.get_receiver, name='receiver-details'),
    # url(r'^upload/proof/(?P<tdid>%s[0-9]{13,20})/payment.gmb$' %settings.TRANSACTION_DETAIL_ID_PREFIX, views.upload_proof_1, name='upload-proof'),
    url(r'^upload/proof/(?P<tdid>%s[0-9]{13,20})/payment.gmb$' %settings.TRANSACTION_DETAIL_ID_PREFIX, POPCreateView.as_view(), name='upload-proof'),
    url(r'^upload/proof/(?P<tdid>%s[0-9]{13,20})/$' % settings.TRANSACTION_DETAIL_ID_PREFIX, POPCreateView.as_view(), name='receiver-details'),
    # url(r'^upload/proof/(?P<tdid>%s[0-9]{13,20})/$' % settings.TRANSACTION_DETAIL_ID_PREFIX, POPCreateView.as_view(), name='upload-proof'),
    url(r'^upload/proof/(?P<tdid>%s[0-9]{13,20})/pay.gmb' %settings.TRANSACTION_DETAIL_ID_PREFIX, views.upload_proof_1, name='pay'),
    url(r'^accept/(?P<tdid>%s[0-9]{13,20})/payment/made.gmb$' %settings.TRANSACTION_DETAIL_ID_PREFIX, views.payment_made, name='payment-made'),
    url(r'^decline/(?P<tdid>%s[0-9]{13,20})/payment.gmb$' %settings.TRANSACTION_DETAIL_ID_PREFIX, views.exception, name='payment-exception'),
    url(r'^confirm/(?P<tdid>%s[0-9]{13,20})/payment.gmb$' %settings.TRANSACTION_DETAIL_ID_PREFIX, views.confirm_payment, name='confirm-payment'),
    url(r'^auto/confirm/(?P<tdid>%s[0-9]{13,20})/(?P<auto>[True]{4})/payment.gmb$' %settings.TRANSACTION_DETAIL_ID_PREFIX, views.confirm_payment, name='auto-confirm-payment'),

    url(r'^%stool/home$' % settings.ADMIN_URL, views.admin_home, name='admin-tool-index'),
    url(r'^account/settings.gmb$', views.account_settings, name='account-settings'),
    url(r'^account/set/password.gmb$', views.set_password, name='set-password'),

    url(r'^naira.gmb$', views.activities, name='account-activities'),
    url(r'^private_account.gmb$', views.my_bank_account, name='bank-account'),
    url(r'^account/update/default.gmb$', views.set_default_account, name='default-account'),
    url(r'^profile.gmb$', views.profile, name='profile'),
    url(r'^api/profile.gmb$', views.profile_json, name='profile-json'),
    # url(r'^test/mail$', views.send_simple_message, name='email'),
    url(r'^activities.gmb$', views.statement, name='statement'),

    url(r'^api/local/v/1/packages/list.gmb', views.get_packages, name='api-package-list'),

    url(r'^1/test.html$', views.test, name="test"),
    url(r'^2/test.html$', views.test2, name="test"),
    # url(r'^test2.html$', views.test2, name="test2"),




    url(r'^upload/pop-upload/(?P<tdid>%s[0-9]{13,20})/$' % settings, POPCreateView.as_view(), name='upload-pop'),
    url(r'^upload/basic-upload/$', BasicVersionCreateView.as_view(), name='upload-basic'),
    url(r'^upload/basic/plus-upload/$', BasicPlusVersionCreateView.as_view(), name='upload-basic-plus'),
    url(r'^upload/new-upload/$', PictureCreateView.as_view(), name='upload-new'),
    url(r'^upload/angular-upload/$', AngularVersionCreateView.as_view(), name='upload-angular'),
    url(r'^upload/jquery-ui-upload/$', jQueryVersionCreateView.as_view(), name='upload-jquery'),
    url(r'^upload/delete-upload/(?P<pk>\d+)$', PictureDeleteView.as_view(), name='upload-delete'),
    url(r'^upload/view-upload/$', PictureListView.as_view(), name='upload-view'),
]
admin.site.site_title = 'Administrator'
admin.site.site_header = '%s Admin' %settings.COY_NAME