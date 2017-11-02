from __future__ import unicode_literals

import threading
from uuid import uuid4

import logging
import os

from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.contrib.auth.base_user import AbstractBaseUser as DjangoAbstractBaseUser, BaseUserManager as DjangoBaseUserManager
from django.contrib.auth.validators import UnicodeUsernameValidator, ASCIIUsernameValidator
from django.contrib.auth.models import User as AuthUser, Permission, AbstractUser as DjangoAbstractUser, PermissionsMixin

from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.contrib.humanize.templatetags.humanize import intcomma
# from django.db import models

from django.contrib.sessions.base_session import AbstractBaseSession
from django.contrib.sessions.models import Session
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _

# Create your models here.
from django.db import models
from django.db.models import base, Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone, six
from django.utils.html import format_html

from django.conf import settings
from notifications.models import Notification
from notifications.signals import notify


auto_manage = True

log = logging.getLogger(settings.PROJECT_NAME+".*")
log.setLevel(settings.DEBUG)


class Account(models.Model):
    ACTIVATION = settings.FS_ACCOUNT_ID_PREFIX; PH = settings.PH_ACCOUNT_ID_PREFIX; RC = settings.RC_ACCOUNT_ID_PREFIX; PH_FEE = settings.PF_ACCOUNT_ID_PREFIX; REFUND = settings.RF_ACCOUNT_ID_PREFIX;
    BONUS = settings.BS_ACCOUNT_ID_PREFIX;

    GH = settings.GH_ACCOUNT_ID_PREFIX; GH_PAUSED = settings.GP_ACCOUNT_ID_PREFIX; ADVERT = settings.AD_ACCOUNT_ID_PREFIX; SPONSOR = settings.SP_ACCOUNT_ID_PREFIX;
    REG_BONUS = settings.RB_ACCOUNT_ID_PREFIX; GUIDER_BONUS = settings.GB_ACCOUNT_ID_PREFIX; SPEED_BONUS = settings.SB_ACCOUNT_ID_PREFIX;

    TYPE = ((ACTIVATION, _('Activation')), (PH, _('PH')), (RC, _('Recommitment')), (PH_FEE, _('PH Fee')), (REFUND, _('Refund')), (BONUS, _('Bonus')),
            (GH, _('GH')), (GH_PAUSED, _('GH Paused')), (ADVERT, _('Advert')), (SPONSOR, _('Referral')), (REG_BONUS, _('Reg Bonus')), (GUIDER_BONUS, _('Sponsor Bonus')), (SPEED_BONUS, _('Speed Bonus')))

    PENDING = 'Pending'; PROCESSING = 'Processing'; PAUSED_EXCEPTION = 'Paused (Exception)'; PAUSED_RECYCLE = 'Paused (Recycle)'; PROCESSED = 'Processed'; PROCESSED_BONUS = 'Processed Bonus'; PARTIAL = 'Partial'; CANCELLED = 'Cancelled'; BLOCKED = 'Blocked'; TIMEOUT = 'Timeout';
    STATUS = ((PENDING, _('Pending')), (PROCESSING, _('Processing')), (PAUSED_EXCEPTION, _('Paused (Exception)')), (PAUSED_RECYCLE, _('Paused (Recycle)')), (PROCESSED, _('Processed')), (PROCESSED_BONUS, _('Processed Bonus')), (PARTIAL, _('Partial')), (CANCELLED, _('Cancelled')), (BLOCKED, _('Blocked')), (TIMEOUT, _('Timeout')))

    def __init__(self, *args, **kwargs):
        super(Account, self).__init__(*args, **kwargs)
        self.amount_2_gh = 0.0
        self.can_split = True

    id = models.CharField(primary_key=True, max_length=20)
    amount = models.DecimalField(decimal_places=12, max_digits=19)
    amount_live = models.DecimalField(decimal_places=12, max_digits=19)
    amount_init = models.DecimalField(decimal_places=12, max_digits=19)
    roi = models.DecimalField(default=0, decimal_places=12, max_digits=19)
    currency = models.ForeignKey('Currency', models.DO_NOTHING)
    owner = models.ForeignKey('Member', models.DO_NOTHING, default=None)
    type = models.CharField(max_length=13, default=None, choices=TYPE)
    status = models.CharField(max_length=21, default=PENDING, choices=STATUS)
    donation = models.ForeignKey('Donation', models.DO_NOTHING, default=None)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(blank=True, null=True, default=None)
    next_update = models.DateTimeField(blank=True, null=True, default=None)
    update_counter = models.IntegerField(default=0)
    fulfilled = models.DateTimeField(blank=True, null=True, default=None)
    maturity = models.DateTimeField()
    commitment_maturity = models.DateTimeField()
    balance = models.DecimalField(decimal_places=12, max_digits=19, default=0)
    max = models.DecimalField(decimal_places=12, max_digits=19)
    match_only = models.DecimalField(decimal_places=12, max_digits=19, default=0, blank=True, null=True)
    # prerequisite = models.ManyToManyField('self', related_name='prerequisites', default=None)
    can_match = models.BooleanField('Can Match', default=True)
    is_bonus = models.BooleanField('Bonus', default=False)
    is_auto_gh = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    can_credit = models.BooleanField(default=True)
    testimony_code = models.ForeignKey('TestimonyCode', models.DO_NOTHING, default=None, blank=True, null=True)

    def __str__(self):
        return self.id or u''

    def __unicode__(self):
        return self.id or u''

    def get_absolute_url(self):
        return reverse('core:account', kwargs={'pk': self.pk})

    def get_admin_list_link(self, item, id=""):
        url = reverse("admin:%s_%s_changelist" % (item._meta.app_label, item._meta.model_name))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, id, item.id))

    def get_admin_list_link_don(self, query, label=""):
        url = reverse("admin:%s_%s_changelist" % (self._meta.app_label, self._meta.model_name))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, query, label))

    @property
    def get_type_text(self):
        if self.type == self.ACTIVATION:
            # return self.TYPE[0][1]
            return ".%s" %self.TYPE[1][1]
        if self.type == self.PH:
            return self.TYPE[1][1]
        elif self.type == self.RC:
            return self.TYPE[2][1]
        elif self.type == self.PH_FEE:
            return self.TYPE[3][1]
        elif self.type == self.REFUND:
            return self.TYPE[4][1]
        elif self.type == self.BONUS:
            return self.TYPE[5][1]
        elif self.type == self.GH:
            return self.TYPE[6][1]
        elif self.type == self.GH_PAUSED:
            return self.TYPE[7][1]
        elif self.type == self.ADVERT:
            return self.TYPE[8][1]
        elif self.type == self.SPONSOR:
            return self.TYPE[9][1]
        elif self.type == self.REG_BONUS:
            return self.TYPE[10][1]
        elif self.type == self.GUIDER_BONUS:
            return self.TYPE[11][1]

    @staticmethod
    def get_recent_user_ph(member):
        return Account.objects.filter(owner=member, type__in=[Account.PH, Account.PH_FEE, Account.REFUND])

    class Meta:
        ordering = ('-created',)
        managed = auto_manage


class Bank(models.Model):
    name = models.CharField(max_length=32)
    code = models.CharField(max_length=3, default=None, unique=True)
    country = models.ForeignKey('Country', models.DO_NOTHING, null=True, default=None)

    def __str__(self):
        return self.name or u''

    def __unicode__(self):
        return self.name or u''

    def get_admin_list_link(self, item, id=""):
        url = reverse("admin:%s_%s_changelist" % (item._meta.app_label, item._meta.model_name))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, id, item.name))

    class Meta:
        managed = auto_manage
        ordering = ('name',)


