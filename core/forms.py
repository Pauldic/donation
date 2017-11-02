import email
import logging

import os
from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone
from django.forms.widgets import Input, TextInput, Select
from django.test import Client
from captcha.fields import CaptchaField

from core.models import Member, Country, State, Bank, Package, TransactionDetail, Account, BankAccount, Currency
from django.conf import settings

# If you don't do this you cannot use Bootstrap CSS
from core.overrides.custom_widget import PhoneInput
from core.utils import get_float_conf


log = logging.getLogger("%s.*" % settings.PROJECT_NAME)


class LoginForm(AuthenticationForm):
    captcha = CaptchaField(label='Are you an human? ', )
    # captcha = CaptchaField(label='Are you an human? ', widget=forms.TextInput(attrs={'class': 'form-control'}))
    username = forms.CharField(label="Member Username", max_length=20,
                               widget=forms.TextInput(attrs={'class': 'form-control _reg', 'name': 'username', 'placeholder': 'Username', 'style': 'margin-bottom_: 15px;'}))
    password = forms.CharField(label="Password", max_length=20,
                               widget=forms.PasswordInput(attrs={'class': 'form-control _reg', 'name': 'password', 'placeholder': 'Password'}))


# class PreMemberForm(forms.ModelForm):
#     # username = forms.CharField(label='Username', max_length=20,
#     #                            widget=forms.TextInput(attrs={'class': 'form-control  form-white', 'name': 'username', 'placeholder': 'Username'}))
#
#     # def __init__(self,*args,**kwargs):
#     #     super(PreMemberForm,self).__init__(*args,**kwargs) # populates the post
#         # now = timezone.now()
#         # self.fields['package'].queryset = Package.objects.filter((Q(end_date__isnull=True) | Q(end_date__gte=now)), status=Package.ACTIVE, start_date__lte=now).order_by('amount')
#
#     class Meta:
#         model = PreMember
#         fields = ('sponsor', 'username', 'first_name', 'email', 'phone', 'password')
#         labels = {
#             "first_name": "Bank Account Name"
#         }
#         widgets = {
#             'sponsor': forms.HiddenInput(),
#             'email': forms.EmailInput(attrs={'class': 'form-control  form-white', 'placeholder': 'Email'}),
#             'password': forms.PasswordInput(attrs={'class': 'form-control  form-white', 'placeholder': 'Password'}),
#             'first_name': forms.TextInput(attrs={'class': 'form-control  form-white', 'placeholder': 'Bank Account Name'}),
#             'username': forms.TextInput(attrs={'class': 'form-control  form-white', 'placeholder': 'Username'}),
#             'phone': forms.TextInput(attrs={'class': 'form-control  form-white', 'placeholder': 'Phone'}),
#             # 'package': forms.Select(attrs={'class': 'form-control  form-white', 'style': 'padding: 0 0 0 10px;'}),
#         }


class MemberPHForm(forms.Form):
    CURRENCIES = [(settings.BITCOIN_CODE, "%s-%s" %("Bitcoin", "B")), ]

    def __init__(self, *args, **kwargs):
        self.me = kwargs.pop('me', None)
        super(MemberPHForm, self).__init__(*args, **kwargs)
        c = self.me.country.currency_set.all()
        if len(c) > 0 and len(self.CURRENCIES) < 2:
            self.CURRENCIES.append((c[0].code, "%s-%s" %(c[0].name, c[0].symbol)))
        self.fields['currency'].choices = self.CURRENCIES

    currency = forms.ChoiceField(choices=CURRENCIES, widget=forms.RadioSelect())
    ph_type = forms.ChoiceField(choices=[(Account.PH, 'Normal PH'), (Account.PH_FEE, 'Fee'), (Account.REFUND, "Refund"), (Account.BONUS, "Bonus")], initial='', widget=forms.Select(), required=True)
    amount = forms.DecimalField(decimal_places=2, max_digits=9)
    usernames = forms.CharField(help_text="Comma separated list of usernames eg: paulina,johnny", widget=forms.widgets.Textarea(attrs={'cols': 80, 'rows': 3}), required=True)
    # prerequisite = forms.ChoiceField(choices=Account.get_recent_user_ph(None), initial=None, widget=forms.Select(), required=False)


