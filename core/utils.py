import json
import random, string, urllib,  urllib2, logging

from datetime import timedelta, datetime, time
from decimal import Decimal

import pytz
import requests
from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.db import transaction
from django.db.models import Q, Max, Sum, Count, F
from django.shortcuts import get_object_or_404
from django.template import Context
from django.template import loader
from django.urls import reverse
from django.utils import timezone
from notifications.models import Notification

from core.exceptions import SuspiousException
from core.models import Message, ResponseCode, Config, Tracker, TransactionDetail, Transaction, Account, SchedulerReport, Donation, Member, Package, TransactionPointer, \
    TransactionDetailPointer, EmailCycler, Reason, TransactionSkippedReason, BankAccountVerification, Bank, CallDetail, TestimonyCode, User, Currency
# from core.tasks import gh_matcher_scheduler
from django.conf import settings


log = logging.getLogger("%s.*" %settings.PROJECT_NAME)
BTC = settings.BITCOIN_CODE

SECONDS = 1
MINUTES = 60
HOURS = MINUTES*60
DAYS = HOURS*24
WEEKS = DAYS*7
MONTHS = DAYS*30


def get_time_diff(time, format=HOURS):
    now = timezone.now()
    secs = (now - time).total_seconds()
    return secs/format


def btc_limit(amount, multiple):
    x=0
    while amount > (x*multiple):
        x += 1
    return (x-1)*multiple


def mask_email(email):
    mail_part = email.split("@")
    l = len(mail_part[0]) - 4
    return "%s%s@%s" % ("*" * l, mail_part[0][l:], mail_part[1])


def generate(length, special='!@#$%^&*()', digitsOnly=False):
    if digitsOnly:
        chars = string.digits
    else:
        chars = string.ascii_letters + string.digits + special

    return ''.join(random.SystemRandom().choice(chars) for i in range(int(length)))


def generate_id(prefix):
    return prefix+timezone.now().strftime("%m%d%H%M%S%f")


def decimal_normalise(f):
    d = Decimal(str(f));
    return d.quantize(Decimal(1)) if d == d.to_integral() else d.normalize()


#https://docs.djangoproject.com/en/dev/ref/models/queries/#django.db.models.F
# def get_notication(request, nid):
#     from django.utils import timezone
#     now = timezone.now()
#     notification = Notification.objects.filter(id=nid, active__lte=now, expires__gte=now)[:1]
#     if notification and notification[0]:
#         # Check if the user has permission to access this notification
#         if notification[0].type == 'Content':
#             return notification[0].message
#         else:
#             pass
#             # get the real value from path/url
#     else:
#         return ""


def sms_send(sender, receivers, message, mid=None, secured=True, connection=None):
    # TODO: use the connection if provided
    # params = {'username': settings.SMS_USER, 'password': settings.SMS_PASS, 'sender': sender, 'message': message, 'mobile': ",".join(receivers)}
    # params = {'username': settings.SMS_USER, 'password': settings.SMS_PASS, 'sender': sender, 'message': message, 'recipient': ",".join(receivers)}
    params = {'sender': sender, 'message': message, 'to': ",".join(receivers), 'type': 0, 'routing': 3, 'token': settings.SMS_API_KEY}
    # message=****route_3***&to=08164018766&sender=Hello&type=0&routing=3&token=bDvL7hGzZRJfUxAyZHV0gleX3PcT1nQtepjDOE1Cel2MHNOakPhNEETXg0NGnWSKLaslCrB2lAHyfxAcLzgfntVPVe4PYGNvTN3F
    if secured:
        url = "https://smartsmssolutions.com/api/?"
        # url = "https://api.smartsmssolutions.com/smsapi.php?"
    else:
        url = "http://smartsmssolutions.com/api/?"
        # url = "http://api.smartsmssolutions.com/smsapi.php?"
    #     https://api.smartsmssolutions.com/smsapi.php?username=evernob&password=
    # if secured:
    #     url = "https://www.bbnplace.com/sms/bulksms/bulksms.php?"
    # else:
    #     url = "http://sms.bbnplace.com/bulksms/bulksms.php?"

    msg = Message.objects.get(id=mid)
    # TODO: Remove this check from here
    if get_bool_conf(1020, None, True):
        response = urllib2.urlopen(url+urllib.urlencode(params)).read()
        print response
        # print response.split(" ")[0]
        res = response.split("||")[0]

        msg.response_code = ResponseCode.objects.filter(id=res).first()

        # if res == "OK":
        if res == "1000":
            msg.sent_time = timezone.now()
            msg.counter += 1
    else:
        msg.response_code = None

    msg.save()
    return ResponseCode.objects.filter(id=res).first()


def sms_check_balance(secured=False):
    params = {'username': settings.SMS_USER, 'password': settings.SMS_PASS}
    if secured:
        url = "https://www.bbnplace.com/sms/bulksms/acctbals.php?"
    else:
        url = "http://sms.bbnplace.com/bulksms/acctbals.php?"
    return urllib2.urlopen(url+urllib.urlencode(params)).read()


def track(obj_id, type_, note, change, updater):
    tracker = Tracker()
    tracker.object_id = obj_id
    tracker.type = type_
    tracker.note = note
    tracker.change = change
    tracker.updater = updater
    tracker.created = timezone.now()
    return tracker


def get_bool_conf(code, country, default=False):
    try:
        if int(Config.objects.get(code=code, country=country).value) == 0:
            return False
        else:
            return True
    except:
        return default


def get_int_conf(code, country, default=0):
    try:
        return int(Config.objects.get(code=code, country=country).value)
    except:
        return default


def get_date_conf(code, country, default='2017,1,1,1,0,0'):
    try:
        x = (Config.objects.get(code=code, country=country).value or default).split(",")
        # return datetime(int(x[0]), int(x[1]), int(x[2]), int(x[3]), int(x[4]), int(x[5]), tzinfo=pytz.timezone('Africa/Lagos')).astimezone(pytz.UTC)

        return datetime(int(x[0]), int(x[1]), int(x[2]), int(x[3])-1, int(x[4]), int(x[5]), tzinfo=pytz.UTC)
    except:
        x = default.split(",")
        # return datetime(int(x[0]), int(x[1]), int(x[2]), int(x[3]), int(x[4]), int(x[5]), tzinfo=pytz.timezone('Africa/Lagos')).astimezone(pytz.UTC)
        return datetime(int(x[0]), int(x[1]), int(x[2]), int(x[3])-1, int(x[4]), int(x[5]), tzinfo=pytz.UTC)


def get_float_conf(code, country, default=1.0):
    try:
        return float(Config.objects.get(code=code, country=country).value)
    except:
        return default


def get_decimal_conf(code, country, default=1.0):
    try:
        return decimal_normalise(Config.objects.get(code=code, country=country).value)
    except:
        return default


def get_str_conf(code, country, default=None):
    try:
        return Config.objects.get(code=code, country=country).value
    except:
        return default


# class IntegerRangeField(models.IntegerField):
#     def __init__(self, verbose_name=None, name=None, min_value=None, max_value=None, **kwargs):
#         self.min_value, self.max_value = min_value, max_value
#         models.IntegerField.__init__(self, verbose_name, name, **kwargs)
#
#     def formfield(self, **kwargs):
#         defaults = {'min_value': self.min_value, 'max_value':self.max_value}
#         defaults.update(kwargs)
#         return super(IntegerRangeField, self).formfield(**defaults)

