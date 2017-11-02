from django.conf.urls import url
from django.contrib import admin

# Register your models here.
from django.contrib.admin import BooleanFieldListFilter
from django.contrib.admin.utils import flatten_fieldsets
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.core import urlresolvers
from django.db import transaction
from django.db.models import F
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.contrib import messages
from django.utils.safestring import mark_safe
from mock.mock import self

from core.utils import decimal_normalise, reverse_transaction_details, confirm_transaction, cancel_defaulted_transaction_details
from django_celery_beat.models import PeriodicTask, PeriodicTasks

from core.models import User, Currency, Country, AuthAudit, SchedulerReport, POPPicture

from core.models import Package, Bank, Config, Message, ResponseCode, BankAccount, Member, Account, Transaction, TransactionDetail, Donation, Reason, BankAccountVerification, \
    TransactionPointer, TransactionDetailPointer

MAX_SHOW_ALL = 2000
PER_PAGE = 500


class ImprovedAdmin(admin.ModelAdmin):
    """Handles column formatting in list display"""
    def __init__(self, *args, **kwargs):
        def generate_formatter(name, str_format):
            formatter = lambda o: str_format%(getattr(o, name) or 0)
            formatter.short_description = name
            formatter.admin_order_field = name
            return formatter

        all_fields = []
        for f in self.list_display:
            if isinstance(f, basestring):
                all_fields.append(f)
            else:
                new_field_name = f[0]+'_formatted'
                setattr(self, new_field_name, generate_formatter(f[0], f[1]))
                all_fields.append(new_field_name)
        self.list_display = all_fields

        super(ImprovedAdmin, self).__init__(*args, **kwargs)


# Define an inline admin descriptor for Employee model
# which acts a bit like a singleton
class MemberInline(admin.StackedInline):
    model = Member
    can_delete = False
    verbose_name_plural = 'member'


# Define a new User admin


class UserAdmin(BaseUserAdmin):
    # The forms to add and change user instances
    form = UserChangeForm
    add_form = UserCreationForm

    # The fields to be used in displaying the User model.
    # These override the definitions on the base UserAdmin
    # that reference specific fields on auth.User.
    list_display = ('username', 'first_name', 'last_name', 'phone', 'email', 'is_staff', 'is_superuser', 'is_active', 'last_login')
    list_filter = ('is_active', 'is_staff', 'is_superuser',)
    fieldsets = (
        (None, {'fields': ('email', 'password', 'username', 'phone')}),
        ('Personal info', {'fields': ('first_name', 'last_name')}),
        ('Permissions', {'fields': ('is_staff', 'is_superuser', 'is_active', 'groups', 'user_permissions')}),
    )
    # add_fieldsets is not a standard ModelAdmin attribute. UserAdmin
    # overrides get_fieldsets to use this attribute when creating a user.
    add_fieldsets = (
        (None, {'classes': ('wide',), 'fields': ('email', 'username', 'phone', 'password1', 'password2')}),
    )
    search_fields = ('username', 'first_name', 'last_name', 'phone', 'email', 'is_staff', 'is_superuser', 'is_active', 'last_login')
    ordering = ('first_name',)
    filter_horizontal = ('groups', 'user_permissions',)

# Re-register UserAdmin
# Now register the new UserAdmin...
# admin.site.unregister(User)
admin.site.register(User, UserAdmin)
# ... and, since we're not using Django's built-in permissions,
# unregister the Group model from admin.
# admin.site.unregister(Group)



