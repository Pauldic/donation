from __future__ import unicode_literals

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

User = get_user_model()

class AvoidPreviousPasswords(object):

   def __init__(self, username, password):
       self.username = username
       self.password = password

   def validate(self, username, password):
       user = User.objects.get(username=username)
       if self.word_1 in password or self.word_2 in password:
           raise ValidationError(
               _("You cannot include '%s' or '%s' in your password." % (self.word_1, self.word_2)),
               code='Invalid password',
           )

   def get_help_text(self):
       return _("You cannot include '%s' or '%s' in your password." % (self.word_1, self.word_2))