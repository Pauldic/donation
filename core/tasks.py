from __future__ import absolute_import, unicode_literals


from django.core import mail
from celery import shared_task
from django.db import transaction
from datetime import timedelta

from django.db.models import Q, Sum, F
from django.template import loader
from django.utils import timezone
from subprocess import Popen, PIPE

from celery.utils.log import get_task_logger
from mailjet_rest import Client

from core.models import Account, Transaction, TransactionDetail, Member, Message, EmailCycler, Donation, BankAccountVerification, TestimonyCode, Country, Currency, SchedulerReport
from core.utils import track, get_int_conf, get_bool_conf, generate_id, can_gh, get_ph_balance, match_ph_2_gh, block_acc, generate_report, confirm_transaction, sms_send, get_str_conf, get_connection, \
    generate_tx, send_mail_via_mailgun, verify_account, get_related_member_ids, get_time_diff, credit_accounts, BTC, get_decimal_conf
from django.conf import settings

log = get_task_logger(__name__)
# from pycharmdebug import pydevd
# from pydev import pydevd

# If a task is modified, celery need to be restarted


@shared_task(name='core.sendMail')
def sendMail(subject, message, recipients, fail_silently=settings.DEBUG, html_message=None, channel="MAILJET", connection_label=None):

    if channel == 'MAILJET':
        mailjet = Client(auth=(settings.API_MAIL['key'], settings.API_MAIL['secret']), version='v3.1')
        # data = {
        #     'FromEmail': settings.DEFAULT_FROM_EMAIL,
        #     'FromName': settings.COY_NAME,
        #     'Subject': subject,
        #     'Text-part': message,
        #     'Html-part': html_message,
        #     'Recipients': recipients
        # }

        data = {
            'Messages': [
                {
                    "From": {"Email": settings.DEFAULT_FROM_EMAIL, "Name": settings.COY_NAME},
                    "To": recipients,
                    "HTMLPart": html_message,
                    "TemplateLanguage": False,
                    "Subject": subject,
                    "Variables": {}
                }
            ]
        }





        print settings.API_MAIL['key']
        print settings.API_MAIL['secret']
        print "------------------------------------'"
        print data['Messages'][0]['From']
        print data['Messages'][0]['From']['Name']
        print data['Messages'][0]['From']['Email']
        print data['Messages'][0]['To']
        print data['Messages'][0]['To'][0]['Name']
        print data['Messages'][0]['To'][0]['Email']
        print "------------------------------------'"
        print data['Messages'][0]['Subject']
        response = mailjet.send.create(data)
        log.info(response)
        log.info(response.status_code)
        log.info(response.json())
        return

    if channel == 'MAILGUN':
        log.info("***donate_v6 Task Logging:::  ---SMTP---  Ready Send Mail to....  ".join(recipients)+'::: From:')
        print "*****************Sending Mail %s**********************to:  %s" % (subject, ",".join(recipients))
        status = send_mail_via_mailgun(subject, ",".join(recipients), message, html_message)
        log.info(status," ***Task Logging::: ---MailGun--- Ready to Send Mail to....  ".join(recipients)+' from '+settings.API_MAIL['sender'])
        return

    connection = get_connection(connection_label or EmailCycler.get_email_label())
    # print recipients
    # print html_message
    # mail.send_mail(subject=subject, html_message=message, from_email=fromm, recipient_list=recipients, fail_silently=fail_silently)

    mail.send_mail(subject=subject, message=message, from_email='"%s" <%s>' % (settings.COY_NAME, connection.username), recipient_list=recipients, fail_silently=fail_silently, html_message=html_message, connection=connection)

    # from django_celery_beat.models import PeriodicTasks
    # PeriodicTasks.changed()
    # DatabaseScheduler.schedule()
    # beat
    email = ", ".join(recipients)
    return "Mail (%s) Sent to: [%s]" % (subject, email)


@shared_task(name='core.sendSMS')
def sendSMS(sender, receivers, message, mid=None, secured=True, connection=None):
    sms_send(sender, receivers, message, mid=mid, secured=secured, connection=connection)