@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    # list_display = ('id', 'donation', 'amount', 'owner', 'type', 'status', 'created', 'updated', 'fulfilled', 'is_bonus', 'donation', 'balance', 'max')
    list_display = ('id', 'donation_list_link', 'member_list_link', 'account_list_link_don', 'balance_value', 'status', 'type', 'fulfilled', 'is_bonus', 'is_fake',  'created_on')
    # search_fields = ['id', 'amount', 'owner__first_name', 'owner__last_name', 'owner__other_names', 'owner__phone', 'owner__user__username', 'type', 'status', 'donation__id', 'donation__recommitment', 'donation__member__user__username']
    search_fields = ['id', 'amount', 'owner__first_name', 'owner__last_name', 'owner__other_names', 'owner__phone', 'owner__user__username', 'type', 'status', 'donation__id', 'donation__member__user__username']
    # search_fields = ['type']
    actions_on_top = True
    actions_on_bottom = True
    date_hierarchy = 'created'
    # list_display_links = ('id',)
    # list_display_links = None
    list_filter = ('type', 'is_bonus', 'currency__symbol', 'donation__is_committed', 'status', 'donation__channel')
    # empty_value_display = '-'
    list_max_show_all = MAX_SHOW_ALL
    list_per_page = PER_PAGE
    # show_full_result_count = False
    # readonly_fields = ('fulfilled',)

    # def value(self, obj):
    #     return "%s%s" %(obj.currency.symbol, decimal_normalise(obj.amount))
    # value.short_description = 'Amount'
    # value.admin_order_field = 'amount'

    def balance_value(self, obj):
        if obj.type in [Account.PH, Account.PH_FEE, Account.RC]:
            return "-" if obj.balance == 0 else "%s%s" % (obj.currency.symbol, decimal_normalise(obj.balance))
        else:
            return "-" if obj.balance == 0 else "%s%s" % (obj.currency.symbol, decimal_normalise(obj.amount-obj.balance))
    balance_value.short_description = 'Balance'
    balance_value.admin_order_field = 'balance'

    def is_fake(self, obj):
        return obj.owner.is_fake
    is_fake.short_description = 'Fake'
    is_fake.admin_order_field = 'fake'

    def created_on(self, obj):
        return obj.created.strftime("%d-%m-%Y %H:%M")
    created_on.short_description = 'Created'
    created_on.admin_order_field = 'created'

    # def donation(self, obj):
    #     # return obj.created.strftime("%d %b %Y %H:%M")
    #     print obj.donation.id
    #     return obj.donation.id[2:]
    # donation.short_description = 'Donation Id'

    def channel(self, obj):
        return obj.donation.channel
    channel.short_description = 'Channel'
    created_on.admin_order_field = 'donation.channel'

    def donation_list_link(self, item):
        return item.donation.get_admin_list_link(item.donation, item.donation.id)
    donation_list_link.allow_tags = True
    donation_list_link.short_description = 'Donation'
    donation_list_link.admin_order_field = 'donation'

    def member_list_link(self, item):
        return item.owner.get_admin_list_link(item.owner, item.owner.user.username)
    member_list_link.allow_tags = True
    member_list_link.short_description = 'Owner'
    member_list_link.admin_order_field = 'owner.first_name'

    def account_list_link_don(self, item):
        return item.get_admin_list_link_don(item.donation.id, "%s%s" %(item.currency.symbol, decimal_normalise(item.amount)))
    account_list_link_don.allow_tags = True
    account_list_link_don.short_description = 'Amount'
    account_list_link_don.admin_order_field = 'amount'

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

@admin.register(AuthAudit)
class AuthAuditAdmin(admin.ModelAdmin):
    list_display = ('ip', 'created', 'last_date', 'user', 'username', 'fingerprint', 'source', 'authentication_status', 'browser',  'operating_system', 'device')
    search_fields = ['ip', 'username', 'fingerprint', 'auth_backend', 'browser', 'os', 'device']
    actions_on_top = True
    actions_on_bottom = True
    date_hierarchy = 'created'
    # list_display_links = ('id',)
    list_filter = ('auth_backend', 'auth_status', 'session_status', 'browser', 'os', 'device')
    list_max_show_all = MAX_SHOW_ALL
    list_per_page = PER_PAGE
    readonly_fields = list_display

    def source(self, obj):
        return obj.auth_backend
    source.short_description = 'Source'
    source.admin_order_field = 'auth_backend'

    def authentication_status(self, obj):
        return "%s (%s)" % (obj.auth_status, obj.session_status)
    authentication_status.short_description = 'Auth Status'
    authentication_status.admin_order_field = 'auth_status'

    def operating_system(self, obj):
        return obj.os
    operating_system.short_description = 'OS'
    operating_system.admin_order_field = 'os'

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

