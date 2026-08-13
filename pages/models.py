from django.db import models
from django.core.validators import FileExtensionValidator

class VendorDocument(models.Model):
    java_user_id = models.IntegerField()  # Reference to Java backend user ID
    document_type = models.CharField(max_length=50, choices=[
        ('gst_certificate', 'GST Certificate'),
        ('pan_card', 'PAN Card'),
        ('bank_statement', 'Bank Statement'),
        ('other', 'Other')
    ])
    document_file = models.FileField(
        upload_to='vendor_documents/',
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'jpg', 'jpeg', 'png'])]
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)
    verification_notes = models.TextField(blank=True)

    def __str__(self):
        return f"Document {self.document_type} for user {self.java_user_id}"

class Material(models.Model):
    MATERIAL_TYPE_CHOICES = [
        ('ROH', 'Raw Material'),
        ('FERT', 'Finished Product'),
        ('HALB', 'Semi-Finished Product'),
        ('HAWA', 'Trading Goods'),
        ('VERP', 'Packaging Material'),
        ('DIEN', 'Service Material'),
        ('NLAG', 'Non-Stock Material'),
        ('ERSA', 'Spare Part'),
        ('LEER', 'Empties'),
        ('PIPE', 'Pipeline Material'),
        ('PROD', 'By-Product?'),
    ]
    material_id = models.AutoField(primary_key=True)
    material_code = models.CharField(max_length=20, unique=True)
    material_name = models.CharField(max_length=100)
    category = models.CharField(max_length=100, blank=True, null=True)
    subcategory = models.CharField(max_length=100, blank=True, null=True)
    material_type = models.CharField(max_length=10, choices=MATERIAL_TYPE_CHOICES, blank=True, null=True)
    uom = models.CharField(max_length=20, verbose_name="Unit of Measurement", blank=True, null=True)
    hsn_code = models.CharField(max_length=20, verbose_name="HSN Code", blank=True, null=True)
    sku = models.CharField(max_length=50, verbose_name="SKU", blank=True, null=True)
    tax_percentage = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="GST %", blank=True, null=True)
    current_stock = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    base_unit = models.CharField(max_length=20, blank=True, null=True)
    material_group = models.CharField(max_length=50, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    barcode_image = models.ImageField(upload_to='barcodes/', verbose_name="Barcode Image", blank=True, null=True)
    vendor_article_number = models.CharField(max_length=50, verbose_name="Vendor Article Number", blank=True, null=True)
    variant_mandatory = models.BooleanField(default=False, verbose_name="Variant Mandatory")
    purchasing_code = models.CharField(max_length=50, verbose_name="Purchasing Code", blank=True, null=True)
    blocked = models.BooleanField(default=False, verbose_name="Blocked")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.material_code} - {self.material_name}"

    class Meta:
        db_table = 'materials'
        ordering = ['-created_at']

# New models for the variant system
class Attribute(models.Model):
    """Attribute model for defining variant attributes like Color, Size, etc."""
    ATTRIBUTE_TYPE_CHOICES = [
        ('VARIANT', 'Variant Attribute'),
        ('GENERAL', 'General Attribute'),
    ]
    
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True)
    type = models.CharField(max_length=10, choices=ATTRIBUTE_TYPE_CHOICES, default='VARIANT')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.type})"

    class Meta:
        db_table = 'attributes'
        ordering = ['name']

class MaterialVariant(models.Model):
    """Child variants of a parent material"""
    id = models.AutoField(primary_key=True)
    variant_code = models.CharField(max_length=50, unique=True, verbose_name="Variant Code")
    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name='variants')
    barcode = models.CharField(max_length=100, blank=True, null=True)
    mrp = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="MRP")
    sp = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Selling Price")
    cost = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Cost Price")
    current_stock = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    vendor_details = models.TextField(blank=True, null=True)
    customer_details = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.variant_code} - {self.material.material_name}"

    class Meta:
        db_table = 'material_variants'
        ordering = ['variant_code']

class MaterialVariantAttributeValue(models.Model):
    """Value of a specific attribute for a specific variant"""
    id = models.AutoField(primary_key=True)
    variant = models.ForeignKey(MaterialVariant, on_delete=models.CASCADE, related_name='attribute_values')
    attribute = models.ForeignKey(Attribute, on_delete=models.CASCADE)
    value = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.variant.variant_code} - {self.attribute.name}: {self.value}"

    class Meta:
        db_table = 'material_variant_attribute_values'
        unique_together = ['variant', 'attribute']
        ordering = ['attribute__name']