class BankAccount(models.Model):
    number = models.CharField(max_length=36)
    name = models.CharField(max_length=128)
    currency = models.ForeignKey('Currency', models.DO_NOTHING)
    is_default = models.BooleanField('Default Account', default=False)
    branch_name = models.CharField(max_length=36, default=None, null=True, blank=True, help_text=mark_safe("<small><i>optional</i></small>"))
    sort_code = models.CharField(max_length=36, default=None, null=True, blank=True, help_text=mark_safe("<small><i>optional</i></small>"))
    created = models.DateTimeField(auto_now_add=True)
    bank = models.ForeignKey(Bank, models.DO_NOTHING, default=None)

    def __str__(self):
        return self.number or u''

    def __unicode__(self):
        return self.number or u''

    def get_admin_list_link(self, item, id=""):
        url = reverse("admin:%s_%s_changelist" % (item._meta.app_label, item._meta.model_name))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, id, item.id))

    class Meta:
        ordering = ('number',)
        managed = auto_manage
        db_table = 'core_bank_account'


class BankAccountVerification(models.Model):
    member = models.ForeignKey('Member', models.DO_NOTHING, default=None)
    account = models.ForeignKey(BankAccount, models.DO_NOTHING, default=None)
    bank = models.ForeignKey(Bank, models.DO_NOTHING, default=None)
    name = models.CharField(max_length=128, default=None, blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)
    verified = models.DateTimeField(blank=True, null=True, default=None)

    def __str__(self):
        return self.name or u''

    def __unicode__(self):
        return self.name or u''

    def get_admin_list_link(self, item, id=""):
        url = reverse("admin:%s_%s_changelist" % (item._meta.app_label, item._meta.model_name))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, id, item.id))

    class Meta:
        managed = auto_manage
        ordering = ('name',)
        db_table = 'core_bank_account_verification'


class CallDetail(models.Model):
    STARTED = 'started'; RINGING = 'ringing'; ANWSERED = 'answered'; COMPLETED = 'completed'; MACHINE = 'machine'; TIMEOUT = 'timeout'; FAILED = 'failed'; REJECTED = 'rejected'; UNANSWERED = 'unanswered'; BUSY = 'busy';
    STATUS = ((STARTED, _('started')), (RINGING, _('ringing')), (ANWSERED, _('answered')), (COMPLETED, _('completed')), (MACHINE, _('machine')), (TIMEOUT, _('timeout')), (FAILED, _('failed')), (REJECTED, _('rejected')), (UNANSWERED, _('unanswered')), (BUSY, _('busy')))

    status = models.CharField(max_length=20, default=STARTED, choices=STATUS)
    fromm = models.CharField(max_length=11)
    to = models.CharField(max_length=14)
    uuid = models.CharField(max_length=256)
    cuuid = models.CharField(max_length=256)
    network = models.CharField(max_length=10, blank=True, null=True, default=None)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return format_html('from {} to {}', self.fromm, self.to)

    def __unicode__(self):
        return format_html('from {} to {}', self.fromm, self.to)

    def get_admin_list_link(self, item, id=""):
        url = reverse("admin:%s_%s_changelist" % (item._meta.app_label, item._meta.model_name))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, id, item.id))

    class Meta:
        ordering = ('created',)
        managed = auto_manage
        db_table = 'core_call_detail'


class ChatHead(models.Model):
    STARTED = 'Started'; ASSIGNED = 'Assigned'; CLOSED = 'Closed';
    STATUS = ((STARTED, _('Started')), (ASSIGNED, _('Assigned')), (CLOSED, _('Closed')))

    title = models.CharField(max_length=128)
    initiator = models.ForeignKey(settings.AUTH_USER_MODEL, models.DO_NOTHING)
    trans_detail = models.ForeignKey('TransactionDetail', models.DO_NOTHING, default=None)
    status = models.CharField(max_length=20, default=STARTED, choices=STATUS)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return format_html(self.title)

    def __unicode__(self):
        return format_html(self.title)

    def get_admin_list_link(self, item, id=""):
        url = reverse("admin:%s_%s_changelist" % (item._meta.app_label, item._meta.model_name))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, id, item.id))

    class Meta:
        ordering = ('created',)
        managed = auto_manage
        db_table = 'core_chat_head'


class Chat(models.Model):
    DELIVERED = 'Delivered'; PENDING = 'Pending'; READ = 'Read'; UNREAD = 'Unread';
    STATUS = ((DELIVERED, _('Delivered')), (PENDING, _('Pending')), (READ, _('Read')), (UNREAD, _('Unread')))

    message = models.TextField()
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, models.DO_NOTHING)
    chat_head = models.ForeignKey(ChatHead, models.DO_NOTHING)
    status = models.CharField(max_length=20, default=PENDING, choices=STATUS)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        if len(self.message) > 40:
            return self.message[0:40]+"..."
        else:
            return self.message

    def __unicode__(self):
        if len(self.message) > 40:
            return self.message[0:40]+"..."
        else:
            return self.message

    def get_admin_list_link(self, item, id=""):
        url = reverse("admin:%s_%s_changelist" % (item._meta.app_label, item._meta.model_name))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, id, item.id))

    class Meta:
        ordering = ('created',)
        managed = auto_manage


class ChatReceiver(models.Model):
    receiver = models.ForeignKey(settings.AUTH_USER_MODEL, models.DO_NOTHING)
    chat = models.ForeignKey(Chat, models.DO_NOTHING)
    status = models.CharField(max_length=20, default=Chat.PENDING, choices=Chat.STATUS)
    read_time = models.DateTimeField(null=True, blank=True, default=None)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.receiver

    def __unicode__(self):
        return self.receiver

    def get_admin_list_link(self, item, id=""):
        url = reverse("admin:%s_%s_changelist" % (item._meta.app_label, item._meta.model_name))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, id, item.id))

    class Meta:
        ordering = ('created',)
        managed = auto_manage
        db_table = 'core_chat_receiver'


def path_and_rename_chat_files(instance, filename):
    now = timezone.now()
    ext = filename.split('.')[-1]
    if instance.pk:
        filename = '{}_{}.{}'.format(instance.sender.phone, instance.pk, ext)
    else:
        filename = '{}.{}'.format(uuid4().hex, ext)
    return os.path.join('uploads/chat/%s/' % (now.strftime("%Y/%m/%d")), filename)


class ChatUpload(models.Model):
    chat = models.ForeignKey(Chat, models.DO_NOTHING)
    file = models.ImageField(upload_to=path_and_rename_chat_files)
    # file = models.ImageField(upload_to=path_and_rename_chat_files, null=True, blank=True, default=None)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.file.url

    def __unicode__(self):
        return self.file.url

    def get_admin_list_link(self, item, id=""):
        url = reverse("admin:%s_%s_changelist" % (item._meta.app_label, item._meta.model_name))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, id, item.id))

    class Meta:
        ordering = ('created',)
        managed = auto_manage
        db_table = 'core_chat_upload'


# class CoinMarket(models.Model):
#     buyer = models.IntegerField()
#     seller = models.CharField(max_length=40)
#     coin = models.CharField(max_length=128)
#     value = models.CharField(max_length=256, blank=True, null=True)
#     rate = models.CharField(max_length=256, blank=True, null=True)
#     fee = models.CharField(max_length=256, blank=True, null=True)
#     currency = models.ForeignKey('Currency', models.DO_NOTHING)
#
#     def __str__(self):
#         return self.label or u''
#
#     def __unicode__(self):
#         return self.label or u''
#
#     class Meta:
#         ordering = ('code',)
#         unique_together = ('code', 'coin_market',)
#         managed = auto_manage


class Config(models.Model):
    code = models.IntegerField()
    label = models.CharField(max_length=40)
    value = models.CharField(max_length=128)
    description = models.CharField(max_length=256, blank=True, null=True)
    country = models.ForeignKey('Country', models.DO_NOTHING, default=None, null=True, blank=True)

    def __str__(self):
        return self.label or u''

    def __unicode__(self):
        return self.label or u''

    def get_admin_list_link(self, item, id=""):
        url = reverse("admin:%s_%s_changelist" % (item._meta.app_label, item._meta.model_name))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, id, item.id))

    class Meta:
        ordering = ('code',)
        unique_together = ('code', 'country',)
        managed = auto_manage