@admin.register(Bank)
class BankAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'country')
    search_fields = ['code', 'name', 'country_name', 'country_code']
    list_max_show_all = MAX_SHOW_ALL
    list_per_page = PER_PAGE


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ('number', 'name', 'currency', 'bank_list_link')
    search_fields = ['number']
    list_max_show_all = MAX_SHOW_ALL
    list_per_page = PER_PAGE

    def bank_list_link(self, item):
        return item.bank.get_admin_list_link(item.bank, item.bank.code)
    bank_list_link.allow_tags = True
    bank_list_link.short_description = 'Bank'
    bank_list_link.admin_order_field = 'bank.name'

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

@admin.register(BankAccountVerification)
class BankAccountVerificationAdmin(admin.ModelAdmin):
    list_display = ('member', 'phone', 'account', 'bank', 'name', 'created', 'verified')
    search_fields = ['account__number', 'bank__name', 'name', 'verified', 'member__first_name', 'member__last_name', 'member__other_names', 'member__user__username', 'member__phone']
    list_filter = ('bank',)
    list_display_links = ('account',)
    list_max_show_all = MAX_SHOW_ALL
    list_per_page = PER_PAGE

    def username(self, obj):
        return obj.member.user.username
    username.short_description = 'Username'
    username.admin_order_field = 'member.user.username'

    def phone(self, obj):
        return obj.member.phone
    phone.short_description = 'Phone'
    phone.admin_order_field = 'member.phone'

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