@shared_task(name='core.BAVRequest')
def sendBAVRequest(bav_id, timeout=10):
    print bav_id
    verify_account(BankAccountVerification.objects.get(id=bav_id), timeout)


@shared_task(name='core.testing')
def testing():
    now = timezone.now()
    bouns_due = Account.objects.filter(status__in=[Account.PENDING], type=Account.GH, donation__type__in=[Donation.PH, Donation.RC], next_update__gte=now)

    for bd in bouns_due:
        if int(get_time_diff(bd.created)) >= bd.update_counter:
            print True

    # print "Testing...... @ :  {0}".format(timezone.now().strftime('%Y-%m-%d %H:%M'))

    # return "Done.....Testing"


@shared_task(name='core.events')
def events():
    # from call_center.models import Campaign
    # from call_center.tasks import campaign_manager
    # now = timezone.now()
    # print Campaign.objects.filter(starting_time__lte=now, expiration_time__gte=now, status__in=['Pending', 'Partial']).query
    # campaign_ids = Campaign.objects.filter(starting_time__lte=now, expiration_time__gte=now, status__in=['Pending', 'Partial']).values_list('id', flat=True).order_by('starting_time')
    #
    # print "*************Periodic*********** "
    # campaign_manager.apply_async(list(campaign_ids))
    # campaign.apply_async(ids, task_id=task_id)
    pass


@shared_task(ignore_result=True)
def log_result(result):
    if result.ready():
        print "***** Task has run"
        if result.successful():
            print "***** Result was: %s" % result.result
        else:
            if isinstance(result.result, Exception):
                print "***** Task failed due to raising an exception"
                raise result.result
            else:
                print "***** Task failed without raising exception"
    else:
        print "***** Task has not yet run"
    print "***** Logging....."
    log.info("***** donate_v5 Task Logging:::    %r", result)


@shared_task(name='core.bonus_creditor')
def bonus_creditor():
    types = [Account.GH, Account.GH_PAUSED]
    bounes = [Account.REG_BONUS, Account.SPONSOR, Account.GUIDER_BONUS, Account.SPEED_BONUS]
    if get_bool_conf(1009, None, False):
        types = types + bounes
    btc = Currency.objects.get(code=BTC)
    accs = Account.objects.filter(status__in=[Account.PENDING, Account.PARTIAL], type__in=types, donation__type__in=[Donation.PH, Donation.RC], currency=btc, roi__gt=0, amount__lte=F('amount_live'))
    if get_bool_conf(1401, btc.country, True):
        accs.filter(amount__lt=F('max'), amount_live__lte=F('max')).update(amount=F('amount_live'))
        Account.objects.filter(status__in=[Account.PENDING, Account.PARTIAL], type__in=types, donation__type__in=[Donation.PH, Donation.RC], currency=btc, roi__gt=0, amount__lte=F('max'),
                                      amount_live__gt=F('max')).update(amount=F('max'))
    else:
        Account.objects.filter(status__in=[Account.PENDING, Account.PARTIAL], type__in=types, donation__type__in=[Donation.PH, Donation.RC], currency=btc, roi__gt=0, amount__lte=F('amount_live')).update(amount=F('amount_live'))

    countries = Country.objects.filter(is_active=True)
    for country in countries:
        types = [Account.GH, Account.GH_PAUSED]
        if get_bool_conf(1009, country, False):
            types = types + bounes
        accs = Account.objects.filter(status__in=[Account.PENDING, Account.PARTIAL], type__in=types, donation__type__in=[Donation.PH, Donation.RC], currency__country=country, roi__gt=0,
                                      amount__lte=F('amount_live'))
        if get_bool_conf(1401, btc.country, True):
            accs.filter(amount__lt=F('max'), amount_live__lte=F('max')).update(amount=F('amount_live'))
            Account.objects.filter(status__in=[Account.PENDING, Account.PARTIAL], type__in=types, donation__type__in=[Donation.PH, Donation.RC], currency__country=country, roi__gt=0, amount__lte=F('max'),
                                          amount_live__gt=F('max')).update(amount=F('max'))