class Country(models.Model):
    code = models.CharField(max_length=3, primary_key=True)
    name = models.CharField(max_length=64)
    name_plain = models.CharField(max_length=64)
    is_active = models.BooleanField(default=False)
    dial_code = models.CharField(max_length=4, blank=True, null=True)
    flag = models.CharField(max_length=4, blank=True, null=True)
    capital = models.CharField(max_length=64, blank=True, null=True)
    region = models.CharField(max_length=64, blank=True, null=True)
    region_des = models.CharField(max_length=64, blank=True, null=True)

    def __str__(self):
        return self.name or u''

    def __unicode__(self):
        return self.name or u''

    def get_admin_list_link(self, item, id=""):
        url = reverse("admin:%s_%s_changelist" % (item._meta.app_label, item._meta.model_name))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, id, item.name))

    class Meta:
        ordering = ('name',)
        managed = auto_manage


class Currency(models.Model):
    BTC = _('Bitcoin')
    LOCAL = _('Local')
    code = models.CharField(max_length=3, primary_key=True)
    symbol = models.CharField(max_length=4)
    name = models.CharField(max_length=8, blank=True, null=True)
    country = models.ForeignKey(Country, models.DO_NOTHING, default=None, blank=True, null=True)
    rate = models.DecimalField(decimal_places=12, max_digits=19)

    def __str__(self):
        return self.name or u''

    def __unicode__(self):
        return self.name or u''

    def get_admin_list_link(self, item, id=""):
        url = reverse("admin:%s_%s_changelist" % (item._meta.app_label, item._meta.model_name))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, id, item.id))

    class Meta:
        ordering = ('name',)
        managed = auto_manage


class Donation(models.Model):
    ACTIVATION = settings.FS_ACCOUNT_ID_PREFIX; PH = settings.PH_ACCOUNT_ID_PREFIX; RC = settings.RC_ACCOUNT_ID_PREFIX; PH_FEE = settings.PF_ACCOUNT_ID_PREFIX; REFUND = settings.RF_ACCOUNT_ID_PREFIX;
    BONUS = settings.BS_ACCOUNT_ID_PREFIX;
    TYPE = ((ACTIVATION, _('Activation')), (PH, _('PH')), (RC, _('Recommitment')), (PH_FEE, _('PH Fee')), (REFUND, _('Refund')), (BONUS, _('Bonus')))

    ADMIN = 'Admin'; AUTO_RECYCLE = 'Auto Recycle'; USER_CHANNEL = 'User'; MANUAL = 'Manual'
    CHANNELS = ((ADMIN, _('Admin')), (AUTO_RECYCLE, _('Auto Recycle')), (USER_CHANNEL, _('User')), (MANUAL, _('Manual')))

    id = models.CharField(primary_key=True, max_length=20)
    amount = models.DecimalField(decimal_places=12, max_digits=19)
    currency = models.ForeignKey('Currency', models.DO_NOTHING)
    member = models.ForeignKey('Member', models.DO_NOTHING, default=None)
    type = models.CharField(max_length=13, default=PH, choices=TYPE)
    status = models.CharField(max_length=15, default=Account.PENDING, choices=Account.STATUS)
    channel = models.CharField(max_length=15, default=MANUAL, choices=CHANNELS)
    created = models.DateTimeField(auto_now_add=True)
    fulfilled = models.DateTimeField(blank=True, null=True, default=None)
    commitment_matched = models.DateTimeField(blank=True, null=True, default=None)
    recommitment = models.ForeignKey('self', models.DO_NOTHING, blank=True, null=True, default=None)
    is_bonus = models.BooleanField('Bonus', default=False)
    is_active = models.BooleanField(default=True)
    is_committed = models.BooleanField('Committed', default=False)
    is_ghed = models.BooleanField('GHed', default=False)
    is_auto_recycle = models.BooleanField('Can Recycle', default=False)
    is_recycled = models.BooleanField('Recycled', default=False)
    reasons = GenericRelation('Reason')

    def __str__(self):
        return str(self.id) or u''

    def __unicode__(self):
        return str(self.id) or u''

    def get_admin_list_link(self, item, id=""):
        url = reverse("admin:%s_%s_changelist" % (item._meta.app_label, item._meta.model_name))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, id, item.id))

    class Meta:
        ordering = ('-created',)
        managed = auto_manage


class EmailCycler(base.ModelBase):
    _counter = -1
    _counter_lock = threading.Lock()
    try:
        _emails = settings.EMAIL_CONNECTIONS.keys()
    except AttributeError:
        _emails = []

    @classmethod
    def get_email_label(cls):
        with cls._counter_lock:
            cls._counter += 1
            return cls._emails[cls._counter%len(cls._emails)]


class PhoneCycler(base.ModelBase):
    _counter = -1
    _counter_lock = threading.Lock()
    try:
        _phones = settings.PHONE_CONNECTIONS
    except AttributeError:
        _phones = []

    @classmethod
    def get_phone(cls):
        with cls._counter_lock:
            cls._counter += 1
            return cls._phones[cls._counter%len(cls._phones)]


class Member(models.Model):
    ACTIVE = 'Active'; BLOCKED = 'Blocked'; SUSPENDED = 'Suspended'; PAUSED = 'Paused'; NOT_VERIFIED = 'Not Verified';
    STATUS = ((ACTIVE, _('Active')), (BLOCKED, _('Blocked')), (SUSPENDED, _('Suspended')), (PAUSED, _('Paused')), (NOT_VERIFIED, 'Not Verified'))

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, default=None)
    phone = models.CharField(max_length=15, null=False, blank=False)
    email = models.CharField(max_length=64)
    password = models.CharField(max_length=64)
    first_name = models.CharField(max_length=32)
    last_name = models.CharField(max_length=32)
    other_names = models.CharField(max_length=32, blank=True, null=True)
    country = models.ForeignKey(Country, models.DO_NOTHING, default='ng')
    state = models.ForeignKey('State', models.DO_NOTHING, default=10)
    address = models.CharField('City', max_length=128, blank=True, null=True, default=None)
    dob = models.DateField(blank=True, null=True)
    sponsor = models.ForeignKey('self', models.DO_NOTHING, blank=True, null=True, default=None)
    min_ph = models.DecimalField(decimal_places=2, max_digits=11, default=0)
    max_ph = models.DecimalField(decimal_places=2, max_digits=11, default=0)
    min_ph_btc = models.DecimalField(decimal_places=12, max_digits=15, default=0)
    max_ph_btc = models.DecimalField(decimal_places=12, max_digits=15, default=0)
    created = models.DateTimeField(auto_now_add=True)
    # bank_account = models.ForeignKey(BankAccount, models.DO_NOTHING, blank=True, null=True)
    status = models.CharField(max_length=14, default=NOT_VERIFIED, choices=STATUS)
    delete_on = models.DateTimeField(blank=True, null=True, default=None)
    gh_balance = models.DecimalField(decimal_places=2, max_digits=11, default=0)
    frozen_balance = models.DecimalField(decimal_places=2, max_digits=11, default=0)
    released_balance = models.DecimalField(decimal_places=2, max_digits=11, default=0)
    coin_account_balance = models.DecimalField(decimal_places=2, max_digits=11, default=0)
    gh_balance_btc = models.DecimalField(decimal_places=12, max_digits=15, default=0)
    frozen_balance_btc = models.DecimalField(decimal_places=12, max_digits=15, default=0)
    released_balance_btc = models.DecimalField(decimal_places=12, max_digits=15, default=0)
    coin_account_balance_btc = models.DecimalField(decimal_places=12, max_digits=15, default=0)
    is_bonus = models.BooleanField('Bonus', default=False)
    is_active = models.BooleanField(default=True, editable=False)
    is_fake = models.BooleanField('Fake', default=False)
    is_phone_verified = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)
    can_receive_sms = models.BooleanField(default=True)
    can_receive_email = models.BooleanField(default=True)
    reasons = GenericRelation('Reason', default=None)
    token = models.CharField(max_length=16, null=False, blank=False)
    code = models.CharField(max_length=10, null=True, blank=True, default=None)
    bank_accounts = models.ManyToManyField(BankAccount, default=None, blank=True)

    @property
    def full_name(self):
        return ("%s %s %s" %(self.first_name, self.last_name, self.other_names or "")).strip(" ")

    def full_name(self):
        return ("%s %s %s" %(self.first_name, self.last_name, self.other_names or "")).strip(" ")
    full_name.short_description = "Full Name"
    full_name.admin_order_field = 'first_name'

    def username(self):
        return format_html('<a href="{}">{}</a>', '#', self.user.username,)
    username.short_description = "Username"
    username.admin_order_field = 'username'

    def get_admin_list_link(self, item, id=""):
        url = reverse("admin:%s_%s_changelist" % (item._meta.app_label, item._meta.model_name))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, id, item.full_name()))

    def __str__(self):
        return self.first_name+" "+self.last_name or u''

    def __unicode__(self):
        return self.first_name+" "+self.last_name or u''

    class Meta:
        ordering = ('-created',)
        managed = auto_manage