# PH, PF, BS, RF posible type
def ph(me, amount, currency, type=Donation.PH, channel=Donation.USER_CHANNEL, force_ph=False):
    if not force_ph and not me.is_email_verified:
        return {'msg': 'Please <a href="%s">Verify</a> your email to complete your registration' %reverse('core:profile'), 'type': 'Info', 'status': 'Rejected'}

    if not force_ph and get_bool_conf(1020, me.country, False) and not me.is_phone_verified:
        return {'msg': 'Please <a href="%s">Verify</a> your phone to complete your registration' % reverse('core:profile'), 'type': 'Info', 'status': 'Rejected'}

    can_ph_now, next_ph, reason = can_ph(me, me.phone, amount)
    # log.info("Can PH Now: %s  ::: Next PH: %s   ::: Reason: %s" % (can_ph_now, next_ph, reason))
    don_id = ''
    don_amount = 0
    country_none = None if currency.code == BTC else me.country
    if can_ph_now or force_ph:
        min_ph = me.min_ph
        if not force_ph and get_bool_conf(1207, country_none, False):  # if the system is configured to prevent downgrade
            if type == Donation.PH and amount < min_ph:  # if member is trying to downgrade
                return {'msg': 'Your minimum PH is (%s %d)' % (currency.symbol, min_ph,), 'next': next_ph, 'type': 'Info', 'status': 'Rejected', 'don_id': don_id, 'don_amount': don_amount}

        with transaction.atomic():
            don = Donation(id=generate_id(settings.DONATION_ID_PREFIX), amount=amount, currency=currency, member=me, type=type, status=Account.PENDING, channel=channel, is_bonus=me.is_bonus,
                           is_active=me.is_active)

            if type in [Donation.PH_FEE, Donation.ACTIVATION]:
                don.is_committed = True
            elif get_decimal_conf(1230, country_none, 0) == 0:
                don.is_committed = True
            else:
                don.is_committed = False

            # don.commitment_matched will remain Null even though is_committed says True, cos this will be the ONLY way know that commitment dose not truly apply to this Donation
            if channel == Donation.USER_CHANNEL and type in [Donation.PH, Donation.RC] and get_bool_conf(1216, country_none, True):
                don.is_auto_recycle = True
            else:
                don.is_auto_recycle = False
            don.save()
            don_id = don.id
            don_amount = don.amount

            if type == Donation.PH and get_decimal_conf(1240, country_none, 0) > 0:
                don_recommitment = Donation.objects.filter(member=me, type=Donation.PH, currency=currency).exclude(Q(status=Account.CANCELLED) | Q(id=don.id)).order_by('created').first()
                if don_recommitment:
                    don_recommitment.recommitment = don
                    don_recommitment.save()
            else:
                # TODO: I think I should set self as the don_recommitment
                pass

            if channel == Donation.USER_CHANNEL and min_ph != amount and type == Donation.PH and get_bool_conf(1207, country_none, False):     # Decide to change min_ph
                me.min_ph = amount
                me.save()

            allow_auto_compute_gh = get_bool_conf(1400, country_none, True)
            stop_over_growth = get_bool_conf(1401, country_none, False)

            # Popluating Accounts************
            # generate_account(prefix, type_, don, owner, allow_auto_compute_gh, stop_over_growth=True, config_id=None, gh_amount=0, don_type='PH'):

            ph_acc = generate_account(type, type, don, me, allow_auto_compute_gh)
            t_code = TestimonyCode(id=generate_id(TestimonyCode.PREFIX), testifier=me, amount=don.amount, object_id=ph_acc.id, type=TestimonyCode.PH, currency=currency)
            t_code.save()
            ph_acc.testimony_code = t_code

            if (not me.is_active) or (type in [Donation.REFUND, Donation.BONUS]):
                don.fulfilled = ph_acc.fulfilled = timezone.now()
                don.is_committed = True
                don.recommitment = don
                ph_acc.status = don.status = Account.PROCESSED
                ph_acc.balance = 0
                ph_acc.is_active = me.is_active
                don.save()
            ph_acc.save()

            # ================Get The GH Accounts Ready==================
            refund_percent = get_decimal_conf(1233, (None if currency.code == BTC else me.country), 0.0)
            if don.type in [Donation.PH, Donation.RC]:
                gh_acc = generate_account(Account.GH, Account.GH, don, me, allow_auto_compute_gh, stop_over_growth=stop_over_growth, config_code=1030)
                gh_acc.save()
            elif don.type in [Donation.REFUND, Donation.BONUS]:
                gh_acc = generate_account(don.type, Account.GH, don, me, allow_auto_compute_gh, stop_over_growth=stop_over_growth)
                gh_acc.save()
            elif don.type in [Donation.ACTIVATION] and refund_percent > 0:
                gh_acc = generate_account(Account.GH, Account.GH, don, me, allow_auto_compute_gh, stop_over_growth=stop_over_growth, gh_amount=don.amount*refund_percent/100)
                gh_acc.save()
            else:
                pass
                # Ignore Donation.PF (PH Fee)

            gh_paused_percent = get_decimal_conf(1218, country_none, 0)
            if gh_paused_percent > 0 and don.type in [Donation.PH] and get_bool_conf(1217, country_none, False) and is_first_package_request(don.amount, currency, me):
                gh_paused_acc = generate_account(Account.GH_PAUSED, Account.GH_PAUSED, don, me, allow_auto_compute_gh, stop_over_growth=stop_over_growth, config_code=1218, gh_amount=gh_acc.amount)
                gh_paused_acc.save()

                gh_acc.amount -= gh_paused_acc.amount

                if allow_auto_compute_gh:
                    gh_acc.max = gh_acc.amount
                else:
                    if stop_over_growth:
                        gh_acc.max = gh_acc.amount
                    else:
                        gh_acc.max = 0
                gh_acc.save()

            sponsor_percent = get_decimal_conf(1061, country_none, 0)
            sponsor_amount = get_decimal_conf(1062, country_none, 0)
            donations = Donation.objects.filter(member=me, account__type__in=[Account.PH], currency=currency).exclude(status__in=[Account.CANCELLED])
            sponsorship_limit = get_int_conf(1064, country_none, 0)
            if get_bool_conf(1060, country_none, False) and (sponsor_percent > 0 or sponsor_amount > 0) and (sponsorship_limit == 0 or (sponsorship_limit >= len(donations))):
                if don.type in [Donation.PH] and not me.is_bonus and me.is_active and me.sponsor:
                    if sponsor_percent > 0:
                        sp_acc = generate_account(Account.SPONSOR, Account.SPONSOR, don, me.sponsor, allow_auto_compute_gh, stop_over_growth=stop_over_growth, config_code=1061, gh_amount=(don.amount*sponsor_percent/100))
                        sp_acc.save()
                    else:
                        sp_acc = generate_account(Account.SPONSOR, Account.SPONSOR, don, me.sponsor, allow_auto_compute_gh, stop_over_growth=stop_over_growth, config_code=1062, gh_amount=sponsor_amount)
                        sp_acc.save()

            reg_percent = get_decimal_conf(1051, country_none, 0)
            reg_amount = get_decimal_conf(1052, country_none, 0)
            if len(donations) == 1 and don.type in [Donation.PH] and not me.is_bonus and me.is_active and (reg_percent > 0 or reg_amount > 0):
                if reg_percent > 0:
                    rb_acc = generate_account(Account.REG_BONUS, Account.REG_BONUS, don, me, allow_auto_compute_gh, stop_over_growth=stop_over_growth, config_code=1051)
                    rb_acc.save()
                else:
                    rb_acc = generate_account(Account.REG_BONUS, Account.REG_BONUS, don, me, allow_auto_compute_gh, stop_over_growth=stop_over_growth, config_code=1052, gh_amount=reg_amount)
                    rb_acc.save()

            if don.type in [Donation.PH, Donation.RC] and not me.is_bonus and me.is_active and get_bool_conf(1080, country_none, False) and get_bool_conf(1081, country_none, 0) > 0:
                ad_acc = generate_account(Account.ADVERT, Account.ADVERT, don, me, allow_auto_compute_gh, stop_over_growth, config_code=1081)
                ad_acc.save()

        trans_details = []
        x = get_int_conf(1211, country_none, 0)
        if x < 1 and not me.is_bonus and me.is_active:
            if x == 0:
                if scheduler_active():
                    trans_details = match_ph_2_gh(ph_acc)
            else:
                trans_details = match_ph_2_gh(ph_acc)

            if len(trans_details) == 0:
                return {'msg': "Your PH Order has been received, we'll inform you as soon as you are matched", 'type': 'Refresh', 'status': 'Successful', 'don_id': don_id, 'don_amount': don_amount}
            else:
                return {'msg': 'Have got some order to give help', 'type': 'Refresh', 'status': 'Successful', 'don_id': don_id, 'don_amount': don_amount}

        # return {'msg': 'We have received your request to Provide Help', 'type': 'Refresh'}
        # return {'msg': 'Thanks %s, your PH request was successfully processed' % me.first_name, 'type': 'Refresh', 'status': 'Successful', 'don_id': don_id, 'don_amount': don_amount}
        return {'msg': 'Thanks %s, your request has been received' % me.first_name, 'type': 'Refresh', 'status': 'Successful', 'don_id': don_id, 'don_amount': don_amount}
    else:
        if next_ph:
            return {'msg': 'Thanks for your attempt, your next PH time is %s' % next_ph.strftime('%d, %b %Y  %H:%M'), 'type': 'Info', 'status': 'Rejected', 'don_id': don_id, 'don_amount': don_amount}
        else:
            return {'msg': 'Thanks for your attempt, %s' % reason, 'type': 'Info', 'status': 'Rejected', 'don_id': don_id, 'don_amount': don_amount}


# returns @can_ph_now, @next_ph, @reason
def can_ph(me, currency, phone, amount=0):
    last_ph = Donation.objects.filter(member__user_id=me.user.id, currency=currency, account__type__in=[Donation.PH]).exclude(status=Account.CANCELLED).aggregate(last=Max('created'))['last']
    user = User.objects.get(id=me.user.id)
    if me and me.status in [Member.ACTIVE, Member.PAUSED] and user and user.is_active:
        if last_ph:
            country_none = None if currency.code == BTC else me.country
            next_ph = last_ph + timedelta(hours=get_int_conf(1208, country_none, 0))
            now = timezone.now()
            if now > next_ph:
                today = datetime.now(pytz.utc).date()
                # tomorrow = today + timedelta(1)
                today_start = datetime.combine(today, time())
                # today_end = datetime.combine(tomorrow, time())

                max_count = get_int_conf(1205, country_none, 2)

                # dons = Donation.objects.filter(member__user_id=me.user.id, account__type__in=[Donation.PH], created__gte=today_start).exclude(status__in=[Account.PROCESSED, Account.PROCESSED_BONUS,Account.CANCELLED])
                dons = Donation.objects.filter(member__user_id=me.user.id, account__type__in=[Donation.PH], status__in=[Account.PENDING, Account.PROCESSING])

                if dons.aggregate(count=Count('id'))['count'] >= max_count:
                    return False, None, "You cannot have more than (%d) unprocessed PH" % max_count
                # if (dons.aggregate(sum=Sum('id'))['sum'] or 0) >= max_value:
                #     return False, None, "You have reached the maximum '%d' allowed PH 'value', please try again later or reduce your PH amount" % max_value

                return True, None, None
            else:
                return False, next_ph, "You're not allowed to PH again till %s" % next_ph
        return True, None, None
    else:
        return False, None, "This is profile is Not Active"