# Channel Management Models
class Channel(models.Model):
    """Channels like Amazon, Flipkart, Myntra, etc."""
    id = models.AutoField(primary_key=True)
    channel_code = models.CharField(max_length=20, unique=True, verbose_name='Channel Code')
    channel_name = models.CharField(max_length=100, verbose_name='Channel Name')
    logo = models.ImageField(upload_to='channel_logos/', blank=True, null=True, verbose_name='Channel Logo')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.channel_code} - {self.channel_name}"

    class Meta:
        db_table = 'channels'
        ordering = ['channel_name']

class ReportingCategory(models.Model):
    """Reporting categories for analytics and reporting"""
    id = models.AutoField(primary_key=True)
    category_code = models.CharField(max_length=20, unique=True, verbose_name='Category Code')
    category_name = models.CharField(max_length=100, verbose_name='Category Name')
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.category_code} - {self.category_name}"

    class Meta:
        db_table = 'reporting_categories'
        ordering = ['category_name']

class ChannelCategory(models.Model):
    """Categories specific to each channel (e.g., Amazon Electronics, Flipkart Fashion)"""
    id = models.AutoField(primary_key=True)
    category_code = models.CharField(max_length=20, verbose_name='Category Code')
    category_name = models.CharField(max_length=100, verbose_name='Category Name')
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name='categories')
    parent_category = models.ForeignKey('self', on_delete=models.CASCADE, related_name='subcategories', blank=True, null=True)

    def __str__(self):
        return f"{self.channel.channel_name} - {self.category_name}"

    class Meta:
        db_table = 'channel_categories'
        ordering = ['channel__channel_name', 'category_name']
        unique_together = ['channel', 'category_code']

class MaterialChannelAssignment(models.Model):
    """Assignment of materials to channels with channel-specific pricing and category"""
    id = models.AutoField(primary_key=True)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Selling Price')
    mrp = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name='MRP')
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name='Cost Price')
    channel_sku = models.CharField(max_length=50, blank=True, null=True, verbose_name='Channel SKU')
    channel_product_id = models.CharField(max_length=100, blank=True, null=True, verbose_name='Channel Product ID')
    is_active = models.BooleanField(default=True)
    commission_percentage = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True, verbose_name='Commission %')
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name='Shipping Cost')
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name='material_assignments')
    channel_category = models.ForeignKey(ChannelCategory, on_delete=models.CASCADE, related_name='material_assignments')
    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name='channel_assignments')
    reporting_category = models.ForeignKey(ReportingCategory, on_delete=models.CASCADE, related_name='material_assignments')

    def __str__(self):
        return f"{self.material.material_name} - {self.channel.channel_name}"

    class Meta:
        db_table = 'material_channel_assignments'
        ordering = ['material__material_name', 'channel__channel_name']
        unique_together = ['material', 'channel']