@shared_task(name='core.bonus_computer')
def bonus_computer():
    now = timezone.now()

    countries = Country.objects.filter(is_active=True)
    for country in countries:
        with transaction.atomic():
            credit_accounts(country, now)

    # For BTC
    with transaction.atomic():
        credit_accounts(None, now)


@shared_task(name='core.gh_sponsor_bonus_scheduler')
def gh_sponsor_bonus_scheduler(aid=None):

    sp_accs = Account.objects.filter(type=Account.SPONSOR, status__in=[Account.PENDING, Account.PARTIAL])
    members = Member.objects.filter(account__in=sp_accs)


@shared_task(name='core.gh_scheduler')
def gh_scheduler(aid=None, gh_amount=0):

    countries = Country.objects.filter(is_active=True)
    for country in countries:
        c_percent = get_int_conf(1230, country, 0)
        process_disabled_members(Member.objects.filter(status=Member.ACTIVE, is_active=False))
        now = timezone.now()

        log.info("\n\n\n::::: Am here... to schedule people for GH :::::******************___***************** \n\n\n")

        acc_2_gh = Account.objects.filter(id=aid).first()
        if acc_2_gh:
            if can_gh(acc_2_gh):
                with transaction.atomic():
                    if acc_2_gh.balance == 0:    # If this account has not been matched b4 set balance to amount
                        acc_2_gh.amount_2_gh = acc_2_gh.amount
                    else:
                        acc_2_gh.amount_2_gh = (acc_2_gh.amount - acc_2_gh.balance)
                    acc_2_gh.save()
                    ba = acc_2_gh.owner.bank_accounts__set.all().filter(is_default=True).first()
                    generate_tx([acc_2_gh], multiple=get_int_conf(1430, acc_2_gh.currency.country, 1000), amount=gh_amount, bank_account=ba, old_bal=0.0, is_bonus=acc_2_gh.is_bonus)

                    # tracker = track(trans.id, 'transaction', 'User triggered GH', 'Insert', 'User')
                    # tracker.save()
        else:
            if get_bool_conf(1400, country, False):  # If Auto GH is enabled
            # if False:  # If Auto GH is enabled
                # GH Condition: Acc Status in (Parital, Pending), is_auto_gh=True, owner-status=Active, donation-created >= GH Time, donation-status in (Processed, Processed_bouns) & fullfilled
                # , balance__isnull=True
                # accs_2_gh = Account.objects.filter(type__in=[Account.GH, Account.ADVERT, Account.BONUS, Account.REG_BONUS], status__in=[Account.PARTIAL, Account.PENDING], owner__status=Member.ACTIVE,
                accs_2_gh = Account.objects.filter(type__in=[Account.GH], status__in=[Account.PARTIAL, Account.PENDING], owner__status=Member.ACTIVE, owner__is_fake=False, is_auto_gh=True,
                                                   donation__fulfilled__isnull=False, donation__recommitment__isnull=False, donation__status__in=[Account.PROCESSED, Account.PROCESSED_BONUS],
                                                   maturity__lte=now, can_match=True, currency__country=country).exclude(balance=F('amount')).order_by('is_active', '-is_bonus', 'donation__created')
                # log.info(accs_2_gh.query)
                print accs_2_gh.query
                log.info("\n\n%d  ::::  Qualified to be queued for GHing\n\n" % len(accs_2_gh))

                for acc_2_gh in accs_2_gh:
                    if can_gh(acc_2_gh):
                        with transaction.atomic():
                            log.info(acc_2_gh.id + "  ::: Qualified to enter GH Queue::: Amount 2 GH: %d" % acc_2_gh.amount)
                            if acc_2_gh.balance is None:    # If this account has not been matched b4 set balance to amount
                                gh_percentage = get_int_conf(1431, country, 0)
                                withhold = 0
                                if gh_percentage > 0 and acc_2_gh.donation.type in [Donation.PH]:
                                    mem = acc_2_gh.owner
                                    if get_bool_conf(1432, country, False):
                                        withhold = (acc_2_gh.amount * gh_percentage)/100
                                    else:
                                        withhold = (acc_2_gh.donation.amount * gh_percentage) / 100
                                    mem.frozen_balance = mem.frozen_balance + withhold
                                    mem.save()
                                acc_2_gh.balance += (acc_2_gh.amount - withhold)
                            acc_2_gh.amount_2_gh = (acc_2_gh.amount - acc_2_gh.balance)
                            acc_2_gh.save()

                            a = acc_2_gh.owner.bank_accounts__set.all().filter(is_default=True)
                            generate_tx([acc_2_gh], multiple=get_int_conf(1430, acc_2_gh.currency.country, 1000), amount=acc_2_gh.amount_2_gh, bank_account=a, old_bal=0.0, is_bonus=acc_2_gh.is_bonus)


                    else:
                        print acc_2_gh.id + " ::: Not Qualified to GH"
            else:
                return log.info("Did nothing... because Auto GH-13 is currently disabled, Please turn off this Task no other country needs it")
                # Gradual incrementation of the Account Balance was done in a different Shchdule to avoid country conflict