def can_gh(acc_2_gh):
    # disable_gh_without_ph = get_bool_conf(1402, me.country, True)
    # if (acc_2_gh.is_bonus and not disable_gh_without_ph) or not acc_2_gh.owner.is_active:

    if not acc_2_gh.owner.is_active:
        return True

    # Use the acc_2_gh to retrieve the corresponding PH account
    ph_accs = acc_2_gh.donation.account_set.filter(type__in=[Account.PH, Account.RC, Account.PH_FEE, Account.REFUND, Account.BONUS], status__in=[Account.PROCESSED, Account.PROCESSED_BONUS])
    ph_acc = ph_accs.first()

    country_none = None if acc_2_gh.currency == BTC else acc_2_gh.owner.country
    if not ph_acc:
        if len(ph_accs) > 1:
            tracker = track(ph_accs[0].id, 'account', 'Attempt to GH %s, but noticed the has more than 1 PH', 'Processing', 'Scheduler')
            tracker.save()

            message = "Found suspicious trend on Account %s, the account has %d donations tied to it. Your attention will be required for further investigation" % (ph_accs[0].id, len(ph_accs))
            html_message = loader.render_to_string('core/mail_templates/notification.html', {'firstName': 'Administrator', 'mail_content': message})

            from core.tasks import sendMail
            admins = []
            for a in settings.ADMINS:
                admins.append("%s <%s>;" % (a[0], a[1]))
            sendMail.apply_async(kwargs={'subject': "***:::Attention Admin:::***", 'message': message, 'recipients': admins, 'html_message': html_message})
        return False
    if ph_acc.type in [Account.REFUND, Account.BONUS]:
        return True

    rc_percent = get_decimal_conf(1240, country_none, 0)
    if rc_percent > 0:
        recommitted = TransactionDetail.objects.filter(account__donation=acc_2_gh.donation.recommitment, status=TransactionDetail.CONFIRMED).aggregate(sum=Sum('amount'))['sum'] or 0
        if ((rc_percent * acc_2_gh.donation.amount)/100) > recommitted:
            return False

    # ***************************************************************************
    today = datetime.now(pytz.utc).date()
    today_start = datetime.combine(today, time())

    disallow_multi_accounts = get_bool_conf(1024, country_none, False) or get_bool_conf(1003, country_none, False) or get_bool_conf(1041, country_none, False)
    if not disallow_multi_accounts and acc_2_gh.donation.type == Donation.PH:
        dons = Donation.objects.filter(member=acc_2_gh.owner, currency=acc_2_gh.currency, created__gte=today_start, type=Donation.PH).exclude(status=Account.CANCELLED).order_by('created')
        if len(dons) >= get_int_conf(1407, country_none, 2):
            log.info("%s NOT qualified to GH because user ***has exceeded the User Max Daily GH count %d" % (acc_2_gh.id, len(dons)))
            return False
        if ((dons.aggregate(sum=Sum('amount'))['sum'] or 0)+acc_2_gh.amount) > get_decimal_conf(1408, country_none, 150000):
            log.info("%s NOT qualified to GH because user ***has exceeded the Max daily GH count %d" % (acc_2_gh.id, len(dons)))
            return False

        related_members = get_related_member_ids([acc_2_gh.owner])

        linked_dons = Donation.objects.filter(member__in=related_members, currency=acc_2_gh.currency, created__gte=today_start, type=Donation.PH).exclude(status=Account.CANCELLED).order_by('created')
        if len(linked_dons) >= get_int_conf(1409, country_none, 6):
            log.info("%s NOT qualified to GH cos it ***has exceeded the Linked User Max Daily GH count %d" % (acc_2_gh.id, len(linked_dons)))
            return False
        if ((linked_dons.aggregate(sum=Sum('amount'))['sum'] or 0)+acc_2_gh.amount) > get_decimal_conf(1410, country_none, 500000):
            log.info("%s NOT qualified to GH cos it ***has exceeded the Max daily GH count %d" % (acc_2_gh.id, len(linked_dons)))
            return False

    # if get_bool_conf(1219, country_none, False):
    #     release_percent = get_float_conf(1220, country_none, 100)
    #     sum = TransactionPointer.objects.filter(account=acc_2_gh, transactiondetailpointer__trans_detail__status__in=[TransactionDetail.AWAITING_PAYMENT,TransactionDetail.AWAITING_CONFIRMATION,TransactionDetail ]).aggregate(sum=Sum('amount'))['sum'] or 0
    #     tps = TransactionPointer.objects.filter(account=acc_2_gh)
    #     if

    # At this point we have only 1 PH, but we need to be sure this PH has been fulfilled
    if not acc_2_gh.is_bonus or acc_2_gh.owner.is_active or ph_acc.type in [Account.PH]:  # if no one is allowed to GH with fulfilling PH or this account is NOT even admin's, then we need to be sure that this PH order has been fulfilled
        total_paid = TransactionDetail.objects.filter(sender=acc_2_gh.owner, account=ph_acc, status=TransactionDetail.CONFIRMED).aggregate(Sum('amount'))['amount__sum']
        if total_paid is None or total_paid < ph_acc.amount:
            return False
    return True


def gh_amount_can_be_matched(amount, trans, be_smart=False, country_none=None):
    daily_limit_bal = get_daily_limit_balance(trans.currency)
    if daily_limit_bal <= 0:
        log.info("Empty daily limit******** Bal: N 0")
        TransactionSkippedReason.objects.create(transaction=trans, message="Empty daily limit Bal: N 0")
        return False
    if amount > daily_limit_bal:
        # we don't want to pay this person cos that will exhaust the daily limit (Small amount 1st)
        log.info("Low daily limit******** Bal: N %d" % daily_limit_bal)
        TransactionSkippedReason.objects.create(transaction=trans, message="GH amount (%d) higher than the current daily limit balance (%d)" % (amount, daily_limit_bal))
        return False

    if be_smart:     # Apply Smart Matching
        matched_count = TransactionDetail.objects.filter(transaction=trans).exclude(status=TransactionDetail.CANCELLED, rematched=TransactionDetail.YES).aggregate(count=Count('id'))['count']
        if matched_count == 0:  # if first time, match at least half
            if trans.amount/2 > amount:
                return False
            else:
                return True
        elif matched_count == 1:
            if trans.amount/4 > amount:
                return False
            else:
                return True
        elif matched_count == 2:
            if trans.amount/8 > amount:
                return False
            else:
                return True
        else:
            return True
    else:
        return True


def get_total_matched_balance(acc):
    return TransactionDetail.objects.filter(account=acc).exclude(status=TransactionDetail.CANCELLED, rematched=TransactionDetail.YES).aggregate(sum=Sum('amount'))['sum'] or 0


def _get_ph_balance(acc):
    amount_matched = TransactionDetail.objects.filter(account=acc).exclude(status=TransactionDetail.CANCELLED, rematched=TransactionDetail.YES).aggregate(sum=Sum('amount'))['sum'] or 0
    if acc.match_only > 0:
        if amount_matched >= acc.match_only:
            return 0, False
        else:
            return (acc.match_only - amount_matched), False
    return (acc.donation.amount - amount_matched), False


def get_ph_balance(acc, c_percent):
    amount_matched = TransactionDetail.objects.filter(account=acc).exclude(status=TransactionDetail.CANCELLED, rematched=TransactionDetail.YES).aggregate(sum=Sum('amount'))['sum'] or 0
    gh_multiple = get_decimal_conf(1430, acc.currency.country, 0.02)
    if acc.type == Account.ACTIVATION:
        acc.can_split = False
        return acc.balance, True
    if c_percent > 0:
        acc.can_split = False
        if acc.match_only > 0:
            if amount_matched >= acc.match_only:
                return 0, True
            else:
                if acc.currency.code == BTC:
                    return (acc.match_only - amount_matched), True
                else:
                    return (acc.match_only - amount_matched), True

        commitment = (c_percent * acc.donation.amount)/100
        if acc.currency.code == BTC:
            pass
            #TODO: you only need this if BTC will have commitment enabled
        else:
            # This will ensure that if we are working with 10% commitment and one PHed 16,000 with 1600 as commitment, it will be upgraded to 2000
            upgrade_commitment = gh_multiple + commitment - (commitment % gh_multiple)
            commitment = commitment if (commitment % gh_multiple) == 0 else (upgrade_commitment if upgrade_commitment < acc.donation.amount else upgrade_commitment)

        if commitment > amount_matched:
            return (commitment - amount_matched), True
        elif acc.maturity < timezone.now():
            # Anything below this line must return False for is_commitment cos commitment has been matched already
            don = acc.donation
            org_don = Donation.objects.filter(recommitment=don).order_by('-created').first()
            if org_don is None:
                # This is most likely the first Donation
                return (acc.donation.amount - amount_matched), False
            elif org_don.fulfilled is None:
                return 0, False
            else:
                if don.recommitment and don.recommitment.id == don.id:  #If this don is recommimtment for itself (Happens when there's no need for recommitment)
                    return (acc.donation.amount - amount_matched), False

            ori_trans = Transaction.objects.filter(transactionpointer__account__donation=org_don)
            if len(ori_trans) == 0:
                return 0, False

            return (acc.donation.amount - amount_matched), False
        else:
            return 0, False
    else:
        if acc.match_only > 0:
            if amount_matched >= acc.match_only:
                return 0, False
            else:
                return (acc.match_only - amount_matched), False
        return (acc.donation.amount - amount_matched), False


def get_daily_limit_balance(currency):
    # total = SchedulerReport.objects.filter(type='Matched', created__date=timezone.now().date()).aggregate(sum=Sum('amount'))['sum'] or 0
    total = TransactionDetail.objects.filter(status__in=[TransactionDetail.AWAITING_PAYMENT, TransactionDetail.AWAITING_CONFIRMATION, TransactionDetail.CONFIRMED], created__date=timezone.now().date(),
                                             currency=currency).aggregate(sum=Sum('amount'))['sum'] or 0
    return get_decimal_conf(1403, currency.country, 500000) - total


