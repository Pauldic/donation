import json
import logging
import shelve
from operator import itemgetter
from urlparse import urlparse

import pytz
from asn1crypto.core import Integer
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm, AdminPasswordChangeForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.core.urlresolvers import reverse
from django.db import transaction
from django.db.models import F, Max
from django.db.models import Q, Sum, Count
from django.conf import settings
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404

# Create your views here.
from django.template import loader
from django.utils.datastructures import MultiValueDictKeyError
from django.views.generic import CreateView, DeleteView, ListView
from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from core.response import response_mimetype, JSONResponse, serialize
from core.tasks import sendMail, sendSMS, sendBAVRequest, gh_matcher_scheduler, bonus_computer
from core.forms import MemberForm, TransactionDetailForm, MemberPHForm, BankAccountForm
from core.models import Member, Message, BankAccount, Package, Donation, Account, TransactionDetail, Transaction, EmailCycler, Reason, BankAccountVerification, PhoneCycler, CallDetail, User, Country, \
    AuthAudit, Currency, PackageConfig, Picture, POPPicture
from core.serializer import PackageSerializer
from core.utils import generate, get_int_conf, get_str_conf, get_bool_conf, block_acc, get_float_conf, detail_call, confirm_transaction, ph, cancel_donations, get_date_conf, check_answered, \
    validate_account, can_gh, generate_tx, get_member_id, decimal_normalise, get_decimal_conf
from datetime import timedelta, datetime
from django.utils import timezone

# from support.models import Ticket, TicketCC
from social_django.models import UserSocialAuth
from social_django.utils import load_strategy

log = logging.getLogger("%s.*" %settings.PROJECT_NAME)
FBID = settings.SOCIAL_AUTH_FACEBOOK_KEY
FB_PAGE = settings.FACEBOOK_PAGE
BTC = settings.BITCOIN_CODE


def home(request, notification=None):
    social_require_email = {}
    if request.GET.get('partial_token'):
        strategy = load_strategy()
        partial_token = request.GET.get('partial_token')
        partial = strategy.partial_load(partial_token)
        social_require_email = {'email_required': True, 'partial_backend_name': partial.backend, 'partial_token': partial_token}
    now = timezone.now()
    packages = Package.objects.filter((Q(end_date__isnull=True) | Q(end_date__gte=now)), status__in=[Package.ACTIVE, Package.COMING_SOON]).order_by('amount')
    opening_date = get_date_conf(53, None, '2017,5,31,13,0,0')

    roi = get_int_conf(1030, None, 100)
    gh_mature_range = {'min': get_str_conf(1209, None, 0), 'max': get_str_conf(1210, None, 30)}
    if not notification:
        notification = ''
    elif len(notification) < 5:
        pass
        # notification = get_notication(request, notification)

    context = {"core": None, 'notification': notification, 'packages': packages, 'roi': roi, 'rootURL': 'https://' + request.get_host(), 'pg_title': 'Home', 'email': request.GET.get('email'),
                           'coyName': settings.COY_NAME, 'cashOutRange': gh_mature_range, 'minGHHours': get_int_conf(1209, None, 0), 'maxGHHours': get_int_conf(1210, None, 30), 'sponsor_id': settings.DEFAULT_SPONSOR,
                           'opening_date': timezone.localtime(opening_date).strftime("%Y/%m/%d %H:%M:%S"), 'defaultSponsor': settings.DEFAULT_SPONSOR, 'fbid': FBID, 'fb_page': FB_PAGE}
    context.update(social_require_email)

    return render(request, "core/index.html", context=context)


def test(request, sid=None):
    gh_matcher_scheduler()
    return render(request, "core/test.html", context={'fbid': FBID, 'fb_page': FB_PAGE})


def test2(request, sid=None):
    bonus_computer()
    return render(request, "core/test2.html", context={'fbid': FBID, 'fb_page': FB_PAGE})


def home_register(request, sid=None):
    print "00000000"
    now = timezone.now()
    packages = Package.objects.filter((Q(end_date__isnull=True) | Q(end_date__gte=now)), status='Active', start_date__lte=now).order_by('amount')

    roi = get_int_conf(1030, None, 100)
    sponsor = Member.objects.filter(phone=sid).first()

    gh_mature_range = {'min': get_str_conf(1209, None, 0), 'max': get_str_conf(1210, None, 30)}
    return render(request, "core/index.html", context={"core": None, 'packages': packages, 'roi': roi, 'rootURL': 'https://' + request.get_host(), 'pg_title': 'Home', 'sponsor': sponsor, 'fbid': FBID,
                                                       'coyName': settings.COY_NAME, 'cashOutRange': gh_mature_range, 'minGHHours': get_int_conf(1209, None, 0), 'maxGHHours': get_int_conf(1210, None, 30), 'defaultSponsor': settings.DEFAULT_SPONSOR})


@login_required
def dashboard(request):
    form = None
    notification = None
    try:
        me = request.user.member
    except User.member.RelatedObjectDoesNotExist:
        return register(request)

    lastOldMember = datetime(2017, 5, 15, 0, 0, 0, tzinfo=pytz.UTC)
    sponsor_accs = Account.objects.filter(owner=me, type=Account.SPONSOR)

    total_gh = int(Account.objects.filter(owner=me, status=Account.PROCESSED, type__in=[Account.GH, Account.GH_PAUSED, Account.ADVERT, Account.SPONSOR, Account.BONUS]).aggregate(Sum('amount'))[
            'amount__sum'] or 0)
    pending = int(Account.objects.filter(owner=me, status__in=[Account.PENDING, Account.PARTIAL, Account.PROCESSING],
                                         type__in=[Account.GH, Account.GH_PAUSED, Account.ADVERT, Account.SPONSOR, Account.BONUS]).aggregate(Sum('amount'))['amount__sum'] or 0)

    all_ph_gh = Transaction.objects.filter(Q(transactiondetail__sender=me) | Q(owner=me)).order_by('created')

    # ---- Certified
    pending_don_amount = Account.objects.filter(owner=me, type=Account.PH, status__in=[Account.PENDING, Account.PARTIAL, Account.PROCESSING, Account.BLOCKED, Account.TIMEOUT], ).aggregate(sum=Sum('balance'))['sum'] or 0
    total_paid = TransactionDetail.objects.filter(sender=me, status__in=[TransactionDetail.CONFIRMED], ).aggregate(sum=Sum('amount'))['sum'] or 0
    total_received = TransactionDetail.objects.filter(transaction__owner=me, status__in=[TransactionDetail.CONFIRMED], ).aggregate(sum=Sum('amount'))['sum'] or 0

    pending_phs = TransactionDetail.objects.filter(sender=me, status__in=[TransactionDetail.AWAITING_PAYMENT, TransactionDetail.AWAITING_CONFIRMATION, TransactionDetail.EXCEPTION])
    pending_ghs = TransactionDetail.objects.filter(transaction__owner=me, status__in=[TransactionDetail.AWAITING_PAYMENT, TransactionDetail.AWAITING_CONFIRMATION, TransactionDetail.EXCEPTION])
    total_bonus_amount = Account.objects.filter(owner=me, balance__isnull=True, type__in=[Account.ADVERT, Account.SPONSOR, Account.REG_BONUS, Account.GUIDER_BONUS, Account.SPEED_BONUS], status__in=[Account.PENDING, Account.PROCESSING, Account.PROCESSED_BONUS, Account.PROCESSED]).aggregate(sum=Sum('amount'))['sum'] or 0

    total_gh_amount = Transaction.objects.filter(owner=me,).exclude(status__in=[Transaction.CANCELLED]).aggregate(sum=Sum('amount'))['sum'] or 0
    pending_ph_amount = Account.objects.filter(owner=me, type__in=[Account.PH, Account.PH_FEE], status__in=[Account.PENDING, Account.PARTIAL]).aggregate(sum=Sum('balance'))['sum'] or 0
    queued_gh_amount = TransactionDetail.objects.filter(transaction__owner=me, status__in=[TransactionDetail.AWAITING_PAYMENT, TransactionDetail.AWAITING_CONFIRMATION, TransactionDetail.EXCEPTION]).aggregate(sum=Sum('amount'))['sum'] or 0
    due_4_gh = Account.objects.filter(owner=me, type__in=[Account.GH], balance__isnull=True, donation__fulfilled__isnull=False, donation__status__in=[Account.PROCESSED, Account.PROCESSED_BONUS]).aggregate(sum=Sum('amount'))['sum'] or 0

    referral_count = Member.objects.filter(sponsor=me, status=Member.ACTIVE).count()
    total_speed_bonus = Account.objects.filter(type=Account.SPEED_BONUS, owner=me,).exclude(Q(status__in=[Account.CANCELLED]) | Q(donation__status__in=[Account.CANCELLED])).aggregate(sum=Sum('amount'))['sum'] or 0

    total_ph_amount = Account.objects.filter(owner=me, type=Account.PH, status__in=['Pending', 'Processing', 'Processed', 'Partial', 'Blocked', 'Timeout'], ).aggregate(sum=Sum('amount'))['sum'] or 0
    comfirmed_ph = TransactionDetail.objects.filter(sender=me, status__in=['Confirmed']).aggregate(sum=Sum('amount'))['sum'] or 0
    ph_bal = total_ph_amount - comfirmed_ph

    accList = []
    ee = Account.objects.filter(owner=me, type__in=[Account.PH, Account.GH_PAUSED]).order_by('created')

    # for a in Account.objects.filter(owner=me).order_by('created'):
    for a in Account.objects.filter(owner=me, type__in=[Account.ACTIVATION, Account.PH, Account.GH_PAUSED, Account.BONUS, Account.PH_FEE, Account.REFUND]).order_by('created'):
        accList.append({'created': a.created, 'obj': a})
    for a in Transaction.objects.filter(owner=me).order_by('created'):
        accList.append({'created': a.created, 'obj': a})

    matches = TransactionDetail.objects.filter((Q(sender=me) | Q(transaction__owner=me))).order_by('-created')

    # accs = sorted(accList, key=lambda k: k['created'])
    accs = sorted(accList, key=itemgetter('created'), reverse=True)
    ghs = Transaction.objects.filter(owner=me).order_by('created')

    pct = get_int_conf(1213, me.country, 24)
    ph_multiple = get_int_conf(1204, me.country, 5000)

    cycle_counter = Account.objects.filter(owner=me, type__in=[Account.PH], status__in=[Account.PROCESSED, Account.PROCESSED_BONUS]).count()

    packages = Package.objects.filter(status=Package.ACTIVE)

    fb_page = FB_PAGE + ''.join(e for e in me.country.name_plain.lower() if e.isalnum())
    return render(request, "core/dashboard.html",
                  context={"core": None, "form": form, 'notification': notification, 'rootURL': 'https://' + request.get_host(), 'pg_title': 'Dashboard', 'roi': get_int_conf(1030, me.country, 100),
                           'max_ph': get_int_conf(1203, me.country, 1000000), 'pending_phs': pending_phs, 'pending_ghs': pending_ghs, 'pending_don_amount': pending_don_amount,
                           'pending_gh_amount': total_paid - total_received, 'total_paid': total_paid, 'lastOldMember': lastOldMember, 'total_received': total_received, 'accounts': accs,
                           'packages': packages, 'sponsor_accs': sponsor_accs, 'ph_multiple': ph_multiple, 'cycle_counter': cycle_counter, 'referral_count': referral_count,
                           'total_speed_bonus': total_speed_bonus, 'total_bonus_amount' :total_bonus_amount, 'pending_ph_amount': pending_ph_amount, 'queued_gh_amount': queued_gh_amount,
                           'total_gh_amount': total_gh_amount, 'due_4_gh': due_4_gh, 'matches': matches, 'total_ph_amount': total_ph_amount, 'ph_bal': ph_bal, 'fbid': FBID, 'fb_page': fb_page,
                           'td_sample': settings.TRANSACTION_DETAIL_ID_PREFIX+'00000000000000'})