@shared_task(name='core.gh_matcher_scheduler')
def gh_matcher_scheduler(trans_ids=None, disabled_only=False):

    countries = Country.objects.filter(is_active=True)
    for country in countries:
        log.info("\n\n\n::::::::::::::::::::::::::::: GH Matching STARTS Now (%s) for %s  ::::::::::::::::::::::::::\n\n\n" % (timezone.now(), country.name))
        gh_matcher_function(trans_ids, disabled_only, country)
        log.info("\n\n\n::::::::::::::::::::::::::::: GH Matching ENDS Now (%s) for %s  ::::::::::::::::::::::::::\n\n\n" % (timezone.now(), country.name))

    log.info("\n\n\n::::::::::::::::::::::::::::: GH Matching STARTS Now (%s) for %s  ::::::::::::::::::::::::::\n\n\n" % (timezone.now(), "Bitcoin"))
    gh_matcher_function(trans_ids, disabled_only, None)
    log.info("\n\n\n::::::::::::::::::::::::::::: GH Matching ENDS Now (%s) for %s  ::::::::::::::::::::::::::\n\n\n" % (timezone.now(), "Bitcoin"))


def gh_matcher_function(trans_ids=None, disabled_only=False, country=None):
    counter = sum = 0
    ids = ""
    email_sender = get_bool_conf(1300, country, 1)
    sms_sender = get_bool_conf(1310, country, 1)
    sms_subject = get_str_conf(1021, country, settings.COY_NAME)
    c_percent = get_int_conf(1230, country, 0)

    if country:
        due_phes = Account.objects.filter(
            (Q(donation__commitment_matched__isnull=True, commitment_maturity__lte=timezone.now()) | Q(donation__commitment_matched__isnull=False, maturity__lte=timezone.now())), balance__gt=0,
            type__in=[Account.ACTIVATION, Account.PH, Account.PH_FEE, Account.RC], owner__is_bonus=False, owner__is_fake=False, owner__is_active=True, can_match=True, currency__country=country,
            owner__status__in=[Member.ACTIVE, Member.PAUSED], status__in=[Account.PENDING, Account.PARTIAL]).distinct().order_by('donation__created')[:2000]
    else:
        due_phes = Account.objects.filter(
            (Q(donation__commitment_matched__isnull=True, commitment_maturity__lte=timezone.now()) | Q(donation__commitment_matched__isnull=False, maturity__lte=timezone.now())), balance__gt=0,
            type__in=[Account.ACTIVATION, Account.PH, Account.PH_FEE, Account.RC], owner__is_bonus=False, owner__is_fake=False, owner__is_active=True, can_match=True, currency__code=BTC,
            owner__status__in=[Member.ACTIVE, Member.PAUSED], status__in=[Account.PENDING, Account.PARTIAL]).distinct().order_by('donation__created')[:2000]

    log.info("\n****** :::GH-01::: *********   %d   Pending Due PHes  [%s] ***************\n" % (len(due_phes), country.name if country else "Bitcoin"))

    if trans_ids is None:
        gh_txs = None
    else:
        gh_txs = Transaction.objects.filter(id__in=trans_ids, can_match=True).exclude(status__in=[Transaction.COMPLETED, Transaction.CANCELLED])

    trans_details = []
    for dph in due_phes:
        ph_bal, is_commitment = get_ph_balance(dph, c_percent=c_percent)
        dph_bal = dph.balance

        if not is_commitment and dph_bal != ph_bal:
            track(dph.id, 'account', "Stored balance %d [%s] is not equal to calculated balance %d" % (dph_bal, dph.id, ph_bal), 'Processing', 'GH Matcher')
            log.info("Stored balance %d is not equal to calculated balance %d" % (dph_bal, ph_bal))
            continue

        trans_details += match_ph_2_gh(dph, gh_txs=gh_txs, disabled_only=disabled_only, c_percent=c_percent, country_none=country)

    senders = []
    for trans_detail in trans_details:
        sum += trans_detail.amount
        ids += trans_detail.id + ", "

        if email_sender and trans_detail.sender.can_receive_email:
            # message = 'You have been matched to fulfil your PH order [%s ::: NGN %d]. Please complete and upload POP before the expiration timer already showing on your dashboard gets to 00:00:00' % (
            message = 'Your previous request to Provide Help (%s) to the sum of %s%d has been matched. We look forward to seeing you fulfil your request and wait for your time to smile. ' \
                      'Thanks for been part of this community, please Note you need to fulfill your order b4 expiration time as shown on your dashboard' % \
                      (trans_detail.id, trans_detail.currency.symbol, trans_detail.amount,)
            html_message = loader.render_to_string('core/mail_templates/notification.html', {'firstName': trans_detail.sender.first_name, 'mail_content': message, 'rootURL': settings.ROOT_URL})
            sendMail.apply_async(kwargs={'subject': 'Payment Notification', 'message': message, 'recipients': [trans_detail.sender.email], 'fail_silently': True, 'html_message': html_message,
                                         'connection_label': EmailCycler.get_email_label()})

        if sms_sender and trans_detail.sender.can_receive_sms and senders.count(trans_detail.sender.id) < 2: # Ensure you don't a user SMS more than twice within a batch
            senders.append(trans_detail.senders.id)
            sms = Message.objects.create(message="Hi %s, your PH order has been matched" % trans_detail.sender.first_name, phone=trans_detail.sender.phone, type=Message.PH_MATCHED)
            sendSMS.apply_async(kwargs={'sender': sms_subject, 'receivers': [sms.phone], 'message': sms.message, 'mid': sms.id})

            # if get_bool_conf(1310, country, 1):
            #     sms = Message.objects.create(message="U've been Matched to pay. Check ur Dashboard 4 details", phone=trans_detail.sender.phone, type='PH Matched')
            #     sms_send(sender=get_str_conf(1021, country, settings.COY_NAME), receivers=["234" + sms.phone[1:]], message=sms.message, mid=sms.id)

    if counter > 0:
        generate_report(SchedulerReport.MATCHED, count=counter, amount=sum, currency=due_phes[0].currency, note="Matched Ids: %s" % ids)
    return "\n\n\nMatched %d transactions (%s) valued at %d... Details: %s\n\n\n" % (counter, (due_phes[0].currency if counter>0 else (country.name if country else "Bitcoin")), sum, ids)


