from django.db.models.signals import post_save
from notifications.signals import notify
from django.utils.translation import ugettext_lazy as _

from core.models import Reason, TransactionDetail


def blocked_reason_handler(sender, instance, created, **kwargs):
    notify.send(instance, verb='was saved')


post_save.connect(blocked_reason_handler, sender=Reason)

logged_smsg = _('Someone recently logged into your account from an unrecognised device')


def transaction_matched_handler(sender, instance, created, **kwargs):
    notify.send(instance, recipient=instance.transaction.owner.user, verb='Your GH order has been matched')
    notify.send(instance, recipient=instance.sender.user, verb='Your PH order has been matched')

post_save.connect(transaction_matched_handler, sender=TransactionDetail)