class Message(models.Model):
    GH_MATCHED = 'GH Matched'; PH_MATCHED = 'PH Matched'; VERIFICATION = 'Verification'; POP_CONFIRMED = 'POP Confirmed'; POP_EXCEPTION = 'POP Exception'; PAYMENT_MADE = 'Payment Made'; CUSTOM = 'Custom';
    TYPES = ((GH_MATCHED, _('GH Matched')), (PH_MATCHED, _('PH Matched')), (VERIFICATION, _('Verification')), (POP_CONFIRMED, _('POP Confirmed')), (POP_EXCEPTION, _('POP Exception')), (PAYMENT_MADE, _('Payment Made')), (CUSTOM, _('Custom')))

    message = models.CharField(max_length=128)
    phone = models.CharField(max_length=15)
    type = models.CharField(max_length=13, choices=TYPES)
    counter = models.IntegerField(default=0)
    created = models.DateTimeField(auto_now_add=True)
    sent_time = models.DateTimeField(blank=True, null=True, default=None)
    code = models.CharField(max_length=20, blank=True, null=True)
    response_code = models.ForeignKey('ResponseCode', models.DO_NOTHING, db_column='response_code', blank=True, null=True)

    def __str__(self):
        return self.phone or u''

    def __unicode__(self):
        return self.phone or u''

    def get_admin_list_link(self, item, id=""):
        url = reverse("admin:%s_%s_changelist" % (item._meta.app_label, item._meta.model_name))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, id, item.id))

    class Meta:
        ordering = ('-created',)
        managed = auto_manage


# class Notification(models.Model):
#     message = models.TextField()
#     created = models.DateTimeField(auto_now_add=True)
#     active = models.DateTimeField(auto_now_add=False)
#     expires = models.DateTimeField(blank=True, null=True, default=None)
#     type = models.CharField(max_length=7)
#
#     def __str__(self):
#         return self.message or u''
#
#     def __unicode__(self):
#         return self.message or u''
#
#     class Meta:
#         ordering = ('-created',)
#         managed = auto_manage


class Package(models.Model):
    ACTIVE = 'Active'; DISABLED = 'Disabled'; COMING_SOON = 'Coming Soon';
    STATUS = ((ACTIVE, _('Active')), (DISABLED, _('Disabled')), (COMING_SOON, _('Coming Soon')))

    amount = models.DecimalField(decimal_places=12, max_digits=19)
    currency = models.ForeignKey('Currency', models.DO_NOTHING)
    name = models.CharField(max_length=32)
    status = models.CharField(max_length=11, choices=STATUS, default=ACTIVE)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField(blank=True, null=True, default=None)

    def __unicode__(self):
        if self.currency.name == Currency.BTC:
            amount = round(float(self.amount), 12)
            amount = "%s%s" % (intcomma(int(amount)), ("%0.12f" % amount)[-3:])
        else:
            amount = round(float(self.amount), 2)
            amount = "%s%s" % (intcomma(int(amount)), ("%0.2f" % amount)[-3:])
        # return self.name + " (%s%s)" % (u"\u20A6", amount) or u''
        return self.name + " (%s %s)" % ("N", amount) or u''
        # return "\u20A6"

    def __str__(self):
        return self.__unicode__() or u''

    def get_admin_list_link(self, item, id=""):
        url = reverse("admin:%s_%s_changelist" % (item._meta.app_label, item._meta.model_name))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, id, item.id))

    class Meta:
        ordering = ('amount',)
        managed = auto_manage


class PackageConfig(models.Model):
    name = models.CharField(max_length=32)
    coin = models.DecimalField(decimal_places=2, max_digits=8)
    currency = models.ForeignKey('Currency', models.DO_NOTHING)
    min_ph = models.DecimalField(decimal_places=12, max_digits=20, default=0)
    max_ph = models.DecimalField(decimal_places=12, max_digits=20, default=0)
    created = models.DateTimeField(auto_now_add=True)

    def __unicode__(self):
        if self.currency.name == Currency.BTC:
            return "{0} ({1} - {2})".format(self.name, self.min_ph_btc, self.max_ph_btc)
        else:
            return "{0} ({1} - {2})".format(self.name, self.min_ph, self.max_ph)

    def get_admin_list_link(self, item, id=""):
        url = reverse("admin:%s_%s_changelist" % (item._meta.app_label, item._meta.model_name))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, id, item.id))

    class Meta:
        ordering = ('currency', 'coin',)
        unique_together = ('currency', 'name', )
        managed = auto_manage
        db_table = 'core_package_config'


# class PreMember(models.Model):
#     PENDING = 'Pending'; VERIFIED_EMAIL = 'Verified Email'; VERIFIED_PHONE = 'Verified Phone'; EXPIRED = 'Expired';
#     STATUS = ((PENDING, _('Pending')), (VERIFIED_EMAIL, _('Verified Email')), (VERIFIED_PHONE, _('Verified Phone')), (EXPIRED, _('Expired')))
#
#     first_name = models.CharField(max_length=32, null=False, blank=False)
#     last_name = models.CharField(max_length=32, null=False, blank=False)
#     username = models.CharField('Username', max_length=20, null=False, blank=False, unique=True)
#     # phone = models.CharField(max_length=11, null=False, blank=False)
#     email = models.CharField(max_length=128, null=False, blank=False)
#     password = models.CharField(max_length=254, null=False, blank=False)
#     # token = models.CharField(max_length=16, null=False, blank=False)
#     # code = models.CharField(max_length=6, default=None, null=True)
#     created = models.DateTimeField(auto_now_add=True)
#     expires = models.DateTimeField(blank=True, null=True, default=None)
#     status = models.CharField(max_length=14, default=PENDING, choices=STATUS)
#     sponsor = models.CharField(max_length=20, default=settings.DEFAULT_SPONSOR)
#     # sponsor = models.ForeignKey(Member, models.DO_NOTHING, blank=True, null=True)
#     # package = models.ForeignKey(Package, models.DO_NOTHING, default=None)
#
#     def __str__(self):
#         return self.first_name+" "+self.last_name or u''
#
#     def __unicode__(self):
#         return self.first_name+" "+self.last_name or u''
#
#     class Meta:
#         ordering = ('-created',)
#         managed = auto_manage
#         db_table = 'core_pre_member'


class Reason(models.Model):
    RESOLVED = 'Resolved'; NOT_RESOLVED = 'Not Resolved'
    STATUS = ((RESOLVED, "Resolved"), (NOT_RESOLVED, "Not Resolved"), )

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.CharField('object_id', max_length=32)
    content_object = GenericForeignKey('content_type', 'object_id')

    # reason_object_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    # reason_object_id = models.CharField('reason_object_id', max_length=32)
    # content_object = GenericForeignKey('reason_object_type', 'reason_object_id')
    message = models.CharField(max_length=128)
    status = models.CharField(max_length=15, choices=STATUS, default=NOT_RESOLVED)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):  # __unicode__ on Python 2
        return self.message

    def get_admin_list_link(self, item, id=""):
        url = reverse("admin:%s_%s_changelist" % (item._meta.app_label, item._meta.model_name))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, id, item.id))

    class Meta:
        ordering = ('-created',)
        managed = auto_manage