@shared_task(name='core.cleanup_defaulters')
def defaulters_cleanup_scheduler():
    # trans_details = TransactionDetail.objects.filter(status='Awaiting Payment', expires__lte=timezone.now())

    countries = Country.objects.filter(is_active=True)
    for country in countries:
        c_percent = get_int_conf(1230, country, 0)
        accs = Account.objects.filter(transactiondetail__status=TransactionDetail.AWAITING_PAYMENT, transactiondetail__expires__lte=timezone.now())
        blocked = disabled = confirmed = 0

        for acc in accs:  # Block members whose PH has timed out
            blocked += block_acc(acc)

        members = Member.objects.filter(user__is_active=True, status='Blocked', delete_on__lte=timezone.now())
        for mem in members:  # Deactivate previously Blocked members
            user = mem.user
            user.is_active = False
            user.save()
            disabled += 1

        # expires = timezone.now() - timedelta(hours=get_int_conf(1213, country, 24))
        # tds = TransactionDetail.objects.filter(status='Awaiting Confirmation', proof_date__isnull=False, proof_date__lte=expires, proof_acknowledge_date__isnull=True)
        # for td in tds:  # Auto confirm payments that has not been confirmed
        #     confirmed += confirm_transaction(td)

    return "Blocked %d Members, Disabled %d profiles and Auto Confirmed %d Transactions" % (blocked, disabled, confirmed)


