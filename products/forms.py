from django import forms
from django.forms import inlineformset_factory
from .models import Product, ProductImage, Category, Brand, Tag


class ProductForm(forms.ModelForm):
    tags = forms.ModelMultipleChoiceField(queryset=Tag.objects.all(), required=False,
                                          widget=forms.CheckboxSelectMultiple)
    class Meta:
        model  = Product
        fields = ['name','category','brand','tags','price','compare_price','cost_price',
                  'short_description','description','specifications','stock',
                  'track_inventory','low_stock_threshold','is_active','is_featured',
                  'is_new','condition','weight','dimensions','meta_title','meta_description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 6}),
            'short_description': forms.Textarea(attrs={'rows': 3}),
            'specifications': forms.Textarea(attrs={'rows': 4, 'placeholder': '{"Color":"Red","Size":"XL"}'}),
        }


class ProductImageForm(forms.ModelForm):
    class Meta:
        model  = ProductImage
        fields = ['image', 'alt_text', 'is_primary', 'order']


ProductImageFormSet = inlineformset_factory(Product, ProductImage, form=ProductImageForm, extra=3, can_delete=True)