class ResponseCode(models.Model):
    id = models.CharField(primary_key=True, max_length=10)
    label = models.CharField(max_length=32)
    description = models.CharField(max_length=256, blank=True, null=True)
    alias = models.CharField(max_length=32, blank=True, null=True)

    def __unicode__(self):
        return self.label or u''

    def __str__(self):
        return self.label or u''

    def get_admin_list_link(self, item, id=""):
        url = reverse("admin:%s_%s_changelist" % (item._meta.app_label, item._meta.model_name))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, id, item.id))

    class Meta:
        ordering = ('id',)
        managed = auto_manage
        db_table = 'core_response_code'


class SchedulerReport(models.Model):
    MATCHED = 'Matched'; EXCEPTION = 'Exception'
    TYPE = ((MATCHED, _('Matched')), (EXCEPTION, _('Exception')))

    type = models.CharField(max_length=10, choices=TYPE)
    count = models.IntegerField(default=0)
    amount = models.DecimalField(decimal_places=12, max_digits=19)
    currency = models.ForeignKey('Currency', models.DO_NOTHING)
    created = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True, null=True, default=None)

    def get_admin_list_link(self, item, id=""):
        url = reverse("admin:%s_%s_changelist" % (item._meta.app_label, item._meta.model_name))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, id, item.id))

    class Meta:
        managed = auto_manage
        db_table = 'core_scheduler_report'


class State(models.Model):
    id = models.IntegerField(primary_key=True)
    name = models.CharField(max_length=64)
    capital = models.CharField(max_length=64)
    appelation = models.CharField(max_length=64)
    country = models.ForeignKey(Country, models.DO_NOTHING, db_column='country', default=None)

    def __str__(self):
        return self.name or u''

    def __unicode__(self):
        return self.name or u''

    def get_admin_list_link(self, item, id=""):
        url = reverse("admin:%s_%s_changelist" % (item._meta.app_label, item._meta.model_name))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, id, item.id))

    class Meta:
        ordering = ('name',)
        managed = auto_manage


class Testimony(models.Model):
    id = models.IntegerField(primary_key=True)
    message = models.TextField()
    transaction = models.ForeignKey('Transaction', models.DO_NOTHING, null=True, blank=True, default=None)
    vidoe_url = models.URLField(blank=True, null=True, default=None)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        if len(self.message) > 40:
            return self.message[0:40]+"..."
        else:
            return self.message

    def __unicode__(self):
        if len(self.message) > 40:
            return self.message[0:40]+"..."
        else:
            return self.message

    def get_admin_list_link(self, item, id=""):
        url = reverse("admin:%s_%s_changelist" % (item._meta.app_label, item._meta.model_name))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, id, item.id))

    class Meta:
        ordering = ('created',)
        managed = auto_manage


def path_and_rename_testimony_file(instance, filename):
    now = timezone.now()
    ext = filename.split('.')[-1]
    if instance.pk:
        filename = '{}_{}.{}'.format(instance.sender.phone, instance.pk, ext)
    else:
        filename = '{}.{}'.format(uuid4().hex, ext)
    return os.path.join('uploads/testimony/%s/' % (now.strftime("%Y/%m/%d")), filename)


class TestimonyCode(models.Model):
    PH = 'PH'; GH = 'GH';
    TYPE = ((PH, _('PH')), (GH, _('GH')), )

    PREFIX = 'TSP'

    id = models.CharField(primary_key=True, max_length=20)
    testifier = models.ForeignKey(Member, models.DO_NOTHING)
    amount = models.DecimalField(decimal_places=12, max_digits=19)
    currency = models.ForeignKey('Currency', models.DO_NOTHING)
    object_id = models.CharField(max_length=40,)
    type = models.CharField(max_length=13, default=None, choices=TYPE)
    is_confirmed = models.BooleanField(default=False)
    confirmed_on = models.DateTimeField(default=None, blank=True, null=True)
    confirmed_by = models.ForeignKey(Member, related_name='confirmed_by', default=None, blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.id

    def __unicode__(self):
        return self.id

    def get_admin_list_link(self, item, id=""):
        url = reverse("admin:%s_%s_changelist" % (item._meta.app_label, item._meta.model_name))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, id, item.id))

    class Meta:
        ordering = ('created',)
        managed = auto_manage
        db_table = 'core_testimony_code'


class TestimonyUpload(models.Model):
    testimony = models.ForeignKey(Chat, models.DO_NOTHING)
    file = models.ImageField(upload_to=path_and_rename_chat_files)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.file.url

    def __unicode__(self):
        return self.file.url

    def get_admin_list_link(self, item, id=""):
        url = reverse("admin:%s_%s_changelist" % (item._meta.app_label, item._meta.model_name))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, id, item.id))

    class Meta:
        ordering = ('created',)
        managed = auto_manage
        db_table = 'core_testimony_upload'


class Tracker(models.Model):
    INSERT = 'Insert'; DELETE = 'Delete'; UPDATE = 'Update'; PROCESSING = 'Processing'
    CHANGES = ((INSERT, _('Insert')), (DELETE, _('Delete')), (UPDATE, _('Update')), (PROCESSING, _('Processing')))

    object_id = models.CharField(max_length=32)
    type = models.CharField(max_length=20)
    note = models.CharField(max_length=128)
    change = models.CharField(max_length=10, choices=CHANGES)
    updater = models.CharField(max_length=20)
    created = models.DateTimeField(auto_now_add=True)

    def get_admin_list_link(self, item, id=""):
        url = reverse("admin:%s_%s_changelist" % (item._meta.app_label, item._meta.model_name))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, id, item.id))

    class Meta:
        ordering = ('-created',)
        managed = auto_manage


class Transaction(models.Model):
    PENDING = 'Pending'; PAUSED_EXCEPTION = 'Paused (Exception)'; PAUSED_RECYCLE = 'Paused (Recycle)'; PROCESSING = 'Processing'; INCOMPLETE = 'Incomplete'; COMPLETED = 'Completed'; CANCELLED = 'Cancelled';
    STATUS = ((PENDING, _('Pending')), (PAUSED_EXCEPTION, _('Paused (Exception)')), (PAUSED_RECYCLE, _('Paused (Recycle)')), (PROCESSING, _('Processing')), (INCOMPLETE, _('Incomplete')), (COMPLETED, _('Completed')), (CANCELLED, _('Cancelled')))

    WITHDRAWAL = 'Withdrawal'; COIN = 'Coin'
    TYPE = ((WITHDRAWAL, _('Withdrawal')), (COIN, _('Coin')))
    def __init__(self, *args, **kwargs):
        super(Transaction, self).__init__(*args, **kwargs)

    PREFIX = settings.TRANSACTION_ID_PREFIX
    id = models.CharField(primary_key=True, max_length=20)
    amount = models.DecimalField(decimal_places=12, max_digits=19)
    currency = models.ForeignKey('Currency', models.DO_NOTHING)
    currency_src = models.ForeignKey('Currency', models.DO_NOTHING, related_name='original_currency')
    owner = models.ForeignKey(Member, models.DO_NOTHING, default=None)
    type = models.CharField(max_length=11, default=WITHDRAWAL, choices=TYPE)
    status = models.CharField(max_length=21, default=PENDING, choices=STATUS)
    created = models.DateTimeField(auto_now_add=True)
    is_bonus = models.BooleanField(default=False)
    balance = models.DecimalField(decimal_places=12, max_digits=19)
    fulfilled = models.DateTimeField(blank=True, null=True, default=None)
    is_active = models.BooleanField(default=True)
    can_match = models.BooleanField('Can Match', default=True)
    prerequisite = models.ManyToManyField(Account, default=None, blank=True)
    testimony_code = models.ForeignKey(TestimonyCode, models.DO_NOTHING, default=None, blank=True, null=True)
    bank_account = models.ForeignKey(BankAccount, models.DO_NOTHING, default=None, blank=True, null=True)

    def __str__(self):
        return str(self.id) or u''

    def __unicode__(self):
        return str(self.id) or u''

    def get_admin_list_link(self, item, id=""):
        url = reverse("admin:%s_%s_changelist" % (item._meta.app_label, item._meta.model_name))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, id, item.id))

    @property
    def get_type_text(self):
        if self.type==self.WITHDRAWAL:
            return "GH"
        else:
            return self.type

    class Meta:
        ordering = ('-created',)
        managed = auto_manage
        verbose_name = _('Queued Transaction')
        verbose_name_plural = _('Queued Transactions')