@admin.register(Config)
class ConfigAdmin(admin.ModelAdmin):
    list_display = ('code', 'label', 'value', 'country', 'description')
    search_fields = ['code', 'label', 'country',]
    list_filter = ('code', 'value', 'country',)
    list_max_show_all = MAX_SHOW_ALL
    list_per_page = PER_PAGE

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'dial_code', 'is_active')
    search_fields = ['name', 'code', 'dial_code']
    list_filter = ('is_active',)
    list_max_show_all = MAX_SHOW_ALL
    list_per_page = PER_PAGE

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ('code', 'symbol', 'name', 'rate', 'country_list_link', 'is_actived')
    search_fields = ['code', 'symbol', 'name', 'rate', 'country__code', 'country__name']
    list_filter = ('code', 'symbol', 'name',)
    list_max_show_all = MAX_SHOW_ALL
    list_per_page = PER_PAGE

    def is_actived(self, obj):
        if obj.country:
            return obj.country.is_active
        elif obj.name in ["BTC", "GMB"]:
            return True
        else:
            return False
    is_actived.short_description = 'Is Actived?'
    is_actived.admin_order_field = 'country.is_active'

    def country_list_link(self, item):
        if not item.country:
            return ""
        return item.country.get_admin_list_link(item.country, item.country.code)
    country_list_link.allow_tags = True
    country_list_link.short_description = 'Country'
    country_list_link.admin_order_field = 'country.name'

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(Donation)
class DonationAdmin(admin.ModelAdmin):
    list_display = ('id', 'member_list_link', 'account_link', 'type', 'status', 'channel', 'is_committed', 'fulfilled', 'created')
    # list_display = ('id', 'member_list_link', 'amount', 'type', 'status', 'channel', 'is_committed', 'donation_list_link', 'fulfilled', 'created')
    search_fields = ['id', 'amount', 'type', 'member__first_name', 'member__last_name', 'member__other_names', 'member__phone', 'member__user__username']
    list_filter = ('status', 'channel', 'is_committed')
    date_hierarchy = 'created'
    actions = ['process_as_admin']
    list_max_show_all = MAX_SHOW_ALL
    list_per_page = PER_PAGE

    def created_on(self, obj):
        return obj.created.strftime("%d-%m-%Y %H:%M")
    created_on.short_description = 'Created'
    created_on.admin_order_field = 'created'

    # def ph_account(self, obj):
    #     print "Supposed PH Account"
    #     print obj.donation.account_set
    #     return obj.donation.id[2:]
    #     ph_account.short_description = 'PH Account'
    #     ph_account.admin_order_field = 'donation.id'
    #
    # def gh_account(self, obj):
    #     print "Supposed GH Account"
    #     print obj.donation.account_set
    #     return obj.donation.id[2:]
    #     gh_account.short_description = 'GH Account'
    #     gh_account.admin_order_field = 'donation.id'

    def channel(self, obj):
        return obj.donation.channel
    channel.short_description = 'Channel'
    created_on.admin_order_field = 'donation.channel'

    def process_as_admin(self, request, queryset):
        now = timezone.now()
        with transaction.atomic():
            accs = Account.objects.filter(donation__in=queryset, transactiondetail__isnull=True)
            accs.update(is_bonus=True)
            accs.filter(type=Account.PH).update(status=Account.PROCESSED_BONUS, balance=0, fulfilled=now)
            rows_updated = Donation.objects.filter(account__in=accs).update(status=Account.PROCESSED_BONUS, fulfilled=now)
            self.message_user(request, "%d records successfully processed as Admin." % rows_updated, messages.SUCCESS)

    # actions = None
    # list_display_links = None

    # def has_add_permission(self, request):
    #     return False

    def member_list_link(self, item):
        return item.member.get_admin_list_link(item.member, item.member.user.username)
    member_list_link.allow_tags = True
    member_list_link.short_description = 'Owner'
    member_list_link.admin_order_field = 'owner.first_name'

    def account_link(self, item):
        url = reverse("admin:%s_%s_changelist" % (item._meta.app_label, 'account'))
        return mark_safe('<a href="{}?q={}">{}</a>'.format(url, item.id, decimal_normalise(item.amount)))
    account_link.allow_tags = True
    account_link.short_description = 'Amount'
    account_link.admin_order_field = 'amount'

    def donation_list_link(self, item):
        return item.donation.get_admin_list_link(item.donation, item.donation.id)
    donation_list_link.allow_tags = True
    donation_list_link.short_description = 'Recommitment'
    donation_list_link.admin_order_field = 'recommitment.id'

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ('user', 'full_name', 'phone', 'email', 'balance_value', 'balance_btc_value', 'is_fake', 'member_list_link', 'status', 'min_ph', 'min_btc', 'is_bonus')
    # list_display = ('user', 'full_name', 'phone', 'email', 'is_fake', 'bank_accounts', 'sponsor_id', 'status', 'min_ph', 'is_bonus')
    # list_display = ('first_name', 'last_name', 'phone', 'email', 'created', 'bank_account', 'status')
    # list_display = [f.name for f in Member._meta.fields]
    search_fields = ['user__username', 'first_name', 'last_name', 'other_names', 'phone', 'email']
    # search_fields = ['user__username', 'first_name', 'last_name', 'other_names', 'phone', 'email', 'bank_account__name', 'bank_account__number', 'bank_account__bank__name']
    actions = ['force_activate', 'block', 'suspend', 'toggle_member_bonus_gher_status', 'toggle_member_fake_status']
    list_filter = ('is_bonus', 'status', 'is_fake', 'is_phone_verified', 'is_email_verified', 'is_active')
    date_hierarchy = 'created'
    list_display_links = ('user',)
    radio_fields = {"status": admin.HORIZONTAL}
    list_max_show_all = MAX_SHOW_ALL
    list_per_page = PER_PAGE
    exclude = ('password',)

    def toggle_member_bonus_gher_status(self, request, queryset):
        counter = queryset(is_bonus=not F('is_bonus'))
        if counter == 1:
            message_bit = "Only 1 member was"
        else:
            message_bit = "%s members were" % counter
        self.message_user(request, "%s successfully toggle Free GHers." % message_bit, level=messages.SUCCESS)
        # messages.success(request, "%s successfully toggle Free GHer." % message_bit)
    toggle_member_bonus_gher_status.short_description = "Toggle selected members as GH Admin"

    def toggle_member_fake_status(self, request, queryset):
        counter = queryset.update(is_fake=not F('is_fake'))
        if counter == 1:
            message_bit = "Only 1 member was"
        else:
            message_bit = "%s members were" % counter
        self.message_user(request, "%s successfully toggle Fake Status." % message_bit, level=messages.SUCCESS)
        # messages.success(request, "%s successfully toggle Free GHer." % message_bit)
    toggle_member_bonus_gher_status.short_description = "Toggle selected members Fakes Status"

    def force_activate(self, request, queryset):
        counter = queryset.update(status=Member.ACTIVE)
        if counter == 1:
            message_bit = "Only 1 member was"
        else:
            message_bit = "%s members were" % counter
        self.message_user(request, "%s successfully toggle Free GHers." % message_bit, level=messages.SUCCESS)
    force_activate.short_description = "Force Active selected members"

    def block(self, request, queryset):
        counter = queryset.update(status=Member.BLOCKED)
        if counter == 1:
            message_bit = "Only 1 member was"
        else:
            message_bit = "%s members were" % counter
        self.message_user(request, "%s successfully toggle Free GHers." % message_bit, level=messages.SUCCESS)
    block.short_description = "Block selected members"

    def suspend(self, request, queryset):
        counter = queryset.update(status=Member.SUSPENDED)
        if counter == 1:
            message_bit = "Only 1 member was"
        else:
            message_bit = "%s members were" % counter
        self.message_user(request, "%s successfully toggle Free GHers." % message_bit, level=messages.SUCCESS)
    suspend.short_description = "Suspended selected members"

    def has_delete_permission(self, request, obj=None):
        #Disable delete
        return False

    # def get_form(self, request, obj=None, **kwargs):
    #     self.exclude = ("password",)
    #     form = super(MemberAdmin, self).get_form(request, obj, **kwargs)
    #     return form

    def get_queryset(self, request):
        qs = super(MemberAdmin, self).get_queryset(request)
        if not request.user.is_superuser:
            qs = qs.exclude(is_active=False)
        return qs

    def min_btc(self, obj):
        return "-" if obj.min_ph_btc == 0 else "%s" %(decimal_normalise(obj.min_ph_btc),)
    min_btc.short_description = 'Min BTC'
    min_btc.admin_order_field = 'min_ph_btc'

    def balance_value(self, obj):
        return "-" if obj.gh_balance == 0 else "%s" %(decimal_normalise(obj.gh_balance),)
    balance_value.short_description = 'Bal Local'
    balance_value.admin_order_field = 'gh_balance'

    def balance_btc_value(self, obj):
        return "-" if obj.gh_balance_btc == 0 else "%s" %(decimal_normalise(obj.gh_balance_btc),)
    balance_btc_value.short_description = 'Bal BTC'
    balance_btc_value.admin_order_field = 'gh_balance_btc'

    def member_list_link(self, item):
        return "-" if not item.sponsor else item.sponsor.get_admin_list_link(item.sponsor, item.sponsor.user.username)
    member_list_link.allow_tags = True
    member_list_link.short_description = 'Sponsor'
    member_list_link.admin_order_field = 'sponsor.first_name'

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('message', 'phone', 'type', 'counter', 'created', 'sent_time', 'code', 'response_code')
    search_fields = ['phone']
    list_max_show_all = MAX_SHOW_ALL
    list_per_page = PER_PAGE

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = ('amount', 'name', 'status', 'start_date', 'end_date', 'test_amount')
    list_max_show_all = MAX_SHOW_ALL
    list_per_page = PER_PAGE

    def test_amount(self, obj):
        return obj.amount

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