@login_required
def my_bank_account(request):
    me = request.user.member
    if request.method == 'POST':
        form = BankAccountForm(request.POST, me=me)

        account_number = request.POST['number'].strip()
        user_account = BankAccount.objects.filter(number=account_number).first()

        if user_account:
            if Member.objects.filter(user=request.user, bank_accounts__number=account_number).first():
                return JsonResponse({'msg': "This account '%s' details already exists" %account_number, 'type': 'Info'})
        if form.is_valid():
            with transaction.atomic():
                ba = form.save(commit=False)
                if ba.bank.code == BTC:
                    currency = Currency.objects.get(code=BTC)
                else:
                    currency = Currency.objects.get(country=me.country)
                    if not me.country.is_active:
                        return JsonResponse({'msg': "Sorry we do not currently support PH in your local currency (%s) for %s" % (currency.symbol, me.country.name), 'type': 'Info'})

                ba.currency = currency
                if ba.is_default:
                    BankAccount.objects.filter(member=me, currency=currency).update(is_default=False)
                elif BankAccount.objects.filter(member=me, currency=currency, is_default=True).count() == 0:
                    ba.is_default = True

                ba.save()
                me.bank_accounts.add(ba)
                me.save()

                if request.user.member.country.code == "ng" and currency.code != BTC and get_bool_conf(1040, request.user.member.country, False):
                    bav = BankAccountVerification()
                    bav.bank = ba.bank
                    bav.account = ba
                    bav.member = me
                    bav.save()
                    sendBAVRequest.apply_async(eta=timezone.now() + timedelta(seconds=10), kwargs={'bav_id': bav.id})
            return JsonResponse({'msg': "Your request have been treated successfully", 'type': 'Success'})
        else:
            print form.errors.as_json()
            return JsonResponse({'msg': "Oops! Something went wrong", 'type': 'Error'})
    else:
        form = BankAccountForm(me=me)
    return render(request, "core/bank_account.html", context={"form": form, 'fbid': FBID, })


@login_required
def set_default_account(request):
    me = request.user.member
    if request.method == 'POST' and request.is_ajax():
        acc = BankAccount.objects.get(member=me, number=request.POST['account'])
        BankAccount.objects.filter(member=me, currency=acc.currency).update(is_default=False)
        acc.is_default = True
        acc.save()
        return JsonResponse({'msg': "Your request have been treated successfully", 'type': 'Success'})
    else:
        return JsonResponse({'msg': "Oops! Something went wrong", 'type': 'Error'})


@login_required
def activities(request):
    accList = []
    me = Member.objects.filter(user=request.user).first()
    for a in Account.objects.filter(owner=me, type__in=[Account.GH, Account.GH_PAUSED, Account.ADVERT, Account.REG_BONUS, Account.GUIDER_BONUS, Account.SPONSOR]).exclude(status__in=[Account.CANCELLED]).order_by('created'):
        accList.append({'created': a.created, 'obj': a, 'release': Account.objects.get(donation=a.donation, type=Account.GH).maturity})
        print len(accList)
    for a in Transaction.objects.filter(owner=me,).exclude(status__in=[Transaction.CANCELLED, Transaction.COMPLETED]).order_by('created'):
        accList.append({'created': a.created, 'obj': a, 'release': ''})

    accs = sorted(accList, key=itemgetter('created'), reverse=True)
    return render(request, "core/naira.html", context={'rootURL': 'https://' + request.get_host() + reverse('core:register', kwargs={'sponsor': request.user.username}), 'accs': accs, 'now': timezone.now(), 'fbid': FBID})


@login_required
def profile(request):
    packages = Package.objects.filter(status=Package.ACTIVE)
    try:
        audit = AuthAudit.objects.get(session_key=request.session.session_key)
    except AuthAudit.DoesNotExist:
        audit = None
    code = "{0}{1}".format(request.user.member.country.code, request.user.member.id+settings.ID_SLUG_CODE)

    fb_page = FB_PAGE + ''.join(e for e in request.user.member.country.name_plain.lower() if e.isalnum())
    return render(request, "core/profile.html", context={'rootURL': 'https://' + request.get_host() + reverse('core:register', kwargs={'sponsor': code}), 'packages': packages, 'code': code,
                                                         'audit': audit, 'fbid': FBID, 'fb_page': fb_page})

@login_required
def statement(request):
    accList = []
    me= request.user.member
    for a in Account.objects.filter(owner=me, type__in=[Account.ACTIVATION, Account.PH, Account.GH_PAUSED, Account.BONUS, Account.PH_FEE, Account.REFUND]).order_by('created'):
        accList.append({'created': a.created, 'obj': a})
    for a in Transaction.objects.filter(owner=me).order_by('created'):
        accList.append({'created': a.created, 'obj': a})

    matches = TransactionDetail.objects.filter((Q(sender=me) | Q(transaction__owner=me))).order_by('-created')

    accs = sorted(accList, key=itemgetter('created'), reverse=True)
    return render(request, "core/statement.html", context={'rootURL': 'https://'+request.get_host() + reverse('core:register', kwargs={'sponsor': request.user.username}), 'accounts': accs, 'fbid': FBID})


@login_required
def profile_json(request):
    me = Member.objects.filter(user=request.user).first()
    rows = []
    if me.is_fake:
        status="Fake"
    else:
        status=me.status
    gp = 'General information (click on the name, then enter the data and then hit "Save" down on the bottom left hand side.)'
    rows.append({"name": "First Name", "value": me.first_name, "group": gp, "editor": "text"})
    rows.append({"name": "Last Name", "value": me.last_name, "group": gp, "editor": "text"})
    rows.append({"name": "Status", "value": status, "group": gp, "editor": "text"})
    rows.append({"name": "Email", "value": me.email, "group": gp, "editor": {
            "type": "validatebox",
            "options": {
                "validType": "email"
            }
        }})
    rows.append({"name": "Cell Phone", "value": me.phone, "group": gp, "editor": "text"})
    rows.append({"name": "Country", "value": me.country.name, "group": gp, "editor": "text"})
    rows.append({"name": "Region", "value": "", "group": gp, "editor": "text"})
    rows.append({"name": "Cite", "value": "", "group": gp, "editor": "text"})
    rows.append({"name": "Registration date", "value": me.created, "group": gp, "editor": "text"})
    rows.append({"name": "Date of birth", "value": "", "group": gp, "editor": "datebox"})

    rows.append({"name": "Skype", "value": "", "group": "Contacts", "editor": "text"})
    rows.append({"name": "Yahoo! Messenger", "value": "", "group": "Contacts", "editor": "text"})
    rows.append({"name": "Website", "value": "", "group": "Contacts", "editor": "text"})
    rows.append({"name": "Facebook", "value": "", "group": "Contacts", "editor": "text"})
    rows.append({"name": "Google", "value": "", "group": "Contacts", "editor": "text"})
    rows.append({"name": "Twitter", "value": "", "group": "Contacts", "editor": "text"})

    rows.append({"name": "Information", "value": "", "group": "Personal information", "editor": "text"})
    rows.append({"name": "Our Contacts", "value": "", "group": "Personal information", "editor": "text"})

    if me.sponsor:
        rows.append({"name": "Account Name", "value": me.sponsor.first_name +" "+me.sponsor.last_name, "group": "Guider / Your direct guider", "editor": "text"})
        rows.append({"name": "Status", "value": "", "group": "Guider / Your direct guider", "editor": "text"})
        rows.append({"name": "Email", "value": me.sponsor.email, "group": "Guider / Your direct guider", "editor": "text"})
        rows.append({"name": "Cell Number", "value": me.sponsor.phone, "group": "Guider / Your direct guider", "editor": "text"})

        if me.sponsor.sponsor:
            rows.append({"name": "Account Name", "value": me.sponsor.sponsor.first_name +" "+me.sponsor.sponsor.last_name, "group": "Guider / Your guider`s guider.", "editor": "text"})
            rows.append({"name": "Status", "value": "", "group": "Guider / Your guider`s guider", "editor": "text"})
            rows.append({"name": "Email", "value": me.sponsor.sponsor.email, "group": "Guider / Your guider`s guider", "editor": "text"})
            rows.append({"name": "Cell Number", "value": me.sponsor.sponsor.phone, "group": "Guider / Your guider`s guider", "editor": "text"})
        else:
            rows.append({"name": "Account Name", "value": "", "group": "Guider / Your guider`s guider.", "editor": "text"})
            rows.append({"name": "Status", "value": "", "group": "Guider / Your guider`s guider", "editor": "text"})
            rows.append({"name": "Email", "value": "", "group": "Guider / Your guider`s guider", "editor": "text"})
            rows.append({"name": "Cell Number", "value": "", "group": "Guider / Your guider`s guider", "editor": "text"})
    else:
        rows.append({"name": "Account Name", "value": "", "group": "Guider / Your direct guider", "editor": "text"})
        rows.append({"name": "Status", "value": "", "group": "Guider / Your direct guider", "editor": "text"})
        rows.append({"name": "Email", "value": "", "group": "Guider / Your direct guider", "editor": "text"})
        rows.append({"name": "Cell Number", "value": "", "group": "Guider / Your direct guider", "editor": "text"})

        rows.append({"name": "Account Name", "value": "", "group": "Guider / Your guider`s guider.", "editor": "text"})
        rows.append({"name": "Status", "value": "", "group": "Guider / Your guider`s guider", "editor": "text"})
        rows.append({"name": "Email", "value": "", "group": "Guider / Your guider`s guider", "editor": "text"})
        rows.append({"name": "Cell Number", "value": "", "group": "Guider / Your guider`s guider", "editor": "text"})

    data = {}
    data['total'] = 26
    data['rows'] = rows

    return JsonResponse(data)


@login_required
def admin_home(request):
    me = request.user.member

    available_ph_count = Account.objects.filter(type__in=[Account.PH, Account.PH_FEE], status__in=[Account.PENDING], owner__member__status=Member.ACTIVE, owner__is_fake=False,
                                                owner__member__is_active=True).count()
    available_ph_amount = Account.objects.filter(type__in=[Account.PH, Account.PH_FEE], status__in=[Account.PENDING], owner__member__status=Member.ACTIVE, owner__is_fake=False,
                                                 owner__member__is_active=True).aggregate(sum=Sum('amount'))['sum'] or 0
    pending_gh_amount = TransactionDetail.objects.filter(
        status__in=[TransactionDetail.AWAITING_PAYMENT, TransactionDetail.PAUSED_EXCEPTION, TransactionDetail.PAUSED_RECYCLE, TransactionDetail.EXCEPTION],
        sender__member__status=Member.ACTIVE).count()

    new_reg_count = None

    if request.method == 'POST' and request.is_ajax():
        if request.POST['action'] == 'Make Donation':
            form = MemberPHForm(request.POST, me=me)
            phes = []
            if form.is_valid():
                amount = decimal_normalise(form.cleaned_data['amount'])
                try:
                    currency = Currency.objects.get(code=form.cleaned_data['currency'])
                except Currency.DoesNotExist:
                    return JsonResponse({'msg': "Please specify currency", 'type': 'Info'})

                usernames = form.cleaned_data['usernames'].replace(" ", "").split(",")
                members = Member.objects.filter(user__in=User.objects.filter(username__in=usernames), )

                if currency.code == BTC and amount > 2:
                    return JsonResponse({'msg': "Don't you think %s %s seems too much?" % (currency.symbol, amount), 'type': 'Info'})

                currency_none = None if currency.code == BTC else currency.country
                gh_min = get_float_conf(1430, currency_none, 10)
                if currency.code != BTC and amount < 2:
                    return JsonResponse({'msg': "Don't you think %s %s seems too small? Enter a amount in multiple of %s" % (currency.symbol, amount, gh_min), 'type': 'Info'})

                ph_username = []
                for mem in members:
                    try:
                        ph_response = ph(mem, amount, currency, type=form.cleaned_data['ph_type'], channel=Donation.ADMIN, force_ph=True)
                        if ph_response['status'] == 'Successful':
                            phes.append({'username': mem.user.username, 'full_name': mem.full_name(), 'don_id': ph_response['don_id'], 'don_amount': ph_response['don_amount']})
                            ph_username.append(mem.user.username)
                    except Exception, e:
                        print e

                skipped = list(set(usernames) - set(ph_username))
            return JsonResponse({'msg': "Your request has been treated", 'type': 'Success', 'result': phes, 'skipped': skipped})
        elif request.POST['action'] == 'Cancel Donation':
            return JsonResponse({'msg': "Your request has been treated", 'type': 'Info'})
    else:
        form = MemberPHForm(me=me)
        messages.warning(request, 'Your request has been treated')
    return render(request, "core/admin/index.html", context={'available_ph_amount': available_ph_amount, 'pending_gh_amount': pending_gh_amount, 'new_reg_count': new_reg_count, 'form': form, 'fbid': FBID})