def path_and_rename(instance, filename):
    now = timezone.now()
    ext = filename.split('.')[-1]
    if instance.pk:
        filename = '{}_{}.{}'.format(instance.sender.phone, instance.pk, ext)
    else:
        filename = '{}.{}'.format(uuid4().hex, ext)
    return os.path.join('uploads/pop/%s/'%(now.strftime("%Y/%m/%d")), filename)


def generic_path_and_rename(instance, filename):
    now = timezone.now()
    ext = filename.split('.')[-1]
    if instance.pk:
        filename = '{}_{}.{}'.format(uuid4().hex, instance.pk, ext)
    else:
        filename = '{}.{}'.format(uuid4().hex, ext)
    return os.path.join('uploads/pop/%s/'%(now.strftime("%Y/%m/%d")), filename)


class Picture(models.Model):
    file = models.ImageField(upload_to=generic_path_and_rename)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.file.name

    def get_absolute_url(self):
        return reverse('core:upload-new',)

    def save(self, *args, **kwargs):
        self.slug = self.file.name
        super(Picture, self).save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """delete -- Remove to leave file."""
        self.file.delete(False)
        super(Picture, self).delete(*args, **kwargs)

    class Meta:
        abstract = True


class POPPicture(Picture):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.CharField('object_id', max_length=32)
    content_object = GenericForeignKey('content_type', 'object_id')

    def __str__(self):
        return self.file.name

    def get_absolute_url(self):
        return reverse('core:upload-new',)

    class Meta:
        # ordering = ('-created',)
        managed = auto_manage
        db_table = 'core_pop_picture'
        verbose_name = _('POP')
        verbose_name_plural = _('POPs')


class TransactionDetail(models.Model):
    AWAITING_PAYMENT = 'Awaiting Payment'; PAUSED_EXCEPTION = 'Paused (Exception)'; PAUSED_RECYCLE = 'Paused (Recycle)'; AWAITING_CONFIRMATION = 'Awaiting Confirmation'; EXCEPTION = 'Exception'; CONFIRMED = 'Confirmed'; CANCELLED = 'Cancelled';
    STATUS = ((AWAITING_PAYMENT, _('Awaiting Payment')), (PAUSED_EXCEPTION, _('Paused (Exception)')), (PAUSED_RECYCLE, _('Paused (Recycle)')), (AWAITING_CONFIRMATION, _('Awaiting Confirmation')), (EXCEPTION, _('Exception')), (CONFIRMED, _('Confirmed')), (CANCELLED, _('Cancelled')))
    NO = 'No'; YES = 'Yes'
    REMATCHED_STATUS = ((NO, _('No')), (YES, _('Yes')), (CANCELLED, _('Cancelled')))

    id = models.CharField(primary_key=True, max_length=20)
    transaction = models.ForeignKey(Transaction, models.DO_NOTHING, default=None)
    account = models.ForeignKey(Account, models.DO_NOTHING, default=None)     #the PH account that will pay for this detail
    sender = models.ForeignKey(Member, models.DO_NOTHING, default=None)
    amount = models.DecimalField(decimal_places=12, max_digits=19)
    currency = models.ForeignKey('Currency', models.DO_NOTHING)
    status = models.CharField(max_length=21, default=AWAITING_PAYMENT, choices=STATUS)
    # proof = models.ImageField(upload_to=path_and_rename, null=True, blank=True, default=None)
    proof_date = models.DateTimeField(blank=True, null=True, default=None)
    proof_acknowledge_date = models.DateTimeField(blank=True, null=True, default=None)
    rematched = models.CharField(max_length=9, default=NO, choices=REMATCHED_STATUS)
    created = models.DateTimeField(auto_now_add=True)
    expires = models.DateTimeField(blank=True, null=True, default=None)
    reasons = GenericRelation(Reason, default=None)
    uploads = GenericRelation(POPPicture)
    testimony_code = models.ForeignKey(TestimonyCode, models.DO_NOTHING, default=None, blank=True, null=True)

    def get_admin_list_link(self, item, id=""):
        url = reverse("admin:%s_%s_changelist" % (item._meta.app_label, item._meta.model_name))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, id, item.id))

    def __str__(self):
        return str(self.amount) or u''

    def __unicode__(self):
        return str(self.amount) or u''

    class Meta:
        # ordering = ('-created',)
        managed = auto_manage
        db_table = 'core_transaction_detail'
        verbose_name = _('Matched Transaction')
        verbose_name_plural = _('Matched Transactions')


class TransactionPointer(models.Model):
    transaction = models.ForeignKey(Transaction, models.DO_NOTHING, default=None)
    account = models.ForeignKey(Account, models.DO_NOTHING, default=None)  # the GH account that lead to this Transaction
    amount = models.DecimalField(decimal_places=12, max_digits=19)
    is_full = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)

    def get_admin_list_link(self, item, id=""):
        url = reverse("admin:%s_%s_changelist" % (item._meta.app_label, item._meta.model_name))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, id, item.id))

    def __str__(self):
        return str(self.amount) or u''

    class Meta:
        ordering = ('-created',)
        managed = auto_manage
        db_table = 'core_transaction_pointer'
        verbose_name = _('Queue Pointer')
        verbose_name_plural = _('Queue Pointers')


class TransactionDetailPointer(models.Model):
    trans_pointer = models.ForeignKey(TransactionPointer, models.DO_NOTHING, default=None)
    trans_detail = models.ForeignKey(TransactionDetail, models.DO_NOTHING, default=None)
    amount = models.DecimalField(decimal_places=12, max_digits=19)
    created = models.DateTimeField(auto_now_add=True)

    def get_admin_list_link(self, item, id=""):
        url = reverse("admin:%s_%s_changelist" % (item._meta.app_label, item._meta.model_name))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, id, item.id))

    def __str__(self):
        return str(self.amount) or u''

    class Meta:
        ordering = ('-created',)
        managed = auto_manage
        db_table = 'core_transaction_detail_pointer'


class TransactionSkippedReason(models.Model):
    MATCHED = "Matched"
    NOT_MATCHED = "Not Matched"
    STATUS = ((MATCHED, _("Matched")), (NOT_MATCHED, _("Not Matched")))

    transaction = models.ForeignKey(Transaction, models.DO_NOTHING, default=None)
    message = models.CharField(max_length=128)
    status = models.CharField(max_length=15, choices=STATUS, default=NOT_MATCHED)
    created = models.DateTimeField(auto_now_add=True)

    def get_admin_list_link(self, item, id=""):
        url = reverse("admin:%s_%s_changelist" % (item._meta.app_label, item._meta.model_name))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, id, item.id))

    def __str__(self):  # __unicode__ on Python 2
        return self.message

    class Meta:
        ordering = ('-created',)
        managed = auto_manage
        db_table = 'core_transaction_skipped_reason'


