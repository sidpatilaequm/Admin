from django.urls import path
from pages.views import image_describe_proxy, bom_aerospace_json_proxy, bom_image_json_proxy, fastapi_proxy
from pages.views import users_list_proxy, user_create_proxy, user_update_proxy
from django.views.generic import TemplateView
from pages.views import (
    login_view,
    register_view,
    vendor_documents,
    vendor_dashboard,
    logout_view,
    PagesView,
    upload_documents_proxy,
    verification_proxy,
    verification_submit_proxy,
    send_email_proxy,
    store_company_id,
    confirm_documents,
    download_report,
    vendors,
    vendor_permissions,
    customers,
    extract_documents,
    customer_documents,
    coming_soon,
    vendor_portal_preview,
    budget_upload,
    department_budget_status,
    purchase_requisitions,
    purchase_requisition_detail,
    upload_pr_excel,
    reset_pr_data,
    download_pr_template,
    upload_po_excel,
    reset_po_data,
    download_po_template,
    upload_subcon_po_excel,
    reset_subcon_po_data,
    download_subcon_po_template,
    upload_service_po_excel,
    reset_service_po_data,
    download_service_po_template,
    quotations,
    new_quotation,
    quotation_detail,
    submit_quotation,
    asn,
    purchase_order_detail,
    service_purchase_order_detail,
    subcontracting_purchase_order_detail,
    purchase_orders,
    subcontracting_purchase_orders,
    scheduling_agreements,
    service_purchase_orders,
    credit_payments,
    create_asn,
    complete_registration,
    registration_complete,
    upload_payment_excel,
    reset_payment_data,
    download_payment_template,
    vendor_payments_view,
    financial_terms_save,
    financial_terms_get,
    financial_terms_customer_save,
    financial_terms_customer_get,
    financial_terms_customer_update,
    material_list,
    material_bom_page,
    material_create,
    material_edit,
    material_delete,
    financial_terms_update,
    material_types_proxy,
    base_units_proxy,
    item_categories_proxy,
    item_subcategories_save_proxy,
    item_subcategories_with_category_details_proxy, 
    materials_list_proxy,
    materials_save_proxy,
    materials_bulk_save_with_images_proxy,
    vendor_register_request,
    admin_vendor_registration_dashboard,
    admin_approve_vendor,
    vendor_onboarding_token,
    vendor_kyc_upload,
    admin_verify_kyc_detail,
    admin_create_invitation,
    admin_list_invitations,
    api_vendor_onboarding_requests_proxy,
    api_vendor_onboarding_generate_link_proxy,
    vendor_prospects,
    materials_image_sequence_proxy,
    attributes_bulk_proxy,
    attributes_list_proxy,
    attributes_by_type_proxy,
    material_detail_proxy,
    material_attributes_proxy,
    material_bom_excel_save_proxy,
    material_bom_excel_get_proxy,
    variant_matrix,
    generate_variants,
    variant_list,
    variant_detail,
    delete_variant,
    bulk_update_variants,
    material_variant_create_proxy,
    material_variant_bulk_create_proxy,
    material_variants_list_proxy,
    material_variant_detail_proxy,
    material_variant_active_status_proxy,
    material_variant_barcode_image_proxy,
    material_variant_image_proxy,
    material_delete_proxy,
    variant_delete_proxy,
    attribute_delete_proxy,
    # Channel Management Views
    channels_list,
    channel_detail,
    channel_create,
    channel_update,
    channel_delete,
    channel_categories_list,
    channel_category_create,
    channel_category_update,
    channel_category_delete,

    material_channel_assignments_list,
    material_channel_assignment_create,
    material_channel_assignment_save,
    material_channel_assignment_update,
    material_channel_assignment_delete,
    get_channel_categories,
    channels_list_proxy,
    channel_detail_proxy,
    material_mappings_get_proxy,
    material_mappings_save_proxy,
    material_mapping_delete_proxy,
    channel_category_delete_proxy,
    catalog_view,
    product_detail_view,
    public_product_detail_view,
    public_product_detail_auto_view,
    public_materials_api_proxy,
    public_materials_api_proxy_flexible,
    catalog_pdf_generate_proxy,
    cover_photo_upload_proxy,
    cover_photos_list_proxy,
    channel_categories_proxy,
    public_orders_checkout_proxy,
    flipbook_hotspots_save_proxy,
    flipbook_hotspots_get_proxy,
    flipbook_pdf_upload_proxy,
    flipbook_pdf_save_proxy,
    flipbook_pdf_load_proxy,
    flipbook_pdf_delete_proxy,
    flipbook_pdf_download_proxy,
    flipbook_pdf_download_with_hotspots_proxy,
    user_deactivate_proxy,
    # Cart API Views
    cart_add_item_proxy,
    cart_items_proxy,
    cart_update_quantity_proxy,
    cart_remove_item_proxy,
    cart_clear_proxy,
    cart_summary_proxy,
    pdf_upload_view,
    # Location Management Views
    locations_list,
    locations_save_proxy,
    locations_list_proxy,
    location_detail_proxy,
    location_delete_proxy,
    location_soft_delete_proxy,
    get_auth_token,
    test_java_connection,
    materials_bulk_upload,
    materials_bulk_payload_proxy,
    materials_template_download,
    vendor_catalogue_check_proxy,
    vendor_catalogue_upload_proxy,
    vendor_catalogue_download_proxy,
    vendor_catalogue_replace_proxy,
    # Inventory Management Views
    inventory_list,
    inventory_list_proxy,
    inventory_update_stock_proxy,
    inventory_bulk_update_stock_proxy,
    inventory_bulk_upload,
    inventory_template_download,
    
    # Procurement PR Views
    purchase_requisitions_proxy,
    purchase_requisition_detail_proxy,
    purchase_requisition_status_proxy,
    vendors_list_proxy,
    vendor_purchase_requisitions_proxy,
    vendor_purchase_requisition_detail_proxy,
    vendor_pr_respond_proxy,
    master_bom_upload_proxy,
    master_bom_fetch_proxy,
    master_bom_files_list_proxy,
    bom_aerospace_json_proxy,
    bom_image_json_proxy,
    # Organization Module Views
    countries_list,
    currencies_list,
    companies_list,
    organization_api_proxy,
    channels_list_org,
    departments_list,
    # Category Management Views
    categories_list,
    categories_proxy,
    subcategories_proxy,
    subcategories_bulk_proxy,
    subcategories_tree_proxy,
    # New Organization Proxy Views
    org_item_categories_proxy,
    org_item_subcategories_proxy,
    org_channel_categories_proxy,
    org_category_mappings_proxy,
    org_material_listings_proxy,
    get_vendor_permissions_proxy,
    save_vendor_permissions_proxy,
    get_my_permissions_proxy,
    workflows,
    workflow_dashboard,
    workflow_requests,
    workflow_groups,
    workflow_analytics,
    workflow_settings,
    workflow_email_action,
    create_po_from_quotation,
    verify_quotation_for_po,
    award_quotation,
    get_awarded_quotations,
    create_po_from_awarded_quotation,
    cancel_purchase_order_proxy,
    indents,
)
from pages.api_views import pdf_extract_start, pdf_extract_status, pdf_extract_images, pdf_extract_cleanup