@login_required
def admin_ph_home(request):
    available_ph_amount = Account.objects.filter(type__in=[Account.PH, Account.PH_FEE], status__in=[Account.PENDING], owner__member__status=Member.ACTIVE, ).count()
    pending_gh_amount = TransactionDetail.objects.filter(
        status__in=[TransactionDetail.AWAITING_PAYMENT, TransactionDetail.PAUSED_RECYCLE, TransactionDetail.PAUSED_EXCEPTION, TransactionDetail.EXCEPTION],
        sender__member__status=Member.ACTIVE).count()
    new_reg_count = Member.objects.filter(created__gte=timezone.now().today()).count()
    return render(request, "core/admin/index.html", context={'available_ph_amount': available_ph_amount, 'pending_gh_amount': pending_gh_amount, 'new_reg_count': new_reg_count, 'fbid': FBID})


def about(request):
    return render(request, "core/includes/base.html", context={"core": None, 'tabs': ('core', 'aboutus',), 'pg_title': 'About Us', 'fbid': FBID, })


def faq(request):
    return render(request, "core/dashboad.html", context={"core": None, 'pg_title': 'FAQ', 'fbid': FBID, })


def contact(request):
    return render(request, "core/sms_password_reset.html", context={"core": None, 'pg_title': 'Contact Us', 'fbid': FBID, })


def warning(request):
    return render(request, "core/warning.html", context={"core": None, 'tabs': ('core', 'aboutus',), 'pg_title': 'Disclaimer', 'fbid': FBID, })


def locked(request):
    return render(request, "core/locked.html", context={"core": None, 'tabs': ('core', 'aboutus',), 'pg_title': 'Disclaimer', 'fbid': FBID, })


def verify_email(request, email=None, token=None):
    me = Member.objects.filter(email=email).first()
    if me:
        msg = ""
        me.is_email_verified = True
        # if get_bool_conf(1040, me.country, False):
        #     validate_account(me)
        if get_bool_conf(1020, me.country, False):
            if me.is_phone_verified:
                me.status = Member.ACTIVE
                msg = "& Your Account Activated"
        else:
            me.status = Member.ACTIVE
            msg = "& Your Account Activated"
        me.save()
        return render(request, "core/notification.html", context={"msg": 'Congratulations %s! Your email has been verified %s' % (me.first_name, msg), 'pg_title': 'INFORMATION', 'fbid': FBID, })
    else:
        raise Http404


@login_required
def referals(request):
    referals = Member.objects.filter(sponsor__user=request.user)
    return render(request, "core/referals.html", context={"core": None, "referals": referals, 'tabs': ('core', 'referals',), 'pg_title': 'Referals', 'fbid': FBID, })


@login_required
def resend_email(request):
    me = request.user.member

    if not get_bool_conf(1001, me.country, True):
        return JsonResponse({'msg': 'Email verification is currently Disabled', 'type': 'Success'})

    print "********************** %s " %request.method

    if request.method == 'POST' and request.is_ajax():
        url = request.build_absolute_uri("{0}".format(reverse("core:verify-email", args=(me.email, me.token))))
        html_message = loader.render_to_string('core/mail_templates/activation.html',
                                               {'firstName': me.first_name, 'lastName': me.last_name, 'email': me.email, 'username': me.username, 'token': me.token,
                                                'sponsor': me.sponsor or settings.DEFAULT_SPONSOR, 'url': url})

        sendMail.apply_async(
            kwargs={'subject': get_str_conf(1005, me.country, "Account Activation"), 'message': "Hello,\n this is your token xyz", 'recipients': [{"Email": me.email, "Name": me.full_name()}],
                    'fail_silently': False, 'html_message': html_message, 'connection_label': EmailCycler.get_email_label()})

        return JsonResponse({'msg': 'Instruction has been sent to  your email ' + me.email, 'type': 'Success', 'fbid': FBID})
        # return JsonResponse({'msg': 'We have re-sent you instructions for your account activation. Please log into your email (' + me.email + ') to continue', 'type': 'Success'})
    else:
        return JsonResponse('Access Denied', status=403)


def register(request, guider=None, code=None):
    opening_date = get_date_conf(53, None, '2017,5,31,13,0,0')

    print get_str_conf(1900, None, '6667')
    print code
    if code != get_str_conf(1900, None, '6667'):
        if request.method == 'GET' and opening_date > timezone.now():
            return render(request, "core/notification.html",
                          context={"msg": 'Coming soon on %s' % (timezone.localtime(opening_date).strftime("%A, %b %d %Y %I:%M:%p")), 'pg_title': 'COMING SOON NOTICE', 'fbid': FBID, })

    now = timezone.now()

    if request.method == 'POST' and request.is_ajax():
        form = MemberForm(request.POST)
        username = request.POST['username'].replace(" ", "").strip().lower()
        email = request.POST['email'].strip().lower()
        phone = request.POST['phone'].strip()
        # account_number = request.POST['account_number'].strip()
        country = Country(code=request.POST['country'])

        user_username_exist = User.objects.filter(username=username).exclude(email=email).first()
        user_username = Member.objects.filter(user__username=username).first()
        user_phone = Member.objects.filter(phone=phone).first()
        user_email = Member.objects.filter(email=email).first()
        # user_account = Member.objects.filter(bank_account__number=account_number).first()

        if user_username or (get_bool_conf(1024, country, False) and user_phone) or (get_bool_conf(1003, country, False) and user_email):
        # if user_username or (get_bool_conf(1024, country, False) and user_phone) or (get_bool_conf(1003, country, False) and user_email) or (get_bool_conf(1041, country, False) and user_account):
        #     if Member.objects.filter(user__username=username, phone=phone, email=email, bank_account__number=account_number).first():
            if Member.objects.filter(user__username=username, phone=phone, email=email).first():
                if request.user.is_authenticated() and request.user.username == username:
                    msg = "Hello <a href='{0}'>{1}</a>, you are already registered!!!".format(reverse('core:dashboard'), username)
                else:
                    msg = "Hello <a href='javascript:;'>{0}</a>, you are already registered!!! Please <a href='{1}'>login</a> to continue".format(username, reverse('core:dashboard'))
                return JsonResponse({'msg': msg, 'type': 'Info'})
            else:
                msg = ""
                if user_username or user_username_exist:
                    msg += "Username '%s' is taken, " % username
                if get_bool_conf(1003, country, False) and user_email:
                    msg += "Email '%s' is taken, " % email
                if get_bool_conf(1024, country, False) and user_phone:
                    msg += "Phone '%s' is taken, " % phone
                # if get_bool_conf(1041, country, False) and user_account:
                #     msg += "Bank Account '%s' is taken, " % account_number

                return JsonResponse({'msg': msg, 'type': 'Info'})

        if (request.POST['guider'] and len(request.POST['guider']) > 8) or guider:
            if request.POST['guider'] and len(request.POST['guider']) > 8:
                try:
                    guider = Member.objects.get(id=get_member_id(request.POST['guider']))
                except Member.DoesNotExist:
                    try:
                        guider = Member.objects.get(id=get_member_id(guider))
                    except Member.DoesNotExist:
                        return JsonResponse({'msg': "A valid Sponsor Code is required for registration", 'type': 'Info'})
        else:
            return JsonResponse({'msg': "A valid Sponsor Code is required for registration", 'type': 'Info'})

        now = timezone.now()

        if form.is_valid():
            # if not form.cleaned_data['account_number'].isdigit() or len(form.cleaned_data['account_number']) != 10:
            #     return JsonResponse({'msg': "Sorry your account number must be 10 digits NUBAN number", 'type': 'Error'})
            # if not form.cleaned_data['bank_name']:
            #     return JsonResponse({'msg': "Please select your Bank Name", 'type': 'Error'})
            if len(form.cleaned_data['first_name'].title()) < 2:
                return JsonResponse({'msg': "Sorry your First Name is not a valid Name", 'type': 'Error'})
            if len(form.cleaned_data['last_name'].title()) < 2:
                return JsonResponse({'msg': "Sorry your Last Name is not a valid Name", 'type': 'Error'})

            # full_names = form.cleaned_data['first_name'].title().split(" ")
            # first_name = full_names[0]
            # del full_names[0]
            with transaction.atomic():
                already_exist = created = False
                try:
                    user = User.objects.get(email=email.lower())
                    if User.objects.filter(username=username.lower()).exclude(id=user.id).count() > 0:
                        return JsonResponse({'msg': "Username '%s' is not available" %username, 'type': 'Info'})
                    already_exist = True
                except User.DoesNotExist:
                    user, created = User.objects.get_or_create(username=username.lower(), email=email.lower(), phone=form.cleaned_data['phone'], first_name=form.cleaned_data['first_name'].title(),
                                                           last_name=form.cleaned_data['last_name'].title())
                # user = User.objects.create_user(username=phone, password=password, email=None)
                if already_exist or created:
                    if already_exist:
                        user.first_name = form.cleaned_data['first_name'].title()
                        user.last_name = form.cleaned_data['last_name'].title()
                        user.phone = form.cleaned_data['phone']
                        user.username = username.lower()
                        user.email = email.lower()

                    # ba = BankAccount()
                    # ba.name = form.cleaned_data['first_name'].title()
                    # ba.number = form.cleaned_data['account_number']
                    # ba.bank = form.cleaned_data['bank_name']
                    # ba.save()

                    form.cleaned_data['phone'] = phone
                    form.instance.user = user

                    me = form.save(commit=False)

                    user.set_password(me.password)  # This line will hash the password
                    user.save()

                    me.email = email.lower()
                    me.first_name = user.first_name
                    me.last_name = user.last_name

                    me.phone = phone
                    try:
                        btc = Currency.objects.get(code=BTC)
                        local = Currency.objects.get(country=me.country)
                        local_pak = PackageConfig.objects.get(name=settings.STARTER_PACKAGE_NAME, currency=local)
                        min_pak = local_pak.min_ph
                        max_pak = local_pak.max_ph
                    except Currency.DoesNotExist:
                        min_pak = 0
                        max_pak = 0

                    me.min_ph = decimal_normalise(min_pak)
                    me.max_ph = decimal_normalise(max_pak)
                    btc_pak = PackageConfig.objects.get(name=settings.STARTER_PACKAGE_NAME, currency=btc)
                    me.min_ph_btc = btc_pak.min_ph
                    me.max_ph_btc = btc_pak.max_ph
                    me.token = generate(settings.EMAIL_TOKEN_LENGTH, '')
                    if already_exist and request.user == user:
                        me.is_email_verified = True

                    if guider is None:
                        try:
                            me.sponsor = Member.objects.get(user=User.objects.get(username=settings.DEFAULT_SPONSOR))
                        except User.DoesNotExist or Member.DoesNotExist:
                            me.sponsor = None
                    else:
                        try:
                            me.sponsor = guider
                        except User.DoesNotExist or Member.DoesNotExist:
                            me.sponsor = None
                    me.save()

                    # bav = BankAccountVerification()
                    # bav.bank = ba.bank
                    # bav.account = ba
                    # bav.member = me
                    # bav.save()

                    msg = ""
                    if not me.is_email_verified and get_bool_conf(1001, country, False):
                        msg = " & we have sent you an activation email"
                        url = request.build_absolute_uri("{0}".format(reverse("core:verify-email", args=(me.email, me.token))))
                        html_message = loader.render_to_string('core/mail_templates/activation.html',
                                                               {'firstName': me.first_name, 'lastName': me.last_name, 'email': me.email, 'token': me.token, 'guider': me.sponsor,
                                                                'username': me.username, 'rootURL': 'https://' + request.get_host(), 'url': url})

                        # sendMail.apply_async(
                        #     kwargs={'subject': get_str_conf(1005, me.country, "Account Activation"), 'message': "Hello,\n this is your token xyz", 'recipients': [request.POST['email']], 'fail_silently': False,
                        #             'html_message': html_message, 'connection_label': EmailCycler.get_email_label()})
                        sendMail.apply_async(
                            kwargs={'subject': get_str_conf(1005, me.country, "Account Activation"), 'message': "Hello,\n this is your token xyz", 'fail_silently': False,
                                    'recipients': [{"Email": me.email, "Name": me.full_name()}], 'html_message': html_message, 'connection_label': EmailCycler.get_email_label()})

                    code = generate(settings.SMS_TOKEN_LENGTH, '', True)
                    sms = Message(message="%s, your Activation code is %s" % (me.first_name, str(code)), phone=phone, code=code, type=Message.VERIFICATION)
                    sms.save()

                    if get_bool_conf(1020, country, False):
                        sendSMS.apply_async(eta=now + timedelta(seconds=0), kwargs={'sender': get_str_conf(1021, me.country, 'Verify'), 'receivers': [sms.phone], 'message': sms.message, 'mid': sms.id})
                        sms.sent_time = now
                        sms.save()
                    elif already_exist:
                        me.status = "Active"
                        me.save()

                    # if country.code == "ng" and get_bool_conf(1040, country, False):
                    #     sendBAVRequest.apply_async(kwargs={'bav_id': bav.id})

            return JsonResponse({'msg': "<b>%s, thank you for signing up with our community. Your Account has been created%s. </b>" % (me.first_name, msg,), 'type': 'Success'})
    else:
        if request.user.username:
            u = request.user
            form = MemberForm(initial={'guider': guider, 'username': u.username, 'phone': u.phone, 'email': u.email, 'first_name': u.first_name, 'last_name': u.last_name})
        else:
            form = MemberForm(initial={'guider': guider})
        return render(request, "core/register.html", context={"form": form, 'guider': guider, 'ip_lookup': settings.IP_LOOKUP_ADDRESS, 'fbid': FBID})


