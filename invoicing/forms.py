# file_upload_app/forms.py
from django import forms
from .models import UploadedFile, MergedData


class UploadFileForm(forms.ModelForm):
    class Meta:
        model = UploadedFile
        fields = ['file']
        widgets = {
            'file': forms.ClearableFileInput(attrs={'class': 'file-input hidden'})
        }


class DynamicFilterForm(forms.Form):
    material = forms.ChoiceField(choices=[], required=False)
    upload_date = forms.ChoiceField(choices=[], required=False)
    supplier = forms.ChoiceField(choices=[], required=False)
    mm_doc_number = forms.ChoiceField(choices=[], required=False)
    reference = forms.ChoiceField(choices=[], required=False)
    root_cause = forms.ChoiceField(choices=[], required=False)

    def __init__(self, *args, **kwargs):
        super(DynamicFilterForm, self).__init__(*args, **kwargs)
        self.fields['material'].label = 'Material'
        self.fields['upload_date'].label = 'Upload date'
        self.fields['supplier'].label = 'Supplier'
        self.fields['mm_doc_number'].label = 'MM Doc.'
        self.fields['reference'].label = 'Reference'
        self.fields['root_cause'].label = 'Root Cause'

        self.fields['material'].choices = self.get_choices('material')
        self.fields['upload_date'].choices = self.get_choices('upload_date')
        self.fields['supplier'].choices = self.get_choices('supplier')
        self.fields['mm_doc_number'].choices = self.get_choices('mm_doc_number')
        self.fields['reference'].choices = self.get_choices('reference')
        self.fields['root_cause'].choices = self.get_choices('root_cause')

    def get_choices(self, field_name):
        examples = MergedData.objects.values_list(field_name, flat=True).distinct()
        choices = [('', '-----')]
        for example in examples:
            choices.append((example, example))
        return choices