app_name = 'pages'

# Create view instances
invoice_view = PagesView.as_view(template_name="pages/invoices-management/invoice.html")
invoice_add_view = PagesView.as_view(template_name="pages/invoices-management/invoice-add.html")
product_list_view = PagesView.as_view(template_name="pages/invoices-management/products/product-list.html")
product_add_view = PagesView.as_view(template_name="pages/invoices-management/products/product-add.html")
# payments_view = PagesView.as_view(template_name="pages/invoices-management/payments.html")
report_payment_summary_view = PagesView.as_view(template_name="pages/invoices-management/report/payment-summary.html")
report_sale_view = PagesView.as_view(template_name="pages/invoices-management/report/sale-report.html")
report_expenses_view = PagesView.as_view(template_name="pages/invoices-management/report/expenses-report.html")
transaction_list_view = PagesView.as_view(template_name="pages/invoices-management/transaction/transaction-list.html")
transaction_new_view = PagesView.as_view(template_name="pages/invoices-management/transaction/transaction-new.html")
taxes_view = PagesView.as_view(template_name="pages/invoices-management/taxes.html")
users_view = PagesView.as_view(template_name="pages/invoices-management/users.html")

# Procurement Views
pr_list_view = PagesView.as_view(template_name="pages/procurement/pr_list.html")
pr_create_view = PagesView.as_view(template_name="pages/procurement/pr_create.html")
quotation_create_view = PagesView.as_view(template_name="pages/procurement/quotation_create.html")