def email_request_form(request, partial_backend_name=None, partial_token=None):
    """Email required page"""
    return render(request, "core/includes/request-email.html", context={'partial_backend_name': partial_backend_name, 'partial_token': partial_token, 'fbid': FBID})


def require_complete_registration(request):
    """Email required page"""
    strategy = load_strategy()
    partial_token = request.GET.get('partial_token')
    partial = strategy.partial_load(partial_token)

    return render(request, "core/register.html", context={'email_required': True,'partial_backend_name': partial.backend,'partial_token': partial_token, 'fbid': FBID})


@login_required
def resend_phone_verification_code(request, phone=None):
    me = request.user.member
    if phone is None:
        phone = me.phone

    msg = Message.objects.filter(phone=phone).order_by('-created').first()

    if msg and msg.counter >= get_int_conf(1023, me.country, 3):
        return JsonResponse({'msg': 'Sorry you have exhausted your verification chances, please contact the admin for further assistance', 'type': 'Info'})
    else:
        now = timezone.now()
        if not msg:
            code = generate(settings.SMS_TOKEN_LENGTH, '', True)
            msg = Message(message="%s Activation code is %s" % (settings.COY_NAME, str(code)), phone=phone, code=code, type=Message.VERIFICATION)
            msg.save()

            if get_bool_conf(1020, request.user.member.country, False):
                sendSMS.apply_async(eta=now + timedelta(seconds=0), kwargs={'sender': get_str_conf(1021, me.country, 'Verify'), 'receivers': [msg.phone], 'message': msg.message, 'mid': msg.id})
                msg.sent_time = now
                msg.save()

            return JsonResponse({'msg': 'We have re-sent you your Phone Verification Code SMS to "' + phone+ '"', 'type': 'Info'})

        if msg.sent_time:
            next_time = msg.sent_time + timedelta(minutes=get_int_conf(1022, me.country, 30))
        else:
            next_time = now - timedelta(days=60)

        if now > next_time:
            if not get_bool_conf(1022, me.country, False):
                return JsonResponse({'msg': "We cannot send you verification code at this time please use %s" % msg.code, 'type': 'Info', 'data': msg.code})

            sendSMS.apply_async(kwargs={'sender': get_str_conf(1021, me.country, 'Verify'), 'receivers': [msg.phone], 'message': msg.message, 'mid': msg.id})
            return JsonResponse({'msg': 'We have re-sent you your Phone Verification Code SMS to "' + phone + '"', 'type': 'Info'})
        else:
            return JsonResponse(
                {'msg': 'We have already sent your the Phone Verification Code SMS to "' + phone + '". Wait till next %d%s' % ((next_time - now).total_seconds(), "secs"),
                 'type': 'Info'})


@login_required
def verify_phone_code(request):
    if request.method == 'POST' and request.is_ajax():
        me = request.user.member
        msg = Message.objects.filter(phone=me.phone).first()
        if msg.code == request.POST['code']:
            me.is_phone_verified = True
            if me.is_email_verified:
                me.is_active = True
                me.status = Member.ACTIVE
            me.save()
            return JsonResponse({'msg': 'Phone Verified', 'type': 'Success'})
        else:
            return JsonResponse({'msg': 'Invalid Verification Code', 'type': 'Info'})


@login_required
def gh_board(request, bank_account_id):
    me = request.user.member
    try:
        ba = BankAccount.objects.get(id=bank_account_id, id__in=me.bank_accounts.all().values_list("id", flat=True))
        c_type = Currency.BTC if ba.currency.code == BTC else Currency.LOCAL
    except BankAccount.DoesNotExist:
        return JsonResponse({'msg': "Your request has been received. <b class='emoji' data-value='0x1F602'></b> ", 'type': 'Success'})

    gh_multiple = get_decimal_conf(1430, ba.currency.country, 1000)
    gh_balance = me.gh_balance_btc if c_type == Currency.BTC else me.gh_balance
    total_phed = TransactionDetail.objects.filter(sender=me, currency=ba.currency, status__in=[TransactionDetail.CONFIRMED], account__type__in=[Account.PH, Account.RC]).aggregate(sum=Sum('amount'))['sum'] or 0

    total_ghed_bonus = Account.objects.filter(owner=me, currency=ba.currency, type__in=[Account.GUIDER_BONUS, Account.SPONSOR, Account.SPEED_BONUS, Account.ADVERT], balance__gt=0,
                                              status__in=[Account.PROCESSING, Account.PARTIAL, Account.PROCESSED, Account.PROCESSED_BONUS]).aggregate(sum=Sum('balance'))['sum'] or 0

    pending_bonus = Account.objects.filter(owner=me, currency=ba.currency, type__in=[Account.GUIDER_BONUS, Account.SPONSOR, Account.SPEED_BONUS, Account.ADVERT], balance__lte=F('amount'),
                                           status__in=[Account.PARTIAL, Account.PENDING], donation__status__in=[Account.PROCESSED, Account.PROCESSED_BONUS])
    total_pending_bonus = pending_bonus.aggregate(sum=Sum('amount')-Sum('balance'))['sum'] or 0
    can_gh_bouns = total_phed - total_ghed_bonus
    ghable_bouns = total_pending_bonus if (can_gh_bouns >= total_pending_bonus) else (total_pending_bonus - can_gh_bouns)

    accs_2_gh = Account.objects.filter(owner=me, currency=ba.currency, type__in=[Account.GH, Account.GUIDER_BONUS, Account.SPONSOR, Account.SPEED_BONUS, Account.ADVERT], owner__status=Member.ACTIVE,
                                       status__in=[Account.PARTIAL, Account.PENDING], donation__status__in=[Account.PROCESSED, Account.PROCESSED_BONUS], donation__fulfilled__isnull=False,
                                       owner__is_fake=False, maturity__lte=timezone.now(), balance__lte=F('amount')).order_by('donation__created')
    accs = []
    total_gh = 0
    gh_ids = ""
    for acc in accs_2_gh:
        if can_gh(acc):
            accs.append(acc)
            total_gh += (acc.amount- acc.balance)
            gh_ids += acc.id+","

    max_gh = gh_balance + total_gh
    factor = settings.MATHS_FACTOR
    if gh_multiple < 1:
        _max_gh = max_gh * factor
        _gh_multiple = gh_multiple * 100000
        _bal = _max_gh % _gh_multiple
        bal = _bal/factor
        to_gh = (_max_gh - _bal)/factor
    else:
        factor = 1
        bal = max_gh%gh_multiple
        to_gh = max_gh - bal

    if request.method == 'POST' and request.is_ajax():
        # for key in request.POST:
        #     log.error("%s: %s" % (key, request.POST[key]))
        #
        # print 'Raw Data: "%s"' % request.body
        data = json.loads(request.body)

        # data = request.POST['data']
        print data
        if len(data['ghes']) > 0:
            gh_accs = []
            integerity_error = "Your request failed our integrity check: error code '0x1F232'"
            for gh in data['ghes']:
                for a in accs_2_gh:
                    if a.id == gh['id']:
                        if (a.amount-a.balance) >= gh['amount']:
                            a.amount_2_gh = Decimal(str(gh['amount']))
                            gh_accs.append(a)
                            break;
                        else:
                            return JsonResponse({'msg': integerity_error, 'type': 'Refresh'})

            bouns_accs = []
            for gh in data['bouns']:
                for a in pending_bonus:
                    if a.id == gh['id']:
                        if (a.amount-a.balance) >= gh['amount']:
                            a.amount_2_gh = Decimal(str(gh['amount']))
                            bouns_accs.append(a)
                            break;
                        else:
                            return JsonResponse({'msg': integerity_error, 'type': 'Refresh'})

            total_ghable = total_gh = gh_balance
            total_bouns = 0

            for gh in gh_accs:
                total_gh += gh.amount_2_gh

            for gh in bouns_accs:
                total_bouns += gh.amount_2_gh

            for gh in accs_2_gh:
                total_ghable += (gh.amount - gh.balance)

            if data['old_balance'] != gh_balance:
                return JsonResponse({'msg': integerity_error, 'type': 'Refresh'})
            if (Decimal(str(data['requested_gh']))+gh_balance) != total_gh or total_gh > total_ghable:
                return JsonResponse({'msg': integerity_error, 'type': 'Refresh'})
            if data['requested_bouns'] != total_bouns or total_bouns > ghable_bouns:
                return JsonResponse({'msg': integerity_error, 'type': 'Refresh'})
            if (total_gh+total_bouns+gh_balance) > (total_ghable + ghable_bouns + gh_balance):
                return JsonResponse({'msg': integerity_error, 'type': 'Refresh'})

            with transaction.atomic():
                generate_tx(gh_accs, multiple=gh_multiple, amount=total_gh, bank_account=ba, old_bal=gh_balance, is_bonus=gh_accs[0].is_bonus)
                generate_tx(bouns_accs, multiple=gh_multiple, amount=total_bouns, bank_account=ba, old_bal=Decimal(0.0), is_bonus=False)
                # raise ValueError('Just to avoid Saving while testing')
            return JsonResponse({'msg': "Your request has been received Successfully. Please wait while the dispatcher processes your request", 'type': 'Success'})

    return render(request, "core/gh_board.html", context={'roi': None, 'rootURL': 'https://' + request.get_host(), 'pg_title': settings.COY_NAME, 'bank_account': ba, 'gh_multiple': gh_multiple,
                                                          'max_gh': max_gh, 'ghable_bouns': ghable_bouns, 'accs': accs, 'total_gh': total_gh, 'gh_ids': gh_ids, 'pending_bonus': pending_bonus,
                                                          'gh_balance': gh_balance, 'factor': factor, 'fbid': FBID})