admin.site.unregister(PeriodicTask)  # First unregister the old class


@admin.register(PeriodicTask)
class PeriodicTaskAdmin(admin.ModelAdmin):
    list_display = ('name', 'enabled', 'total_run_count', 'last_run_at', 'interval')
    actions = ['toggle_enabled_status']
    list_max_show_all = MAX_SHOW_ALL
    list_per_page = PER_PAGE

    def toggle_enabled_status(self, request, queryset):
        msg = ""
        for x in queryset:
            if x.enabled:
                x.enabled = False
                msg += "<li>"+x.name+" was turned OFF</li>"
            else:
                x.enabled = True
                msg += "<li>" + x.name + " was turned ON</li>"
            x.save()

        self.message_user(request, format_html(msg), level=messages.SUCCESS, extra_tags='safe')
    toggle_enabled_status.short_description = "Toggle selected Schedulers"

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

# @admin.register(PreMember)
# class PreMemberAdmin(admin.ModelAdmin):
#     list_display = ('first_name', 'last_name', 'username', 'email', 'token', 'code', 'created', 'expires', 'sponsor', 'status', 'package')
#     date_hierarchy = 'created'
#     list_max_show_all = MAX_SHOW_ALL
#     list_per_page = PER_PAGE
#
#     search_fields = ['first_name', 'last_name', 'token', 'email', 'created', 'username', 'status', 'package']