urlpatterns = [
    # Specific API Proxies (Prioritized)
    path('api/organization/item-categories/', org_item_categories_proxy, name='org_item_categories_proxy'),
    path('api/organization/item-subcategories/', org_item_subcategories_proxy, name='org_item_subcategories_proxy'),
    path('api/organization/channel-categories/<int:channel_id>/', org_channel_categories_proxy, name='org_channel_categories_proxy'),
    path('api/organization/category-mappings/', org_category_mappings_proxy, name='org_category_mappings_proxy'),
    path('api/organization/material-listings/', org_material_listings_proxy, name='org_material_listings_proxy'),
    
    path('api/channels/', channels_list_proxy, name='channels_list_proxy'),
    path('api/channels/create/', channels_list_proxy, name='channels_create_proxy_slashed'),
    path('api/channels/create', channels_list_proxy, name='channels_create_proxy'),
    path('api/channels/<int:channel_id>/', channel_detail_proxy, name='channel_detail_proxy_slashed'),
    path('api/channels/<int:channel_id>', channel_detail_proxy, name='channel_detail_proxy'),
    
    path('api/categories/', categories_proxy, name='categories_proxy_slashed'),
    path('api/categories', categories_proxy, name='categories_proxy'),
    path('api/categories/<int:pk>/', categories_proxy, name='category_detail_proxy_slashed'),
    path('api/categories/<int:pk>', categories_proxy, name='category_detail_proxy'),
    
    path('api/subcategories/', subcategories_proxy, name='subcategories_proxy_slashed'),
    path('api/subcategories', subcategories_proxy, name='subcategories_proxy'),
    path('api/subcategories/bulk/', subcategories_bulk_proxy, name='subcategories_bulk_proxy_slashed'),
    path('api/subcategories/bulk', subcategories_bulk_proxy, name='subcategories_bulk_proxy'),
    path('api/subcategories/tree/<int:category_id>', subcategories_tree_proxy, name='subcategories_tree_proxy'),

    # Vendor Permission APIs
    path('api/vendor-permissions/save', save_vendor_permissions_proxy, name='save_vendor_permissions_proxy'),
    path('api/vendor-permissions/<int:company_id>/', get_vendor_permissions_proxy, name='get_vendor_permissions_proxy'),
    path('api/vendor-permissions/my-permissions/', get_my_permissions_proxy, name='get_my_permissions_proxy'),

    # Authentication
    path('login/', login_view, name='login'),
    path('register/', register_view, name='register'),
    path('logout/', logout_view, name='logout'),
    
    # Vendor Onboarding Workflow
    path('vendor/register-request/', vendor_register_request, name='vendor_register_request'),
    path('admin/vendor-registration/', admin_vendor_registration_dashboard, name='vendor_registration'),
    path('admin/approve-vendor/<int:registration_id>/', admin_approve_vendor, name='admin_approve_vendor'),
    path('vendor/onboarding/', vendor_onboarding_token, name='vendor_onboarding_token'),
    path('vendor/kyc/', vendor_kyc_upload, name='vendor_kyc_upload'),
    path('admin/verify-kyc/<int:registration_id>/', admin_verify_kyc_detail, name='admin_verify_kyc_detail'),
    path('admin/invitation/create/', admin_create_invitation, name='admin_create_invitation'),
    path('admin/invitation/list/', admin_list_invitations, name='admin_list_invitations'),
    path('api/vendor-onboarding/requests', api_vendor_onboarding_requests_proxy, name='api_vendor_onboarding_requests_proxy'),
    path('api/vendor-onboarding/generate-link/<int:user_id>', api_vendor_onboarding_generate_link_proxy, name='api_vendor_onboarding_generate_link_proxy'),
    
    # Vendor Flow
    path('vendor/documents/', vendor_documents, name='vendor_documents'),
    path('vendor/vendors/', vendors, name='vendors'),
    path('vendor/prospects/', vendor_prospects, name='vendor_prospects'),
    path('vendor/permissions/', vendor_permissions, name='vendor_permissions'),
    path('vendor/customers/', customers, name='customers'),
    path('vendor/dashboard/', vendor_dashboard, name='vendor_dashboard'),
    path('vendor/download-report/', download_report, name='download_report'),
    path('store-company-id/', store_company_id, name='store_company_id'),
    
    # Procurement
    path('procurement/purchase-requisitions/', pr_list_view, name='pr_list'),
    path('procurement/purchase-requisitions/create/', pr_create_view, name='pr_create'),
    path('procurement/quotations/create/', quotation_create_view, name='quotation_create'),
    
    # Registration
    path('complete-registration/', complete_registration, name='complete_registration'),
    path('registration/complete/', registration_complete, name='registration_complete'),
    
    # Invoices
    path('indents/', indents, name='indents'),
    path('invoice/', invoice_view, name='invoice'),
    path('invoice/add/', invoice_add_view, name='invoice_add'),
    
    # Products
    path('products/', product_list_view, name='product_list'),
    path('products/add/', product_add_view, name='product_add'),
    
    # Payments
    path('payments/', vendor_payments_view, name='payments'),
    path('payments/upload-excel/', upload_payment_excel, name='upload_payment_excel'),
    path('payments/download-template/', download_payment_template, name='download_payment_template'),
    path('payments/reset/', reset_payment_data, name='reset_payment_data'),
    
    # Reports
    path('reports/payment-summary/', report_payment_summary_view, name='report_payment_summary'),
    path('reports/sales/', report_sale_view, name='report_sale'),
    path('reports/expenses/', report_expenses_view, name='report_expenses'),
    
    # Transactions
    path('transactions/', transaction_list_view, name='transaction_list'),
    path('transactions/new/', transaction_new_view, name='transaction_new'),
    
    # Taxes
    path('taxes/', taxes_view, name='taxes'),
    
    # Users
    path('users/', users_view, name='users'),
    
    # Proxy views
    path('upload/documents/', upload_documents_proxy, name='upload_documents_proxy'),
    path('api/verification/<str:doc_type>', verification_proxy, name='verification_proxy'),
    path('api/verification/<str:doc_type>/submit', verification_submit_proxy, name='verification_submit_proxy'),
    path('email/send/', send_email_proxy, name='send_email_proxy'),
    path('confirm-documents/', confirm_documents, name='confirm_documents'),
    path('extract-documents/', extract_documents, name='extract_documents'),
    
    # Customer Documents
    path('customer/documents/<int:user_id>/', customer_documents, name='customer_documents'),
    
    # Financial Terms
    path('financial-terms/save/', financial_terms_save, name='financial_terms_save'),
    path('financial-terms/get/', financial_terms_get, name='financial_terms_get'),
    path('financial-terms-customer/save/', financial_terms_customer_save, name='financial_terms_customer_save'),
    path('financial-terms-customer/get/', financial_terms_customer_get, name='financial_terms_customer_get'),
    path('financial-terms-customer/update/', financial_terms_customer_update, name='financial_terms_customer_update'),
    path('financial-terms/update/', financial_terms_update, name='financial_terms_update'),
    
    # Material URLs (AJAX endpoints)
    path('materials/', material_list, name='material_list'),
    path('material-bom/', material_bom_page, name='material_bom'),
    path('materials/create/', material_create, name='material_create'),
    path('materials/<int:pk>/edit/', material_edit, name='material_edit'),
    path('materials/<int:pk>/delete/', material_delete, name='material_delete'),
    path('material-types/', material_types_proxy, name='material_types_proxy'),
    path('base-units/', base_units_proxy, name='base_units_proxy'),
    path('item-categories/', item_categories_proxy, name='item_categories_proxy'),
    path('item-subcategories/save/', item_subcategories_save_proxy, name='item_subcategories_save_proxy'),
    path('item-subcategories/with-category-details/', item_subcategories_with_category_details_proxy, name='item_subcategories_with_category_details_proxy'),
    path('api/materials', materials_list_proxy, name='materials_list_proxy'),
    path('api/materials/<int:material_id>', material_detail_proxy, name='material_detail_proxy'),
    path('api/materials/<int:material_id>/attributes', material_attributes_proxy, name='material_attributes_proxy'),
    path('api/materials/<int:material_id>/bom-excel/save', material_bom_excel_save_proxy, name='material_bom_excel_save_proxy'),
    path('api/materials/<int:material_id>/bom-excel/get', material_bom_excel_get_proxy, name='material_bom_excel_get_proxy'),
    path('api/materials/save', materials_save_proxy, name='materials_save_proxy'),
    path('api/materials/bulk-save-with-images', materials_bulk_save_with_images_proxy, name='materials_bulk_save_with_images_proxy'),
    path('api/materials/images/sequence', materials_image_sequence_proxy, name='materials_image_sequence_proxy'),
    path('api/attributes/bulk', attributes_bulk_proxy, name='attributes_bulk_proxy'),
    path('api/attributes', attributes_list_proxy, name='attributes_list_proxy'),
    path('api/attributes/by-type/<str:attr_type>', attributes_by_type_proxy, name='attributes_by_type_proxy'),
    path('api/materials/<int:material_id>/delete', material_delete_proxy, name='material_delete_proxy'),
    path('api/attributes/<int:attribute_id>/delete', attribute_delete_proxy, name='attribute_delete_proxy'),
    
    path('variants/matrix/', variant_matrix, name='variant_matrix'),
    
    # Procurement (REST API Proxies)
    path('api/vendors/all/', vendors_list_proxy, name='vendors_list_proxy'),
    path('api/proxy/purchase-requisitions', purchase_requisitions_proxy, name='purchase_requisitions_proxy'),
    path('api/proxy/purchase-requisitions/<str:pr_id>', purchase_requisition_detail_proxy, name='purchase_requisition_detail_proxy'),
    path('api/proxy/purchase-requisitions/<str:pr_id>/status', purchase_requisition_status_proxy, name='purchase_requisition_status_proxy'),
    path('api/proxy/vendor/purchase-requisitions', vendor_purchase_requisitions_proxy, name='vendor_purchase_requisitions_proxy'),
    path('api/proxy/vendor/purchase-requisitions/details', vendor_purchase_requisition_detail_proxy, name='vendor_purchase_requisition_detail_proxy'),
    path('api/vendor/purchase-requisitions/<str:pr_id>/accept', vendor_pr_respond_proxy, name='vendor_pr_accept_proxy'),
    path('api/vendor/purchase-requisitions/<str:pr_id>/reject', vendor_pr_respond_proxy, name='vendor_pr_reject_proxy'),
    path('api/vendor/purchase-requisitions/<str:pr_id>/respond', vendor_pr_respond_proxy, name='vendor_pr_respond_proxy'),
    path('api/proxy/vendor/quotations/submit/', submit_quotation, name='submit_quotation_proxy'),
    path('variants/generate/', generate_variants, name='generate_variants'),
    path('variants/', variant_list, name='variant_list'),
    path('variants/material/<int:material_id>/', variant_list, name='variant_list_by_material'),
    path('variants/<int:variant_id>/', variant_detail, name='variant_detail'),
    path('variants/<int:variant_id>/delete/', delete_variant, name='delete_variant'),
    path('variants/material/<int:material_id>/bulk-update/', bulk_update_variants, name='bulk_update_variants'),
    path('api/materials/<int:material_id>/variants', material_variant_create_proxy, name='material_variant_create_proxy'),
    path('api/materials/<int:material_id>/variants/bulk', material_variant_bulk_create_proxy, name='material_variant_bulk_create_proxy'),
    path('api/materials/variants', material_variants_list_proxy, name='material_variants_list_proxy'),
    path('api/materials/variants/<str:variant_code>', material_variant_detail_proxy, name='material_variant_detail_proxy'),
    path('api/materials/variants/<str:variant_code>/active-status', material_variant_active_status_proxy, name='material_variant_active_status_proxy'),
    path('api/materials/variants/<str:variant_code>/barcode-image', material_variant_barcode_image_proxy, name='material_variant_barcode_image_proxy'),
    path('api/materials/variants/<str:variant_code>/variant-image', material_variant_image_proxy, name='material_variant_image_proxy'),
    path('api/materials/variants/<str:variant_code>/delete', variant_delete_proxy, name='variant_delete_proxy'),
    
    # Channel Management URLs
    path('channels/', channels_list, name='channels_list'),
    path('channels/create/', channel_create, name='channel_create'),
    path('channels/<int:channel_id>/', channel_detail, name='channel_detail'),
    path('channels/<int:channel_id>/update/', channel_update, name='channel_update'),
    path('channels/<int:channel_id>/delete/', channel_delete, name='channel_delete'),
    path('channels/<int:channel_id>/categories/', channel_categories_list, name='channel_categories_list'),
    path('channels/<int:channel_id>/categories/create/', channel_category_create, name='channel_category_create'),
    path('channels/categories/<int:category_id>/update/', channel_category_update, name='channel_category_update'),
    path('channels/categories/<int:category_id>/delete/', channel_category_delete, name='channel_category_delete'),
    path('channels/<int:channel_id>/categories/ajax/', get_channel_categories, name='get_channel_categories'),
    
    # Catalog URLs
    path('catalog/', catalog_view, name='catalog'),
    path('catalog/<str:channel_code>/', catalog_view, name='catalog_by_channel'),
    path('products/<int:material_id>/', product_detail_view, name='product_detail'),
    path('public/products/<int:material_id>/<int:channel_id>/', public_product_detail_view, name='public_product_detail'),
    path('public/products/<int:material_id>/', public_product_detail_auto_view, name='public_product_detail_auto'),
    
    # Public API URLs (no authentication required)
    path('api/public/materials/<int:material_id>/<int:channel_id>/', public_materials_api_proxy, name='public_materials_api'),
    path('api/public/materials/<int:material_id>/', public_materials_api_proxy_flexible, name='public_materials_api_flexible'),
    # Flipbook hotspots save/load proxies
    path('api/flipbook/hotspots/save/', flipbook_hotspots_save_proxy, name='flipbook_hotspots_save_proxy'),
    path('api/flipbook/hotspots/', flipbook_hotspots_get_proxy, name='flipbook_hotspots_get_proxy'),
    path('api/flipbook/pdf/upload/', flipbook_pdf_upload_proxy, name='flipbook_pdf_upload_proxy'),
    path('api/flipbook/pdf/save/', flipbook_pdf_save_proxy, name='flipbook_pdf_save_proxy'),
    path('api/flipbook/pdf/load/', flipbook_pdf_load_proxy, name='flipbook_pdf_load_proxy'),
    path('api/flipbook/pdf/delete/', flipbook_pdf_delete_proxy, name='flipbook_pdf_delete_proxy'),
    path('api/flipbook/pdf/download/', flipbook_pdf_download_proxy, name='flipbook_pdf_download_proxy'),
    path('api/flipbook/pdf/download-with-hotspots/', flipbook_pdf_download_with_hotspots_proxy, name='flipbook_pdf_download_with_hotspots_proxy'),
    path('api/public/orders/checkout/', public_orders_checkout_proxy, name='public_orders_checkout_proxy'),
    
    # User Management API URLs
    path('api/users/<int:user_id>/deactivate/', user_deactivate_proxy, name='user_deactivate_proxy'),
    
    # Material Mappings Proxy URLs
    path('api/materials/<int:material_id>/mappings', material_mappings_get_proxy, name='material_mappings_get_proxy'),
    path('api/materials/<int:material_id>/mappings/save', material_mappings_save_proxy, name='material_mappings_save_proxy'),
    path('api/materials/<int:material_id>/mappings/<int:channel_id>', material_mapping_delete_proxy, name='material_mapping_delete_proxy'),
    path('api/channels/<int:channel_id>/categories/<int:category_id>', channel_category_delete_proxy, name='channel_category_delete_proxy'),
    # Catalog PDF generation proxy
    path('api/catalog/generate-pdf/', catalog_pdf_generate_proxy, name='catalog_pdf_generate_proxy'),
    # Cover photo upload proxy
    path('api/cover-photo/upload/', cover_photo_upload_proxy, name='cover_photo_upload_proxy'),
    # Cover photos list proxy
    path('api/cover-photos/all/', cover_photos_list_proxy, name='cover_photos_list_proxy'),
    # Channel categories proxy
    path('api/channels/<int:channel_id>/categories/', channel_categories_proxy, name='channel_categories_proxy'),
    
    # Cart API URLs
    path('api/cart/add-item/', cart_add_item_proxy, name='cart_add_item_proxy'),
    path('api/cart/items/', cart_items_proxy, name='cart_items_proxy'),
    path('api/cart/update-quantity/', cart_update_quantity_proxy, name='cart_update_quantity_proxy'),
    path('api/cart/remove-item/', cart_remove_item_proxy, name='cart_remove_item_proxy'),
    path('api/cart/clear/', cart_clear_proxy, name='cart_clear_proxy'),
    path('api/cart/summary/', cart_summary_proxy, name='cart_summary_proxy'),
    
    # Reporting Categories URLs

    
    # Material Channel Assignment URLs
    path('material-channel-assignments/', material_channel_assignments_list, name='material_channel_assignments_list'),
    path('material-channel-assignments/create/', material_channel_assignment_create, name='material_channel_assignment_create'),
    path('material-channel-assignments/save/', material_channel_assignment_save, name='material_channel_assignment_save'),
    path('material-channel-assignments/<int:assignment_id>/update/', material_channel_assignment_update, name='material_channel_assignment_update'),
    path('material-channel-assignments/<int:assignment_id>/delete/', material_channel_assignment_delete, name='material_channel_assignment_delete'),
    path('api/pdf/upload/', pdf_upload_view, name='pdf_upload'),
    # PDF image extraction API
    path('api/pdf/extract/start/', pdf_extract_start, name='pdf_extract_start'),
    path('api/pdf/extract/<str:job_id>/status/', pdf_extract_status, name='pdf_extract_status'),
    path('api/pdf/extract/<str:job_id>/images/', pdf_extract_images, name='pdf_extract_images'),
    path('api/pdf/extract/<str:job_id>/cleanup/', pdf_extract_cleanup, name='pdf_extract_cleanup'),
    
    # Location Management URLs
    path('locations/', locations_list, name='locations_list'),
    path('api/locations/save/', locations_save_proxy, name='locations_save_proxy'),
    path('api/locations/', locations_list_proxy, name='locations_list_proxy'),
    path('api/locations/<int:location_id>/', location_detail_proxy, name='location_detail_proxy'),
    path('api/locations/<int:location_id>/delete/', location_delete_proxy, name='location_delete_proxy'),
    path('api/locations/<int:location_id>/soft-delete/', location_soft_delete_proxy, name='location_soft_delete_proxy'),
    path('api/auth-token/', get_auth_token, name='get_auth_token'),
    path('api/test-java-connection/', test_java_connection, name='test_java_connection'),
    path('api/materials/bulk-upload/payload/', materials_bulk_payload_proxy, name='materials_bulk_payload_proxy'),
    path('api/materials/bulk-upload/', materials_bulk_upload, name='materials_bulk_upload'),
    path('api/materials/master-bom/upload/', master_bom_upload_proxy, name='master_bom_upload_proxy'),
    path('api/materials/master-bom/fetch/', master_bom_fetch_proxy, name='master_bom_fetch_proxy'),
    path('api/materials/master-bom/files/', master_bom_files_list_proxy, name='master_bom_files_list_proxy'),
    path('api/materials/template/download/', materials_template_download, name='materials_template_download'),
    
    # Vendor Catalogue URLs
    path('api/vendor/catalogue/check/', vendor_catalogue_check_proxy, name='vendor_catalogue_check'),
    path('api/vendor/catalogue/upload/', vendor_catalogue_upload_proxy, name='vendor_catalogue_upload'),
    path('api/vendor/catalogue/download/', vendor_catalogue_download_proxy, name='vendor_catalogue_download'),
    path('api/vendor/catalogue/replace/', vendor_catalogue_replace_proxy, name='vendor_catalogue_replace'),
    
    # Inventory Management URLs
    path('inventory/', inventory_list, name='inventory_list'),
    path('api/inventory/', inventory_list_proxy, name='inventory_list_proxy'),
    path('api/inventory/<int:material_id>/stock/', inventory_update_stock_proxy, name='inventory_update_stock_proxy'),
    path('api/inventory/bulk-update-stock/', inventory_bulk_update_stock_proxy, name='inventory_bulk_update_stock_proxy'),
    path('api/inventory/bulk-upload/', inventory_bulk_upload, name='inventory_bulk_upload'),
    path('api/inventory/template/download/', inventory_template_download, name='inventory_template_download'),

    path('api/image-describe/', image_describe_proxy, name='image_describe_proxy'),
    path('api/materials/bom/generate-from-cad/', bom_aerospace_json_proxy, name='bom_aerospace_json_proxy'),
    path('api/materials/bom/generate-from-image/', bom_image_json_proxy, name='bom_image_json_proxy'),

    # Organization Module URLs
    path('organization/countries/', countries_list, name='countries_list'),
    path('organization/currencies/', currencies_list, name='currencies_list'),
    path('organization/companies/', companies_list, name='companies_list'),
    path('organization/channels/', channels_list_org, name='channels_list_org'),
    path('organization/departments/', departments_list, name='departments_list'),

    # Budget API URLs
    path('api/budget/budget-upload', budget_upload, name='budget_upload'),
    path('api/department-status', department_budget_status, name='department_budget_status'),

    # Organization API Proxies (Generic)
    path('api/organization/<str:module>/', organization_api_proxy, name='organization_api_list_proxy'),
    path('api/organization/<str:module>/<int:pk>/', organization_api_proxy, name='organization_api_detail_proxy'),

    # Category Management HTML View
    path('categories/', categories_list, name='categories_list'),
    path('module/<str:module_name>/', coming_soon, name='coming_soon'),
    path('workflows/', workflows, name='workflows'),
    path('workflow/dashboard/', workflow_dashboard, name='workflow_dashboard'),
    path('workflow/requests/', workflow_requests, name='workflow_requests'),
    path('workflow/groups/', workflow_groups, name='workflow_groups'),
    path('workflow/analytics/', workflow_analytics, name='workflow_analytics'),
    path('workflow/settings/', workflow_settings, name='workflow_settings'),
    path('workflow/email-action/', workflow_email_action, name='workflow_email_action'),
    path('action/<str:token>/', workflow_email_action, name='workflow_email_action_direct'),
    path('vendor/portal/', vendor_portal_preview, name='vendor_portal_preview'),
    path('purchase-requisitions/', purchase_requisitions, name='purchase_requisitions'),
    path('purchase-requisitions/upload-excel/', upload_pr_excel, name='upload_pr_excel'),
    path('purchase-requisitions/download-template/', download_pr_template, name='download_pr_template'),
    path('purchase-requisitions/reset/', reset_pr_data, name='reset_pr_data'),
    path('purchase-orders/upload-excel/', upload_po_excel, name='upload_po_excel'),
    path('purchase-orders/download-template/', download_po_template, name='download_po_template'),
    path('purchase-orders/reset/', reset_po_data, name='reset_po_data'),
    path('purchase-orders/create-from-quotation/', create_po_from_quotation, name='create_po_from_quotation'),
    path('api/quotation/verify-for-po/', verify_quotation_for_po, name='verify_quotation_for_po'),
    path('api/admin/quotations/awarded', get_awarded_quotations, name='get_awarded_quotations'),
    path('api/purchase-orders/from-awarded-quotation/<int:quotation_id>/', create_po_from_awarded_quotation, name='create_po_from_awarded_quotation'),
    path('api/purchase-orders/<str:po_id>/cancel/', cancel_purchase_order_proxy, name='cancel_purchase_order_proxy'),
    path('purchase-requisition/<str:pr_id>/', purchase_requisition_detail, name='purchase_requisition_detail'),
    path('quotations/', quotations, name='quotations'),
    path('quotation/new/', new_quotation, name='new_quotation'),
    path('quotation/<str:qtn_id>/', quotation_detail, name='quotation_detail'),
    path('procurement/quotations/award/<int:qtn_id>/', award_quotation, name='award_quotation'),
    path('asn/', asn, name='asn'),
    path('purchase-order/<str:po_id>/', purchase_order_detail, name='purchase_order_detail'),
    path('service-purchase-order/<str:po_id>/', service_purchase_order_detail, name='service_purchase_order_detail'),
    path('subcontracting-purchase-order/<str:po_id>/', subcontracting_purchase_order_detail, name='subcontracting_purchase_order_detail'),
    path('purchase-orders/', purchase_orders, name='purchase_orders'),
    path('subcontracting-purchase-orders/', subcontracting_purchase_orders, name='subcontracting_purchase_orders'),
    path('subcontracting-purchase-orders/upload-excel/', upload_subcon_po_excel, name='upload_subcon_po_excel'),
    path('subcontracting-purchase-orders/download-template/', download_subcon_po_template, name='download_subcon_po_template'),
    path('subcontracting-purchase-orders/reset/', reset_subcon_po_data, name='reset_subcon_po_data'),
    path('scheduling-agreements/', scheduling_agreements, name='scheduling_agreements'),
    path('service-purchase-orders/', service_purchase_orders, name='service_purchase_orders'),
    path('service-purchase-orders/upload-excel/', upload_service_po_excel, name='upload_service_po_excel'),
    path('service-purchase-orders/download-template/', download_service_po_template, name='download_service_po_template'),
    path('service-purchase-orders/reset/', reset_service_po_data, name='reset_service_po_data'),
    path('credit-payments/', credit_payments, name='credit_payments'),
    path('create-asn/<str:po_id>/', create_asn, name='create_asn'),
    
    # Catch-all for FastAPI proxy
    path('api/<path:path>', fastapi_proxy, name='fastapi_proxy'),
]