@login_required
def gh_request(request):  # User Clicked on PH
    me = request.user.member
    if request.method == 'POST' and request.is_ajax():
        try:
            amount = int(request.POST['amount'])
            if amount < 0:
                return JsonResponse({'msg': "Something went wrong", 'type': 'Info'})
        except ValueError:
            return JsonResponse({'msg': "Something went wrong", 'type': 'Info'})

        sum = 0
        ids = []
        if request.POST['type'] == 'GH':
            due_ghes = Account.objects.filter(owner=me, type__in=[Account.GH], balance__isnull=True, donation__fulfilled__isnull=False, donation__status__in=[Account.PROCESSED, Account.PROCESSED_BONUS])

            for gh in due_ghes:
                rec = gh.donation.recommitment
                total_paid = TransactionDetail.objects.filter(account__donation=rec, status__in=[TransactionDetail.CONFIRMED]).aggregate(sum=Sum('amount'))['sum'] or 0
                if rec.type in [Donation.BONUS, Donation.REFUND] or gh.is_bonus or not gh.is_active or total_paid >= ((get_int_conf(1240, me.country, 0) * rec.amount)/100):
                    sum += gh.amount
                    ids.append(gh.id)

            if amount > sum:
                return JsonResponse({'msg': "Request Denied, authorised amount %d" %sum, 'type': 'Info'})

            if sum == 0:
                return JsonResponse({'msg': "You are not due for GH", 'type': 'Info'})

            for acc_2_gh in Account.objects.filter(id__in=ids, owner=me):
                if can_gh(acc_2_gh):
                    with transaction.atomic():
                        log.info(acc_2_gh.id + "  ::: Qualified to enter GH Queue::: Amount 2 GH: %d" % acc_2_gh.amount)
                        acc_2_gh.updated = timezone.now()
                        if acc_2_gh.balance is None:    # If this account has not been matched b4 set balance to amount
                            acc_2_gh.balance = acc_2_gh.amount
                        acc_2_gh.save()

                        trans, trans_pointers, accs = generate_tx([acc_2_gh], acc_2_gh.amount, acc_2_gh.is_bonus)
                        trans.save()
                        for tp in trans_pointers:
                            tp.save()
            return JsonResponse({'msg': "Request treated", 'type': 'Success'})

    elif request.method == 'GET':
        member = request.user.member
        now = timezone.now()
        # accs_2_gh = Account.objects.filter(owner=member, is_committed=True, type__in=[Account.GH, Account.ADVERT, Account.BONUS, Account.REG_BONUS, Account.GUIDER_BONUS], status__in=[Account.PARTIAL, Account.PENDING],
        accs_2_gh = Account.objects.filter(owner=member, donation__is_committed=True, type__in=[Account.GH],
                                           status__in=[Account.PARTIAL, Account.PENDING], owner__status=Member.ACTIVE, donation__created__lte=(now - timedelta(hours=get_int_conf(1209, me.country, 0))),
                                           donation__status__in=[Account.PROCESSED,Account.PROCESSED_BONUS], donation__fulfilled__isnull=False).exclude(balance=0).order_by('type','donation__created')

        accs_2_gp = Account.objects.filter(owner=member, donation__is_committed=True, type__in=[Account.GH_PAUSED],
                                           status__in=[Account.PARTIAL, Account.PENDING], owner__status=Member.ACTIVE, donation__created__lte=(now - timedelta(hours=get_int_conf(1209, me.country, 0))),
                                           donation__status__in=[Account.PROCESSED,Account.PROCESSED_BONUS], donation__fulfilled__isnull=False).exclude(balance=0).order_by('type','donation__created')

        accs_2_sp = Account.objects.filter(owner=member, donation__is_committed=True, type__in=[Account.SPONSOR],
                                           status__in=[Account.PARTIAL, Account.PENDING], owner__status=Member.ACTIVE, donation__created__lte=(now - timedelta(hours=get_int_conf(1209, me.country, 0))),
                                           donation__status__in=[Account.PROCESSED,Account.PROCESSED_BONUS], donation__fulfilled__isnull=False).exclude(balance=0).order_by('type','donation__created')

        accs_2_ad = Account.objects.filter(owner=member, donation__is_committed=True, type__in=[Account.ADVERT],
                                           status__in=[Account.PARTIAL, Account.PENDING], owner__status=Member.ACTIVE, donation__created__lte=(now - timedelta(hours=get_int_conf(1209, me.country, 0))),
                                           donation__status__in=[Account.PROCESSED,Account.PROCESSED_BONUS], donation__fulfilled__isnull=False).exclude(balance=0).order_by('type','donation__created')

        accs_2_sb = Account.objects.filter(owner=member, donation__is_committed=True, type__in=[Account.SPEED_BONUS],
                                           status__in=[Account.PARTIAL, Account.PENDING], owner__status=Member.ACTIVE, donation__created__lte=(now - timedelta(hours=get_int_conf(1209, me.country, 0))),
                                           donation__status__in=[Account.PROCESSED,Account.PROCESSED_BONUS], donation__fulfilled__isnull=False).exclude(balance=0).order_by('type','donation__created')

        accs_2_rb = Account.objects.filter(owner=member, donation__is_committed=True, type__in=[Account.REG_BONUS],
                                           status__in=[Account.PARTIAL, Account.PENDING], owner__status=Member.ACTIVE, donation__created__lte=(now - timedelta(hours=get_int_conf(1209, me.country, 0))),
                                           donation__status__in=[Account.PROCESSED,Account.PROCESSED_BONUS], donation__fulfilled__isnull=False).exclude(balance=0).order_by('type','donation__created')

        accs_2_gb = Account.objects.filter(owner=member, donation__is_committed=True, type__in=[Account.GUIDER_BONUS],
                                           status__in=[Account.PARTIAL, Account.PENDING], owner__status=Member.ACTIVE, donation__created__lte=(now - timedelta(hours=get_int_conf(1209, me.country, 0))),
                                           donation__status__in=[Account.PROCESSED,Account.PROCESSED_BONUS], donation__fulfilled__isnull=False).exclude(balance=0).order_by('type','donation__created')
        #
        print "======TO GH 1======"
        print accs_2_gh.query
        return render(request, "core/ghing.html", context={'roi': None, 'rootURL': 'https://' + request.get_host(), 'pg_title': settings.COY_NAME, 'accs_2_gh':accs_2_gh, 'accs_2_gp':accs_2_gp,
                                                           'accs_2_sp':accs_2_sp, 'accs_2_ad':accs_2_ad, 'accs_2_sb':accs_2_sb, 'accs_2_rb': accs_2_rb, 'accs_2_gb':accs_2_gb, 'fbid': FBID })


@login_required
def coin_convert(request):
    me = request.user.member

    accs_2_gh = Account.objects.filter(owner=me, donation__type__in=[Donation.ACTIVATION, Donation.PH, Donation.BONUS, Donation.RC], type__in=[Account.GH, Account.ACTIVATION], donation__status__in=[Account.PROCESSED],
                                       balance__lt=F('amount'))
    btc = Currency.objects.get(code=BTC)
    local = None
    if me.country.is_active:
        local = Currency.objects.get(country=me.country)

    if request.method == 'POST' and request.is_ajax():
        data = json.loads(request.body)

        gh_balance = me.coin_account_balance

        accs = []
        total_coin = total_gh = total_btc = total_local = Decimal(0)
        gh_ids = ""
        integerity_error = "Your request failed our integrity check: error code '0x1F232'"
        for acc in accs_2_gh:
            for a in data['coins_details']:
                if a['id'] == acc.id:
                    if (acc.amount - acc.balance) < Decimal(str(a['amount'])):
                        return JsonResponse({'msg': integerity_error, 'type': 'Refresh'})

                    acc.amount_2_gh = Decimal(str(a['amount']))
                    if acc.currency == btc:
                        total_btc += Decimal(str(a['amount']))
                        total_coin += Decimal(str(a['amount']))/btc.rate
                    else:
                        total_local += Decimal(str(a['amount']))
                        total_coin += Decimal(str(a['amount']))/local.rate
                    accs.append(acc)
                    break

        total_gh = total_coin + me.coin_account_balance
        if total_gh < (Decimal(str(data['local_coins'])) + Decimal(str(data['btc_coins'])) + Decimal(str(data['old_balance']))):
            return JsonResponse({'msg': integerity_error, 'type': 'Failed'})

        local_bank_acc = BankAccount.objects.filter(member=me, is_default=True).exclude(currency__code=BTC).first()
        btc_bank_acc = BankAccount.objects.filter(member=me, is_default=True, currency__code=BTC).first()
        btc = Currency.objects.get(code=BTC)
        if not btc and not local:
            return JsonResponse({'msg': "Please add bank accounts", 'type': 'Failed'})
        acc_local = []
        acc_btc = []
        for acc in accs:
            if acc.currency == btc:
                acc_btc.append(acc)
            else:
                acc_local.append(acc)

        with transaction.atomic():
            if len(acc_btc) > 0:
                generate_tx(acc_btc, 0, total_btc, btc_bank_acc, old_bal=0, is_bonus=False, typee=Transaction.COIN)
            if len(acc_local) > 0:
                generate_tx(acc_local, 0, total_local, local_bank_acc, old_bal=0, is_bonus=False, typee=Transaction.COIN)
            me.coin_account_balance += total_coin
            me.save()

            # raise ValueError('Just to avoid Saving while testing')

            return JsonResponse({'msg': "Your transaction has been completed", 'type': 'Success'})

    return render(request, "core/coin_convert.html", context={'accs': accs_2_gh, 'local': local, 'btc': btc})


@login_required
def gh_ph_wallet(request):
    me = request.user.member

    accList = []
    ee = Account.objects.filter(owner=me, type__in=[Account.PH, Account.GH_PAUSED]).order_by('created')
    print ee.query

    for a in Account.objects.filter(owner=me).order_by('created'):
        accList.append({'created': a.created, 'obj': a})
    for a in Transaction.objects.filter(owner=me).order_by('created'):
        accList.append({'created': a.created, 'obj': a})

    accs = sorted(accList, key=itemgetter('created'), reverse=True)

    accs_2_sp = Account.objects.filter(owner=me, type__in=[Account.SPONSOR], status__in=[Account.PARTIAL, Account.PENDING], owner__status=Member.ACTIVE, donation__fulfilled__isnull=False,
                                       donation__status__in=[Account.PROCESSED, Account.PROCESSED_BONUS]).exclude(balance=0).order_by('type', 'donation__created')

    accs_2_sb = Account.objects.filter(owner=me, type__in=[Account.SPEED_BONUS], status__in=[Account.PARTIAL, Account.PENDING], owner__status=Member.ACTIVE, donation__fulfilled__isnull=False,
                                       donation__status__in=[Account.PROCESSED, Account.PROCESSED_BONUS]).exclude(balance=0).order_by('type', 'donation__created')

    sp_total = accs_2_sp.aggregate(sum=Sum('amount'))['sum'] or 0
    sb_total = accs_2_sb.aggregate(sum=Sum('amount'))['sum'] or 0

    sp_due = accs_2_sp.aggregate(sum=Sum('amount'))['sum'] or 0
    sb_due = accs_2_sb.aggregate(sum=Sum('amount'))['sum'] or 0

    packages = Package.objects.filter(status=Package.ACTIVE)

    return render(request, "core/gh_ph_wallet_bonus.html", context={'roi': None, 'rootURL': 'https://' + request.get_host(), 'pg_title': settings.COY_NAME, 'accs': accs, 'accs_2_sp': accs_2_sp,
                                                                 'accs_2_sb': accs_2_sb, 'sp_total': sp_total, 'sp_due': sp_due, 'sb_total': sb_total, 'sb_due': sb_due, 'packages': packages, 'fbid': FBID})


@login_required
def gh_wallet(request):  # User Clicked on PH
    if request.method == 'GET':
        me = request.user.member
        now = timezone.now()
        # accs_2_gh = Account.objects.filter(donation__created__lte=(now - timedelta(hours=get_int_conf(1209, me.country, 0))), owner=member, is_committed=True, type__in=[Account.GH, Account.GH_PAUSED, Account.SPONSOR, Account.ADVERT, Account.SPEED_BONUS, Account.REG_BONUS, Account.GUIDER_BONUS], status__in=[Account.PARTIAL, Account.PENDING],
        accs_2_gh = Account.objects.filter(owner=me, type__in=[Account.GH], status__in=[Account.PARTIAL, Account.PENDING], owner__status=Member.ACTIVE, donation__fulfilled__isnull=False,
                                           donation__status__in=[Account.PROCESSED, Account.PROCESSED_BONUS]).exclude(balance=0).order_by('type', 'donation__created')

        accs_2_gp = Account.objects.filter(owner=me, type__in=[Account.GH_PAUSED], status__in=[Account.PARTIAL, Account.PENDING], owner__status=Member.ACTIVE, donation__fulfilled__isnull=False,
                                           donation__status__in=[Account.PROCESSED, Account.PROCESSED_BONUS]).exclude(balance=0).order_by('type', 'donation__created')

        accs_2_sp = Account.objects.filter(owner=me, type__in=[Account.SPONSOR], status__in=[Account.PARTIAL, Account.PENDING], owner__status=Member.ACTIVE, donation__fulfilled__isnull=False,
                                           donation__status__in=[Account.PROCESSED, Account.PROCESSED_BONUS]).exclude(balance=0).order_by('type', 'donation__created')

        accs_2_ad = Account.objects.filter(owner=me, type__in=[Account.ADVERT], status__in=[Account.PARTIAL, Account.PENDING], owner__status=Member.ACTIVE, donation__fulfilled__isnull=False,
                                           donation__status__in=[Account.PROCESSED, Account.PROCESSED_BONUS]).exclude(balance=0).order_by('type', 'donation__created')

        accs_2_sb = Account.objects.filter(owner=me, type__in=[Account.SPEED_BONUS], status__in=[Account.PARTIAL, Account.PENDING], owner__status=Member.ACTIVE, donation__fulfilled__isnull=False,
                                           donation__status__in=[Account.PROCESSED, Account.PROCESSED_BONUS]).exclude(balance=0).order_by('type', 'donation__created')

        accs_2_rb = Account.objects.filter(owner=me, type__in=[Account.REG_BONUS], status__in=[Account.PARTIAL, Account.PENDING], owner__status=Member.ACTIVE, donation__fulfilled__isnull=False,
                                           donation__status__in=[Account.PROCESSED, Account.PROCESSED_BONUS]).exclude(balance=0).order_by('type', 'donation__created')

        accs_2_gb = Account.objects.filter(owner=me, type__in=[Account.GUIDER_BONUS], status__in=[Account.PARTIAL, Account.PENDING], owner__status=Member.ACTIVE, donation__fulfilled__isnull=False,
                                           donation__status__in=[Account.PROCESSED, Account.PROCESSED_BONUS]).exclude(balance=0).order_by('type', 'donation__created')

        accs = Account.objects.filter(owner=me, type__in=[Account.GH, Account.GH_PAUSED, Account.SPONSOR, Account.ADVERT, Account.SPEED_BONUS, Account.REG_BONUS, Account.GUIDER_BONUS],
                                      donation__status__in=[Account.PROCESSED, Account.PROCESSED_BONUS]).exclude(balance=0).order_by('type', 'donation__created')

        sp_total = accs_2_sp.aggregate(sum=Sum('amount'))['sum'] or 0
        sb_total = accs_2_sb.aggregate(sum=Sum('amount'))['sum'] or 0

        sp_due = accs_2_sp.aggregate(sum=Sum('amount'))['sum'] or 0
        sb_due = accs_2_sb.aggregate(sum=Sum('amount'))['sum'] or 0

        print "======TO GH 2======"
        packages = Package.objects.filter(status=Package.ACTIVE)

        return render(request, "core/gh_wallet_bonus.html", context={'roi': None, 'rootURL': 'https://' + request.get_host(), 'pg_title': settings.COY_NAME, 'accs': accs, 'accs_2_gh': accs_2_gh,
                                                                     'accs_2_gp': accs_2_gp, 'accs_2_sp': accs_2_sp, 'accs_2_ad': accs_2_ad, 'accs_2_sb': accs_2_sb, 'accs_2_rb': accs_2_rb, 'fbid': FBID,
                                                                     'accs_2_gb': accs_2_gb, 'sp_total': sp_total, 'sp_due': sp_due, 'sb_total': sb_total, 'sb_due': sb_due, 'packages': packages})


