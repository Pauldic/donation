from django import forms
from django import forms


class PhoneInput(forms.TextInput):
    input_type = 'tel'


class GenderField(forms.ChoiceField):
    def __init__(self, *args, **kwargs):
        super(GenderField, self).__init__(*args, **kwargs)
        self.error_messages = {"required": "Please select a gender, it's required"}
        self.choices = ((None, 'Select gender'), ('M', 'Male'), ('F', 'Female'))