def match_ph_2_gh(ph_acc, gh_txs=None, disabled_only=False, ph_only_amount=0, c_percent=0, be_smart=False, country_none=None):
    trans_details = []
    if get_daily_limit_balance(ph_acc.currency) == 0:
        return trans_details

    if gh_txs is not None:
        gh_transs = gh_txs
    else:
        gh_transs = Transaction.objects.filter(status__in=[Transaction.PENDING, Transaction.INCOMPLETE], owner__status=Member.ACTIVE, owner__is_fake=False, can_match=True, currency=ph_acc.currency
                                               ).exclude(owner=ph_acc.owner).distinct().order_by('is_active', '-is_bonus', 'created')[:10]

    for gh_trans in gh_transs:
        if gh_txs and len(gh_txs) > 0:
            total_matched = get_amount_matched(gh_trans, True)
        else:
            total_matched = get_amount_matched(gh_trans)

        if total_matched >= gh_trans.amount:
            if TransactionDetail.objects.filter(transaction=gh_trans, status=TransactionDetail.CONFIRMED).aggregate(sum=Sum('amount'))['sum'] or 0 >= gh_trans.amount:
                gh_trans.status = Transaction.COMPLETED
                gh_trans.balance = 0
            else:
                gh_trans.status = Transaction.PROCESSING
            gh_trans.save()
            continue
        else:
            tds_2_rematch = TransactionDetail.objects.filter(transaction=gh_trans, status=TransactionDetail.CANCELLED, rematched=TransactionDetail.NO)
            total_2_rematch = tds_2_rematch.aggregate(sum=Sum('amount'))['sum'] or 0
            gh_trans.balance = gh_trans.amount - total_matched - total_2_rematch

            # Let's rematch all that need to re-matched first
            for td_2_rematch in tds_2_rematch:  # Let try to re-match each GHed trans detail that need to be re-matched
                with transaction.atomic():
                    # We need the user's Ph Balance at real time to avoid excesses
                    ph_bal, is_commitment = get_ph_balance(ph_acc, c_percent=c_percent)

                    if ph_bal == 0:
                        break

                    if td_2_rematch.amount >= ph_bal:   # TODO: Think of how to ensure Commitment is matched at once and not splited
                        if not gh_amount_can_be_matched(ph_bal, gh_trans, be_smart=be_smart, country_none=country_none):
                            continue

                        trans_detail, trans_detail_pointers = generate_td_from_tx(gh_trans, ph_acc, ph_bal)

                        td_2_rematch.rematched = TransactionDetail.YES
                        td_2_rematch.save()

                        don = ph_acc.donation
                        if is_commitment and ph_acc.type != Account.ACTIVATION:
                            don.commitment_matched = timezone.now()
                            ph_acc.status = don.status = Account.PARTIAL
                            ph_acc.balance = ph_acc.amount - get_total_matched_balance(ph_acc)
                        else:
                            ph_acc.status = don.status = Account.PROCESSING
                            ph_acc.balance = 0
                        don.save()
                        ph_acc.save()

                        gh_trans.balance = gh_trans.amount - get_amount_matched(gh_trans)

                        if gh_trans.balance <= 0:
                            gh_trans.status = Transaction.PROCESSING
                        else:
                            gh_trans.status = Transaction.INCOMPLETE
                        update_gh_account_status(gh_trans)
                        gh_trans.save()

                        trans_details.append(trans_detail)
                        log.info("Re-Matched Transaction amount %d  MATCH-01 (%s)" % (ph_bal, trans_detail.id))
                        break
                    else:
                        if is_commitment:   # if it is commitment, I don't want to break the money in pieces
                            continue
                        if not gh_amount_can_be_matched(td_2_rematch.amount, gh_trans, be_smart=be_smart, country_none=country_none):
                            continue
                            # generate_td_from_tx(trans, acc, amount):
                        trans_detail, trans_detail_pointers = generate_td_from_tx(gh_trans, ph_acc, td_2_rematch.amount)

                        td_2_rematch.rematched = TransactionDetail.YES
                        td_2_rematch.save()

                        don = ph_acc.donation
                        ph_acc.status = don.status = Account.PARTIAL
                        ph_acc.balance = ph_acc.amount - get_total_matched_balance(ph_acc)
                        don.save()
                        ph_acc.save()

                        gh_trans.balance = gh_trans.amount - get_amount_matched(gh_trans)
                        if gh_trans.balance <= 0:
                            gh_trans.status = Transaction.PROCESSING
                        else:
                            gh_trans.status = Transaction.INCOMPLETE
                        update_gh_account_status(gh_trans)
                        gh_trans.save()

                        trans_details.append(trans_detail)
                        log.info("Re-Matched Transaction amount %d  MATCH-02 (%s)" % (td_2_rematch.amount, trans_detail.id))
                        continue
            # Done Re-Matching

            ph_bal, is_commitment = get_ph_balance(ph_acc, c_percent=c_percent)
            if ph_bal == 0:
                return trans_details

            if len(tds_2_rematch) > 0:   # If it is > 0 it means the 1st loop executed we need to re-update the parameters
                tds_2_rematch = TransactionDetail.objects.filter(transaction=gh_trans, status=TransactionDetail.CANCELLED, rematched=TransactionDetail.NO)
                total_2_rematch = tds_2_rematch.aggregate(sum=Sum('amount'))['sum'] or 0
                total_matched = get_amount_matched(gh_trans)
                gh_trans.balance = gh_trans.amount - total_matched - total_2_rematch

            if gh_trans.balance > 0:
                # If we get here it means we need to create some more TransactionDetails to complete the Transactions or cos this transaction has not been matched at all
                # bal = gh_trans.amount - (total_matched + total_2_rematch)
                with transaction.atomic():
                    if gh_trans.balance >= ph_bal:
                        if not gh_amount_can_be_matched(ph_bal, gh_trans, be_smart=be_smart, country_none=country_none):
                            continue
                        trans_detail, trans_detail_pointers = generate_td_from_tx(gh_trans, ph_acc, ph_bal)

                        don = ph_acc.donation
                        if is_commitment and ph_acc.type != Account.ACTIVATION:
                            don.commitment_matched = timezone.now()
                            ph_acc.status = don.status = Account.PARTIAL
                            ph_acc.balance = ph_acc.amount - get_total_matched_balance(ph_acc)
                        else:
                            ph_acc.status = don.status = Account.PROCESSING
                            ph_acc.balance = 0
                        don.save()
                        ph_acc.save()

                        gh_trans.balance = gh_trans.amount - get_amount_matched(gh_trans)

                        if gh_trans.balance == ph_bal:
                            gh_trans.status = Transaction.PROCESSING
                        else:
                            gh_trans.status = Transaction.INCOMPLETE
                        update_gh_account_status(gh_trans)
                        gh_trans.save()

                        trans_details.append(trans_detail)
                        log.info("Matched Transaction amount %d  MATCH-03 (%s)" % (ph_bal, trans_detail.id))
                    else:
                        if is_commitment:   # if it is commitment, I don't want to break the money in pieces
                            continue
                        if not gh_amount_can_be_matched(gh_trans.balance, gh_trans):
                            continue
                        trans_detail, trans_detail_pointers = generate_td_from_tx(gh_trans, ph_acc, gh_trans.balance)

                        don = ph_acc.donation
                        ph_acc.status = don.status = Account.PARTIAL
                        ph_acc.balance = ph_acc.amount - get_total_matched_balance(ph_acc)
                        don.save()
                        ph_acc.save()

                        gh_trans.balance = gh_trans.amount - get_amount_matched(gh_trans)
                        gh_trans.status = Transaction.PROCESSING
                        update_gh_account_status(gh_trans)
                        gh_trans.save()

                        trans_details.append(trans_detail)
                        log.info("Matched Transaction amount %d  MATCH-04 (%s)" % (gh_trans.balance, trans_detail.id))
            else:
                gh_trans.status = Transaction.PROCESSING
                gh_trans.save()

    return trans_details


def credit_accounts(country, now=timezone.now(), id=None):
    prevent_over_growth = get_bool_conf(1401, country, True)
    if id:
        ghes = Account.objects.filter(id=id)
    else:
        types = [Account.GH, Account.GH_PAUSED]
        if get_bool_conf(1009, country, False):
            types = types + [Account.REG_BONUS, Account.SPONSOR, Account.GUIDER_BONUS, Account.SPEED_BONUS]
        ghes = Account.objects.filter(status__in=[Account.PENDING, Account.PARTIAL], type__in=types, donation__type__in=[Donation.PH, Donation.RC], currency__country=country, can_credit=True,
                                      roi__gt=0, balance__lt=F('amount_init'))
        if prevent_over_growth:
            ghes = ghes.filter(amount_live__lte=F('max'))

    for gh in ghes:
        hours_since_creation = int(get_time_diff(gh.created))
        max_count = get_int_conf(1210, country, 24 * 30)
        credit_interval = get_int_conf(1008, country, 24)
        unit_credit = gh.amount_init * gh.roi / 100 / max_count

        current_counter = credit_interval * (hours_since_creation / credit_interval)
        credit = unit_credit * current_counter
        if gh.amount_live < (credit + gh.donation.amount):
            total_credit = gh.donation.amount * gh.roi / 100
            gh.amount_live = credit + gh.amount_init
            gh.update_counter = current_counter
            gh.updated = now
            gh.can_credit = True if not prevent_over_growth else (gh.amount_live < (gh.donation.amount + total_credit))
            gh.save()


def block_acc(acc, reason=None, action=None):
    trans_details = TransactionDetail.objects.filter(account=acc, status=TransactionDetail.AWAITING_PAYMENT)
    sender = acc.owner
    counter = sum = 0
    ids = ""

    sender.status = Member.SUSPENDED
    sender.delete_on = timezone.now() + timedelta(hours=get_int_conf(1006, acc.owner.country, 72))
    sender.save()

    for td in trans_details:
        if timezone.now() > td.expires or action in ['***TIMEOUT***', '***CANT PAY***']:   # Reason is ONLY Provided if payer initiated this cancellation or Receiver raised Exception
            with transaction.atomic():
                trans = td.transaction
                trans.balance += td.amount
                if trans.balance == trans.amount:
                    trans.status = trans.PENDING
                else:
                    trans.status = Transaction.INCOMPLETE
                trans.save()

                td.status = TransactionDetail.CANCELLED
                td.reasons.create(message="%s ::: %s" % (action, reason))
                td.save()

                ph_acc = td.account
                don = ph_acc.donation
                ph_acc.status = don.status = Account.CANCELLED
                ph_acc.balance += td.amount
                ph_acc.save()
                don.save()

                don.reasons.create(message="%s ::: %s" % (action, reason))

                counter += 1
                sum += td.amount
                ids += td.id+", "

    if counter > 0:
        report = generate_report(typee=SchedulerReport.EXCEPTION, count=counter, amount=sum, currency=acc.currency, note="Blocked Ids: %s" % ids)
        report.save()
        if get_bool_conf(1405, acc.currency.country, 0):    # if the system is set to rematch immediately, then move into action
            from core.tasks import gh_matcher_scheduler
            gh_matcher_scheduler(trans_details[0].transaction_id)
    return counter