@login_required
def gh_wallet_bonus(request, type=None):  # User Clicked on PH
    if request.method == 'GET':
        me = request.user.member
        now = timezone.now()

        print "***********Hello************"
        if type and type != "All":
            accs_2_gh = Account.objects.filter(owner=me, donation__is_committed=True, type__in=type,
                                               status__in=[Account.PARTIAL, Account.PENDING], owner__status=Member.ACTIVE, donation__created__lte=(now - timedelta(hours=get_int_conf(1209, me.country, 0))),
                                               donation__status__in=[Account.PROCESSED, Account.PROCESSED_BONUS], donation__fulfilled__isnull=False).exclude(balance=0).order_by('donation__created')
        else:
            accs_2_gh = Account.objects.filter(owner=me, type__in=[Account.GH, Account.GH_PAUSED, Account.SPONSOR, Account.ADVERT, Account.SPEED_BONUS, Account.REG_BONUS, Account.GUIDER_BONUS],
                                               donation__is_committed=True, status__in=[Account.PARTIAL, Account.PENDING], owner__status=Member.ACTIVE, donation__created__lte=(now - timedelta(hours=get_int_conf(1209, me.country, 0))),
                                               donation__status__in=[Account.PROCESSED, Account.PROCESSED_BONUS], donation__fulfilled__isnull=False).exclude(balance=0).order_by('type','donation__created')

        print "======----TO GH---======"
        packages = Package.objects.filter(status=Package.ACTIVE)

        return render(request, "core/gh_wallet_bonus.html", context={'roi': None, 'rootURL': 'https://' + request.get_host(), 'pg_title': settings.COY_NAME, 'accs_2_gh':accs_2_gh, 'packages': packages, 'fbid': FBID })


@login_required
def phing(request, amount=None, code=None, c_type=Currency.LOCAL):  # User Clicked on PH
    me = request.user.member
    error = None

    local = me.country.currency_set.all().first()
    btc = Currency.objects.get(code=BTC)
    phing_options = [(Currency.BTC, get_float_conf(1030, None), get_float_conf(1204, None))]
    if me.country.is_active:
        phing_options.append((Currency.LOCAL, get_float_conf(1030, me.country), get_float_conf(1204, me.country)))

    if request.method == 'GET' and request.is_ajax():

        return render(request, "core/phing.html", context={'error': error, 'local': local, 'btc': btc, 'phing_options': phing_options, 'rootURL': 'https://' + request.get_host(), 'pg_title': settings.COY_NAME, 'fbid': FBID})

    if me.coin_account_balance == 0:
        if c_type == Currency.LOCAL:
            currency = Currency.objects.get(country=me.country)
        else:
            currency = Currency.objects.get(code=BTC)
        conf = PackageConfig.objects.filter(name=settings.STARTER_PACKAGE_NAME, currency=currency).first()

        error = "Sorry you do not have enough GMBC to perform action. To start Providing Help you need a minimum of {0} GMBC at the rate of {1}G/{2}, <a href='javascript:;' onClick=\"activation_fee('{3}')\">Request</a> for GMBC to proceed".format(decimal_normalise(conf.coin), decimal_normalise(currency.rate), currency.symbol.encode('utf-8'), c_type)

    if not error and request.method == 'POST' and request.is_ajax():
        if Account.objects.filter(owner=me, status__in=[Account.PROCESSED, Account.PROCESSED_BONUS]).count() == 0:
            error = "Sorry you do not have enough GMBC to perform action. To start Providing Help you need a minimum of {0} GMBC at the rate of {1}G/{2}, <a href='{3}' >Buy GMBC</a> to proceed".format(decimal_normalise(conf.coin), decimal_normalise(currency.rate), currency.symbol.encode('utf-8'), reverse('core:market-place'))
    if error and request.method == 'POST' and request.is_ajax():
        return JsonResponse({'msg': error, 'type': 'Info'})

    return render(request, "core/phing.html", context={'error': error, 'local': local, 'btc': btc, 'rootURL': 'https://' + request.get_host(), 'pg_title': settings.COY_NAME, 'fbid': FBID})


@login_required
def ph_request(request, amount=None, code=None, c_type=Currency.LOCAL, first=None):  # User Clicked on PH
    try:
        c_type = request.POST['c_type']
        is_local = True if c_type == Currency.LOCAL else False
    except MultiValueDictKeyError or KeyError:
        is_local = True if c_type == Currency.LOCAL else False

    me = request.user.member
    currency_local = me.country.currency_set.all().first()
    currency_btc = Currency.objects.get(code='BTC')
    currency = currency_local if is_local else  currency_btc

    activation = False
    if first and request.method == 'POST' and request.is_ajax():
        conf = PackageConfig.objects.filter(name=settings.STARTER_PACKAGE_NAME, currency=currency).first()
        # total_local = Donation.objects.filter(member=me, currency=currency_local, status__in=[Account.PROCESSED, Account.PROCESSED_BONUS]).aggregate(sum=Sum('amount'))['sum'] or 0
        # total_btc = Donation.objects.filter(member=me, currency=currency_btc, status__in=[Account.PROCESSED, Account.PROCESSED_BONUS]).aggregate(sum=Sum('amount'))['sum'] or 0
        # total = Donation.objects.filter(member=me, currency=currency, status__in=[Account.PROCESSED]).aggregate(sum=Sum('amount'))['sum'] or 0

        total = Account.objects.filter(owner=me, type__in=[Account.GH, Account.GH_PAUSED, Account.ACTIVATION], currency=currency, donation__status__in=[Account.PROCESSED], balance__lt=F('amount')
                                       ).aggregate(sum=Sum(F('amount')-F('balance')))['sum'] or 0

        amount = conf.coin * currency.rate
        try:

            if me.coin_account_balance < conf.coin:
                if total >= amount: # TODO: what if the user have this money confirmed in another currency
                    return JsonResponse({'msg': 'You already have Confirmed %s%d, please <a href="%s">acquired</a> %d required for PH' % (currency.symbol, total, reverse("core:market-place"), conf.coin), 'type': 'Info'})
                else:
                    total = Donation.objects.filter(member=me, currency=currency, status__in=[Account.PENDING, Account.PROCESSING]).aggregate(sum=Sum('amount'))['sum'] or 0
                    if total >= amount:
                        return JsonResponse({'msg': 'Please wait till your previous request is confirmed', 'type': 'Info'})
                    else:
                        activation = True
            else:
                return JsonResponse({'msg': 'You already have %d GMBC in your GMBC Wallet please proceed to PH' %me.coin_account_balance, 'type': 'Info'})
        except AttributeError:
            s_email = me.sponsor.email if me.sponsor else settings.SERVER_EMAIL
            return JsonResponse({'msg': '%s, your profile is not allowed to Provide Help in your Local Currency %s. Please contact your <a href="mailto:%s?subject=Unable to PH in Local Currency">Sponsor</a>, if issue persist write to <a href="mailto:%s?subject=Unable to PH in Local Currency">Support</a>' %(me.first_name, currency.symbol, s_email, settings.SERVER_EMAIL), 'type': 'Info'})

    if amount:
        amount = decimal_normalise(amount)
    else:
        amount = decimal_normalise(request.POST['amount'])

    if not activation and me.coin_account_balance == 0:
        return phing(request, amount, c_type=c_type)

    if activation or (request.method == 'POST' and request.is_ajax()):

        opening_date = get_date_conf(1201, (me.country if is_local else None), '2017,5,31,13,0,0')

        if code != get_str_conf(1900, me.country, '6667'):
            if opening_date > timezone.now():
                # return render(request, "core/notification.html", context={"msg": 'PHing is starting on %s' % (timezone.localtime(opening_date).strftime("%A, %b %d %Y %I:%M:%p")), 'pg_title': 'NOTICE', })
                return JsonResponse({'msg': 'PHing is starting on %s' % (timezone.localtime(opening_date).strftime("%A, %b %d %Y %I:%M:%p")), 'type': 'Info'})

        if get_bool_conf(1200, (me.country if is_local else None), True):
            if Package.objects.filter(amount=amount).first() is None:
                return JsonResponse({'msg': 'Your PH must amount is not in the defined list', 'type': 'Info'})
        else:
            multiple = get_decimal_conf(1204, (me.country if is_local else None), 1000)
            if is_local:
                if amount < me.min_ph or amount > me.max_ph:
                    return JsonResponse({'msg': 'Please PH within NGN %d to NGN %d' %(me.min_ph, me.max_ph), 'type': 'Info'})
                if (amount % multiple) > 0:
                    return JsonResponse({'msg': 'Please in multiple of NGN %d' %(multiple), 'type': 'Info'})
            else:
                if not activation:
                    if amount < me.min_ph_btc or amount > me.max_ph_btc:
                        return JsonResponse({'msg': 'Please PH within NGN %d to NGN %d' %(me.min_ph, me.max_ph), 'type': 'Info'})
                    if (amount/multiple)%1 > 0:
                        return JsonResponse({'msg': 'Please in multiple of NGN %d' %(multiple), 'type': 'Info'})

        return JsonResponse(ph(me, amount, currency=currency, type=Donation.ACTIVATION if activation else Donation.PH))
    else:
        packages = Package.objects.filter(status=Package.ACTIVE)
        if get_bool_conf(1200, me.country, True):
            if Package.objects.filter(amount=amount).first() is None:
                selected_packages = Package.objects.filter(status=Package.ACTIVE)
            else:
                selected_packages = Package.objects.filter(status=Package.ACTIVE, amount=amount)

        pending_phs = Account.objects.filter(type__in=[Account.PH, Account.PH_FEE, Account.REFUND, Account.RC, Account.BONUS], owner=me,
                                            status__in=[Account.PENDING, Account.PARTIAL, Account.PROCESSING, Account.PAUSED_EXCEPTION, Account.PAUSED_RECYCLE, Account.TIMEOUT])

        return render(request, "core/package.html", context={'roi': None, 'rootURL': 'https://' + request.get_host(), 'pg_title': settings.COY_NAME, 'packages': packages, 'pending_phs': pending_phs,
                                                             'selected_packages': selected_packages, 'fbid': FBID})


@login_required
def market_place(request):
    return render(request, "core/market.html", context={'pg_title': 'GMBC Dashborad', 'fbid': FBID})