# class TransactionBreakdown(models.Model):
#     account = models.ForeignKey(Account, models.DO_NOTHING, default=None)  # the GH account that lead to this Transaction
#     transaction = models.ForeignKey(Transaction, models.DO_NOTHING, default=None)
#     trans_detail = models.ForeignKey(TransactionDetail, models.DO_NOTHING, default=None)
#     amount = models.DecimalField(decimal_places=12, max_digits=19)
#     status = models.CharField(max_length=21, default='Awaiting Payment', choices=(
#     ('Awaiting Payment', 'Awaiting Payment'), ('Awaiting Confirmation', 'Awaiting Confirmation'), ('Exception', 'Exception'), ('Confirmed', 'Confirmed'), ('Cancelled', 'Cancelled')))
#     created = models.DateTimeField(auto_now_add=True)
#
#     def __str__(self):
#         return str(self.amount) or u''
#
#     class Meta:
#         ordering = ('-created',)
#         managed = auto_manage
#         db_table = 'transaction_breakdown'



# # These two auto-delete files from filesystem when they are unneeded:
# @receiver(models.signals.post_delete, sender=TransactionDetail)
# def auto_delete_file_on_delete(sender, instance, **kwargs):
#     """Deletes file from filesystem when corresponding `TransactionDetail` object is deleted. """
#     if instance.audio:
#         if os.path.isfile(instance.proof.path):
#             print "Deleteing.....1 %s" % instance.proof.path[instance.proof.path.rfind("/")+1:]
#             os.remove(instance.proof.path)
#
#
# @receiver(models.signals.pre_save, sender=TransactionDetail)
# def auto_delete_file_on_change(sender, instance, **kwargs):
#     """Deletes file from filesystem when corresponding `TransactionDetail` object is changed. """
#     if not instance.pk:
#         return False
#     try:
#         old_file = TransactionDetail.objects.get(pk=instance.pk).proof
#     except TransactionDetail.DoesNotExist:
#         return False
#
#     new_file = instance.proof
#     if old_file and not old_file == new_file:
#         if os.path.isfile(old_file.path):
#             print "Deleteing.....2 %s" % old_file.path[old_file.path.rfind("/")+1:]
#             os.remove(old_file.path)
#
#     mems = Member.objects.filter(status='Blocked', member__user__is_active=False)
#     users = User.objects.filter(member__in=mems, is_active=False)
#
#     accs = Member.objects.filter(donation__account__type='PH').exclude(donation__account__status__in=['Pending', 'Processing'])
#     # accs = Account.objects.filter(type='PH', status__in=['Pending', 'Processing'])


# ****************************** CUSTOM SECURITY IMPLEMENTATION ******************************


# class UserManager_(UserManager):
class UserManager(DjangoBaseUserManager):
    use_in_migrations = True

    def _create_user(self, username, email, phone, password, **extra_fields):
        """Creates and saves a User with the given username, email and password."""
        from core.utils import get_bool_conf
        if not username:
            raise ValueError('The username must be set')
        if not phone and get_bool_conf(80, False):
            raise ValueError('Did you forgot the phone number')
        if not email:
            raise ValueError('Users must have a valid email address')

        # TODO: Fix this
        # db_user = User.objects.filter(Q(phone=phone) | Q(email=email))
        # if len(db_user) > 0:
        #     if db_user.phone == phone:
        #         raise ValueError('Phone number is already in use')
        #     else:
        #         raise ValueError('Email number is already in use')

        email = self.normalize_email(email)
        username = self.model.normalize_username(username)
        user = self.model(username=username, email=email, phone=phone, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, username, email=None, phone=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(username, email, phone, password, **extra_fields)

    def create_superuser(self, username, email, phone, password, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self._create_user(username, email, phone, password, **extra_fields)


# @python_2_unicode_compatible
# class User(AbstractUser):
class AbstractUser(DjangoAbstractUser):
    """
    An abstract base class implementing a fully featured User model with
    admin-compliant permissions.

    Username and password are required. Other fields are optional.
    """
    username_validator = UnicodeUsernameValidator() if six.PY3 else ASCIIUsernameValidator()

    username = models.CharField(_('username'), unique=True, max_length=20, validators=[username_validator], help_text=_('Required. 20 characters or fewer. Letters, digits and @/./+/-/_ only.'), error_messages={'unique': _("A user with that username already exists."),})
    phone = models.CharField(_('phone number'), max_length=15, null=True, default=None)
    last_login_signature = models.ForeignKey('AuthAudit', related_name='signatures', related_query_name='signature', null=True, default=None)
    failed_attempts = models.IntegerField(_('failed attempts'), default=0)
    last_password_change = models.DateTimeField(_('last password change'), null=True, blank=True, default=None)
    force_password_change = models.BooleanField(_('force password change'), default=False)
    avatar_url = models.URLField(null=True, blank=True, default=None)

    objects = UserManager()

    EMAIL_FIELD = 'email'
    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['phone', EMAIL_FIELD]    # This must contain all required fields on ur user model, but shouldn't contain de USERNAME_FIELD/password as these fields 'll always be prompted for.

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')
        abstract = True


def post_save_receiver(sender, instance, created, **kwargs):
    print ("----User Saved----")

post_save.connect(post_save_receiver, sender=settings.AUTH_USER_MODEL)

# content_type = ContentType.objects.get_for_model(User)
# permission = Permission.objects.create(
#     codename='can_make_user_super',
#     name='Can Promote User to Super User',
#     content_type=content_type,
# )


class User(AbstractUser):
    """
    Concrete class of AbstractUser.
    Use this if you don't need to extend User.
    """

    def get_admin_list_link(self, item, id=""):
        url = reverse("admin:%s_%s_changelist" % (item._meta.app_label, item._meta.model_name))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, id, item.id))

    class Meta:  # noqa: D101
        app_label = 'core'
        swappable = 'AUTH_USER_MODEL'
        db_table = 'core_auth_user'


class AuthAudit(models.Model):
    FAILED = 'Failed'; SUCCESSFUL = 'Successful'
    STATUS = ((FAILED, _('Failed')), (SUCCESSFUL, _('Successful')),)

    ACTIVE = 'Active'; ANONYMOUS = 'Anonymous'; LOGGED_OUT = 'Logged Out'; INVALIDATED = 'Invalidated'; EXPIRED = 'Expired'
    SESSION_STATUS = ((ACTIVE, _('Active')), (ANONYMOUS, _('Anonymous')), (EXPIRED, _('Expired')), (INVALIDATED, _('Invalidated')), (LOGGED_OUT, _('Logged Out')),)

    PASSWORD = 'Password'; FACEBOOK = 'Facebook'; GOOGLE = 'Google'; TWITTER = 'Twitter'; YAHOO = 'Yahoo'; LINKEDIN = 'LinkedIn'; INSTAGRAM = 'Instagram'; AMAZON = 'Amazon'; DROPBOX = 'Dropbox';
    GITHUB = 'Github'; GITLAB = 'GitLab'; STACKOVERFLOW = 'Stackoverflow';
    AUTH_BACKEND = [(PASSWORD, _('Password')), (FACEBOOK, _('Facebook')), (GOOGLE, _('Google')), (TWITTER, _('Twitter')), (YAHOO, _('Yahoo')), (LINKEDIN, _('LinkedIn')), (INSTAGRAM, _('Instagram')),
                    (AMAZON, _('Amazon')), (DROPBOX, _('Dropbox')), (GITHUB, _('Github')), (GITLAB, _('GitLab')), (STACKOVERFLOW, _('Stackoverflow'))]

    ip = models.GenericIPAddressField(_('ip address'), null=True)
    session_key = models.CharField(_('session key'), max_length=40, null=True, blank=True, default=None)
    created = models.DateTimeField(_('created'), auto_now_add=True, editable=True)
    last_date = models.DateTimeField(_('last date'), null=True, blank=True, default=None)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, default=None)
    username = models.CharField(_('username'), max_length=128)
    fingerprint = models.CharField(_('fingerprint'), max_length=32)
    auth_backend = models.CharField(_('authenticated via'), max_length=14, choices=AUTH_BACKEND, default=PASSWORD)
    auth_status = models.CharField(_('authentication status'), max_length=10, choices=STATUS, default=SUCCESSFUL)
    session_status = models.CharField(_('session status'), max_length=12, choices=SESSION_STATUS, default=ANONYMOUS)
    browser = models.CharField(_('browser'), max_length=16, null=True)
    browser_version = models.CharField(_('browser version'), max_length=16, null=True)
    os = models.CharField(_('operating system (OS)'), max_length=16, null=True)
    os_version = models.CharField(_('OS version'), max_length=16, null=True)
    current_resolution = models.CharField(_('current resolution'), max_length=16, null=True)
    available_resolution = models.CharField(_('available resolution'), max_length=16, null=True)
    device = models.CharField(_('device'), max_length=16, null=True)
    language = models.CharField(_('language'), max_length=16, null=True)

    def get_admin_list_link(self, item, id=""):
        url = reverse("admin:%s_%s_changelist" % (item._meta.app_label, item._meta.model_name))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, id, item.id))

    def __unicode__(self):
        return '{0} - {1} - {2}'.format(self.os, self.browser, self.ip)

    class Meta:
        db_table = 'core_auth_audit'