def confirm_transaction(td, auto=False, initiator=None, channel="User"):
    status = False
    # if channel == 'User' and initiator and td.transaction.owner != initiator:     # Transaction owner cannot confirm His own transaction
    #     expires = timezone.now() - timedelta(hours=get_int_conf(1213, td.currency.country, 24))
    #     print "***********::Expired Drugs::*************"
    #     if not TransactionDetail.objects.filter(id=td.id, status=TransactionDetail.AWAITING_CONFIRMATION, proof_date__isnull=False, proof_date__lte=expires, proof_acknowledge_date__isnull=True).first():
    #         return status

    with transaction.atomic():
        phing_acc = td.account
        sender = td.account.owner
        don = td.account.donation

        total_fulfilled = TransactionDetail.objects.filter(account=phing_acc, status=TransactionDetail.CONFIRMED).aggregate(sum=Sum('amount'))['sum'] or 0

        Reason.objects.filter(object_id=td.id, status=Reason.NOT_RESOLVED, content_type=ContentType.objects.get_for_model(td)).update(status=Reason.RESOLVED)
        Reason.objects.filter(object_id=phing_acc.id, status=Reason.NOT_RESOLVED, content_type=ContentType.objects.get_for_model(phing_acc)).update(status=Reason.RESOLVED)
        
        reasons = Reason.objects.filter(object_id=td.id, status=Reason.NOT_RESOLVED, content_type=ContentType.objects.get_for_model(td))

        if len(reasons) > 0 or sender.status == Member.SUSPENDED:  # if user was blocked b4 eliminate, if this transaction is part of the reasons for blocking

            all_my_td_ids = TransactionDetail.objects.filter(sender=sender).exclude(status=TransactionDetail.CONFIRMED)
            reasons = Reason.objects.filter(object_id__in=all_my_td_ids, content_type=ContentType.objects.get_for_model(td), status=Reason.NOT_RESOLVED)

            if len(reasons) == 0:
                sender.status = Member.ACTIVE
                if (total_fulfilled+td.amount) >= td.account.amount:  # if this PH is completed
                    phing_acc.status = don.status = Account.PROCESSED
                    phing_acc.fulfilled = don.fulfilled = timezone.now()
                    Account.PROCESSED
                else:
                    phing_acc.status = don.status = Account.PROCESSING
        else:
            if (total_fulfilled+td.amount) >= td.account.amount:  # if this PH is completed
                phing_acc.status = don.status = Account.PROCESSED
                phing_acc.fulfilled = don.fulfilled = timezone.now()
            else:
                total_matched = TransactionDetail.objects.filter(account=phing_acc).exclude(status=TransactionDetail.CANCELLED).aggregate(sum=Sum('amount'))['sum'] or 0
                if total_matched >= phing_acc.amount:
                    phing_acc.status = don.status = Account.PROCESSING
                else:
                    phing_acc.status = don.status = Account.PARTIAL

        don.save()
        sender.save()
        phing_acc.save()

        # TODO: Update status for the GHing Account
        td.status = TransactionDetail.CONFIRMED
        td.proof_acknowledge_date = timezone.now()
        td.save()

        trans = td.transaction
        total_confirmed = get_amount_confirmed(trans)
        if total_confirmed >= trans.amount:  # if this GH is completed
            trans.status = Transaction.COMPLETED
            trans.fulfilled = timezone.now()
            trans.balance = 0
            if get_bool_conf(1216, td.currency.country, True):
                ph(trans.owner, trans.owner.min_ph, currency=trans.currency_src, channel=Donation.AUTO_RECYCLE, force_ph=True)
        elif get_amount_matched(trans) >= trans.amount:
            trans.status = Transaction.PROCESSING
        else:
            trans.status = Transaction.INCOMPLETE

        trans.save()
        status = True

    if status:
        if get_bool_conf(1302, td.currency.country, 1):
            if auto:
                message = "The beneficiary for this Order [%s ::: %s %d] did not confirm the payment before the allocated time. To ensure the Participant who made this payment will have " \
                                                               " opportunity to get help, the system has automatically stamped this transaction as completed"  % (td.id, td.currency.symbol, td.amount)
            else:
                message = "We are glad to inform you, this Order [%s ::: %s %d] has been confirmed." % (td.id, td.currency.symbol, td.amount)

            html_message = loader.render_to_string('core/mail_templates/notification.html', {'firstName': 'Participants', 'mail_content': message})
            # send_trans_detail_notification(td, "Confirmation Notification", message, html_message)

            from core.tasks import sendMail
            sendMail.apply_async(kwargs={'subject': "Confirmation Notification", 'message': message, 'recipients': [td.transaction.owner.email, td.sender.email],
                                         'fail_silently': False, 'html_message': html_message,'connection_label': EmailCycler.get_email_label()})

    return status


def generate_tx(accs, multiple, amount, bank_account, old_bal=0, is_bonus=False, typee=Transaction.WITHDRAWAL):
    if len(accs) == 0 or amount == 0:
        return None
    av_bal = 0
    # Calculate all balance in the account to ensure it is up to the proposed withdrawal
    for a in accs:
        av_bal += a.amount_2_gh

    if (amount-old_bal) != av_bal:
        return
        # raise SuspiousException("Withdrawal Amount greater than available amount")

    max = amount
    if multiple > 0:
        if accs[0].currency.code == BTC:
            amount = btc_limit(amount=max, multiple=multiple)
            left_over = max - amount
        else:
            amount = max - (max % multiple)
            left_over = (max % multiple)

        if left_over > 0:
            mem = accs[0].owner
            if accs[0].currency.code == BTC:
                mem.gh_balance_btc = left_over
            else:
                mem.gh_balance = left_over
            mem.save()

    trans = Transaction()
    trans.id = generate_id(Transaction.PREFIX)
    trans.type = typee
    trans.amount = amount
    trans.balance = 0 if typee == Transaction.COIN else amount
    trans.owner = accs[0].owner
    trans.currency = trans.currency_src = accs[0].currency
    trans.status = Transaction.COMPLETED if typee == Transaction.COIN else Transaction.PENDING
    trans.bank_account = bank_account
    trans.is_bonus = is_bonus
    trans.is_active = True

    for a in accs:
        if not a.is_active:
            trans.is_active = False
            break;

    accounts = []
    trans_pointers = []
    stamped_amount = Decimal(0)
    trans.save()

    for acc in accs:
        if (amount-stamped_amount) >= acc.amount_2_gh:
            stamped_amount += acc.amount_2_gh

            acc.balance += acc.amount_2_gh
            acc.status = Account.PROCESSED if trans.type == Transaction.COIN and acc.balance == acc.amount else Account.PROCESSING if acc.balance == acc.amount else Account.PARTIAL
            trans_pointers.append(TransactionPointer.objects.create(amount=acc.amount_2_gh, account=acc, transaction=trans, is_full=True if acc.balance >= acc.amount else False))
            if acc.balance >= acc.amount:
                acc.can_credit = False
            acc.amount_2_gh = 0.0
            acc.save()
            accounts.append(acc)
        else:
            if (amount - stamped_amount) > 0:
                amt = amount - stamped_amount
                trans_pointers.append(TransactionPointer.objects.create(amount=acc.amount_2_gh, account=acc, transaction=trans, is_full=False))
                acc.balance += acc.amount_2_gh
                acc.status = Account.PARTIAL
                acc.amount_2_gh = 0.0
                acc.save()
                accounts.append(acc)
                break
            else:
                break

    t_code = TestimonyCode(id=generate_id(TestimonyCode.PREFIX), testifier=trans.owner, amount=trans.amount, object_id=trans.id, type=TestimonyCode.GH, currency=trans.currency)
    t_code.save()
    trans.testimony_code = t_code
    trans.save()
    return trans, trans_pointers, accounts


def generate_td_from_tx(trans, acc, amount):
    trans_detail = TransactionDetail()
    trans_detail.id = generate_id(settings.TRANSACTION_DETAIL_ID_PREFIX)
    trans_detail.transaction = trans
    trans_detail.account = acc
    trans_detail.currency = acc.currency
    trans_detail.amount = amount
    trans_detail.sender = acc.owner
    trans_detail.proof = None
    trans_detail.proof_date = None
    trans_detail.rematched = TransactionDetail.NO
    trans_detail.expires = timezone.now() + timedelta(hours=get_int_conf(1212, acc.currency.country, 48))
    trans_detail.save()

    trans_detail_pointers = []
    trans_pointers = TransactionPointer.objects.filter(transaction=trans)

    for tp in trans_pointers:   # Each TP has one or more Details
        if amount <= 0:
            break

        total_matched = TransactionDetailPointer.objects.filter(trans_pointer=tp).aggregate(total_matched=Sum('amount'))['total_matched'] or 0
        if total_matched == tp.amount:
            continue

        bal = tp.amount - total_matched
        tdp = TransactionDetailPointer(trans_pointer=tp, trans_detail=trans_detail)
        if bal <= amount:
            tdp.amount = bal
        else:
            tdp.amount = amount
        tdp.save()

        trans_detail_pointers.append(tdp)
        amount -= bal

    return trans_detail, trans_detail_pointers


# generate_account(PH, Donation.PH, don, member, allow_auto_compute_gh)
# def generate_account(prefix, type_, don, owner, allow_auto_compute_gh, stop_over_growth=True, config_id=None, gh_amount=0, allow_auto_recycle=False):
# generate_account(Account.SPONSOR, Account.SPONSOR, don, me.sponsor, allow_auto_compute_gh, stop_over_growth=stop_over_growth, config_code=1061)
def generate_account(prefix, type_, don, owner, allow_auto_compute_gh, stop_over_growth=True, config_code=None, gh_amount=0):
    acc = Account(id=generate_id(prefix), owner=owner, type=type_, status=Account.PENDING, donation=don, is_bonus=owner.is_bonus, is_active=owner.is_active, is_auto_gh=allow_auto_compute_gh)
    country_none = None if don.currency.code == BTC else owner.country

    now = timezone.now()
    if type_ in [Account.SPONSOR, Account.SPEED_BONUS, Account.ADVERT, Account.REG_BONUS, Account.GUIDER_BONUS]:
        acc.roi = 0
    elif type_ in [Account.GH, Account.GH_PAUSED]:
        acc.roi = get_decimal_conf(1030, country_none, 30)

    if type_ in [Donation.REFUND, Donation.BONUS, Donation.PH, Donation.RC, Donation.PH_FEE, Donation.ACTIVATION]:    # if it is PHing (Paying) & Not the GHing Receiving Account
        acc.balance = don.amount
        acc.amount = acc.amount_live = acc.amount_init = don.amount
        acc.max = don.amount
        acc.currency = don.currency
        acc.maturity = now if don.type in [Donation.RC, Donation.ACTIVATION] else now + timedelta(hours=get_int_conf(1211, country_none, 0))
        acc.commitment_maturity = now if don.type in [Donation.RC, Donation.ACTIVATION] else now + timedelta(hours=get_int_conf(1231, country_none, 0))
        acc.can_credit = False
    else:
        acc.currency = don.currency
        acc.maturity = now + timedelta(hours=get_int_conf(1209, country_none, 0))
        acc.commitment_maturity = now
        acc.balance = 0
        acc.can_credit = True
        acc.amount_init = don.amount

        # Possible prefix:  GH/GP/AD/SP/RF/BS/PH/PF
        if prefix == Account.GH:
            if don.type == Donation.PH:
                percent = get_decimal_conf(config_code, country_none, 100) + 100
                amt = don.amount
            elif don.type in [Donation.REFUND, Donation.BONUS]:
                percent = 100
                amt = don.amount
                acc.can_credit = False
            elif don.type == Donation.ACTIVATION and gh_amount > 0:
                amt = gh_amount
                acc.can_credit = False
            else:   # PH Fee or any other PH that need no fee
                percent = 0
                amt = 0
                acc.can_credit = False
        elif prefix == Account.GH_PAUSED:
            percent = get_decimal_conf(config_code, country_none, 0)
            amt = acc.amount_init = acc.max = percent * gh_amount / 100
        elif (prefix == Account.REG_BONUS or prefix == Account.SPONSOR) and gh_amount > 0:  # Check those with chances of having a fixed amount
            amt = acc.amount_init = gh_amount
        else:
            percent = get_decimal_conf(config_code, country_none, 100)
            amt = 0

        if allow_auto_compute_gh or don.type in [Donation.REFUND, Donation.BONUS]:
            if prefix == Account.GH_PAUSED:
                acc.amount = acc.amount_live = acc.amount_init = acc.max = amt
            elif (prefix == Account.REG_BONUS or prefix == Account.SPONSOR or don.type == Donation.ACTIVATION) and gh_amount > 0:
                acc.amount = acc.amount_live = acc.amount_init = acc.max = amt
            else:
                acc.amount = acc.amount_live = acc.max = acc.amount_init = percent / 100 * don.amount
        else:
            acc.amount = acc.amount_live = acc.amount_init = amt
            if stop_over_growth:
                if prefix == Account.GH_PAUSED:
                    pass
                elif prefix == Account.REG_BONUS or prefix == Account.SPONSOR:
                    acc.max = acc.amount + acc.amount * get_decimal_conf(1030, country_none, 0)/100
                else:
                    acc.max = percent / 100 * don.amount
            else:
                acc.max = 0

        if don.type in [Donation.REFUND, Donation.BONUS]:
            acc.maturity = now

    return acc