@shared_task(name='core.database_backup')
def database_backup_scheduler():
    pass


def gh_fix(aid=None):
    now = timezone.now()

    acc_2_gh = Account.objects.filter(id=aid).first()
    if acc_2_gh:
        print "Yes...."
        with transaction.atomic():
            print "Owner %s %s (%s)" % (acc_2_gh.owner.first_name, acc_2_gh.owner.last_name, acc_2_gh.owner.phone)

            log.info(acc_2_gh.id + " ::: Amount 2 GH: %d" % acc_2_gh.amount)
            acc_2_gh.updated = now
            acc_2_gh.balance = acc_2_gh.amount
            acc_2_gh.save()

            ghing_ph_acc = Account.objects.filter(donation=acc_2_gh.donation, type='PH').first()

            if ghing_ph_acc.is_bonus or ghing_ph_acc.owner.is_bonus:
                print "is Admin...."
                if TransactionDetail.objects.filter(
                        account=ghing_ph_acc).first() is None and ghing_ph_acc.status != 'Admin Processed':  # if we have not Matched this Admin PH (Free GHer). Please set it as Admin's PH so we dont Matched to Pay
                    ghing_ph_acc.status = 'Admin Processed'
                    ghing_ph_acc.balance = 0
                    ghing_ph_acc.is_bonus = True
                    ghing_ph_acc.fulfilled = now
                    ghing_ph_acc.save()

                    acc_2_gh.is_bonus = True
                    acc_2_gh.save()

            trans = Transaction()
            trans.id = generate_id('TX')
            trans.amount = acc_2_gh.amount
            trans.balance = acc_2_gh.amount
            trans.owner = acc_2_gh.owner
            trans.status = 'Pending'
            trans.is_bonus = acc_2_gh.is_bonus
            trans.save()


def process_disabled_members(mems):
    for mem in mems:
        now = timezone.now()
        dons = Donation.objects.filter(member=mem, member__is_active=False, status=Account.PENDING)
        accs = Account.objects.filter(donation__in=dons, transactiondetail__isnull=True, status=Account.PENDING)
        accs.filter(type=Account.PH).update(status=Account.PROCESSED, balance=0, fulfilled=now)
        Donation.objects.filter(account__in=accs).update(status=Account.PROCESSED, fulfilled=now)



# def health_check():
# dons = Donation.objects.all().exclude(status__in=['Cancelled'])
#

# ph.status = Account.PARTIAL
# ph.save()
# print "%s  %d    %d" % (ph.id, ph.amount, total)