def auth_audit_log(c, request, user, username, auth_status, backend, session_status=AuthAudit.ANONYMOUS, session_key=None, last_date=None):
    browser = c[1].split(" ")
    browser_version = browser[-1]
    browser.remove(browser_version)
    browser_name = " ".join(browser)

    os = c[2].split(" ")
    os_version = os[-1]
    os.remove(os_version)
    os_name = " ".join(os)

    audit = AuthAudit.objects.create(ip=request.META.get('REMOTE_ADDR'), session_key=session_key, username=username, user=user, fingerprint=c[0], browser=browser_name, browser_version=browser_version,
                                     auth_status=auth_status, auth_backend=backend, session_status=session_status, last_date=last_date, os=os_name, os_version=os_version, current_resolution=c[3],
                                     available_resolution=c[4], device=c[5], language=request.META.get('HTTP_ACCEPT_LANGUAGE'))
    return audit


@receiver(user_logged_in)
def user_logged_in_callback(sender, request, user, **kwargs):
    """DJango Clears Session after a successful Login, however, backend for auth, user id, user hash will be saved"""
    backend = get_login_backend(None, request.session['_auth_user_backend'])

    print "***********------Logged In _auth_user_backend -------*************"
    # print request.session.session_key
    # for k in request.session.keys():
    #     print k+":\t\t"+request.session[k]

    try:
        client_id = request.POST['id_client']
    except KeyError:
        request.session._get_or_create_session_key()
        try:
            client_id = request.session['client_id']
            request.session.modified = True
        except KeyError:
            return

    user.failed_attempts = 0

    c = client_id.split("::")
    if len(c) > 5:
        audit = auth_audit_log(c, request, user, user.username, AuthAudit.SUCCESSFUL, backend, AuthAudit.ACTIVE, request.session.session_key)
        user.last_login_signature = audit
        previous = AuthAudit.objects.filter(fingerprint=audit.fingerprint, user=user, auth_backend=audit.auth_backend, auth_status=AuthAudit.SUCCESSFUL).count()
        if previous == 1:
            from core import notification
            notify.send(audit, recipient=user, verb=notification.logged_smsg)
    else:
        # You can logged this user immediately from here
        pass
    user.save()


@receiver(user_logged_out)
def user_logged_out_callback(sender, request, user, **kwargs):
    audit = AuthAudit.objects.filter(session_key=request.session.session_key).exclude(session_key__isnull=True).order_by('-created').first()
    if audit:
        audit.session_key = None
        audit.session_status = AuthAudit.LOGGED_OUT
        audit.last_date = timezone.now()
        audit.save()

@receiver(user_login_failed)
def user_login_failed_callback(sender, credentials, **kwargs):
    # return kwargs['request'].session.flush()
    print "Login Fail..............................................."
    backend = get_login_backend(kwargs['request'].path)
    try:
        client_id = kwargs['request'].POST['id_client']
    except KeyError:
        kwargs['request'].session._get_or_create_session_key()
        try:
            client_id = kwargs['request'].session['client_id']
            kwargs['request'].session.modified = True
        except KeyError:
            return

    c = client_id.split("::")
    if len(c) < 6:
        return

    try:
        user = User.objects.get(username=credentials['username'])
        user.last_failed_attempt = timezone.now()
        user.failed_attempts += 1
        user.save()
    except User.DoesNotExist:
        user = None

    auth_audit_log(c, kwargs['request'], user, credentials['username'], AuthAudit.FAILED, backend)

    # r=kwargs['request']
    # log.info("Scheme:\t%s" % r.scheme)
    # log.info("body:\t%s" % r.body)
    # log.info("path:\t%s" % r.path)
    # log.info("path_info:\t%s" % r.path_info)
    # log.info("method:\t%s" % r.method)
    # log.info("encoding:\t%s" % r.encoding)
    # log.info("content_type:\t%s" % r.content_type)
    # log.info("content_params:\t%s" % r.content_params)
    # log.info('HTTP_ACCEPT:\t%s' % r.META.get('HTTP_ACCEPT'))
    # log.info('REMOTE_ADDR\t%s' % r.META.get('REMOTE_ADDR'))
    # log.info('HTTP_ACCEPT_ENCODING\t%s' % r.META.get('HTTP_ACCEPT_ENCODING'))
    # log.info('HTTP_ACCEPT_LANGUAGE\t%s' % r.META.get('HTTP_ACCEPT_LANGUAGE'))
    # log.info('HTTP_HOST\t%s' % r.META.get('HTTP_HOST'))
    # log.info('HTTP_REFERER\t%s' % r.META.get('HTTP_REFERER'))
    # log.info('HTTP_USER_AGENT\t%s' % r.META.get('HTTP_USER_AGENT'))
    # log.info('QUERY_STRING\t%s' % r.META.get('QUERY_STRING'))
    # log.info('REMOTE_ADDR\t%s' % r.META.get('REMOTE_ADDR'))
    # log.info('REMOTE_HOST\t%s' % r.META.get('REMOTE_HOST'))
    # log.info('REMOTE_USER\t%s' % r.META.get('REMOTE_USER'))
    # log.info('REQUEST_METHOD\t%s' % r.META.get('REQUEST_METHOD'))
    # log.info('SERVER_NAME\t%s' % r.META.get('SERVER_NAME'))
    # log.info('SERVER_PORT\t%s' % r.META.get('SERVER_PORT'))
    # log.info('HTTP_USER_AGENT\t%s' % r.META.get('HTTP_USER_AGENT'))


def get_login_backend(path=None, backend_path=None):
    if path:
        if reverse(settings.LOGIN_URL) == path:
            return AuthAudit.PASSWORD
        else:
            try:
                backends = []
                for b in AuthAudit.AUTH_BACKEND:
                    backends.append(b[0])
                backends.pop(0)
                auth_backend = path.split("/")[4].title()
                if auth_backend in backends:
                    return auth_backend
                else:
                    return None
            except IndexError:
                return None
    else:
        paths = backend_path.split(".")
        if len(paths) in [4, 5]:
            if backend_path in ['django.contrib.auth.backends.ModelBackend', 'core.overrides.auth_backend.SDBackend']:
                return AuthAudit.PASSWORD
            backends = []
            for b in AuthAudit.AUTH_BACKEND:
                backends.append(b[0])
            backends.pop(0)
            auth_backend = paths[2].title()
            if auth_backend in backends:
                return auth_backend
            else:
                return None
        else:
            return None


# class CustomSession(SessionStore):
class AuthSession(AbstractBaseSession):
    # The example below shows a custom database-backed session engine that includes an additional database column to store an account ID
    # (thus providing an option to query the database for all active sessions for an account):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, default=None)

    @classmethod
    def get_session_store_class(cls):
        from core.overrides.cached_db import SessionStore
        return SessionStore

    class Meta:
        db_table = 'core_auth_session'


class PasswordHistory(models.Model):
    harsh = models.CharField(max_length=128)
    user = models.ForeignKey(settings.AUTH_USER_MODEL,)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'core_auth_password_history'


# ****************************** END OF CUSTOM SECURITY IMPLEMENTATION ******************************