@admin.register(POPPicture)
class POPPictureAdmin(admin.ModelAdmin):
    list_display = ('object_id', 'content_type', 'file_name', 'created', 'content_object')
    search_fields = ['object_id', 'file_name', 'content_object']
    date_hierarchy = 'created'
    list_max_show_all = MAX_SHOW_ALL
    list_per_page = PER_PAGE

    def file_name(self, item):
        return format_html(u'<a href="{}" target="_blank"><i class="glyphicon glyphicon-picture"></i></a>', item.file.url)
    file_name.allow_tags = True
    file_name.short_description = 'File'
    file_name.admin_order_field = 'file'

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(Reason)
class ReasonAdmin(admin.ModelAdmin):
    list_display = ('object_id', 'content_type', 'message', 'created', 'content_object', 'status')
    search_fields = ['object_id', 'message', 'status']
    date_hierarchy = 'created'
    list_max_show_all = MAX_SHOW_ALL
    list_per_page = PER_PAGE

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(ResponseCode)
class ResponseCodeAdmin(admin.ModelAdmin):
    list_display = ('label', 'description', 'alias')
    search_fields = ['label', 'alias']
    list_max_show_all = MAX_SHOW_ALL
    list_per_page = PER_PAGE

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(SchedulerReport)
class SchedulerReportAdmin(admin.ModelAdmin):
    list_display = ('type', 'count', 'amount', 'currency', 'note')
    search_fields = ['type', 'currency__code', 'currency__symbol', 'note']
    date_hierarchy = 'created'
    list_filter = ('type', 'currency__code',)
    list_max_show_all = MAX_SHOW_ALL
    list_per_page = PER_PAGE

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'value',  'balance_value', 'member_list_link', 'type', 'status', 'is_bonus', 'created_on')
    search_fields = ['id', 'amount', 'owner__first_name', 'owner__last_name', 'owner__phone', 'owner__user__username', 'created']

    date_hierarchy = 'created'
    list_filter = ('status', 'type',)
    list_max_show_all = MAX_SHOW_ALL
    list_per_page = PER_PAGE

    def value(self, obj):
        return "%s%s" %(obj.currency.symbol, decimal_normalise(obj.amount))
    value.short_description = 'Amount'
    value.admin_order_field = 'amount'

    def balance_value(self, obj):
        if obj.type == Transaction.COIN:
            return "-" if obj.balance == 0 else "%s%s" %(obj.currency.symbol, decimal_normalise(obj.amount-obj.balance))
        else:
            return "-" if obj.balance == 0 else "%s%s" % (obj.currency.symbol, decimal_normalise(obj.balance))
    balance_value.short_description = 'Balance'
    balance_value.admin_order_field = 'balance'

    def created_on(self, obj):
        # return obj.created.strftime("%d %b %Y %H:%M")
        return obj.created.strftime("%d-%m-%Y %H:%M")
    created_on.short_description = 'Created'

    def get_queryset(self, request):
        qs = super(TransactionAdmin, self).get_queryset(request)
        if not request.user.is_superuser:
            qs = qs.exclude(owner__is_active=False)
        return qs

    def member_list_link(self, item):
        return item.owner.get_admin_list_link(item.owner, item.owner.user.username)
    member_list_link.allow_tags = True
    member_list_link.short_description = 'Owner'
    member_list_link.admin_order_field = 'owner'