def generate_report(typee, count, amount, currency, note):
    return SchedulerReport(type=typee, count=count, amount=amount, currency=currency, note=note)


def is_first_package_request(amount, currency, me):
    if get_bool_conf(1216, me.sender.country, 0):     # If auto recycle is on all PH are consider 1st until atleast one has been fulfilled
        return Donation.objects.filter(amount=amount, member=me, currency=currency, status=Account.PROCESSED).count() == 0
    else:
        return Donation.objects.filter(amount=amount, member=me, currency=currency, status__in=[Account.PENDING, Account.PROCESSED]).count() == 0


def scheduler_active():
    from django_celery_beat.models import PeriodicTask
    gh_matcher = PeriodicTask.objects.filter(name='GH Matcher').first()
    if gh_matcher and gh_matcher.enabled:
        return True
    return False


def scheduler_toggle(scheduler):
    from django_celery_beat.models import PeriodicTask
    gh_matcher = PeriodicTask.objects.filter(name=scheduler).first()
    if gh_matcher:
        return gh_matcher.update(enabled=not F('enabled'))
    return 0


class MissingConnectionException(Exception):
    pass


def cancel_donations(dids):
    counter = 0
    with transaction.atomic():
        dons = Donation.objects.filter(id__in=dids, account__transactiondetail__id__isnull=True, account__type__in=[Account.PH, Account.PH_FEE, Account.REFUND, Account.ACTIVATION],
                                       status__in=[Account.PENDING, Account.TIMEOUT, Account.BLOCKED])

        counter = dons.update(status=Account.CANCELLED)
        if len(dons) == 0:
            return 0
        Account.objects.filter(donation__in=dons).update(status=Account.CANCELLED, updated=timezone.now())

        me = dons[0].member
        for d in dons:
            if get_bool_conf(1207, d.currency.country, False):
                acc = Account.objects.filter(owner=me, type__in=[Account.PH], currency=d.currency).exclude(status__in=[Account.CANCELLED]).order_by('-created').first()
                if d.currency.code == BTC:
                    if acc:
                        me.min_ph_btc = acc.donation.amount
                    else:
                        me.min_ph_btc = get_decimal_conf(1202, d.currency.country, 0.02)
                else:
                    if acc:
                        me.min_ph = acc.donation.amount
                    else:
                        me.min_ph = get_decimal_conf(1202, d.currency.country, 0.02)
            else:
                if d.currency.code == BTC:
                    me.min_ph_btc = get_decimal_conf(1202, d.currency.country, 0.02)
                else:
                    me.min_ph = get_decimal_conf(1202, d.currency.country, 0.02)

        me.save()
    return counter


def reverse_transactions(tids):
    counter = 0
    with transaction.atomic():
        transs = Transaction.objects.filter(id__in=tids)
        for trans in transs:
            pointers = TransactionPointer.objects.filter(transaction=trans)
            total = pointers.aggregate(sum=Sum('amount'))['sum'] or 0
            with transaction.atomic():
                tds = TransactionDetail.objects.filter(transaction=trans, status__in=[TransactionDetail.AWAITING_PAYMENT])
                awaiting_payment = tds.aggregate(sum=Sum('amount'))['sum'] or 0
                if trans.amount == awaiting_payment:
                    reverse_transaction_details(tds.values_list('id', flat=True))
                    trans.status = Transaction.CANCELLED
                    trans.can_match = False
                    trans.balance = trans.amount
                    trans.save()
                    for p in pointers:
                        gh_acc = p.account
                        me = gh_acc.owner
                        gh_acc.balance -= p.amount
                        if p.amount < trans.amount:
                            if gh_acc.currency.code == BTC:
                                me.gh_balance_btc += trans.amount-p.amount
                            else:
                                me.gh_balance += trans.amount-p.amount
                        elif p.amount > trans.amount:
                            if gh_acc.currency.code == BTC:
                                me.gh_balance_btc -= p.amount - trans.amount
                            else:
                                me.gh_balance -= p.amount - trans.amount

                        if gh_acc.balance <= 0:
                            gh_acc.status = Account.PENDING
                        else:
                            gh_acc.status = Account.PARTIAL
                            other_amount = TransactionPointer.objects.filter(account=gh_acc).exclude(transaction__status=Transaction.CANCELLED).aggregate(sum=Sum('amount'))['sum'] or 0

                            gh_bal = gh_acc.amount - (other_amount + p.amount)

                            if gh_acc.balance >= gh_bal:
                                if gh_acc.currency.code == BTC:
                                    me.gh_balance_btc -= gh_bal
                                else:
                                    me.gh_balance -= gh_bal
                                me.save()
                        counter += 1
                        gh_acc.save()
                elif trans.amount > awaiting_payment:
                    tds = TransactionDetail.objects.filter(transaction=trans).exclude(status__in=[TransactionDetail.AWAITING_PAYMENT, TransactionDetail.CANCELLED], rematched=TransactionDetail.YES)
                    others = tds.aggregate(sum=Sum('amount'))['sum'] or 0
                    if others+awaiting_payment >= trans.amount:
                        reverse_transaction_details(tds.values_list('id', flat=True))
                        trans.status = Transaction.CANCELLED
                        trans.can_match = False
                        trans.balance = trans.amount
                        trans.save()
                        for p in pointers:
                            gh_acc = p.account
                            me = gh_acc.owner
                            gh_acc.balance -= p.amount
                            if p.amount < trans.amount:
                                if gh_acc.currency.code == BTC:
                                    me.gh_balance_btc += trans.amount - p.amount
                                else:
                                    me.gh_balance += trans.amount - p.amount
                            elif p.amount > trans.amount:
                                if gh_acc.currency.code == BTC:
                                    me.gh_balance_btc -= p.amount - trans.amount
                                else:
                                    me.gh_balance -= p.amount - trans.amount

                            if gh_acc.balance <= 0:
                                gh_acc.status = Account.PENDING
                            else:
                                gh_acc.status = Account.PARTIAL
                                other_amount = TransactionPointer.objects.filter(account=gh_acc).exclude(transaction__status=Transaction.CANCELLED).aggregate(sum=Sum('amount'))['sum'] or 0

                                gh_bal = gh_acc.amount - (other_amount + p.amount)

                                if gh_acc.balance >= gh_bal:
                                    if gh_acc.currency.code == BTC:
                                        me.gh_balance_btc -= gh_bal
                                    else:
                                        me.gh_balance -= gh_bal
                                    me.save()
                            counter += 1
                            gh_acc.save()

    return counter


# Tested and certified Okay
def reverse_transaction_details(tdids):
    tds = TransactionDetail.objects.filter(id__in=tdids, status=TransactionDetail.AWAITING_PAYMENT)
    msg = ""
    for td in tds:
        td.status = TransactionDetail.CANCELLED
        td.rematched = TransactionDetail.YES
        td.save()

        trans = td.transaction
        trans.status = Transaction.INCOMPLETE
        trans.balance += td.amount
        trans.save()

        TransactionPointer.objects.filter(transaction=trans).update(is_full=False)

        acc = td.account
        don = acc.donation

        amount = TransactionDetail.objects.filter(account=td.account).exclude(status=TransactionDetail.CANCELLED).aggregate(amount=Sum('amount'))['amount'] or 0

        acc.balance = acc.amount - amount
        if amount > 0:
            acc.status = don.status = Account.PARTIAL
        else:
            acc.status = don.status = Account.PENDING

        acc.save()
        don.save()
        msg += "%s %s(%d), " %(td.id, td.currency.symbol, td.amount)

    log.info("Reversed ::: %s" % msg)
    return "Reversed ::: %s" % msg


def cancel_defaulted_transaction_details(tdids, requester):
    tds = TransactionDetail.objects.filter(id__in=tdids, status=TransactionDetail.EXCEPTION)
    counter = sum = 0
    ids = ""

    for td in tds:
        with transaction.atomic():
            trans = td.transaction
            trans.balance += td.amount
            trans.status = trans.PENDING if trans.balance == trans.amount else Transaction.INCOMPLETE
            trans.save()

            td.status = TransactionDetail.CANCELLED
            td.reasons.create(message="%s ::: %s" % ('***ADMIN DECISION***', requester.usename))
            td.save()

            sender = td.sender
            sender.status = Member.SUSPENDED
            sender.delete_on = timezone.now() + timedelta(hours=get_int_conf(1006, td.sender.country, 72))
            sender.save()

            ph_acc = td.account
            don = ph_acc.donation
            ph_acc.status = don.status = Account.CANCELLED
            ph_acc.balance += td.amount
            ph_acc.save()
            don.save()

            don.reasons.create(message="%s ::: %s" % ('***ADMIN DECISION***', requester.usename))

            counter += 1
            sum += td.amount
            ids += td.id + ", "

    if counter > 0:
        report = generate_report(typee=SchedulerReport.EXCEPTION, count=counter, amount=sum, currency=tds[0].currency, note="Blocked Ids: %s" % ids)
        report.save()
        if get_bool_conf(1405, tds[0].currency.country, 0):  # if the system is set to rematch immediately, then move into action
            from core.tasks import gh_matcher_scheduler
            gh_matcher_scheduler(tds[0].transaction_id)
    return counter


def reactivate_transaction(tids):
    tds = TransactionDetail.objects.filter(id__in=tids)


