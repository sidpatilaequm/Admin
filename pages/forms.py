from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Material

class VendorRegistrationForm(forms.Form):
    email = forms.EmailField(required=True)
    password = forms.CharField(widget=forms.PasswordInput)
    first_name = forms.CharField(max_length=100, required=True)
    last_name = forms.CharField(max_length=100, required=True)
    phone_number = forms.CharField(max_length=15, required=True)

class VendorAddressForm(forms.Form):
    address1 = forms.CharField(max_length=255, required=True)
    address2 = forms.CharField(max_length=255, required=False)
    city = forms.CharField(max_length=100, required=True)
    state = forms.CharField(max_length=100, required=True)
    country = forms.CharField(max_length=100, required=True, initial='India')
    pincode = forms.CharField(max_length=10, required=True)

class VendorDocumentForm(forms.Form):
    gst_file = forms.FileField(required=True, widget=forms.FileInput(attrs={'class': 'form-control'}))
    pan_file = forms.FileField(required=True, widget=forms.FileInput(attrs={'class': 'form-control'}))
    cheque_file = forms.FileField(required=True, widget=forms.FileInput(attrs={'class': 'form-control'}))
    coi_file = forms.FileField(required=True, widget=forms.FileInput(attrs={'class': 'form-control'}))

class MaterialForm(forms.ModelForm):
    class Meta:
        model = Material
        fields = [
            'material_code', 'material_name', 'category', 'subcategory',
            'material_type', 'uom', 'hsn_code', 'sku', 'tax_percentage',
            'current_stock', 'price', 'base_unit', 'material_group', 'description',
            'barcode_image', 'vendor_article_number', 'variant_mandatory', 
            'purchasing_code', 'blocked'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'tax_percentage': forms.NumberInput(attrs={'step': '0.01'}),
            'current_stock': forms.NumberInput(attrs={'step': '0.01'}),
            'price': forms.NumberInput(attrs={'step': '0.01'}),
            'barcode_image': forms.FileInput(attrs={'accept': 'image/jpeg,image/png'}),
            'vendor_article_number': forms.TextInput(attrs={'placeholder': 'e.g. DL-14I-INTEL'}),
            'variant_mandatory': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'purchasing_code': forms.TextInput(attrs={'placeholder': 'e.g. PURCH-001'}),
            'blocked': forms.CheckboxInput(attrs={'class': 'form-check-input'})
        } 