# Location Management Models
class Location(models.Model):
    """Location model for managing warehouse and storage locations"""
    id = models.AutoField(primary_key=True)
    location_name = models.CharField(max_length=255, verbose_name='Location Name')
    pin_code = models.CharField(max_length=20, verbose_name='PIN Code')
    address = models.TextField(verbose_name='Address')
    city = models.CharField(max_length=100, verbose_name='City', blank=True, null=True)
    state = models.CharField(max_length=100, verbose_name='State', blank=True, null=True)
    country = models.CharField(max_length=100, verbose_name='Country', blank=True, null=True)
    is_active = models.BooleanField(default=True, verbose_name='Is Active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.location_name} - {self.city}, {self.state}"

    class Meta:
        db_table = 'locations'
        ordering = ['location_name']
        unique_together = ['location_name']


class VendorRegistration(models.Model):
    STATUS_CHOICES = [
        ('INVITED', 'INVITED'),
        ('REGISTRATION_SUBMITTED', 'REGISTRATION_SUBMITTED'),
        ('REGISTRATION_APPROVED', 'REGISTRATION_APPROVED'),
        ('DOCUMENTS_SUBMITTED', 'DOCUMENTS_SUBMITTED'),
        ('UNDER_VERIFICATION', 'UNDER_VERIFICATION'),
        ('ACTIVE', 'ACTIVE'),
        ('REJECTED', 'REJECTED'),
        ('CORRECTION_REQUIRED', 'CORRECTION_REQUIRED'),
    ]
    vendor_name = models.CharField(max_length=255)
    address = models.TextField()
    contact_name = models.CharField(max_length=255)
    designation = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=50)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='REGISTRATION_SUBMITTED')
    created_date = models.DateTimeField(auto_now_add=True)
    approved_by = models.CharField(max_length=255, blank=True, null=True)
    approved_date = models.DateTimeField(blank=True, null=True)
    invitation = models.ForeignKey('SupplierInvitation', on_delete=models.SET_NULL, blank=True, null=True)
    user_id = models.IntegerField(blank=True, null=True)
    
    # Generated during approval (Step 3)
    vendor_code = models.CharField(max_length=50, blank=True, null=True, unique=True)
    onboarding_token = models.CharField(max_length=255, blank=True, null=True, unique=True)
    
    # KYC details (Step 5)
    gst_number = models.CharField(max_length=50, blank=True, null=True)
    pan_number = models.CharField(max_length=50, blank=True, null=True)
    msme_number = models.CharField(max_length=50, blank=True, null=True)
    cin_number = models.CharField(max_length=50, blank=True, null=True)
    
    # Bank Details (Step 5)
    account_number = models.CharField(max_length=100, blank=True, null=True)
    ifsc_code = models.CharField(max_length=50, blank=True, null=True)
    bank_name = models.CharField(max_length=255, blank=True, null=True)
    
    # Uploaded documents paths (Step 5)
    gst_certificate = models.FileField(upload_to='vendor_documents/gst/', blank=True, null=True)
    pan_card = models.FileField(upload_to='vendor_documents/pan/', blank=True, null=True)
    msme_certificate = models.FileField(upload_to='vendor_documents/msme/', blank=True, null=True)
    cancelled_cheque = models.FileField(upload_to='vendor_documents/cheque/', blank=True, null=True)
    coi_certificate = models.FileField(upload_to='vendor_documents/coi/', blank=True, null=True)

    @property
    def gst_doc_path(self):
        return self.gst_certificate.name if self.gst_certificate else None

    @property
    def pan_doc_path(self):
        return self.pan_card.name if self.pan_card else None

    @property
    def cheque_doc_path(self):
        return self.cancelled_cheque.name if self.cancelled_cheque else None

    @property
    def msme_doc_path(self):
        return self.msme_certificate.name if self.msme_certificate else None

    @property
    def coi_doc_path(self):
        return self.coi_certificate.name if self.coi_certificate else None
    
    # For login once onboarding is complete or approved
    password = models.CharField(max_length=255, blank=True, null=True)
    
    # Verification details (Step 6)
    verification_notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'vendor_registration'


class SupplierInvitation(models.Model):
    STATUS_CHOICES = [
        ('INVITED', 'INVITED'),
        ('USED', 'USED'),
        ('EXPIRED', 'EXPIRED'),
    ]
    admin_id = models.IntegerField()
    supplier_email = models.EmailField(unique=True)
    token = models.CharField(max_length=500, unique=True)
    expiry_date = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='INVITED')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'supplier_invitation'


class Department(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    projects_count = models.IntegerField(default=0)
    activities_count = models.IntegerField(default=0)
    approved_budget = models.DecimalField(max_digits=15, decimal_places=2, default=0.0)

    class Meta:
        db_table = 'master_department'

    def __str__(self):
        return f"{self.code} - {self.name}"

class BudgetAllocation(models.Model):
    department = models.ForeignKey(Department, on_delete=models.CASCADE)
    fiscal_year = models.CharField(max_length=20)
    project_code = models.CharField(max_length=100)
    project_name = models.CharField(max_length=255, null=True, blank=True)
    activity_name = models.CharField(max_length=255, null=True, blank=True)
    wbs = models.CharField(max_length=50, null=True, blank=True)
    cost_center = models.CharField(max_length=15, null=True, blank=True)
    
    apr = models.DecimalField(max_digits=15, decimal_places=2, default=0.0)
    may = models.DecimalField(max_digits=15, decimal_places=2, default=0.0)
    jun = models.DecimalField(max_digits=15, decimal_places=2, default=0.0)
    jul = models.DecimalField(max_digits=15, decimal_places=2, default=0.0)
    aug = models.DecimalField(max_digits=15, decimal_places=2, default=0.0)
    sep = models.DecimalField(max_digits=15, decimal_places=2, default=0.0)
    oct = models.DecimalField(max_digits=15, decimal_places=2, default=0.0)
    nov = models.DecimalField(max_digits=15, decimal_places=2, default=0.0)
    dec = models.DecimalField(max_digits=15, decimal_places=2, default=0.0)
    jan = models.DecimalField(max_digits=15, decimal_places=2, default=0.0)
    feb = models.DecimalField(max_digits=15, decimal_places=2, default=0.0)
    mar = models.DecimalField(max_digits=15, decimal_places=2, default=0.0)

    class Meta:
        db_table = 'budget_allocation'

    def __str__(self):
        return f"{self.project_code} - {self.cost_center}"