def get_connection(label=None, **kwargs):
    if label is None:
        label = getattr(settings, 'EMAIL_CONNECTION_DEFAULT', None)

    try:
        connections = getattr(settings, 'EMAIL_CONNECTIONS')
        options = connections[label]
    except KeyError, AttributeError:
        raise MissingConnectionException(
            'Settings for connection "%s" were not found' % label)

    options.update(kwargs)
    return mail.get_connection(**options)


def auto_recycle(me, amount, currency, force_ph=False):
    # TODO: Call ph() to handle this
    amount = me.min_ph
    can_ph_now, next_ph, reason = can_ph(me, me.phone, amount)
    print can_ph_now
    print next_ph
    print reason
    if can_ph_now or force_ph:
        min_ph = Member.objects.get(phone=me.phone).min_ph

        with transaction.atomic():
            don = Donation()
            don.id = generate_id(settings.DONATION_ID_PREFIX)
            don.amount = amount
            don.member = me
            don.status = Account.PENDING
            don.type = Donation.PH
            don.channel = Donation.AUTO_RECYCLE
            don.is_active = me.is_active
            don.is_bonus = me.is_bonus
            don.currency = currency

            don.save()

            if min_ph != amount:
                me.min_ph = amount
                me.save()

            allow_auto_compute_gh = get_bool_conf(1400, me.country, True)
            stop_over_growth = get_bool_conf(1401, me.country, False)

            # Popluating Accounts************
            ph_acc = generate_account(Account.PH, Account.PH, don, me, allow_auto_compute_gh)

            if me.is_bonus:
                ph_acc.status = don.status = Account.PROCESSED_BONUS
                ph_acc.balance = 0
                ph_acc.fulfilled = don.status = timezone.now()
            elif not me.is_active:
                ph_acc.status = don.status = Account.PROCESSED
                ph_acc.balance = 0
                ph_acc.fulfilled = don.status = timezone.now()
            ph_acc.save()
            don.save()

            # tracker = track(ph_acc.id, 'account', 'We have new PH', 'Insert', 'User Created')
            # tracker.save()
            # generate_account(prefix, type_, don, owner, allow_auto_compute_gh, stop_over_growth=True, config_id=None, gh_amount=0, don_type='PH'):
            gh_acc = generate_account(Account.GH, Account.GH, don, me, allow_auto_compute_gh, stop_over_growth=stop_over_growth, config_code=8)
            gh_acc.is_bonus = me.is_bonus
            gh_acc.is_active = me.is_active
            gh_acc.save()

            gh_paused_percent = get_decimal_conf(1218, me.country, 0)
            if get_bool_conf(1218, me.country, False) and gh_paused_percent > 0 and is_first_package_request(don.amount, me):
                gh_paused_acc = generate_account(Account.GH_PAUSED, Account.GH_PAUSED, don, me, allow_auto_compute_gh, stop_over_growth, 32, gh_acc.amount)
                gh_paused_acc.save()

                gh_acc.amount -= gh_paused_acc.amount
                gh_acc.save()

            if not me.is_bonus and me.is_active and get_bool_conf(1060, me.country, False) and get_decimal_conf(1061, me.country, 0) > 0 and me.sponsor:
                sp_acc = generate_account(Account.SPONSOR, Account.SPONSOR, don, me.sponsor, allow_auto_compute_gh, stop_over_growth, 16)
                sp_acc.save()

            if not me.is_bonus and me.is_active and get_bool_conf(1080, me.country, False) and get_bool_conf(1081, me.country, 0) > 0:
                ad_acc = generate_account(Account.ADVERT, Account.ADVERT, don, me, allow_auto_compute_gh, stop_over_growth, 17)
                ad_acc.save()

        trans_details = []
        x = get_int_conf(1211, me.country, 0)
        if x < 1 and not me.is_bonus and me.is_active:
            if x == 0:
                if scheduler_active():
                    trans_details = match_ph_2_gh(ph_acc)
            else:
                trans_details = match_ph_2_gh(ph_acc)

            if len(trans_details) == 0:
                return {'msg': "Your Order to Provide Help has been received, we'll inform you as soon as you are matched", 'type': 'Refresh'}
            else:
                return {'msg': 'Have got some order to give help', 'type': 'Refresh'}

        return {'msg': 'We have received your request to Provide Help', 'type': 'Refresh'}
    else:
        if next_ph:
            return {'msg': 'Thanks for your attempt, to ensure system sustainability your next PH period is %s' % next_ph.strftime('%d, %b %Y  %H:%M'), 'type': 'Info'}
        else:
            return {'msg': 'Thanks for your attempt, %s' % reason, 'type': 'Info'}


def get_amount_matched(gh_trans, exclude_cancelled=False):
    if exclude_cancelled:
        return TransactionDetail.objects.filter(transaction=gh_trans).exclude(status=TransactionDetail.CANCELLED).aggregate(sum=Sum('amount'))['sum'] or 0
    else:
        return TransactionDetail.objects.filter(transaction=gh_trans).exclude((Q(rematched=TransactionDetail.YES) | Q(rematched=TransactionDetail.NO)), status=TransactionDetail.CANCELLED).aggregate(sum=Sum('amount'))['sum'] or 0


def get_amount_confirmed(gh_trans):
    return TransactionDetail.objects.filter(transaction=gh_trans, status__in=[TransactionDetail.CONFIRMED]).aggregate(Sum('amount'))['amount__sum'] or 0


def update_gh_account_status(trans):
    # completed_gh_accs = Account.objects.filter(transactionpointer__transaction=gh_trans)
    # completed_gh_accs.update(status=Account.PROCESSED)
    completed_gh_accs = Account.objects.filter(transactionpointer__transaction=trans, transactionpointer__transactiondetailpointer__trans_detail__status=TransactionDetail.CONFIRMED).distinct()
    for acc in completed_gh_accs:
        if acc.amount == (completed_gh_accs.aggregate(sum=Sum('amount'))['sum'] or 0):
            acc.status = Account.PROCESSED
        else:
            acc.status = Account.PARTIAL

    Account.objects.filter(transactionpointer__transaction=trans, transactionpointer__transactiondetailpointer__trans_detail__status__in=[TransactionDetail.AWAITING_CONFIRMATION, TransactionDetail.AWAITING_PAYMENT]).update(status=Account.PROCESSING)


def get_related_member_ids(members):
    prev_count = 0
    related_members = []

    for member in members:
        related = Member.objects.filter(Q(phone=member.phone) | Q(email=member.email) | Q(bank_account__number=member.bank_account.number))

        related_members = list(set(list(related.values_list('id', flat=True)) + related_members))

        if len(related) > 1:
            while len(related_members) > prev_count:
                for mem in related:
                    prev_count = len(related_members)
                    related_members += list(set(list(Member.objects.filter(Q(phone=mem.phone) | Q(email=mem.email) | Q(bank_account__number=mem.bank_account.number)).values_list('id', flat=True)) + related_members))
                    related_members = list(set(related_members))
        else:
            prev_count = len(related_members)

    return related_members


def get_related_member_ghs(members):
    tds = TransactionDetail.objects.filter(transaction__owner__in=members, status__in=[TransactionDetail.AWAITING_PAYMENT, TransactionDetail.AWAITING_CONFIRMATION])
    # txs = Transaction.objects.filter(transactiondetail__in=tds, status__in=[Transaction.PROCESSING, Transaction.PENDING, Transaction.INCOMPLETE])

    return tds


def customised_sms(phones, message, country):
    from core.tasks import sendSMS
    tt="{first_name}, we are happy to info U dat we coming back STRONGER. Join us @evernobsystem or https://t.me/evernobsystem for more"
    counter = 0
    for phone in phones:
        try:
            member = Member.objects.get(phone=phone)
        except Member.DoesNotExist:
            continue

        template = string.Template(message)
        context = Context({"first_name": member.first_name})
        template.render(context)

        sms = Message.objects.create(message=message, phone=phone, type=Message.CUSTOM)
        sendSMS.apply_async(kwargs={'sender': get_str_conf(1021, country, 'System'), 'receivers': ["234" + sms.phone[1:]], 'message': sms.message, 'mid': sms.id})

        counter += 1


# curl -s --user 'api:key-9505c8f5d66a736d7e77421ff2db898b' 'https://api.mailgun.net/v3/mail.evernob.com/messages' -F from='Devoice <support@evernob.com>' -F 'devoicetester@gmail.com' -F subject='Hello' -F text='Testing some Mailgun awesomness!'
def send_simple_message():
    print "Ready to send......."
    data= {"from": "Evernob NoReply <noreply@mail.evernob.com>", "to": ["devoicetester@gmail.com", "donationmove@gmail.com"], "subject": "Hello Donation", "text": "Congratulations Donation, you just sent an email with Mailgun!  You are truly awesome!"}
    return requests.post("https://api.mailgun.net/v3/mail.evernob.com/messages", auth=("api", "key-9505c8f5d66a736d7e77421ff2db898b"), data=data)
    # print "----IN...."
    # return requests.post("https://api.mailgun.net/v3/mail.evernob.com/messages", auth=("api", "api:key-9505c8f5d66a736d7e77421ff2db898b"),
    #                     data={"from": "noreply@evernob.com>", "to": ["Donation <devoicetester@gmail.com>"], "subject": "Hello Donation",
    #                           "text": "Congratulations Donation, you just sent an email with Mailgun!  You are truly awesome!"})


def send_complex_message():
    return requests.post(
        "https://api.mailgun.net/v3/mail.evernob.com/messages",
        auth=("api", "key-9505c8f5d66a736d7e77421ff2db898b"),
        files=[("attachment", ("test.jpg", open("files/test.jpg","rb").read())), ("attachment", ("test.txt", open("files/test.txt","rb").read()))],
        data={"from": "CoreDope NoReply <noreply@mail.evernob.com>",
              "to": "foo@example.com",
              "cc": "baz@example.com",
              "bcc": "bar@example.com",
              "subject": "Hello",
              "text": "Testing some Mailgun awesomness!",
              "html": "<html>HTML version of the body</html>"})


# to/cc/bcc:    "Bob <bob@host.com>". You can use commas to separate multiple recipients.
def send_mail_via_mailgun(subject, to, text, html, cc=None, bcc=None, files=None, fromm=settings.API_MAIL['sender']):
    print to
    print fromm
    print settings.API_MAIL['url']
    print settings.API_MAIL['key']
    print subject
    print text
    print html
    res = requests.post(settings.API_MAIL['url'], auth=("api", settings.API_MAIL['key']), files=files, data={"from": fromm, "to": to, "cc": cc, "bcc": bcc, "subject": subject, "text": text, "html": html})
    return res.status_code