@login_required
def cancel_ph(request):
    if request.method == 'POST' and request.is_ajax():
        don = None
        try:
            don = Donation.objects.get(id=request.POST['did'])
        except Donation.DoesNotExist or MultiValueDictKeyError:
            return JsonResponse({'msg': 'Invalid request', 'type': 'Failed'})

        min_ph = get_int_conf(1214, don.currency.country, 0)
        if Donation.objects.filter(member=request.user.member, status='Pending', currency=don.currency).count() <= min_ph:
            return JsonResponse({'msg': 'Sorry, we could not honor your request. You need atleast %d active PH' % min_ph, 'type': 'Failed'})

        if cancel_donations(Donation.objects.filter(id=don.id).values_list('id')) > 0:
            return JsonResponse({'msg': 'Your request has been completed successfully', 'type': 'Success'})
        else:
            return JsonResponse({'msg': 'Sorry, we could not honor your request.', 'type': 'Failed'})


@login_required
def extend_time(request, tdid=None):
    me = request.user.member
    try:
        td = TransactionDetail.objects.get((Q(sender=me) | Q(transaction__owner=me)), id=tdid)
    except TransactionDetail.DoesNotExist:
        return JsonResponse("Integrity check failed", status=403, safe=False)
    max = get_int_conf(1232, td.currency.country, 24)

    if request.method == 'POST' and request.is_ajax() and tdid:
        time = int(request.POST['time'])
        if 0 > time or time > max:
            return JsonResponse({'msg': 'Time value out of range', 'type': 'Failed'})

        if (td.status == TransactionDetail.AWAITING_PAYMENT and td.transaction.owner == me) or (td.status == TransactionDetail.AWAITING_CONFIRMATION and td.sender == me):
            td.expires = td.expires + timedelta(hours=time)
            td.save()
        return JsonResponse({'msg': 'Time extended by %d hour' %time, 'type': 'Success'})

    return render(request, 'core/extend_time.html', {'max': max})


@login_required
def cant_pay(request, tdid):
    acc = Account.objects.filter(transactiondetail__id=tdid, type__in=[Account.PH, Account.ACTIVATION]).first()
    if tdid == request.POST['tdid'] and acc and acc.owner == request.user.member:
        if len(request.POST['reason'].strip()) > 3:
            if block_acc(acc, request.POST['reason'], '***CANT PAY***') > 0:
                return JsonResponse({'msg': 'This account has been blocked', 'type': 'Success'})
            else:
                return JsonResponse({'msg': 'We found no reason to block this account or it may have been blocked already', 'type': 'Failed'})
        else:
            return JsonResponse({'msg': 'Please provide a valid reason why you refuse to pay', 'type': 'Failed'})
    else:
        return JsonResponse({'msg': 'Invalid request', 'type': 'Failed'})


@login_required
def pay_timeout(request, tdid):
    me = request.user.member
    # acc = Account.objects.filter((Q(owner=me) | Q(transaction__owner=me)),  transactiondetail__id=tdid, type__in=[Account.PH, Account.PH_FEE, Account.ACTIVATION, Account.RC],).first()
    try:
        td = TransactionDetail.objects.get((Q(sender=me) | Q(transaction__owner=me)), id=tdid)
    except TransactionDetail.DoesNotExist:
        return JsonResponse({'msg': 'Invalid request', 'type': 'Failed'})

    if block_acc(td.account, "***TIMEOUT***", me) > 0:
        return JsonResponse({'msg': 'This account has been blocked', 'type': 'Success'})
    else:
        return JsonResponse({'msg': 'This request may have been treated', 'type': 'Failed'})


@login_required
def block_user(request, tdid):
    me = request.user.member
    return JsonResponse({'msg': "Your request failed some integrity validation", 'type': 'Error'})
    if tdid != request.POST['tdid']:
        return JsonResponse({'msg': "Your request failed some integrity validation", 'type': 'Error'})
    if len(request.POST['reason']) < 4:
        return JsonResponse({'msg': "Please provide a valid reason why you want to decline", 'type': 'Error'})

    if request.method == 'POST' and request.is_ajax():
        if block_acc(Account.objects.filter(transactiondetail__id=tdid, type__in=[Account.PH, Account.PH_FEE, Account.ACTIVATION, Account.RC]).first(), owner=me, reason=request.POST['reason'], action='***CANT PAY***') > 0:
            return JsonResponse({'msg': 'This account has been blocked', 'type': 'Success'})
        else:
            return JsonResponse({'msg': 'No Action, account may have been blocked/cancelled already', 'type': 'Failed'})


@login_required
def get_receiver(request, tdid):
    me = request.user.member
    td = TransactionDetail.objects.filter((Q(transaction__owner=me) | Q(sender=me)), id=tdid).first()
    ce = None
    if td and td.proof_date:
        ce = td.proof_date + timedelta(hours=get_int_conf(1213, me.country, 24))
    form = TransactionDetailForm(instance=td)
    return render(request, "core/receiver_details.html", context={"form": form, "transDetail": td, 'maxUploadSize': get_float_conf(1007, me.country, 1.0), 'pg_title': 'GMBC Dashborad',
                                                                  'confirmExpires': ce, 'gh_multiple': get_int_conf(1430, me.country, 1000), 'fbid': FBID})


@login_required
def upload_proof(request, tdid):
    td = TransactionDetail.objects.filter(sender=request.user.member, id=tdid, proof_date__isnull=True).first()

    if not td or request.user.member != td.sender:
        return JsonResponse("You are not authorised to do this", status=403, safe=False)

    if request.method == 'POST':
        if tdid != request.POST['id']:
            return JsonResponse("Integrity check failed", status=403, safe=False)

        log.info(request.FILES)
        form = TransactionDetailForm(request.POST, request.FILES, instance=get_object_or_404(TransactionDetail, id=tdid))
        try:
            if form.is_valid():
                try:
                    td = form.save()
                    td.proof_date = timezone.now()
                    td.status = TransactionDetail.AWAITING_CONFIRMATION
                    td.save()

                    if get_bool_conf(1301, td.sender.country, False):
                        message = 'Your GH order [%s ::: NGN %d] has been paid and POP uploaded. Please confirm payment before the expiration timer already showing on your dashboard gets to 00:00:00' % (
                        td.id, td.amount)
                        html_message = loader.render_to_string('core/mail_templates/notification.html', {'firstName': td.transaction.owner.first_name, 'mail_content': message})
                        sendMail.apply_async(kwargs={'subject': 'POP Notification', 'message': message, 'fail_silently': True, 'html_message': html_message,
                                                     'recipients': [{"Email": td.transaction.owner.email, "Name": td.transaction.owner.full_name()}], 'connection_label': EmailCycler.get_email_label()})

                    if get_bool_conf(1311, td.sender.country, False):
                        sms = Message.objects.create(message="POP has been uploaded! Plz confirm & share ur Testimony", phone=td.transaction.owner.phone, type='Payment Made')
                        sendSMS.apply_async(kwargs={'sender': get_str_conf(1021, td.sender.country, settings.COY_NAME), 'receivers': [sms.phone], 'message': sms.message, 'mid': sms.id})

                    # return JsonResponse({'msg': 'POP successfully uploaded, please wait while the receiver confirms your payment.', 'type': 'Success'})
                    return render(request, "core/notification.html", context={"msg": 'POP successfully uploaded, please wait while the receiver confirms your payment.' , 'pg_title': 'INFORMATION', 'fbid': FBID, })

                except ValueError:
                    return JsonResponse({'msg': 'Something went wrong', 'type': 'Failed'})
            else:
                return JsonResponse({'msg': 'Something went wrong', 'type': 'Failed'})
        except ValueError:
            return JsonResponse({'msg': 'Something went wrong', 'type': 'Failed'})
    else:
        form = TransactionDetailForm(instance=td)
        return render(request, "core/receiver_details.html", context={"form": form, "transDetail": td, 'pg_title': 'GMBC Dashborad', 'fbid': FBID, })


@login_required
def upload_proof_1(request, tdid):
    td = TransactionDetail.objects.filter(sender=request.user.member, id=tdid, proof_date__isnull=True).first()
    uploads = POPPicture.objects.filter(object_id=tdid)
    if not td or len(uploads) < 1:
        return JsonResponse("You are not authorised to do this", status=403, safe=False)

    # if request.method == 'POST' and request.is_ajax():
    if request.method == 'POST':
        if tdid != request.POST['id']:
            return JsonResponse("Integrity check failed", status=403, safe=False)
        try:
            try:
                td.proof_date = timezone.now()
                td.status = TransactionDetail.AWAITING_CONFIRMATION
                td.save()

                if get_bool_conf(1301, td.sender.country, False):
                    message = 'Your GH order [%s ::: NGN %d] has been paid. Please confirm payment before the expiration timer already showing on your dashboard gets to 00:00:00' % (
                    td.id, td.amount)
                    html_message = loader.render_to_string('core/mail_templates/notification.html', {'firstName': td.transaction.owner.first_name, 'mail_content': message})
                    sendMail.apply_async(kwargs={'subject': 'POP Notification', 'message': message, 'fail_silently': True, 'html_message': html_message,
                                                 'recipients': [{"Email": td.transaction.owner.email, "Name": td.transaction.owner.full_name()}], 'connection_label': EmailCycler.get_email_label()})

                if get_bool_conf(1311, td.sender.country, False):
                    sms = Message.objects.create(message="Payment has been made! Plz confirm & share ur Testimony", phone=td.transaction.owner.phone, type='Payment Made')
                    sendSMS.apply_async(kwargs={'sender': get_str_conf(1021, td.sender.country, settings.COY_NAME), 'receivers': [sms.phone], 'message': sms.message, 'mid': sms.id})

                # return JsonResponse({'msg': 'POP successfully uploaded, please wait while the receiver confirms your payment.', 'type': 'Success'})
                return JsonResponse({'msg': 'Successful', 'type': 'Successful'})
            except ValueError:
                return JsonResponse({'msg': 'Something went wrong', 'type': 'Failed'})
        except ValueError:
            return JsonResponse({'msg': 'Something went wrong', 'type': 'Failed'})
    else:
        return JsonResponse({'msg': 'Something went wrong', 'type': 'Failed'})


@login_required
def payment_made(request, tdid):
    td = TransactionDetail.objects.filter(sender=request.user.member, id=tdid, proof_date__isnull=True, status=TransactionDetail.AWAITING_PAYMENT).first()

    if not td or request.user.member != td.sender:
        return JsonResponse("You are not authorised to do this", status=403, safe=False)

    if request.method == 'POST' and request.is_ajax():
        # if tdid != request.POST['tdid']:
        #     return JsonResponse("Integrity check failed", status=403, safe=False)

        TransactionDetail.objects.filter(account__donation__type=Donation.BONUS)
        Transaction.objects.filter(owner__donation__type='BS').exclude(status=Transaction.COMPLETED)
        try:
            td.proof_date = timezone.now()
            td.status = TransactionDetail.AWAITING_CONFIRMATION
            td.save()

            if get_bool_conf(1301, td.sender.country, False):
                message = 'Your GH order [%s ::: NGN %d] has been paid. Please confirm payment soon by loging into your dashboard' % (td.id, td.amount)
                html_message = loader.render_to_string('core/mail_templates/notification.html', {'firstName': td.transaction.owner.first_name, 'mail_content': message})
                sendMail.apply_async(kwargs={'subject': 'Payment Notification', 'message': message, 'recipients': [{"Email": td.transaction.owner.email, "Name": td.transaction.owner.full_name()}],
                                     'fail_silently': True, 'html_message': html_message, 'connection_label': EmailCycler.get_email_label()})

            if get_bool_conf(1311, td.sender.country, False):
                sms = Message.objects.create(message="Payment has been made! Please confirm", phone=td.transaction.owner.phone, type='Payment Made')
                sendSMS.apply_async(kwargs={'sender': get_str_conf(1021, td.sender.country, settings.COY_NAME), 'receivers': [sms.phone], 'message': sms.message, 'mid': sms.id})

            return JsonResponse({'msg': 'Payment successfully completed, please wait while the receiver confirms your payment', 'type': 'Success'})
        except ValueError:
            return JsonResponse({'msg': 'Something went wrong', 'type': 'Failed'})
    else:
        return JsonResponse("You are not authorised to do this", status=403, safe=False)