# class MyModelAdmin(ImprovedAdmin):
#     list_display = ('id', ('amount', '%.2f EUR'), ('interest', '%.2f %%'))

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(TransactionDetail)
class TransactionDetailAdmin(ImprovedAdmin):
    list_display = ('id', 'transaction_link', 'value', 'account_link', 'member_link', 'status', 'proof_date', 'total', 'expires')
    # list_display = ('id', 'transaction', ('amount', '%.2f'), 'account', 'sender', 'status', 'proof_date', 'total', 'expires')
    search_fields = ['id', 'amount', 'account__id', 'sender__first_name', 'sender__last_name', 'sender__phone', 'sender__user__username', 'status', 'expires', 'transaction__id']
    actions = ['reverse_matched', 'confirm_transaction', 'cancel_defaulted_transaction_details']
    date_hierarchy = 'created'
    list_filter = ('status', 'currency')
    list_max_show_all = MAX_SHOW_ALL
    list_per_page = PER_PAGE

    def transaction_link(self, item):
        return item.transaction.get_admin_list_link(item.transaction, item.transaction.id)
    transaction_link.allow_tags = True
    transaction_link.short_description = 'Transaction'
    transaction_link.admin_order_field = 'transaction.id'

    def account_link(self, item):
        return item.account.get_admin_list_link(item.account, item.account.id)
    account_link.allow_tags = True
    account_link.short_description = 'Account'
    account_link.admin_order_field = 'account.id'

    def member_link(self, item):
        return item.sender.get_admin_list_link(item.sender, item.sender.user.username)
    member_link.allow_tags = True
    member_link.short_description = 'Sender'
    member_link.admin_order_field = 'sender.first_name'

    def value(self, obj):
        return "%s%s" %(obj.currency.symbol, decimal_normalise(obj.amount))
    value.short_description = 'Amount'
    value.admin_order_field = 'amount'

    # def balance_value(self, obj):
    #     return "-" if obj.balance == 0 else "%s%s" %(obj.currency.symbol, decimal_normalise(obj.balance))
    # balance_value.short_description = 'Balance'
    # balance_value.admin_order_field = 'balance'

    def total(self, obj):
        return "%s%s" %(obj.currency.symbol, decimal_normalise(obj.transaction.amount))
    total.short_description = 'Total'
    total.admin_order_field = 'transaction.amount'

    def created_on(self, obj):
        # return obj.created.strftime("%d %b %Y %H:%M")
        return obj.created.strftime("%d-%m-%Y %H:%M")
    created_on.short_description = 'Created'

    def reverse_matched(self, request, queryset):
        # TODO: Check Permission
        with transaction.atomic():
            msg = reverse_transaction_details(queryset.filter(status__in=[TransactionDetail.AWAITING_PAYMENT]).values_list("id", flat=True))
        self.message_user(request, "Successfully %s" %msg, level=messages.SUCCESS)
    reverse_matched.short_description = "Reverse Matched Transaction(s)"

    def confirm_transaction(self, request, queryset):
        # TODO: Check Permission
        org = queryset.count()
        tds = queryset.filter(status__in=[TransactionDetail.AWAITING_CONFIRMATION, TransactionDetail.EXCEPTION])
        done = 0
        for td in tds:
            done += confirm_transaction(td)
        msg = "all selected transactions" if org == done else "%d out of %d transactions" % (done, org)
        self.message_user(request, "Successfully confirmed %s " %msg, level=messages.SUCCESS)
    confirm_transaction.short_description = "Confirm Transaction(s)"

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def cancel_defaulted_transaction_details(self, request, queryset):
        # TODO: Check Permission
        org = queryset.count()
        done = cancel_defaulted_transaction_details(queryset.filter(status__in=[TransactionDetail.EXCEPTION]), request.user)
        self.message_user(request, "Cancelled %d transactions out of %d" % (done, org), level=messages.SUCCESS)
    cancel_defaulted_transaction_details.short_description = "Confirm Transaction(s)"

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(TransactionPointer)
class TransactionPointerAdmin(admin.ModelAdmin):
    list_display = ('member_link', 'balance', 'transaction_link', 'account_link', 'value', 'is_full', 'status', 'created', )
    search_fields = ['amount',  'account__id', 'transaction__id', 'transaction__status', 'transaction__owner__first_name', 'transaction__owner__last_name', 'transaction__owner__phone', 'transaction__owner__user__username', 'created']

    date_hierarchy = 'created'
    list_filter = ('transaction__status', 'is_full')
    list_max_show_all = MAX_SHOW_ALL
    list_per_page = PER_PAGE

    def status(self, obj):
        return obj.transaction.status
    status.short_description = 'Status'
    status.admin_order_field = 'transaction.status'

    def owner(self, obj):
        return obj.transaction.owner
    owner.short_description = 'Owner'
    owner.admin_order_field = 'transaction.owner__first_name'

    def value(self, obj):
        return "%s%s" %(obj.transaction.currency.symbol, decimal_normalise(obj.amount))
    value.short_description = 'Matched'
    value.admin_order_field = 'amount'

    def balance(self, obj):
        return "%s%s" % (obj.transaction.currency.symbol, decimal_normalise(obj.transaction.amount))
    balance.short_description = 'GHing'
    balance.admin_order_field = 'transaction.balance'

    def transaction_link(self, item):
        return item.transaction.get_admin_list_link(item.transaction, item.transaction.id)
    transaction_link.allow_tags = True
    transaction_link.short_description = 'Transaction'
    transaction_link.admin_order_field = 'transaction.id'

    def account_link(self, item):
        return item.account.get_admin_list_link(item.account, item.account.id)
    account_link.allow_tags = True
    account_link.short_description = 'Account'
    account_link.admin_order_field = 'account.id'

    def member_link(self, item):
        return item.transaction.owner.get_admin_list_link(item.transaction.owner, item.transaction.owner.user.username)
    member_link.allow_tags = True
    member_link.short_description = 'Owner'
    member_link.admin_order_field = 'transaction.owner.first_name'

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(TransactionDetailPointer)
class TransactionDetailPointerAdmin(admin.ModelAdmin):
    list_display = ('gh_account', 'transaction', 'queued_amount', 'matched', 'ph_account', 'matched_amount', 'status', 'pop', 'created', )
    search_fields = ['trans_pointer__account__id', 'trans_pointer__transaction__id', 'trans_detail__status', 'trans_detail__id', 'trans_pointer__transaction__owner__first_name', 'trans_pointer__transaction__owner__last_name', 'trans_pointer__transaction__owner__phone', 'trans_pointer__transaction__owner__user__username', 'created']

    date_hierarchy = 'created'
    list_filter = ('trans_detail__status',)
    list_max_show_all = MAX_SHOW_ALL
    list_per_page = PER_PAGE

    def gh_account(self, obj):
        return obj.trans_pointer.account.id
    gh_account.short_description = 'GHing Account'
    gh_account.admin_order_field = 'trans_pointer.account.id'

    def transaction(self, obj):
        return obj.trans_pointer.transaction.id
    transaction.short_description = 'Queue'
    transaction.admin_order_field = 'trans_pointer.transaction.id'

    def queued_amount(self, obj):
        return "%s%s" % (obj.trans_pointer.transaction.currency.symbol, decimal_normalise(obj.trans_pointer.transaction.amount))
    queued_amount.short_description = 'Queued'
    queued_amount.admin_order_field = 'trans_pointer.transaction.amount'

    def ph_account(self, obj):
        return obj.trans_detail.account.id
    ph_account.short_description = 'PHing Account'
    ph_account.admin_order_field = 'trans_detail.account.id'

    def matched(self, obj):
        return obj.trans_detail.id
    matched.short_description = 'Matched'
    matched.admin_order_field = 'trans_detail.id'

    def matched_amount(self, obj):
        return "%s%s" % (obj.trans_detail.currency.symbol, decimal_normalise(obj.trans_detail.amount))
    matched_amount.short_description = 'Paying'
    matched_amount.admin_order_field = 'trans_detail.amount'

    def status(self, obj):
        return obj.trans_detail.status
    status.short_description = 'Pay Status'
    status.admin_order_field = 'trans_detail.status'

    def pop(self, obj):
        # return format_html(u'<img src="{}" />', obj.trans_detail.proof.url)
        uploads = obj.trans_detail.uploads.all()
        if len(uploads) > 0:
            links = ""
            for up in uploads:
                links += format_html(u'<a href="{}" target="_blank" /><i class="glyphicon glyphicon-picture"></i></a>', up.file.url)
            return format_html(links)
        else:
            return format_html(u'<i class="glyphicon glyphicon-ban-circle"></i>')
    pop.short_description = 'POP'
    pop.admin_order_field = 'trans_detail.proof'

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
