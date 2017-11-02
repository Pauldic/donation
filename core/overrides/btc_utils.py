from decimal import Decimal

from django.conf import settings
from django.core import validators
from django.db import models
from django.http import HttpResponse
from django.utils.module_loading import import_string

from blockchain import receive as bc_receive

HASH_LEN = 64
MIN_ADDR_LEN = 26
MAX_ADDR_LEN = 36


def check_tx_hash(tx_hash):
    """Does the input look like a hash?"""

    if not tx_hash.isalnum():
        raise validators.ValidationError('tx_hash must be alphanumeric')

    if len(tx_hash) != HASH_LEN:
        raise validators.ValidationError('tx_hash length not {}'.format(HASH_LEN))


def check_addr(dest_addr):
    """Does the input look like a bitcoin address?"""

    if not dest_addr.isalnum():
        raise validators.ValidationError('dest_addr must be alphanumeric')

    if not MIN_ADDR_LEN <= len(dest_addr) <= MAX_ADDR_LEN:
        raise validators.ValidationError('dest_addr length between {} and {}'.format(MIN_ADDR_LEN, MAX_ADDR_LEN))


def check_cb_url(cb_url):
    """Is our callback url a url?"""

    validator = validators.URLValidator()
    validator(cb_url)

def receive_notification(request):
    """Imports your ReceiveNotification class and uses it"""

    if settings.BLOCKCHAIN_RECEIVE_CONFIRMATION_LIMIT is None:
        raise ValueError('Need settings.BLOCKCHAIN_RECEIVE_CONFIRMATION_LIMIT')

    cls = import_string(settings.BLOCKCHAIN_RECEIVE_NOTIFICATION_MODEL)

    notification = cls.parse_notification(request.GET.copy())

    # Unhandled exceptions should be mailed to admins
    notification.full_clean()

    # One last thing, check this is not spam!
    rec_exists = models.ReceiveResponse.objects.filter(
        destination_address=notification.destination_address,
        input_address=notification.input_address,
    ).exists()

    if rec_exists:
        notification.save()
    else:
        return HttpResponse('Spam ignored', content_type='text/plain')

    if notification.confirmations >= settings.BLOCKCHAIN_RECEIVE_CONFIRMATION_LIMIT:
        return HttpResponse('*ok*', content_type='text/plain')

    return HttpResponse('More confirmations required', content_type='text/plain')


class ReceiveResponse(models.Model):
    """Store ReceiveResponse objects
    """

    fee_percent = models.IntegerField()
    destination_address = models.CharField(max_length=35)
    input_address = models.CharField(max_length=35)
    callback_url = models.URLField()

    def __unicode__(self):
        return u'{} -> {}'.format(self.input_address, self.destination_address)

    @staticmethod
    def receive(dest_addr=settings.BLOCKCHAIN_DESTINATION_ADDRESS, cb_url=settings.BLOCKCHAIN_RECEIVE_API_ENDPOINT, api_code=None):
        """Wrap the receive function here instead of the manager or wherever
        XXX: This method should be allowed to fail cleanly!
        """

        check_addr(dest_addr)
        check_cb_url(cb_url)

        res = bc_receive.receive(dest_addr, cb_url, api_code=api_code)

        new = ReceiveResponse()
        for field in ReceiveResponse._meta.get_all_field_names():
            if field == 'id':
                continue

            setattr(new, field, getattr(res, field))

        new.save()

        return new


class ReceiveNotificationBase(models.Model):
    """Once any BTC is received, store the notification
    """

    date_received = models.DateTimeField(auto_now_add=True)

    value = models.PositiveIntegerField(help_text='In satoshi')
    input_address = models.CharField(max_length=35)
    confirmations = models.PositiveIntegerField()
    transaction_hash = models.CharField(max_length=64)
    input_transaction_hash = models.CharField(max_length=64)
    destination_address = models.CharField(max_length=35)

    class Meta:
        """Make this abstract so you can handle custom parameters how you want
        Returns unsaved class; override this method to further deal with data
        """

        abstract = True

    @property
    def value_btc(self):
        """Satoshi -> BTC
        """

        if self.value is None:
            raise AttributeError('Need a value to divide')

        return Decimal(self.value) / 100000000

    @classmethod
    def parse_notification(cls, data):
        """Override this class to set data
        """

        fields = ReceiveNotificationBase._meta.get_all_field_names()

        new = cls()
        for field in fields:
            if field == 'date_received':
                continue

            setattr(new, field, data[field])

        return new

    def clean(self):
        """XXX: These should be fields' validators!
        """

        check_tx_hash(self.transaction_hash)
        check_tx_hash(self.input_transaction_hash)
        check_addr(self.input_address)
        check_addr(self.destination_address)