class BankAccountForm(forms.ModelForm):
    # def __init__(self,company,*args,**kwargs): #You will need this if you want to pass parameter, say for query filter
    def __init__(self,*args,**kwargs):
        self.me = kwargs.pop('me', None)
        super(BankAccountForm, self).__init__(*args,**kwargs) # populates the post
        self.fields['bank'].queryset = Bank.objects.filter(Q(country=self.me.country) | Q(code='BTC')).order_by('name')

    class Meta:
        model = BankAccount

        fields = ('bank', 'name', 'number', 'branch_name', 'sort_code', 'is_default')
        labels = {
            "bank": "Bank Name",
            "name": "Account Name/Owner",
            "number": "Account Number/BTC Address",
            "Branch Name": "Branch Name",
            "Sort Code": "Sort Code <small>Optional</small>"
        }
        # < input class ="easyui-textbox" name="name" style="width:100%" data-options="label:'Name:',required:true" >

        widgets = {
            'name': forms.TextInput(attrs={'class': 'easyui-textbox-', 'placeholder': '', 'data-options': "label:'Name:',required:true"}),
            'number': forms.TextInput(attrs={'class': 'easyui-textbox-', 'data-options': "label:'Bank Account Name:',required:true"}),
            # 'bank': forms.TextInput(attrs={'class': 'easyui-textbox-', 'data-options': "label:'Account Number:',required:true"}),
        }


class MemberForm(forms.ModelForm):
    def __init__(self,*args,**kwargs):
        super(MemberForm, self).__init__(*args,**kwargs) # populates the post
        # self.fields['country'].queryset = Country.objects.filter(id=52).order_by('name')
        # self.fields['state'].queryset = State.objects.all().order_by('name')
        # self.fields.get('user').required = False
        self.fields['guider'].widget = TextInput(attrs={'class': 'form-control',})
        self.fields['username'].widget = TextInput(attrs={'class': 'form-control',})

    # bank_name = forms.ModelChoiceField(queryset=Bank.objects.all(), required=True)
    # account_number = forms.CharField(max_length=10, required=True)
    username = forms.CharField(max_length=20, required=True, )
    # verification_code = forms.CharField(max_length=6, required=True, )
    guider = forms.CharField(max_length=20, required=False, )
    # show_password = forms.BooleanField(required=False)

    class Meta:
        model = Member
        fields = ('first_name', 'last_name', 'email', 'country', 'phone', 'username', 'password', 'guider')
        # fields = ('email', 'phone', 'verification_code', 'first_name', 'bank_name', 'account_number', 'country', 'state', 'address', 'username', 'password')
        labels = {
            # "first_name": "Bank Account Name",
            "guider": "Sponsor's Username",
        }

        widgets = {
            # 'sponsor': forms.HiddenInput({'required': False}),
            'guider': forms.TextInput({'class': 'form-control', 'required': False, 'placeholder': "Sponsor's username"}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'}),
            'phone': PhoneInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}),
            # 'address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'City'}),
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username'}),
            'password': forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'}),
            'country': forms.Select(attrs={'class': 'form-control'})
        }



    # @staticmethod
    # def clean_user(self, value):
    #     print "Validating.............."
    #     return User()

    #     print "************* 1"
    #     value = self.cleaned_data['user']
    #     print value
    #     # if User.objects.filter(user=value[0]):
    #     #     raise ValidationError(u'The username %s is already taken' % value)
    #     return value

    # def clean_user(self, exclude=['user']):
    #     super(MemberForm, self).clean_user(exclude)

        # if self.field_name and not self.field_name_required:
        #     raise ValidationError({'field_name_required':["You selected a field, so field_name_required is required"]}


class TransactionDetailForm(forms.ModelForm):
    class Meta:
        model = TransactionDetail
        fields = ('id',)
        # fields = ('id', 'proof')
        widgets ={
            'id': forms.HiddenInput(attrs={'required': False, 'readonly': True}),
            # 'proof': forms.FileInput(attrs={'class': "file"})
        }

    # Add some custom validation to our file field
    def clean_proof(self):
        proof_file = self.cleaned_data.get('proof', False)
        if proof_file:
            maxMB = get_float_conf(settings.MAX_EMAIL_ATTACHMENT_SIZE, 1.0)
            if proof_file.size > maxMB * 1024 * 1024:
                print "FILE SIZE NOT ACCEPTED ::::::::::::: %d" % proof_file.size
                log.error("FILE SIZE NOT ACCEPTED ::::::::::::: %d" % proof_file.size)
                raise ValidationError("Image file too large ( > %dkb )", (maxMB * 1024))
            if proof_file.content_type not in ["image/jpg", "image/jpeg", "image/png", "image/gif"]:
                print "FILE TYPE NOT ACCEPTED ::::::::::::: %s" % proof_file.content_type
                log.error("FILE TYPE NOT ACCEPTED ::::::::::::: %s" % proof_file.content_type)
                raise ValidationError("Content-Type is not jpeg/jpg/png/gif")
            if os.path.splitext(proof_file.name)[1].lower() not in [".gif", ".jpg", ".jpeg", ".png"]:
                print "FILE EXTENSION NOT ACCEPTED ::::::::::::: %s" % os.path.splitext(proof_file.name)[1]
                log.error("FILE EXTENSION NOT ACCEPTED ::::::::::::: %s" % os.path.splitext(proof_file.name)[1])
                raise ValidationError("Doesn't have proper extension")

            return proof_file
        else:
            raise ValidationError("Couldn't read uploaded file")