# to/cc/bcc:    "Bob <bob@host.com>". You can use commas to separate multiple recipients.
def send_mail_via_mailjet(subject, to, text, html, cc=None, bcc=None, files=None, fromm=settings.API_MAIL['sender']):
    print to
    print fromm
    print settings.API_MAIL['url']
    print settings.API_MAIL['key']
    print subject
    print text
    print html
    res = requests.post(settings.API_MAIL['url'], auth=("api", settings.API_MAIL['key']), files=files, data={"from": fromm, "to": to, "cc": cc, "bcc": bcc, "subject": subject, "text": text, "html": html})
    return res.status_code

# curl -s --user 'api:key-9505c8f5d66a736d7e77421ff2db898b' \
# https://api.mailgun.net/v3/mail.evernob.com/messages \
#  -F from='Evernob NoReply <noreply@mail.evernob.com>' \
#  -F to='devoicetester@gmail.com' \
#  -F subject='Hello' \
#  -F text='Testing some Mailgun awesomeness!'


def validate_account(me, bank_account):
    BankAccountVerification.objects.filter(Q(name__isnull=True) | Q(name__contains='Failed') | Q(name__contains='Transaction Timed Out'))
    bav = BankAccountVerification.objects.filter(account=bank_account, verified__isnull=True).first()
    if bav and me.country.code == "ng" and get_bool_conf(1040, me.country, False):
        from core.tasks import sendBAVRequest
        sendBAVRequest.apply_async(kwargs={'bav_id': bav.id})


def get_member_id(slug):
    try:
        return int(slug[2:]) - settings.ID_SLUG_CODE
    except TypeError:
        return None


def get_my_referral_count(me):
    return Member.objects.filter(sponsor=me).count()


def verify_account(bav, timeout=10):
    print settings.BANK_ACC_VERIFICATION_URL %(bav.bank.code, bav.account)

    # headers = {'content-type': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8', 'Accept-Language': 'en-US,en;q=0.8', 'Accept-Encoding': 'gzip, deflate, sdch', 'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'}
    # payload = {'bank': bav.bank.code, 'account': bav.account}
    # response=requests.get(settings.BANK_ACC_VERIFICATION_URL, verify=False, timeout=timeout, data=payload)
    try:
        response=requests.get(settings.BANK_ACC_VERIFICATION_URL %(bav.bank.code, bav.account), timeout=timeout)
    except:
        return
    # response = urllib2.urlopen(settings.BANK_ACC_VERIFICATION_URL + urllib.urlencode(params)).read()
    status = False

    for name in bav.member.full_name().lower().split(" "):
        if name in response.text.lower():
            print "Found===%s==*=" %response.text.title()
            status = True
            break

    bav.name = response.text.title()
    bav.verified = timezone.now()
    bav.save()
    member = bav.member
    member.is_fake = not status
    member.save()
    print "===%s==========%s==="

    return response, status


def verify_bank():
    return requests.post("http://196.6.103.15/numap/faces/PublicVerify.jsp", data={"form1:selbankdd_list": "058", "form1:nubantf_field": "0106296667"})
    # return requests.post("https://moneywave.herokuapp.com/v1/merchant/verify", headers={ "Accept": "application/json" }, auth={ "apiKey": "your_api_key", "secret": "your_secret" });)
    # requests.post("https://moneywave.herokuapp.com/v1/transfer", headers={ "content-type": "application/json" }, auth=("ts_U6ZCOTFT532F9O891LQR", "ts_F90ZTYAK86S2TK4KY7UAGKVE9F8VTO"))
    # response = unirest.post("https://moneywave.herokuapp.com/v1/merchant/verify", headers = {"Accept": "application/json"}, params = {"apiKey": "ts_U6ZCOTFT532F9O891LQR", "secret": "ts_F90ZTYAK86S2TK4KY7UAGKVE9F8VTO" });
    #
    # params = {"account_number": "0690000005", "bank_code": "044"};
    # params = {"account_number": "0106296667", "bank_code": "058"};
    # response = unirest.post("https://moneywave.herokuapp.com/v1/resolve/account", params=params, headers={"content-type": "application/json", "Authorization": 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6MTI1NCwibmFtZSI6IlNvZnQgRG9uZ2xlIEx0ZCIsImFjY291bnROdW1iZXIiOiIiLCJiYW5rQ29kZSI6Ijk5OSIsImlzQWN0aXZlIjp0cnVlLCJjcmVhdGVkQXQiOiIyMDE3LTA1LTI5VDE2OjMyOjUzLjAwMFoiLCJ1cGRhdGVkQXQiOiIyMDE3LTA1LTI5VDE2OjM0OjM4LjAwMFoiLCJkZWxldGVkQXQiOm51bGwsImlhdCI6MTQ5NjA3ODc4NywiZXhwIjoxNDk2MDg1OTg3fQ.2WsbVDP87mhOhz_T0rKWSJQahPsXl2AXjv7J1Qi5Tm4'})
    #
    # response = unirest.post("https://moneywave.herokuapp.com/v1/resolve/account", headers = {"content-type": "application/json", "Authorization": "sedxsawegtyrerw3srsdfzxzzvbhgehh213fdsz"}, params = params)


def check_answered(cds):
    for cd in cds:
        d = detail_call(cd.uuid)
        if cd.status == d['status']:
            continue
        cd.status = d['status']
        try:
            cd.network = d['network']
        except KeyError:
            pass
        cd.save()
        if cd.status == CallDetail.COMPLETED:
            return True
    return False


def detail_call(uuid):
    request = urllib2.Request(settings.CALL_BASE_URL + settings.CALL_VERSION + "/calls/" + uuid)
    request.add_header('Content-type', 'application/json')
    request.add_header("Authorization", "Bearer {0}".format(generate_jwt()))
    try:
        response = urllib2.urlopen(request)
        data = response.read()
        if response.code == 200:
            return json.loads(data.decode('utf-8'))
        else:
            log.error(json.loads(data.decode('utf-8')))
    except urllib2.HTTPError as e:
        log.error(e)


def list_call_(mins_ago):
    params = {
        'page_size': '100',
        'date_start': (timezone.now() - timedelta(minutes=mins_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    url = settings.CALL_BASE_URL + settings.CALL_VERSION + "/calls?" + urllib.urlencode(params)
    request = urllib2.Request(url)
    request.add_header('Content-type', 'application/json')
    request.add_header("Authorization", "Bearer {0}".format(generate_jwt()))
    try:
        response = urllib2.urlopen(request)
        data = response.read()
        if response.code == 200:
            return json.loads(data.decode('utf-8'))
        else:
            log.error(json.loads(data.decode('utf-8')))
            return None
    except urllib2.HTTPError as e:
        # log.error(e)
        pass


import jwt
from base64 import urlsafe_b64encode
import os
import calendar


def generate_jwt(application_id=settings.CALL_APP_ID, keyfile=settings.CALL_PRIVATE_KEY) :
    application_private_key = open(keyfile, 'r').read()
    # Add the unix time at UCT + 0
    d = datetime.utcnow()

    token_payload = {"iat": calendar.timegm(d.utctimetuple()), "application_id": application_id, "jti": urlsafe_b64encode(os.urandom(64)).decode('utf-8')}

    # generate our token signed with this private key...
    return jwt.encode(payload=token_payload, key=application_private_key, algorithm='RS256')


def check_and_rematch_cancelled_transaction():
    trans_ids = []
    tds = TransactionDetail.objects.filter(status=TransactionDetail.CANCELLED, rematched=TransactionDetail.NO).exclude(transaction__status=Transaction.CANCELLED)
    for td in tds:
        trans = td.transaction
        total_matched = TransactionDetail.objects.filter(transaction=trans, rematched=TransactionDetail.NO).aggregate(sum=Sum('amount'))['sum'] or 0
        if trans.amount >= total_matched:
            trans_ids.append(trans.id)

    if len(trans_ids) > 0:
        from core.tasks import gh_matcher_scheduler
        gh_matcher_scheduler(list(set(trans_ids)))


def check_users_cashed_out(user_ids=[], usernames=[], member_ids=[], ):
    members = Member.objects.filter(Q(user__in=user_ids) | Q(user__username__in=usernames) | Q(id__in=member_ids))
    sum = 0
    for mem in members:
        total = TransactionDetail.objects.filter(transaction__owner=mem, status=TransactionDetail.CONFIRMED).aggregate(sum=Sum('amount'))['sum'] or 0
        print "%s  %s" %(mem.user.username, total)
        sum += total
    return sum

def nothing():
    from core.models import Member, Transaction, TransactionDetail, Account
    from core.utils import ph
    trans = Transaction.objects.filter(status__in=['Pending', 'Incomplete', 'Processing'])
    from django.utils import timezone
    from django.db.models import Q, Max, Sum, Count, F
    from datetime import timedelta, datetime, time

    mems = []
    for t in trans:
        mems.append(t.owner)
    # 2017, 5, 31, 13, 0, 0
    Account.objects.filter(type__in=['GH'], donation__type='BS').update(maturity=F('maturity') - timedelta(days=3))
    Account.objects.filter(donation__id='DO0826172839188207').update(maturity=F('maturity') - timedelta(days=3))

    from core.tasks import sendSMS
    dons = Donation.objects.filter(type='PH', created__lt=datetime(2017, 8, 24, 12, 0, 0, tzinfo=pytz.UTC))
    dons = Donation.objects.filter(type='PH', created__lt=datetime(2017, 8, 24, 12, 0, 0, tzinfo=pytz.UTC))
    for acc in dons:
        if "xyz" == acc.owner.first_name:
            msg="Hey, ur GH release date is %s, hence the dispatcher is set to match ur PH. Fix Ur Dashboard @fasttracking" %acc.maturity
        else:
            msg="Hey %s, ur GH release date is %s & the dispatcher is set to match ur PH. Let's rock @fasttracking" % (acc.owner.first_name,acc.maturity.strftime("%y-%m-%d %H:%M"),)
        sms = Message(message=msg, phone=acc.owner.phone, code=None, type='Custom')
        sms.save()
        sendSMS.apply_async(eta=timezone.now() + timedelta(seconds=0), kwargs={'sender': 'FastTrack', 'receivers': ["234" + sms.phone[1:]], 'message': sms.message, 'mid': sms.id})

    Account.objects.filter(can_match=False, type='PH')