@login_required
def payment_made_1(request, tdid):
    td = TransactionDetail.objects.filter(sender=request.user.member, id=tdid, proof_date__isnull=True, status=TransactionDetail.AWAITING_PAYMENT).first()
    if not td or request.user.member != td.sender:
        return JsonResponse("You are not authorised to do this", status=403, safe=False)

    if request.method == 'POST' and request.is_ajax():
        TransactionDetail.objects.filter(account__donation__type=Donation.BONUS)
        Transaction.objects.filter(owner__donation__type='BS').exclude(status=Transaction.COMPLETED)
        try:
            td.proof_date = timezone.now()
            td.status = TransactionDetail.AWAITING_CONFIRMATION
            td.save()

            if get_bool_conf(1301, td.sender.country, False):
                message = 'Your GH order [%s ::: NGN %d] has been paid. Please confirm payment soon by loging into your dashboard' % (td.id, td.amount)
                html_message = loader.render_to_string('core/mail_templates/notification.html', {'firstName': td.transaction.owner.first_name, 'mail_content': message})
                sendMail.apply_async(kwargs={'subject': 'Payment Notification', 'message': message, 'recipients': [{"Email": td.transaction.owner.email, "Name": td.transaction.owner.full_name()}],
                                             'fail_silently': True, 'html_message': html_message, 'connection_label': EmailCycler.get_email_label()})

            if get_bool_conf(1311, td.sender.country, False):
                sms = Message.objects.create(message="Payment has been made! Please confirm", phone=td.transaction.owner.phone, type='Payment Made')
                sendSMS.apply_async(kwargs={'sender': get_str_conf(1021, td.sender.country, settings.COY_NAME), 'receivers': [sms.phone], 'message': sms.message, 'mid': sms.id})

            return JsonResponse({'msg': 'Payment successfully completed, please wait while the receiver confirms your payment', 'type': 'Success'})
        except ValueError:
            return JsonResponse({'msg': 'Something went wrong', 'type': 'Failed'})
    else:
        return JsonResponse("You are not authorised to do this", status=403, safe=False)


@login_required
def exception(request, tdid):
    td = TransactionDetail.objects.filter(transaction__owner=request.user.member, id=tdid, status=TransactionDetail.AWAITING_CONFIRMATION).first()

    if not td or request.user.member != td.transaction.owner:
        return JsonResponse("You are not authorised to do this", status=403, safe=False)

    note = request.POST['note']
    if request.method == 'POST' and request.is_ajax():
        if tdid != request.POST['tdid']:
            return JsonResponse("Integrity check failed", status=403, safe=False)
        if len(note) < 3:
            return JsonResponse("Request Rejected!!! You need to add a short note!!!", status=500, safe=False)

        # return JsonResponse({'msg': 'Your claim has been received and user blocked, we will review and pass final verdict', 'type': 'Success'})

        with transaction.atomic():
            td.status = TransactionDetail.EXCEPTION
            td.proof_acknowledge_date = timezone.now()
            td.save()

            mem = td.sender
            mem.status = Member.PAUSED
            mem.save()
            Reason(content_object=td, message="***Payment Not Received (%s)*** ::: %s" % (td.id, note)).save()

            phing_acc = td.account
            phing_acc.status = Account.PAUSED_EXCEPTION
            phing_acc.save()

            # Reason.objects.filter(reason_object_id=td, reason_object_type=ContentType.objects.get_for_model(td)).update(message="***User refused to pay*** ::: %s" % note)

            trans = td.transaction
            # ticket = Ticket()
            # ticket.title = "***Payment Not Received (%s) ***" % td.id
            # ticket.submitter_email = td.transaction.owner.email
            # ticket.description = "************* Beneficiary Says (%s) ***************<br>%s <br>************* Receiver's Account Details ***************<br>Full Name: %s<br>Phone Number: %s<br>Account Number: %s<br>Bank Name: %s<br><br>************* Sender's Account Details ***************<br>Full Name: %s<br>Phone Number: %s<br>Account Number: %s<br>Bank Name: %s" % (
            # td.id, note, trans.owner, trans.owner.phone, trans.owner.bank_account.number, trans.owner.bank_account.bank, td.sender, td.sender.phone, td.sender.bank_account.number,
            # td.sender.bank_account.bank,)
            # ticket.queue_id = 1
            # ticket.save()
            #
            # tcc = TicketCC(ticket=ticket, email=td.sender.email, can_view=True, can_update=True)
            # tcc.save()

            return JsonResponse({'msg': 'Your claim has been received and sender Paused, we will review and pass final verdict', 'type': 'Success'})

    else:
        return JsonResponse("You are not authorised to do this", status=403, safe=False)


@login_required
def confirm_payment(request, tdid, force=False):
    me = request.user.member
    try:
        td = TransactionDetail.objects.get(transaction__owner=me, id=tdid, status__in=[TransactionDetail.AWAITING_CONFIRMATION, TransactionDetail.EXCEPTION])
    except TransactionDetail.DoesNotExist:
        return JsonResponse("You are not authorised to do this", status=403, safe=False)

    if request.method == 'POST' and request.is_ajax():
        if tdid != request.POST['tdid']:
            return JsonResponse("Integrity check failed", status=403, safe=False)

        if confirm_transaction(td, False, me):
            return JsonResponse({'msg': 'Payment has been confirmed!', 'type': 'Success'})
        else:
            return JsonResponse({'msg': 'Payment may have been confirmed!', 'type': 'Failed'})
    else:
        return JsonResponse("You are not authorised to do this", status=403, safe=False)


@login_required
@api_view(['GET', 'POST'])
@permission_classes((permissions.AllowAny,))
def get_packages(request):
    # if request.method == 'GET' and request.is_ajax():
    if request.method == 'GET':
        packages = PackageSerializer(Package.objects.filter(status='Active'), many=True)
        # return JsonResponse(packages.data, safe=False)
        return Response(packages.data)


def send_trans_detail_notification(td, subject, message, html_message):
    sendMail.apply_async(kwargs={'recipients': [{"Email": td.transaction.owner.email, "Name": td.transaction.owner.full_name()}, {"Email": td.sender.email, "Name": td.sender.full_name()}],
                                  'subject': subject, 'message': message, 'fail_silently': False, 'html_message': html_message, 'connection_label': EmailCycler.get_email_label(), 'fbid': FBID})


@login_required
def set_password(request):
    pass

@login_required
def account_settings(request):
    user = request.user

    try:
        github_login = user.social_auth.get(provider='github')
    except UserSocialAuth.DoesNotExist:
        github_login = None

    try:
        twitter_login = user.social_auth.get(provider='twitter')
    except UserSocialAuth.DoesNotExist:
        twitter_login = None

    try:
        facebook_login = user.social_auth.get(provider='facebook')
    except UserSocialAuth.DoesNotExist:
        facebook_login = None

    try:
        google_oauth2_login = user.social_auth.get(provider='google-oauth2')
    except UserSocialAuth.DoesNotExist:
        google_oauth2_login = None

    can_disconnect = (user.social_auth.count() > 1 or user.has_usable_password())

    return render(request, 'core/account_settings.html', {'github_login': github_login, 'twitter_login': twitter_login, 'facebook_login': facebook_login, 'google_oauth2_login':google_oauth2_login,
                                                          'can_disconnect': can_disconnect})


@login_required
def account_password(request):
    if request.user.has_usable_password():
        PasswordForm = PasswordChangeForm
    else:
        PasswordForm = AdminPasswordChangeForm

    if request.method == 'POST':
        form = PasswordForm(request.user, request.POST)
        if form.is_valid():
            form.save()
            update_session_auth_hash(request, form.user)
            messages.success(request, 'Your password was successfully updated!')
            return redirect('password')
        else:
            messages.error(request, 'Please correct the error below.')
    else:
        form = PasswordForm(request.user)
    return render(request, 'core/password.html', {'form': ""})


def handle400(request, exception):
    from django.contrib.auth.views import logout
    msg = "The request's session was deleted before the request completed. The user may have logged out in a concurrent request"
    if msg in exception.message:
        logout(request)
        return redirect(reverse("core:logout"))
    return render(request, "400.html", context={'pg_title': 'GMBC Dashborad', 'fbid': FBID}, content_type='text/html; charset=utf-8', status=404)


def handle404(request, exception):
    return render(request, "404.html", context={'pg_title': 'GMBC Dashborad', 'fbid': FBID}, content_type='text/html; charset=utf-8', status=404)


def handle500(request):
    return render(request, "500.html", context={'pg_title': 'GMBC Dashborad', 'fbid': FBID}, content_type='text/html; charset=utf-8', status=500)


# ##  Used by my custom login module (login.*) to create/update the session each time user tries logging into the system
# def client_session_update(request):
#     if request.method == 'POST' and request.is_ajax():
#         request.session._get_or_create_session_key()
#         try:
#             client = request.session['client_id']
#             if client != request.POST['id_client']:
#                 request.session['client_id'] = request.POST['id_client']
#                 request.session.modified = True
#         except KeyError:
#             try:
#                 request.session['client_id'] = request.POST['id_client']
#                 request.session.modified = True
#             except:
#                 print "error........"
#
#         print "***********------POST-------*************"
#         print request.session.session_key
#         for k in request.session.keys():
#             print request.session[k] +'\n'
#
#         # request.session.flush()
#         return JsonResponse({'msg': "_"})


class PictureCreateView(LoginRequiredMixin, CreateView):
    model = Picture
    # fields = "__all__"
    fields = ['file',]


class POPCreateView(PictureCreateView):
    model = POPPicture
    # template_name = 'core/picture_pop_form.html'
    template_name = 'core/receiver_details.html'

    def get_context_data(self, **kwargs):
        context = super(PictureCreateView, self).get_context_data(**kwargs)
        context['maxImageSize'] = get_decimal_conf(1007, self.request.user.member.country, 1.0)*1024*1024
        context['tdid'] = self.kwargs['tdid']
        try:
            context['transDetail'] = TransactionDetail.objects.get((Q(sender=self.request.user.member) | Q(transaction__owner=self.request.user.member)), pk=self.kwargs['tdid'])
        except TransactionDetail.DoesNotExist:
            # logout(self.request)
            pass
        return context

    def form_valid(self, form):
        # TODO: Find away to report this error on the template, it is not reported
        def invalidate(msg):
            errors = form.errors.copy()
            errors.update({'file_size': msg})
            if self.request.is_ajax():
                return HttpResponse(content=json.dumps(errors), status=400, content_type='application/json')
            else:
                return super(JSONResponse, self).form_invalid(form)

        if int(form.files['file'].size) > int(get_decimal_conf(1007, self.request.user.member.country, 1.0)*1024*1024):
            return invalidate("File size too large");
        td = TransactionDetail.objects.get(pk=self.kwargs['tdid'], sender=self.request.user.member)
        if POPPicture.objects.filter(object_id=td.id).count() >= 3:
            return invalidate("Reached maximum file upload count")

        form.instance.object = td
        form.instance.object_id = td.id

        self.object = form.save(commit=False)
        td_type = ContentType.objects.get_for_model(td)
        upload = POPPicture(content_type=td_type, file=self.object.file, object_id=td.id)
        upload.save()
        data = {'files': [serialize(upload)]}
        response = JSONResponse(data, mimetype=response_mimetype(self.request))
        response['Content-Disposition'] = 'inline; filename=files.json'
        return response
        # return super(POPCreateView, self).form_valid(form)

    def form_invalid(self, form):
        data = json.dumps(form.errors)
        if self.request.is_ajax():
            return HttpResponse(content=data, status=400, content_type='application/json')
        else:
            return super(JSONResponse, self).form_invalid(form)


class BasicVersionCreateView(PictureCreateView):
    template_name_suffix = '_basic_form'


class BasicPlusVersionCreateView(PictureCreateView):
    template_name_suffix = '_basicplus_form'


class AngularVersionCreateView(PictureCreateView):
    template_name_suffix = '_angular_form'


class jQueryVersionCreateView(PictureCreateView):
    template_name_suffix = '_jquery_form'


class PictureDeleteView(DeleteView):
    model = Picture

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()
        response = JSONResponse(True, mimetype=response_mimetype(request))
        response['Content-Disposition'] = 'inline; filename=files.json'
        return response


class PictureListView(ListView):
    model = POPPicture

    def render_to_response(self, context, **response_kwargs):
        files = [serialize(p) for p in self.get_queryset()]
        data = {'files': files}
        response = JSONResponse(data, mimetype=response_mimetype(self.request))
        response['Content-Disposition'] = 'inline; filename=files.json'
        return response