#
# tds = TransactionDetail.objects.all().exclude(status__in=[TransactionDetail.CONFIRMED, TransactionDetail.CANCELLED])
#
#
# ph_accs = Account.objects.filter(type='PH').exclude(status__in=[Account.CANCELLED, Account.PROCESSED_BONUS, Account.PROCESSED])
# phs = []
# counter0 =counter1=counter2=counter3 = 0
# for ph in ph_accs:
#     total = TransactionDetail.objects.filter(account=ph).exclude(status='Cancelled').aggregate(sum=Sum('amount'))['sum'] or 0
#     if int(total) > int(ph.amount):
#         counter0 += 1
#         print "%s  Amount: %d    Total: %d" % (ph.id, ph.amount, total)
#     elif int(total) < int(ph.amount) and total >0 and ph.balance != (ph.amount - total):
#         counter1 += 1
#         print "Partial:  %s  Amount: %d    Total: %d    Bal: %d    Supposed: %d" % (ph.id, ph.amount, total, ph.balance, ph.amount - total)
#     elif int(ph.amount) == int(total):
#         counter2 += 1
#         # print "===>>3 %s  Amount: %d    Total: %d" % (ph.id, ph.amount, total)
#     elif ph.balance == ph.amount:
#         counter3 += 1
#         print "===>>4 %s  Amount: %d    Total: %d" % (ph.id, ph.amount, total)
#
# from core.models import Member,Account, Member,TransactionDetail,Transaction
# from django.db.models import Q, Max, Sum, Count, F
#
#
#
# tds = TransactionDetail.objects.all().exclude(status='Cancelled').values('transaction').annotate(sum=Sum('amount'))
# for td in tds:
#     tran = Transaction.objects.filter(id=td['transaction']).exclude(status=Transaction.COMPLETED).first()
#     if tran and td['sum'] > tran.amount:
#         # tran.status = Transaction.COMPLETED
#         print "'%s',    %s    Total Paid: %d    Supposed: %d    Bal: %d    Current Bal: %d  " %(td['transaction'], tran.status, td['sum'], tran.amount, tran.balance, tran.amount-td['sum'])
#
# ttt=[]
# ts = Transaction.objects.all().exclude(status='Completed')
# for t in ts:
#     tds = TransactionDetail.objects.filter(transaction=t).exclude(status=TransactionDetail.CANCELLED).values('transaction').annotate(sum=Sum('amount'))
#     # tran = Transaction.objects.filter().exclude(status=Transaction.COMPLETED).first()
#     # print tds
#     if len(tds)==0:
#         ttt.append(t)
#         continue
#     td = tds[0]
#     if len(tds) ==1 and td['sum'] >= t.amount and t.status != Transaction.INCOMPLETE:
#         t.status = Transaction.COMPLETED
#         t.save()
#         print "'%s',    %s   Amount: %d    Total Paid: %d      Bal: %d    Current Bal: %d  " %(td['transaction'], t.status, t.amount, td['sum'], t.balance, t.amount-td['sum'])
#
#
# select t.id, m.first_name, m.last_name, m.phone, m.id as mid, u.id as uid, u.username from core_transaction t join
# core_member m on m.id = t.owner_id join
# auth_user u on u.id = m.user_id where t.id in (
# 'TX0609062236933069',
# 'TX0609062237129426',
# 'TX0609062237171403',
# 'TX0609062237198784',
# 'TX0609062238433956',
# 'TX0609062238496811',
# 'TX0609062240055027',
# 'TX0609062240074706',
# 'TX0609062758590780',
# 'TX0609062758603774',
# 'TX0609062758648774',
# 'TX0609070056668851',
# 'TX0609070756354593',
# 'TX0609070756630876',
# 'TX0609080206610920',
# 'TX0609080206634907',
# 'TX0609080208019489',
# 'TX0609080209747945',
# 'TX0609080211053735',
# 'TX0609173257596349',
# 'TX0609173257774926',
# 'TX0609173257858621',
# 'TX0609173257917566',
# 'TX0609173258183979',
# 'TX0609173259147811',
# 'TX0609173300539001',
# 'TX0609173300650621',
# 'TX0609173300695312',
# 'TX0609173300984519',
# 'TX0609173301109974',
# 'TX0609173311132640',
# 'TX0609173311993194',
# 'TX0609175433776478',
# 'TX0609175434159038',
# 'TX0609175434196437',
# 'TX0609175434228566',
# 'TX0609175434539778',
# 'TX0609175434661296', ) order by m.last_name
#
#
#
#
#
#     tds = TransactionDetail.objects.filter(status='Cancelled',rematched='No')
#     if ph.amount < total:
#         print "===>> %s  Amount: %d    Total: %d" % (ph.id, ph.amount, total)
#
#
# for ph in ph_accs:
#     total = TransactionDetail.objects.filter(~(Q(status='Cancelled'),Q(rematched='Yes')),account=ph).exclude(status='Cancelled', rematched='Yes').aggregate(sum=Sum('amount'))['sum'] or 0
#
#     tds = TransactionDetail.objects.filter(status='Cancelled',rematched='No')
#     if ph.amount < total:
#         print "===>> %s  Amount: %d    Total: %d" % (ph.id, ph.amount, total)
#
# for ph in ph_accs:
#     tds = TransactionDetail.objects.filter(account=ph).exclude(status='Cancelled', rematched='Yes')
#     for td in tds:
#         td
#         if ph.amount < total:
#             print "===>> %s  Amount: %d    Total: %d" % (ph.id, ph.amount, total)
#
#
# tds = TransactionDetail.objects.filter(~Q(Q(status='Cancelled'),Q(rematched='Yes')), )
# tds = TransactionDetail.objects.filter(status__in=[TransactionDetail.AWAITING_PAYMENT,TransactionDetail.PAUSED_EXCEPTION,TransactionDetail.PAUSED_RECYCLE])
#
#
# select * from core_transaction_detail where account_id in (
# 'PH0610051800828986',
# 'PH0610051800677204',
# 'PH0610051800606776',
# 'PH0610051800458229',
# 'PH0610051800365811',
# 'PH0610051800063338',
# 'PH0610051759737876',
# 'PH0610051759506140',
# 'PH0610051759360693',
# 'PH0610051759259593',
# 'PH0610051759169256')
#
#
# ng = TransactionDetail.objects.filter(amount__lt=0).exclude(status=TransactionDetail.CONFIRMED)
# for n in ng:
#     print n.id
#     print n.amount
#     n.status = TransactionDetail.CANCELLED
#     n.rematched = 'Yes'
#     n.save()
#
#
# td = TransactionDetail.objects.get(id='TD0609173353454905')
# td.status=TransactionDetail.CANCELLED
# td.rematched='Yes'
# td.save()
#
# td = TransactionDetail.objects.get(id='TD0609175439250722')
# td.status=TransactionDetail.CANCELLED
# td.rematched='Yes'
# td.save()
#
# tds = TransactionDetail.objects.filter(id__in=['TD0609175447647695','TD0609175447813578','TD0609175447641128','TD0609175447566223','TD0609175447320763','TD0609175447288148'])
# for td in tds:
#     td.status=TransactionDetail.CANCELLED
#     td.rematched='Yes'
#     td.save()
#
# trans = td.transaction
# if trans.status != TransactionDetail.CONFIRMED:
#     trans.status = Transaction.INCOMPLETE
#     trans.save()
#
#
#
#
# bavs = BankAccountVerification.objects.filter(verified__isnull=True)
# for bav in bavs:
#     try:
#         datetime(2017, 6, 10, 9, 30, 0, tzinfo=pytz.UTC)
#
#
#         verify_account(BankAccountVerification.objects.get(id=bav.id))
#     except:
#         print "Error: %d %s" % (bav.id,bav.member)
#
#
#
#     Account.objects.get(transaction__id='TX0608202133156206', transactiondetail__transaction__id='TX0608202133156206')
#     Donation.objects.filter(status__in=['Processing', 'Pending', 'Paused (Exception)',  'Paused (Recycle)', 'Partial', 'Timeout', 'Blocked'])
#
#
# bavs = BankAccountVerification.objects.filter(verified__isnull=True)
# for bav in bavs:
#     try:
#         verify_account(BankAccountVerification.objects.get(id=bav.id))
#     except:
#         print "Error: %d %s" % (bav.id,bav.member)

####