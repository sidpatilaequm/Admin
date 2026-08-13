from django.contrib import admin
from .models import (
    VendorDocument, Material, Attribute, MaterialVariant, MaterialVariantAttributeValue,
    Channel, ChannelCategory, ReportingCategory, MaterialChannelAssignment
)

# Register your models here.

@admin.register(VendorDocument)
class VendorDocumentAdmin(admin.ModelAdmin):
    list_display = ['java_user_id', 'document_type', 'uploaded_at', 'is_verified']
    list_filter = ['document_type', 'is_verified', 'uploaded_at']
    search_fields = ['java_user_id', 'document_type']

@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ['material_code', 'material_name', 'category', 'material_type', 'current_stock', 'price']
    list_filter = ['material_type', 'category', 'created_at']
    search_fields = ['material_code', 'material_name', 'sku']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(Attribute)
class AttributeAdmin(admin.ModelAdmin):
    list_display = ['name', 'type', 'is_active']
    list_filter = ['type', 'is_active']
    search_fields = ['name']

@admin.register(MaterialVariant)
class MaterialVariantAdmin(admin.ModelAdmin):
    list_display = ['variant_code', 'material', 'mrp', 'sp', 'cost', 'current_stock', 'is_active']
    list_filter = ['is_active', 'created_at']
    search_fields = ['variant_code', 'material__material_name']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(MaterialVariantAttributeValue)
class MaterialVariantAttributeValueAdmin(admin.ModelAdmin):
    list_display = ['variant', 'attribute', 'value']
    list_filter = ['attribute']
    search_fields = ['variant__variant_code', 'attribute__name', 'value']

# Channel Management Admin
@admin.register(Channel)
class ChannelAdmin(admin.ModelAdmin):
    list_display = ['channel_code', 'channel_name', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['channel_code', 'channel_name']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['channel_name']

@admin.register(ReportingCategory)
class ReportingCategoryAdmin(admin.ModelAdmin):
    list_display = ['category_code', 'category_name', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['category_code', 'category_name']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['category_name']

@admin.register(ChannelCategory)
class ChannelCategoryAdmin(admin.ModelAdmin):
    list_display = ['category_code', 'category_name', 'channel', 'parent_category', 'is_active']
    list_filter = ['channel', 'is_active', 'created_at']
    search_fields = ['category_code', 'category_name', 'channel__channel_name']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['channel__channel_name', 'category_name']
    autocomplete_fields = ['channel', 'parent_category']

@admin.register(MaterialChannelAssignment)
class MaterialChannelAssignmentAdmin(admin.ModelAdmin):
    list_display = [
        'material', 'channel', 'channel_category', 'selling_price', 
        'mrp', 'channel_sku', 'is_active'
    ]
    list_filter = [
        'channel', 'channel_category', 'reporting_category', 
        'is_active', 'created_at'
    ]
    search_fields = [
        'material__material_name', 'material__material_code',
        'channel__channel_name', 'channel_sku', 'channel_product_id'
    ]
    readonly_fields = ['created_at', 'updated_at']
    autocomplete_fields = ['material', 'channel', 'channel_category', 'reporting_category']
    fieldsets = (
        ('Basic Information', {
            'fields': ('material', 'channel', 'channel_category', 'reporting_category')
        }),
        ('Pricing', {
            'fields': ('selling_price', 'mrp', 'cost_price', 'commission_percentage', 'shipping_cost')
        }),
        ('Channel Details', {
            'fields': ('channel_sku', 'channel_product_id', 'is_active')
        }),
        ('Additional Information', {
            'fields': ('notes', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
