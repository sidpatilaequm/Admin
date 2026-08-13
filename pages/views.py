
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import TemplateView
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_GET, require_POST
import requests
import json
from django.conf import settings
import logging
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .models import Material, Attribute, MaterialVariant, MaterialVariantAttributeValue, Channel, ChannelCategory, ReportingCategory, MaterialChannelAssignment, VendorRegistration, SupplierInvitation
from .forms import MaterialForm
from django.forms.models import model_to_dict
from itertools import product
import re
from django.views.decorators.csrf import csrf_exempt
# Set up logging
logger = logging.getLogger(__name__)
import jwt

# FastAPI proxy view
@csrf_exempt
def fastapi_proxy(request, path):
    """Proxy any request to the FastAPI backend.
    URL pattern: /api/<path>
    """
    try:
        method = request.method
        # Forward query string parameters
        query_string = request.META.get('QUERY_STRING', '')
        target_url = f'http://localhost:8001/api/{path}'
        if query_string:
            target_url = f'{target_url}?{query_string}'
        headers = {
            'Content-Type': request.headers.get('Content-Type', 'application/json')
        }
        resp = requests.request(method, target_url, headers=headers, data=request.body, timeout=30, allow_redirects=True)
        content_type = resp.headers.get('Content-Type', 'application/json')
        return HttpResponse(content=resp.content, status=resp.status_code, content_type=content_type)
    except Exception as e:
        logger.exception('FastAPI proxy error')
        return JsonResponse({'status': 'error', 'error': str(e)}, status=500)

# Java backend API URL
JAVA_API_URL = settings.INTERNAL_JAVA_API_URL

class PagesView(TemplateView):
    pass

# ------------------- Public Orders (Checkout) Proxy -------------------
@csrf_exempt
@require_http_methods(["POST"]) 
def public_orders_checkout_proxy(request):
    try:
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError:
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': 'Invalid JSON payload',
                'errorCode': 'BAD_REQUEST',
                'data': {}
            }, status=400)

        logger.info("Forwarding public checkout payload to Java API")
        resp = requests.post(
            f"{JAVA_API_URL}/api/public/orders/checkout",
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )

        # Try to relay JSON body; if not JSON, return generic error
        try:
            body = resp.json()
        except ValueError:
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': 'Upstream returned non-JSON response',
                'errorCode': 'UPSTREAM_INVALID',
                'data': {}
            }, status=502)

        return JsonResponse(body, status=resp.status_code)

    except requests.exceptions.RequestException as e:
        logger.exception("Checkout upstream error")
        return JsonResponse({
            'status': 'ERROR',
            'statusMsg': 'Unable to reach checkout service',
            'errorCode': 'UPSTREAM_UNAVAILABLE',
            'data': {}
        }, status=502)
    except Exception as e:
        logger.exception("Checkout proxy error")
        return JsonResponse({
            'status': 'ERROR',
            'statusMsg': 'Internal server error',
            'errorCode': 'INTERNAL',
            'data': {}
        }, status=500)

def try_local_login(email, password, login_type, request):
    try:
        reg = VendorRegistration.objects.filter(email=email).first()
        if reg and reg.password == password and reg.status in ['APPROVED', 'DOCUMENT_SUBMITTED', 'UNDER_VERIFICATION', 'ACTIVE']:
            user_data = {
                'superAdminId': reg.id,
                'email': reg.email,
                'firstName': reg.contact_name,
                'lastName': '',
                'phoneNumber': reg.phone,
                'role': 'VENDOR',
                'authName': reg.vendor_name,
                'vendorId': reg.id,
                'vendor_code': reg.vendor_code,
                'status': reg.status
            }
            
            email_lower = str(reg.email).lower()
            special_workflow_emails = {
                'siddarthpatil17+2001@gmail.com',
                'siddarthpatil17+2002@gmail.com',
                'siddarthpatil17+2003@gmail.com'
            }
            if email_lower in special_workflow_emails:
                user_data['isDocumentsPresent'] = True
                request.session['workflow_only'] = True
                redirect_url = '/workflow/requests/'
            else:
                request.session['workflow_only'] = False
                redirect_url = '/vendor/dashboard/'

            request.session['auth_token'] = f"local_token_{reg.id}"
            request.session['user_data'] = user_data
            request.session['vendor_permissions'] = {
                'PR_MANAGEMENT': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'QUOTATION_MANAGEMENT': {'view': True, 'create': True, 'edit': True, 'delete': False},
                'PO_MANAGEMENT': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'PAYMENT_MANAGEMENT': {'view': True, 'create': False, 'edit': False, 'delete': False},
                'SUPPLIER_DASHBOARD': {'view': True, 'create': True, 'edit': True, 'delete': True}
            }
            request.session.modified = True
            return JsonResponse({
                'status': 'success',
                'redirect_url': redirect_url,
                'token': f"local_token_{reg.id}",
                'user_data': user_data
            })
    except Exception as e:
        logger.error(f"Error checking local vendor login: {e}")

    if login_type != 'vendor':
        try:
            from django.contrib.auth import authenticate as django_authenticate
            user = django_authenticate(username=email, password=password)
            if user:
                user_data = {
                    'superAdminId': user.id,
                    'email': user.email,
                    'firstName': user.first_name or 'Admin',
                    'lastName': user.last_name or 'User',
                    'role': 'SUPER_ADMIN'
                }
                request.session['auth_token'] = f"local_admin_token_{user.id}"
                request.session['user_data'] = user_data
                request.session.modified = True
                return JsonResponse({
                    'status': 'success',
                    'redirect_url': '/vendor/dashboard/',
                    'token': f"local_admin_token_{user.id}",
                    'user_data': user_data
                })
        except Exception as e:
            logger.error(f"Error checking local admin login: {e}")
            
    return None

@csrf_exempt
@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            email = data.get('email')
            login_type = data.get('login_type', 'standard')
            vendor_id = data.get('vendor_id')
            
            # Log pre-request state
            logger.info("=== LOGIN PROCESS START ===")
            logger.info(f"Attempting {login_type} login for: {email} (Vendor ID: {vendor_id})")
            
            if login_type == 'vendor':
                api_endpoint = f"{JAVA_API_URL}/api/users/login"
                payload = {
                    "email": email,
                    "password": data.get('password')
                }
            elif login_type == 'employee':
                # Employee / Purchase Dept login → new Java endpoint
                api_endpoint = f"{JAVA_API_URL}/api/employee/login"
                payload = {
                    "email": email,
                    "password": data.get('password')
                }
            else:
                api_endpoint = f"{JAVA_API_URL}/api/super-admin/login"
                payload = {
                    "email": email,
                    "password": data.get('password')
                }

            try:
                response = requests.post(
                    api_endpoint,
                    json=payload,
                    headers={'Content-Type': 'application/json'},
                    timeout=5
                )
                
                logger.info(f"API Response Status: {response.status_code}")
                
                if response.status_code == 200:
                    try:
                        response_data = response.json()
                        logger.info(f"RAW API RESPONSE: {response_data}")

                        # Handle both legacy and new auth responses
                        super_admin = response_data.get('superAdmin', {})
                        
                        # For employee login, role comes from 'userType' field
                        role = (
                            response_data.get('userType')
                            or response_data.get('role')
                            or response_data.get('authName')
                            or super_admin.get('role')
                            or 'SUPER_ADMIN'
                        )

                        user_data = {
                            'superAdminId': super_admin.get('superAdminId') or response_data.get('userId'),
                            'email': super_admin.get('email') or response_data.get('email'),
                            'firstName': super_admin.get('firstName') or response_data.get('firstName') or response_data.get('name', '').split(' ')[0],
                            'lastName': super_admin.get('lastName') or response_data.get('lastName') or (' '.join(response_data.get('name', '').split(' ')[1:]) if response_data.get('name') else ''),
                            'phoneNumber': super_admin.get('phoneNumber') or response_data.get('phoneNumber'),
                            'role': role,
                            'authName': response_data.get('authName'),
                            'vendorId': response_data.get('companyId') or response_data.get('vendorId') or vendor_id,
                            'isDocumentsPresent': response_data.get('isDocumentsPresent'),
                            # Employee-specific fields from /api/employee/login
                            'employeeCode': response_data.get('employeeCode'),
                            'deptCode': response_data.get('deptCode'),
                            'deptName': response_data.get('deptName'),
                            'title': response_data.get('title'),
                            'managerCode': response_data.get('managerCode'),
                        }

                        # For VENDOR logins: look up the actual vendor_id from vendor_master
                        # The Java companyId is from company_details table (different numbering system).
                        # The Vendor Portal uses vendor_master.vendor_id for filtering PRs.
                        if str(role).upper() == 'VENDOR':
                            try:
                                login_email = user_data.get('email', '')
                                vm_resp = requests.get(
                                    f'http://127.0.0.1:8001/api/vendors/all',
                                    timeout=5
                                )
                                if vm_resp.status_code == 200:
                                    vm_list = vm_resp.json()
                                    matched = next(
                                        (v for v in vm_list if str(v.get('email', '')).lower() == str(login_email).lower()),
                                        None
                                    )
                                    if matched:
                                        real_vendor_id = matched['vendor_id']
                                        user_data['vendor_id'] = real_vendor_id
                                        user_data['company_id'] = real_vendor_id  # used by PurchaseRequisition.jsx
                                        logger.info(f"Resolved vendor_master.vendor_id={real_vendor_id} for {login_email}")
                                    else:
                                        logger.warning(f"No vendor_master entry found for email: {login_email}")
                            except Exception as vm_err:
                                logger.error(f"Failed to resolve vendor_master vendor_id: {vm_err}")

                        request.session['auth_token'] = response_data.get('token')
                        request.session['user_data'] = user_data
                        
                        # If it's a vendor, handle their permissions for the sidebar
                        if str(role).upper() == 'VENDOR':
                            # Flattening function for permissions
                            flat_permissions = {}
                            def flatten(perms):
                                for p in perms:
                                    if 'permissionCode' in p:
                                        flat_permissions[p['permissionCode']] = {
                                            'view': p.get('view', False),
                                            'create': p.get('create', False),
                                            'edit': p.get('edit', False),
                                            'delete': p.get('delete', False)
                                        }
                                        if p.get('children'):
                                            flatten(p['children'])
                            
                            # 1. Try to get permissions directly from the login response (NEW)
                            raw_permissions = response_data.get('permissions', {}).get('permissions')
                            if raw_permissions:
                                flatten(raw_permissions)
                                request.session['vendor_permissions'] = flat_permissions
                                logger.info(f"Extracted {len(flat_permissions)} vendor permissions from login response")
                            
                            # 2. Fallback: Fetch permissions if not in login response or extraction failed
                            if not request.session.get('vendor_permissions'):
                                try:
                                    logger.info("Permissions not in login response, falling back to secondary fetch")
                                    perm_response = requests.get(
                                        f"{JAVA_API_URL}/api/vendor-permissions/my-permissions",
                                        headers={'Authorization': f'Bearer {response_data.get("token")}', 'Content-Type': 'application/json'},
                                        timeout=10
                                    )
                                    if perm_response.status_code == 200:
                                        perm_data = perm_response.json()
                                        if perm_data.get('status') == '200':
                                            raw_permissions = perm_data.get('data', {}).get('result', {}).get('permissions', [])
                                            flatten(raw_permissions)
                                            request.session['vendor_permissions'] = flat_permissions
                                            logger.info(f"Fetched {len(flat_permissions)} vendor permissions via fallback fetch")
                                except Exception as e:
                                    logger.error(f"Failed to fetch vendor permissions during fallback: {e}")
                        
                        request.session.modified = True

                        # Decide landing page based on role and isDocumentsPresent
                        email_lower = str(user_data.get('email', '')).lower()
                        special_workflow_emails = {
                            'siddarthpatil17+2001@gmail.com',
                            'siddarthpatil17+2002@gmail.com',
                            'siddarthpatil17+2003@gmail.com'
                        }
                        if email_lower in special_workflow_emails:
                            user_data['isDocumentsPresent'] = True
                            request.session['workflow_only'] = True
                            redirect_url = '/workflow/requests/'
                        else:
                            request.session['workflow_only'] = False
                            role_upper = str(role).upper()
                            if role_upper == 'CUSTOMER':
                                redirect_url = '/catalog/'
                            elif role_upper == 'VENDOR' and response_data.get('isDocumentsPresent') is False:
                                redirect_url = '/vendor/documents/'
                            elif role_upper in ('EMPLOYEE', 'PURCHASE_DEPT'):
                                # Employee & Purchase Dept both use the React SPA (role-based rendering)
                                redirect_url = '/vendor/dashboard/'
                            else:
                                redirect_url = '/vendor/dashboard/'

                        logger.info(f"Stored user_data in session: {request.session.get('user_data')}")
                        return JsonResponse({
                            'status': 'success',
                            'redirect_url': redirect_url,
                            'token': response_data.get('token'),
                            'user_data': user_data
                        })
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse API response: {e}")
                        return JsonResponse({
                            'status': 'error',
                            'error': 'Invalid response from server'
                        }, status=500)
                else:
                    # Java response code is not 200: Try local DB fallback
                    local_resp = try_local_login(email, data.get('password'), login_type, request)
                    if local_resp:
                        logger.info("Java backend rejected credentials, fell back to local credentials successfully.")
                        return local_resp

                    error_message = 'Login failed'
                    try:
                        error_data = response.json()
                        if 'message' in error_data:
                            error_message = error_data['message']
                    except:
                        pass
                    logger.warning(f"Login failed: {error_message}")
                    return JsonResponse({
                        'status': 'error',
                        'error': error_message
                    }, status=response.status_code)
                    
            except requests.exceptions.ConnectionError as e:
                logger.error(f"Connection error to Java backend: {e}")
                # Try local DB fallback on connection error
                local_resp = try_local_login(email, data.get('password'), login_type, request)
                if local_resp:
                    logger.info("Java backend offline, fell back to local credentials successfully.")
                    return local_resp
                return JsonResponse({
                    'status': 'error',
                    'error': 'Could not connect to login server. Please try again later.'
                }, status=503)
                
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in request: {e}")
            return JsonResponse({
                'status': 'error',
                'error': 'Invalid request format'
            }, status=400)
        except Exception as e:
            logger.error(f"Unexpected error during login: {e}")
            return JsonResponse({
                'status': 'error',
                'error': 'An unexpected error occurred. Please try again.'
            }, status=500)
            
    return render(request, 'pages/login.html')

@require_http_methods(["GET", "POST"])
def register_view(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            logger.info("=== REGISTRATION PROCESS START ===")
            logger.info(f"Registration data received: {data}")

            # Make request to Java backend
            response = requests.post(
                f"{JAVA_API_URL}/api/super-admin/register",
                json={
                    "email": data.get('email'),
                    "password": data.get('password'),
                    "firstName": data.get('firstName'),
                    "lastName": data.get('lastName'),
                    "phoneNumber": data.get('phoneNumber')
                },
                headers={'Content-Type': 'application/json'}
            )
            
            logger.info(f"Java backend response status: {response.status_code}")
            
            if response.status_code == 200:
                response_data = response.json()
                logger.info(f"Registration successful: {response_data}")
                return JsonResponse({
                    'status': 'success',
                    'redirect_url': '/login/'
                })
            else:
                error_message = 'Registration failed'
                try:
                    error_data = response.json()
                    if 'message' in error_data:
                        error_message = error_data['message']
                except:
                    pass
                logger.warning(f"Registration failed: {error_message}")
                return JsonResponse({
                    'status': 'error',
                    'error': error_message
                }, status=response.status_code)
                
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error to Java backend: {e}")
            return JsonResponse({
                'status': 'error',
                'error': 'Could not connect to registration server. Please try again later.'
            }, status=503)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in request: {e}")
            return JsonResponse({
                'status': 'error',
                'error': 'Invalid request format'
            }, status=400)
        except Exception as e:
            logger.error(f"Unexpected error during registration: {e}")
            return JsonResponse({
                'status': 'error',
                'error': 'An unexpected error occurred. Please try again.'
            }, status=500)
    if request.method == 'GET':
        token = request.GET.get('token')
        if token:
            try:
                payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
                email = payload.get('email')
                
                # Check database invitation status
                invite = SupplierInvitation.objects.filter(token=token, status='INVITED').first()
                if not invite:
                    return render(request, 'pages/login.html', {
                        'error': 'This invitation link is invalid or has already been used.',
                        'hide_register_toggle': True
                    })
                    
                if invite.expiry_date < timezone.now():
                    invite.status = 'EXPIRED'
                    invite.save()
                    return render(request, 'pages/login.html', {
                        'error': 'This invitation link has expired. Please contact the procurement team.',
                        'hide_register_toggle': True
                    })
                    
                # Valid token! Render login.html with force_signup=True and the supplier email pre-populated
                return render(request, 'pages/login.html', {
                    'is_invited': True,
                    'supplier_email': email,
                    'token': token,
                    'force_signup': True
                })
                
            except jwt.ExpiredSignatureError:
                return render(request, 'pages/login.html', {
                    'error': 'This invitation link has expired.',
                    'hide_register_toggle': True
                })
            except jwt.InvalidTokenError:
                return render(request, 'pages/login.html', {
                    'error': 'This invitation link is invalid.',
                    'hide_register_toggle': True
                })
            except Exception as e:
                logger.error(f"Error validating invite token: {e}")
                return render(request, 'pages/login.html', {
                    'error': 'An error occurred during invitation validation.',
                    'hide_register_toggle': True
                })

    return render(request, 'pages/authentication/auth-signup.html')

def logout_view(request):
    request.session.flush()
    return redirect('pages:login')

def check_auth(view_func):
    def wrapper(request, *args, **kwargs):
        token = request.session.get('auth_token')
        if not token:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'status': '401',
                    'statusMsg': 'Session expired. Please login again.'
                }, status=401)
            return redirect('pages:login')

        user_data = request.session.get('user_data', {}) or {}
        role = str(user_data.get('role', '')).upper()

        if role == 'CUSTOMER':
            resolver = getattr(request, 'resolver_match', None)
            url_name = resolver.url_name if resolver else None
            customer_allowed_views = {
                'catalog',
                'catalog_by_channel',
                'product_detail',
                'cart_add_item_proxy',
                'cart_items_proxy',
                'cart_update_quantity_proxy',
                'cart_remove_item_proxy',
                'cart_clear_proxy',
                'cart_summary_proxy',
                'catalog_pdf_generate_proxy',
                'image_describe_proxy',
                'master_bom_files_list_proxy',
                'master_bom_upload_proxy',
                'master_bom_fetch_proxy',
                'bom_image_json_proxy',
                # Organization Module Views
                'countries_list',
                'currencies_list',
                'companies_list',
                'channels_list_org',
                'material_bom',
                'organization_api_list_proxy',
                'organization_api_detail_proxy',
                'channels_list_proxy',
                'channel_detail_proxy',
                'org_item_categories_proxy',
                'org_item_subcategories_proxy',
                'org_channel_categories_proxy',
                'org_category_mappings_proxy',
                'org_material_listings_proxy',
            }

            if url_name and url_name not in customer_allowed_views:
                logger.warning(f"BLOCKED: Role {role} tried to access {url_name}")
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({
                        'status': '403',
                        'statusMsg': f'Access denied for {role} role on {url_name}.',
                    }, status=403)
                return redirect('pages:catalog')

        elif role == 'VENDOR':
            resolver = getattr(request, 'resolver_match', None)
            url_name = resolver.url_name if resolver else None
            
            if request.session.get('workflow_only') is True:
                workflow_allowed_views = {'workflow_requests', 'logout'}
                if url_name and url_name not in workflow_allowed_views:
                    logger.warning(f"BLOCKED workflow-only vendor: tried to access {url_name}")
                    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                        return JsonResponse({
                            'status': '403',
                            'statusMsg': 'Access denied.',
                        }, status=403)
                    return redirect('pages:workflow_requests')
            else:
                # Check if vendor needs to upload documents first
                is_docs_present = user_data.get('isDocumentsPresent')
                if is_docs_present is False:
                    if url_name not in ['vendor_documents', 'verification_proxy', 'verification_submit_proxy', 'logout']:
                        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                            return JsonResponse({
                                'status': '403',
                                'statusMsg': 'Documents upload required.',
                            }, status=403)
                        return redirect('pages:vendor_documents')

                vendor_allowed_views = {
                    'vendor_dashboard',
                    'vendor_documents',
                    'verification_proxy',
                    'verification_submit_proxy',
                    'purchase_requisitions',
                    'purchase_requisition_detail',
                    'quotations',
                    'new_quotation',
                    'submit_quotation_proxy',
                    'quotation_detail',
                    'asn',
                    'purchase_orders',
                    'purchase_order_detail',
                    'subcontracting_purchase_orders',
                    'subcontracting_purchase_order_detail',
                    'scheduling_agreements',
                    'service_purchase_orders',
                    'service_purchase_order_detail',
                    'credit_payments',
                    'payments',
                    'coming_soon',
                    'logout',
                }

                if url_name and url_name not in vendor_allowed_views:
                    logger.warning(f"BLOCKED: Role {role} tried to access {url_name}")
                    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                        return JsonResponse({
                            'status': '403',
                            'statusMsg': f'Access denied for {role} role on {url_name}.',
                        }, status=403)
                    return redirect('pages:vendor_dashboard')

        return view_func(request, *args, **kwargs)
    return wrapper

@csrf_exempt
@check_auth
@require_http_methods(["GET"])
def get_vendor_permissions_proxy(request, company_id):
    auth_token = request.session.get('auth_token')
    try:
        response = requests.get(
            f"{JAVA_API_URL}/api/vendor-permissions/{company_id}",
            headers={'Authorization': f'Bearer {auth_token}', 'Content-Type': 'application/json'},
            timeout=15
        )
        try:
            return JsonResponse(response.json(), status=response.status_code)
        except:
            return JsonResponse({'status': '500', 'statusMsg': 'Upstream returned invalid JSON'}, status=500)
    except Exception as e:
        logger.error(f"Error fetching vendor permissions: {e}")
        return JsonResponse({'status': '500', 'statusMsg': str(e)}, status=500)

@csrf_exempt
@check_auth
@require_http_methods(["POST"])
def save_vendor_permissions_proxy(request):
    auth_token = request.session.get('auth_token')
    try:
        payload = json.loads(request.body)
        response = requests.post(
            f"{JAVA_API_URL}/api/vendor-permissions/save",
            json=payload,
            headers={'Authorization': f'Bearer {auth_token}', 'Content-Type': 'application/json'},
            timeout=15
        )
        try:
            return JsonResponse(response.json(), status=response.status_code)
        except:
            return JsonResponse({'status': '500', 'statusMsg': 'Upstream returned invalid JSON'}, status=500)
    except Exception as e:
        logger.error(f"Error saving vendor permissions: {e}")
        return JsonResponse({'status': '500', 'statusMsg': str(e)}, status=500)

@csrf_exempt
@check_auth
@require_http_methods(["GET"])
def get_my_permissions_proxy(request):
    auth_token = request.session.get('auth_token')
    try:
        response = requests.get(
            f"{JAVA_API_URL}/api/vendor-permissions/my-permissions",
            headers={'Authorization': f'Bearer {auth_token}', 'Content-Type': 'application/json'},
            timeout=15
        )
        try:
            return JsonResponse(response.json(), status=response.status_code)
        except:
            return JsonResponse({'status': '500', 'statusMsg': 'Upstream returned invalid JSON'}, status=500)
    except Exception as e:
        logger.error(f"Error fetching my permissions: {e}")
        return JsonResponse({'status': '500', 'statusMsg': str(e)}, status=500)

@check_auth
def vendor_documents(request):
    user_data = request.session.get('user_data', {})
    user_id = user_data.get('superAdminId')
    return render(request, 'pages/vendor_documents.html', {'user_data': user_data})

@check_auth
def vendors(request):
    logger.info("=== VENDORS PAGE ACCESS ===")
    logger.info(f"Session data: {dict(request.session)}")
    
    user_data = request.session.get('user_data', {})
    logger.info(f"User data: {user_data}")
    
    try:
        # Get auth token from session
        auth_token = request.session.get('auth_token')
        if not auth_token:
            logger.error("No auth token found in session")
            messages.error(request, "Session expired. Please login again.")
            return redirect('pages:login')
            
        # Make API call to get vendors
        response = requests.get(
            f"{JAVA_API_URL}/api/vendors/all",
            headers={
                'Authorization': f'Bearer {auth_token}',
                'Content-Type': 'application/json'
            }
        )
        
        logger.info(f"Vendors API Response Status: {response.status_code}")
        
        if response.status_code == 200:
            vendors_data = response.json()
            logger.info(f"Vendors data received: {vendors_data}")
            vendors = vendors_data.get('data', {}).get('vendors', [])
            # Add JSON string for each vendor
            for v in vendors:
                v['json'] = json.dumps(v)
            return render(request, 'pages/vendors.html', {
                'user_data': user_data,
                'vendors': vendors
            })
        else:
            error_message = 'Failed to fetch vendors'
            try:
                error_data = response.json()
                if 'message' in error_data:
                    error_message = error_data['message']
            except:
                pass
            logger.error(f"Failed to fetch vendors: {error_message}")
            messages.error(request, error_message)
            # Return empty vendors list when API fails
            return render(request, 'pages/vendors.html', {
                'user_data': user_data,
                'vendors': [],
                'modules': modules
            })
        
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error to Java backend: {e}")
        messages.error(request, "Could not connect to server. Please try again later.")
        return render(request, 'pages/vendors.html', {
            'user_data': user_data,
            'vendors': []
        })
    except Exception as e:
        logger.error(f"Unexpected error in vendors view: {e}")
        messages.error(request, "An unexpected error occurred. Please try again.")
        return render(request, 'pages/vendors.html', {
            'user_data': user_data,
            'vendors': []
        })

@check_auth
def vendor_permissions(request):
    logger.info("=== VENDOR PERMISSIONS PAGE ACCESS ===")
    user_data = request.session.get('user_data', {})
    auth_token = request.session.get('auth_token')
    
    vendors = []
    try:
        if auth_token:
            response = requests.get(
                f"{JAVA_API_URL}/api/vendors/all",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                },
                timeout=10
            )
            if response.status_code == 200:
                vendors_data = response.json()
                vendors = vendors_data.get('data', {}).get('vendors', [])
    except Exception as e:
        logger.error(f"Error fetching vendors for permissions: {e}")

    return render(request, 'pages/vendor_permissions.html', {
        'user_data': user_data,
        'vendors': vendors
    })

@check_auth
def customers(request):
    logger.info("=== CUSTOMERS PAGE ACCESS ===")
    logger.info(f"Session data: {dict(request.session)}")
    
    # Ensure user_data is present in session for logout dropdown
    if 'user_data' not in request.session or not request.session['user_data']:
        messages.error(request, 'Session expired. Please login again.')
        return redirect('pages:login')
    
    user_data = request.session.get('user_data', {})
    logger.info(f"User data: {user_data}")
    
    # Get the auth token from session
    auth_token = request.session.get('auth_token')
    
    if not auth_token:
        messages.error(request, 'Session expired. Please login again.')
        return redirect('pages:login')
    
    try:
        # Make API call to fetch customers
        api_url = f"{JAVA_API_URL}/api/customers/all"
        logger.info(f"Making API call to: {api_url}")
        
        # Include auth token in headers
        headers = {
            'Authorization': f'Bearer {auth_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        response = requests.get(api_url, headers=headers)
        logger.info(f"API Response Status: {response.status_code}")
        logger.info(f"API Response Content: {response.text}")
        
        if response.status_code == 200:
            customers_data = response.json()
            logger.info(f"Parsed customers_data: {customers_data}")
            
            if customers_data.get('status') == '200':
                customers = customers_data.get('data', {}).get('customers', [])
                logger.info(f"Found {len(customers)} customers")
            else:
                customers = []
                error_msg = customers_data.get('statusMsg', 'Failed to fetch customers')
                logger.error(f"API returned error: {error_msg}")
                messages.error(request, error_msg)
        else:
            customers = []
            logger.error(f"API request failed with status {response.status_code}")
            messages.error(request, 'Failed to fetch customers from server')
        # Add JSON string for each customer
        for c in customers:
            c['json'] = json.dumps(c)
    except Exception as e:
        logger.error(f"Error fetching customers: {str(e)}")
        customers = []
        messages.error(request, 'Error connecting to server')
    
    return render(request, 'pages/customers.html', {
        'user_data': user_data,
        'customers': customers
    })

# ------------------- User Deactivation Proxy -------------------
@csrf_exempt
@check_auth
def user_deactivate_proxy(request, user_id):
    """Proxy view for deactivating users (including vendors)"""
    if request.method == 'DELETE':
        try:
            # Get auth token from session
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': 'Authentication required',
                    'errorCode': 'UNAUTHORIZED',
                    'data': {}
                }, status=401)
            
            logger.info(f"Deactivating user with ID: {user_id}")
            
            # Make DELETE request to Java backend
            response = requests.delete(
                f"{JAVA_API_URL}/api/users/{user_id}",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                },
                timeout=30
            )
            
            logger.info(f"User deactivation API response status: {response.status_code}")
            logger.info(f"User deactivation API response: {response.text}")
            
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': response.text or 'Invalid response from backend',
                    'errorCode': 'INVALID_RESPONSE',
                    'data': {}
                }, status=500)
                
        except Exception as e:
            logger.error(f"Error in user_deactivate_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e),
                'errorCode': 'INTERNAL_ERROR',
                'data': {}
            }, status=500)
    
    return JsonResponse({
        'status': 'ERROR',
        'statusMsg': 'Method not allowed',
        'errorCode': 'METHOD_NOT_ALLOWED',
        'data': {}
    }, status=405)

# ------------------- Additional User Proxies -------------------
@csrf_exempt
@check_auth
def users_list_proxy(request):
    """Proxy view for listing users from Java API"""
    try:
        auth_token = request.session.get('auth_token')
        if not auth_token:
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': 'Authentication required',
                'errorCode': 'UNAUTHORIZED',
                'data': {}
            }, status=401)
        
        response = requests.get(
            f"{JAVA_API_URL}/api/users",
            headers={
                'Authorization': f'Bearer {auth_token}',
                'Content-Type': 'application/json'
            },
            timeout=30
        )
        
        if response.status_code != 200:
            response = requests.get(
                f"{JAVA_API_URL}/api/users/all",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                },
                timeout=30
            )
            
        try:
            data = response.json()
            return JsonResponse(data, safe=False, status=response.status_code)
        except ValueError:
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': response.text or 'Invalid response from backend',
                'errorCode': 'INVALID_RESPONSE',
                'data': {}
            }, status=500)
            
    except Exception as e:
        logger.error(f"Error in users_list_proxy: {str(e)}")
        return JsonResponse({
            'status': 'ERROR',
            'statusMsg': str(e),
            'errorCode': 'INTERNAL_ERROR',
            'data': {}
        }, status=500)

@csrf_exempt
@check_auth
def user_create_proxy(request):
    """Proxy view for creating a user in the Java API"""
    if request.method == 'POST':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': 'Authentication required',
                    'errorCode': 'UNAUTHORIZED',
                    'data': {}
                }, status=401)
            
            payload = json.loads(request.body.decode('utf-8'))
            response = requests.post(
                f"{JAVA_API_URL}/api/users",
                json=payload,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                },
                timeout=30
            )
            
            try:
                return JsonResponse(response.json(), safe=False, status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': response.text or 'Invalid response from backend',
                    'errorCode': 'INVALID_RESPONSE',
                    'data': {}
                }, status=500)
                
        except Exception as e:
            logger.error(f"Error in user_create_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e),
                'errorCode': 'INTERNAL_ERROR',
                'data': {}
            }, status=500)
            
    return JsonResponse({
        'status': 'ERROR',
        'statusMsg': 'Method not allowed',
        'errorCode': 'METHOD_NOT_ALLOWED',
        'data': {}
    }, status=405)

@csrf_exempt
@check_auth
def user_update_proxy(request, user_id):
    """Proxy view for updating a user in the Java API"""
    if request.method in ['PUT', 'POST']:
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': 'Authentication required',
                    'errorCode': 'UNAUTHORIZED',
                    'data': {}
                }, status=401)
            
            payload = json.loads(request.body.decode('utf-8'))
            response = requests.put(
                f"{JAVA_API_URL}/api/users/{user_id}",
                json=payload,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                },
                timeout=30
            )
            
            try:
                return JsonResponse(response.json(), safe=False, status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': response.text or 'Invalid response from backend',
                    'errorCode': 'INVALID_RESPONSE',
                    'data': {}
                }, status=500)
                
        except Exception as e:
            logger.error(f"Error in user_update_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e),
                'errorCode': 'INTERNAL_ERROR',
                'data': {}
            }, status=500)
            
    return JsonResponse({
        'status': 'ERROR',
        'statusMsg': 'Method not allowed',
        'errorCode': 'METHOD_NOT_ALLOWED',
        'data': {}
    }, status=405)

def debug_session(request):
    logger.info("=== DEBUG SESSION DATA ===")
    logger.info(f"All session data: {dict(request.session)}")
    logger.info(f"User data: {request.session.get('user_data')}")
    logger.info(f"Auth ID: {request.session.get('auth_id')}")
    logger.info("========================")

@check_auth
def vendor_dashboard(request):
    # Handle exiting the vendor portal preview
    if request.GET.get('exit_portal') == 'true':
        request.session.pop('is_vendor_portal', None)
        
    logger.info("=== DASHBOARD VIEW START ===")
    logger.info(f"Session keys: {list(request.session.keys())}")
    user_data = request.session.get('user_data', {})
    logger.info(f"Session user_data at dashboard: {user_data}")
    context = {'user': user_data}
    logger.info(f"Context being sent to template: {context}")
    return render(request, 'pages/vendor_dashboard.html', context)

@csrf_exempt
@check_auth
def upload_documents_proxy(request):
    if request.method == 'POST':
        try:
            # Log request details
            logger.info("Received document upload request")
            logger.info(f"Files in request: {request.FILES}")
            logger.info(f"POST data: {request.POST}")
            logger.info(f"Session data: {dict(request.session)}")  # Log session data
            
            # Get files from request
            files = {
                'gstFile': request.FILES.get('gstFile'),
                'panFile': request.FILES.get('panFile'),
                'chequeFile': request.FILES.get('chequeFile'),
                'coiFile': request.FILES.get('coiFile')
            }
            
            # Get user ID from session
            user_id = request.session.get('user_data', {}).get('superAdminId')
            if not user_id:
                logger.error("No super admin ID found in session")
                return JsonResponse({
                    'status': 'error',
                    'error': 'Super Admin ID not found'
                }, status=401)
            
            # Log the request
            logger.info(f"Processing upload for user: {user_id}")
            logger.info(f"Files received: {[key for key, value in files.items() if value]}")
            
            # Validate files
            missing_files = [key for key, value in files.items() if not value]
            if missing_files:
                logger.error(f"Missing required files: {missing_files}")
                return JsonResponse({
                    'status': 'error',
                    'error': f'Missing required files: {", ".join(missing_files)}'
                }, status=400)
            
            # Get token from session
            token = request.session.get('auth_token')
            if not token:
                logger.error("No auth token found in session")
                return JsonResponse({
                    'status': 'error',
                    'error': 'Authentication required'
                }, status=401)

            # Log file details
            for file_key, file_obj in files.items():
                logger.info(f"{file_key}: {file_obj.name}, size: {file_obj.size} bytes")

            logger.info("Making request to Java backend...")
            # Filter out None values from files to handle optional coiFile correctly
            files_to_send = {k: v for k, v in files.items() if v is not None}
            
            # Determine authKey
            auth_key = request.POST.get('authKey')
            if not auth_key:
                role = str(request.session.get('user_data', {}).get('role', '')).upper()
                auth_key = 'Customer' if role == 'CUSTOMER' else 'Vendor'
            
            logger.info(f"Using authKey: {auth_key}")
            
            # Prepare payload - ONLY authKey as per user spec
            payload_data = {
                'authKey': auth_key
            }
            logger.info(f"Sending payload data: {payload_data}")
            logger.info(f"Sending files: {list(files_to_send.keys())}")

            # Make request to Java backend
            response = requests.post(
                f"{JAVA_API_URL}/api/files/extract",
                files=files_to_send,
                data=payload_data,
                headers={
                    'Authorization': f'Bearer {token}',
                    'Accept': 'application/json'
                }
            )
            
            # Log the response status and content
            logger.info(f"Java backend response status: {response.status_code}")
            logger.info(f"Java backend response: {response.text}")
            logger.info(f"Java backend response headers: {dict(response.headers)}")
            
            if response.status_code == 200:
                try:
                    response_data = response.json()
                    logger.info("Successfully processed documents")
                    return JsonResponse(response_data)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to decode JSON response: {e}")
                    return JsonResponse({
                        'status': 'error',
                        'error': 'Invalid response from server'
                    }, status=500)
            else:
                error_message = 'Document processing failed'
                try:
                    error_data = response.json()
                    if 'message' in error_data:
                        error_message = error_data['message']
                except:
                    if response.text:
                        error_message = response.text
                logger.warning(f"Document processing failed: {error_message}")
                return JsonResponse({
                    'status': 'error',
                    'error': error_message
                }, status=response.status_code)
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Connection error to Java backend: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'error': 'Could not connect to document processing server'
            }, status=503)
        except Exception as e:
            logger.error(f"Error processing document upload: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'error': 'An error occurred while processing the documents'
            }, status=500)
            
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=400)

@require_http_methods(["GET", "POST"])
def send_email_proxy(request):
    if request.method == 'POST':
        # Add your email sending logic here
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error'}, status=400)

@require_http_methods(["GET", "POST"])
def get_company_id(request):
    """Helper to retrieve company_id from session or default to 1"""
    user_data = request.session.get('user_data', {})
    # Check multiple possible keys
    cid = user_data.get('company_id') or user_data.get('companyId') or request.session.get('company_id')
    try:
        return int(cid) if cid else 1
    except (ValueError, TypeError):
        return 1

@csrf_exempt
def store_company_id(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            company_id = data.get('companyId')
            if company_id:
                request.session['company_id'] = company_id
                # Also update user_data if present
                user_data = request.session.get('user_data', {})
                user_data['company_id'] = company_id
                request.session['user_data'] = user_data
                request.session.modified = True
                return JsonResponse({'status': 'success', 'companyId': company_id})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error'}, status=400)

@csrf_exempt
def public_material_detail_proxy(request, material_id, channel_id):
    """Proxy view for public material detail API (no authentication required)"""
    if request.method == 'GET':
        try:
            logger.info(f"Fetching public material details for material ID: {material_id}, channel ID: {channel_id}")
            
            response = requests.get(
                f"{JAVA_API_URL}/api/public/materials/{material_id}/{channel_id}",
                headers={
                    'Accept': 'application/json'
                },
                timeout=30
            )
            
            logger.info(f"Public material API response status: {response.status_code}")
            
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': response.text or 'Invalid response from backend'
                }, status=500)
                
        except Exception as e:
            logger.error(f"Error in public_material_detail_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    
    return JsonResponse({
        'status': 'ERROR',
        'statusMsg': 'Method not allowed'
    }, status=405)

@csrf_exempt
@require_GET
def public_materials_api_proxy(request, material_id, channel_id):
    """Public API proxy for materials (no authentication required)"""
    try:
        logger.info(f"Public API request for material ID: {material_id}, channel ID: {channel_id}")
        
        # Make request to Java backend
        api_url = f"{JAVA_API_URL}/api/public/materials/{material_id}/{channel_id}"
        logger.info(f"Making API call to: {api_url}")
        
        response = requests.get(
            api_url,
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            },
            timeout=30
        )
        
        logger.info(f"API Response Status: {response.status_code}")
        
        if response.status_code == 200:
            try:
                response_data = response.json()
                logger.info(f"API Response: {response_data}")
                return JsonResponse(response_data)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse API response: {e}")
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': 'Invalid response from server',
                    'errorCode': 'PARSE_ERROR',
                    'data': None,
                    'dataString': ''
                }, status=500)
        else:
            logger.error(f"API request failed with status: {response.status_code}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': f'Failed to fetch material details. Status: {response.status_code}',
                'errorCode': 'API_ERROR',
                'data': None,
                'dataString': ''
            }, status=response.status_code)
            
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error to Java backend: {e}")
        return JsonResponse({
            'status': 'ERROR',
            'statusMsg': 'Could not connect to server. Please try again later.',
            'errorCode': 'CONNECTION_ERROR',
            'data': None,
            'dataString': ''
        }, status=503)
    except Exception as e:
        logger.error(f"Error in public_materials_api_proxy: {str(e)}")
        return JsonResponse({
            'status': 'ERROR',
            'statusMsg': f'An error occurred: {str(e)}',
            'errorCode': 'INTERNAL_ERROR',
            'data': None,
            'dataString': ''
        }, status=500)

@csrf_exempt
@require_GET
def public_materials_api_proxy_flexible(request, material_id):
    """Public API proxy for materials without channel_id (no authentication required)"""
    try:
        logger.info(f"Public API request (flexible) for material ID: {material_id}")
        
        # Make request to Java backend without channel_id
        api_url = f"{JAVA_API_URL}/api/public/materials/{material_id}"
        logger.info(f"Making API call to: {api_url}")
        
        response = requests.get(
            api_url,
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            },
            timeout=30
        )
        
        logger.info(f"API Response Status: {response.status_code}")
        
        if response.status_code == 200:
            try:
                response_data = response.json()
                logger.info(f"API Response: {response_data}")
                return JsonResponse(response_data)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse API response: {e}")
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': 'Invalid response from server',
                    'errorCode': 'PARSE_ERROR',
                    'data': None,
                    'dataString': ''
                }, status=500)
        else:
            logger.error(f"API request failed with status: {response.status_code}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': f'Failed to fetch material details. Status: {response.status_code}',
                'errorCode': 'API_ERROR',
                'data': None,
                'dataString': ''
            }, status=response.status_code)
            
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error to Java backend: {e}")
        return JsonResponse({
            'status': 'ERROR',
            'statusMsg': 'Could not connect to server. Please try again later.',
            'errorCode': 'CONNECTION_ERROR',
            'data': None,
            'dataString': ''
        }, status=503)
    except Exception as e:
        logger.error(f"Error in public_materials_api_proxy_flexible: {str(e)}")
        return JsonResponse({
            'status': 'ERROR',
            'statusMsg': f'An error occurred: {str(e)}',
            'errorCode': 'INTERNAL_ERROR',
            'data': None,
            'dataString': ''
        }, status=500)

@csrf_exempt
def public_product_detail_view(request, material_id, channel_id):
    """Public view for displaying individual product details (no authentication required)"""
    try:
        logger.info(f"Loading public product detail for material ID: {material_id}, channel ID: {channel_id}")
        
        # Make direct request to Java backend API
        api_url = f"{JAVA_API_URL}/api/public/materials/{material_id}/{channel_id}"
        logger.info(f"Making API call to: {api_url}")
        
        material_response = requests.get(
            api_url,
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            },
            timeout=30
        )
        
        logger.info(f"API Response Status: {material_response.status_code}")
        
        if material_response.status_code != 200:
            logger.error(f"Failed to fetch public material {material_id}/{channel_id}: {material_response.status_code}")
            
            # Return error response when API fails
            logger.error(f"Failed to fetch public material {material_id}/{channel_id}: {material_response.status_code}")
            return JsonResponse({
                "status": "ERROR",
                "statusMsg": "Failed to retrieve material details",
                "errorCode": "MATERIAL_NOT_FOUND",
                "data": None
            }, status=404)
        
        # If Java API returned success, use real data
        if material_response.status_code == 200:
            material_data = material_response.json()
            logger.info(f"Parsed JSON response: {material_data}")
            
            if material_data.get('status') != 'SUCCESS':
                logger.error(f"Public API error for material {material_id}/{channel_id}: {material_data.get('statusMsg')}")
                return render(request, 'pages/error.html', {
                    'error_message': material_data.get('statusMsg', 'Product not found')
                })
            
            # Extract material details from the nested structure
            material_details = material_data.get('data', {}).get('materialDetails', {})
            logger.info(f"Material details extracted: {material_details}")
            
            # Process images
            first_image_base64 = material_data.get('data', {}).get('firstImageBase64')
            total_images = material_data.get('data', {}).get('totalImages', 0)
            
            logger.info(f"Raw firstImageBase64 length: {len(first_image_base64) if first_image_base64 else 0}")
            logger.info(f"Total images: {total_images}")
            logger.info(f"Material images count: {len(material_details.get('materialImages', []))}")
            
            # Clean up the base64 data if it has a leading slash
            if first_image_base64 and first_image_base64.startswith('/'):
                first_image_base64 = first_image_base64[1:]
                logger.info("Removed leading slash from firstImageBase64")
            
            # Process material images - add imageData field for template compatibility
            if material_details.get('materialImages'):
                logger.info(f"Processing {len(material_details['materialImages'])} material images")
                
                for i, image in enumerate(material_details['materialImages']):
                    logger.info(f"Image {i}: {image.get('imageName', 'unnamed')}, isPrimary: {image.get('isPrimary', False)}")
                    
                    # If image has imageBase64, copy it to imageData for template compatibility
                    if image.get('imageBase64'):
                        # Clean up the base64 data if it has a leading slash
                        image_base64 = image['imageBase64']
                        if image_base64.startswith('/'):
                            image_base64 = image_base64[1:]
                            logger.info(f"Removed leading slash from image {i}")
                        
                        # Ensure the base64 data is valid
                        if len(image_base64) > 50:  # Basic validation
                            image['imageData'] = image_base64
                            logger.info(f"Added imageData to image {i}: {image.get('imageName')} (length: {len(image_base64)})")
                        else:
                            logger.warning(f"Image {i} has invalid base64 data (too short): {len(image_base64)}")
                    else:
                        logger.warning(f"Image {i} has no imageBase64 data")
            
            # Process barcode image
            barcode_image = material_details.get('barcodeImage')
            if barcode_image:
                logger.info(f"Processing barcode image (length: {len(barcode_image)})")
                # Clean up the barcode base64 data if it has a leading slash
                if barcode_image.startswith('/'):
                    barcode_image = barcode_image[1:]
                    logger.info("Removed leading slash from barcode image")
                
                # Ensure the barcode base64 data is valid
                if len(barcode_image) > 50:  # Basic validation
                    material_details['barcodeImage'] = barcode_image
                    logger.info(f"Barcode image processed successfully (length: {len(barcode_image)})")
                else:
                    logger.warning(f"Barcode image has invalid base64 data (too short): {len(barcode_image)}")
                    material_details['barcodeImage'] = None
            
            # Process firstImageBase64 - add it to the primary image or first image if they don't have data
            if first_image_base64 and material_details.get('materialImages'):
                logger.info(f"Processing firstImageBase64 (length: {len(first_image_base64)})")
                
                # Clean up the firstImageBase64 if it has a leading slash
                if first_image_base64.startswith('/'):
                    first_image_base64 = first_image_base64[1:]
                    logger.info("Removed leading slash from firstImageBase64")
                
                # Find primary image first
                primary_image = None
                for image in material_details['materialImages']:
                    if image.get('isPrimary', False):
                        primary_image = image
                        break
                
                # If primary image exists and doesn't have imageData, use firstImageBase64
                if primary_image and not primary_image.get('imageData'):
                    primary_image['imageData'] = first_image_base64
                    logger.info(f"Added firstImageBase64 to primary image: {primary_image.get('imageName')}")
                # If no primary image or primary image already has data, use first image
                elif material_details['materialImages'] and not material_details['materialImages'][0].get('imageData'):
                    material_details['materialImages'][0]['imageData'] = first_image_base64
                    logger.info(f"Added firstImageBase64 to first image: {material_details['materialImages'][0].get('imageName')}")
            
            # Extract remaining products from the API response
            remaining_products = material_data.get('data', {}).get('remainingProducts', [])
            logger.info(f"Remaining products count: {len(remaining_products)}")
            
            return render(request, 'pages/public_product_detail.html', {
                'material': material_details,
                'channel_id': channel_id,
                'company_id': material_details.get('channelId'),  # Using channelId as company_id for now
                'total_images': total_images,
                'firstImageBase64': first_image_base64,
                'remaining_products': remaining_products
            })
        
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error to Java backend: {e}")
        return render(request, 'pages/error.html', {
            'error_message': 'Could not connect to server. Please try again later.'
        })
    except Exception as e:
        logger.error(f"Error in public_product_detail_view: {str(e)}")
        return render(request, 'pages/error.html', {
            'error_message': f'An error occurred while loading the product: {str(e)}'
        })

@csrf_exempt
def public_product_detail_auto_view(request, material_id):
    """Public view for displaying individual product details without channel_id (auto-detects channel)"""
    try:
        logger.info(f"Loading public product detail (auto) for material ID: {material_id}")
        
        # Try to get channel_id from query parameters or use default
        channel_id = request.GET.get('channel_id') or request.GET.get('channelId')
        
        # If no channel_id provided, try to get from session or use a default
        if not channel_id:
            # Try to get from session
            channel_id = request.session.get('channel_id') or request.session.get('channelId')
        
        # If still no channel_id, use flexible API endpoint
        if channel_id:
            # Use the regular endpoint with channel_id
            api_url = f"{JAVA_API_URL}/api/public/materials/{material_id}/{channel_id}"
        else:
            # Use flexible endpoint without channel_id
            api_url = f"{JAVA_API_URL}/api/public/materials/{material_id}"
        
        logger.info(f"Making API call to: {api_url}")
        
        material_response = requests.get(
            api_url,
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            },
            timeout=30
        )
        
        logger.info(f"API Response Status: {material_response.status_code}")
        
        if material_response.status_code != 200:
            logger.error(f"Failed to fetch public material {material_id}: {material_response.status_code}")
            return JsonResponse({
                "status": "ERROR",
                "statusMsg": "Failed to retrieve material details",
                "errorCode": "MATERIAL_NOT_FOUND",
                "data": None
            }, status=404)
        
        # If Java API returned success, use real data
        if material_response.status_code == 200:
            material_data = material_response.json()
            logger.info(f"Parsed JSON response: {material_data}")
            
            if material_data.get('status') != 'SUCCESS':
                logger.error(f"Public API error for material {material_id}: {material_data.get('statusMsg')}")
                return render(request, 'pages/error.html', {
                    'error_message': material_data.get('statusMsg', 'Product not found')
                })
            
            # Extract material details from the nested structure
            material_details = material_data.get('data', {}).get('materialDetails', {})
            logger.info(f"Material details extracted: {material_details}")
            
            # Get channel_id from material details if not already set
            if not channel_id:
                channel_id = material_details.get('channelId')
            
            # Process images
            first_image_base64 = material_data.get('data', {}).get('firstImageBase64')
            total_images = material_data.get('data', {}).get('totalImages', 0)
            
            # Clean up the base64 data if it has a leading slash
            if first_image_base64 and first_image_base64.startswith('/'):
                first_image_base64 = first_image_base64[1:]
            
            # Process material images - add imageData field for template compatibility
            if material_details.get('materialImages'):
                for i, image in enumerate(material_details['materialImages']):
                    if image.get('imageBase64'):
                        image_base64 = image['imageBase64']
                        if image_base64.startswith('/'):
                            image_base64 = image_base64[1:]
                        
                        if len(image_base64) > 50:
                            image['imageData'] = image_base64
            
            # Process barcode image
            barcode_image = material_details.get('barcodeImage')
            if barcode_image:
                if barcode_image.startswith('/'):
                    barcode_image = barcode_image[1:]
                
                if len(barcode_image) > 50:
                    material_details['barcodeImage'] = barcode_image
                else:
                    material_details['barcodeImage'] = None
            
            # Process firstImageBase64
            if first_image_base64 and material_details.get('materialImages'):
                if first_image_base64.startswith('/'):
                    first_image_base64 = first_image_base64[1:]
                
                primary_image = None
                for image in material_details['materialImages']:
                    if image.get('isPrimary', False):
                        primary_image = image
                        break
                
                if primary_image and not primary_image.get('imageData'):
                    primary_image['imageData'] = first_image_base64
                elif material_details['materialImages'] and not material_details['materialImages'][0].get('imageData'):
                    material_details['materialImages'][0]['imageData'] = first_image_base64
            
            # Extract remaining products from the API response
            remaining_products = material_data.get('data', {}).get('remainingProducts', [])
            
            return render(request, 'pages/public_product_detail.html', {
                'material': material_details,
                'channel_id': channel_id,
                'company_id': material_details.get('channelId'),
                'total_images': total_images,
                'firstImageBase64': first_image_base64,
                'remaining_products': remaining_products
            })
        
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error to Java backend: {e}")
        return render(request, 'pages/error.html', {
            'error_message': 'Could not connect to server. Please try again later.'
        })
    except Exception as e:
        logger.error(f"Error in public_product_detail_auto_view: {str(e)}")
        return render(request, 'pages/error.html', {
            'error_message': f'An error occurred while loading the product: {str(e)}'
        })

@require_http_methods(["GET", "POST"])
@check_auth
def confirm_documents(request):
    if request.method == 'POST':
        try:
            # Get data from request
            data = json.loads(request.body)
            
            # Get token from session
            token = request.session.get('auth_token')
            if not token:
                logger.error("No auth token found in session")
                return JsonResponse({
                    'status': 'error',
                    'error': 'Authentication required'
                }, status=401)

            # Get user ID from session and validate it matches the payload
            session_user_id = request.session.get('user_data', {}).get('superAdminId')
            payload_user_id = data.get('userId')
            
            if not session_user_id:
                logger.error("No super admin ID found in session")
                return JsonResponse({
                    'status': 'error',
                    'error': 'Super Admin ID not found in session'
                }, status=401)
            
            if str(session_user_id) != str(payload_user_id):
                logger.error(f"User ID mismatch: session={session_user_id}, payload={payload_user_id}")
                return JsonResponse({
                    'status': 'error',
                    'error': 'Invalid user ID'
                }, status=403)

            # Log the request
            logger.info(f"Confirming documents for user: {session_user_id}")
            logger.info(f"Request payload: {data}")

            # Call the confirm API
            confirm_response = requests.post(
                f"{JAVA_API_URL}/api/files/confirm",
                json=data,
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {token}',
                    'Accept': 'application/json'
                }
            )
            
            # Log the response
            logger.info(f"Java backend response status: {confirm_response.status_code}")
            logger.info(f"Java backend response: {confirm_response.text}")
            
            if confirm_response.status_code == 200:
                # If confirmation successful, send email
                email_data = {
                    "userId": session_user_id,
                    "subject": "Welcome to Aequm",
                    "body": "Hi User,\n\nThanks for uploading your documents!\n\nRegards,\nAequm Team"
                }
                
                email_response = requests.post(
                    f"{JAVA_API_URL}/email/send",
                    json=email_data,
                    headers={
                        'Content-Type': 'application/json',
                        'Authorization': f'Bearer {token}'
                    }
                )
                
                if email_response.status_code == 200:
                    return JsonResponse({
                        'status': 'success',
                        'message': 'Documents confirmed and email sent successfully'
                    })
                else:
                    return JsonResponse({
                        'status': 'warning',
                        'message': 'Documents confirmed but email sending failed',
                        'email_error': email_response.text
                    })
            else:
                error_message = 'Failed to confirm documents'
                try:
                    error_data = confirm_response.json()
                    if 'message' in error_data:
                        error_message = error_data['message']
                except:
                    if confirm_response.text:
                        error_message = confirm_response.text
                logger.error(f"Document confirmation failed: {error_message}")
                return JsonResponse({
                    'status': 'error',
                    'error': error_message
                }, status=confirm_response.status_code)
                
        except json.JSONDecodeError:
            logger.error("Invalid JSON in request body")
            return JsonResponse({
                'status': 'error',
                'error': 'Invalid JSON data'
            }, status=400)
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to connect to backend service: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'error': f'Failed to connect to backend service: {str(e)}'
            }, status=503)
        except Exception as e:
            logger.error(f"Unexpected error during document confirmation: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'error': f'An unexpected error occurred: {str(e)}'
            }, status=500)
            
    return JsonResponse({'status': 'error', 'error': 'Method not allowed'}, status=405)

@check_auth
def download_report(request):
    try:
        # Get user ID from session
        user_data = request.session.get('user_data', {})
        user_id = user_data.get('superAdminId')
        
        if not user_id:
            messages.error(request, 'User ID not found. Please log in again.')
            return redirect('pages:vendor_dashboard')

        # Make request to Java backend for Excel export
        response = requests.get(
            f"{JAVA_API_URL}/api/export/user/{user_id}",
            headers={
                'Authorization': f'Bearer {request.session.get("auth_token")}',
                'Accept': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            }
        )
        
        if response.status_code == 200:
            # Create the HttpResponse object with Excel content
            django_response = HttpResponse(
                response.content,
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            django_response['Content-Disposition'] = 'attachment; filename="user_report.xlsx"'
            return django_response
        else:
            logger.error(f"Failed to download report. Status code: {response.status_code}")
            logger.error(f"Response content: {response.text}")
            messages.error(request, 'Failed to download report. Please try again later.')
            return redirect('pages:vendor_dashboard')
            
    except Exception as e:
        logger.error(f"Error downloading report: {str(e)}")
        messages.error(request, 'An error occurred while downloading the report.')
        return redirect('pages:vendor_dashboard') 

@check_auth
def customer_documents(request, user_id):
    # You may want to fetch the user data from your user model, for now just pass user_id
    # If you have a User model, you can fetch user details here
    # user = get_object_or_404(User, pk=user_id)
    return render(request, 'pages/customer_documents.html', {'user_id': user_id}) 

@csrf_exempt
@check_auth
def extract_documents(request):
    if request.method == 'POST':
        try:
            files = {
                'gstFile': request.FILES.get('gstFile'),
                'panFile': request.FILES.get('panFile'),
                'chequeFile': request.FILES.get('chequeFile'),
                'coiFile': request.FILES.get('coiFile')
            }
            
            # Filter out None values from files to handle optional coiFile correctly
            files_to_send = {k: v for k, v in files.items() if v is not None}
            
            # Determine authKey
            auth_key = request.POST.get('authKey')
            if not auth_key:
                role = str(request.session.get('user_data', {}).get('role', '')).upper()
                auth_key = 'Customer' if role == 'CUSTOMER' else 'Vendor'
            
            logger.info(f"Using authKey: {auth_key}")
            
            token = request.session.get('auth_token')
            if not token:
                logger.error("No auth token found in session")
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)

            # Prepared payload - ONLY authKey as per user spec
            payload_data = {
                'authKey': auth_key
            }
            
            logger.info(f"Sending payload data: {payload_data}")
            logger.info(f"Sending files: {list(files_to_send.keys())}")

            response = requests.post(
                f"{JAVA_API_URL}/api/files/extract",
                files=files_to_send,
                data=payload_data,
                headers={
                    'Authorization': f'Bearer {token}',
                    'Accept': 'application/json'
                }
            )
            
            logger.info(f"Java backend response status: {response.status_code}")
            
            if response.status_code == 200:
                return JsonResponse(response.json())
            else:
                error_msg = 'Failed to extract documents'
                try:
                    error_data = response.json()
                    error_msg = error_data.get('error', error_msg) or error_data.get('message', error_msg)
                except:
                    error_msg = response.text or error_msg
                logger.error(f"Extraction failed: {error_msg}")
                return JsonResponse({'status': 'error', 'error': error_msg}, status=response.status_code)
                
        except Exception as e:
            logger.error(f"Error in extract_documents: {str(e)}")
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=400)

@csrf_exempt
@check_auth
def complete_registration(request):
    if request.method == 'POST':
        try:
            # Get the auth token from session
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({
                    'status': 'error',
                    'error': 'Authentication required'
                }, status=401)

            # Get the payload from request
            payload = json.loads(request.body)
            
            # Make request to Java backend
            response = requests.post(
                f"{JAVA_API_URL}/api/registration/complete",
                json=payload,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                }
            )
            
            # Return the response from Java backend
            return JsonResponse(response.json(), status=response.status_code)
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in request: {e}")
            return JsonResponse({
                'status': 'error',
                'error': 'Invalid request format'
            }, status=400)
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error to Java backend: {e}")
            return JsonResponse({
                'status': 'error',
                'error': 'Could not connect to server. Please try again later.'
            }, status=503)
        except Exception as e:
            logger.error(f"Unexpected error during registration completion: {e}")
            return JsonResponse({
                'status': 'error',
                'error': 'An unexpected error occurred. Please try again.'
            }, status=500)
            
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=400)

@check_auth
def registration_complete(request):
    if request.method == 'POST':
        try:
            # Get the payload from the request
            payload = json.loads(request.body)
            logger.info(f"Registration complete payload: {payload}")
            
            # Get the auth token from the session
            auth_token = request.session.get('auth_token')
            if not auth_token:
                logger.error("No auth token found in session")
                return JsonResponse({
                    'status': '401',
                    'statusMsg': 'Authentication token not found'
                }, status=401)
            
            # Make the API call to the Java backend
            headers = {
                'Authorization': f'Bearer {auth_token}',
                'Content-Type': 'application/json'
            }
            
            logger.info(f"Making request to Java backend with headers: {headers}")
            response = requests.post(
                f"{JAVA_API_URL}/api/registration/complete",
                json=payload,
                headers=headers
            )
            
            logger.info(f"Java backend response status: {response.status_code}")
            logger.info(f"Java backend response: {response.text}")
            
            # Return the response from the Java backend
            return JsonResponse(response.json(), status=response.status_code)
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in request: {e}")
            return JsonResponse({
                'status': '400',
                'statusMsg': 'Invalid request format'
            }, status=400)
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error to Java backend: {e}")
            return JsonResponse({
                'status': '503',
                'statusMsg': 'Could not connect to server. Please try again later.'
            }, status=503)
        except Exception as e:
            logger.error(f"Error in registration_complete: {str(e)}")
            return JsonResponse({
                'status': '500',
                'statusMsg': str(e)
            }, status=500)
    
    return JsonResponse({
        'status': '405',
        'statusMsg': 'Method not allowed'
    }, status=405)

@csrf_exempt
@check_auth
def financial_terms_save(request):
    if request.method == 'POST':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
            payload = json.loads(request.body)
            response = requests.post(
                f"{JAVA_API_URL}/api/financial-terms/save",
                json=payload,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                }
            )
            return JsonResponse(response.json(), status=response.status_code)
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=400)

@csrf_exempt
@check_auth
def financial_terms_get(request):
    if request.method == 'GET':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
            
            gstin_number = request.GET.get('gstinNumber')
            auth_key = request.GET.get('authKey')
            
            if not gstin_number or not auth_key:
                return JsonResponse({'status': 'error', 'error': 'Missing required parameters'}, status=400)
            
            response = requests.get(
                f"{JAVA_API_URL}/api/financial-terms/get",
                params={'gstinNumber': gstin_number, 'authKey': auth_key},
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                }
            )
            return JsonResponse(response.json(), status=response.status_code)
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=400)

@csrf_exempt
@check_auth
def financial_terms_customer_save(request):
    if request.method == 'POST':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
            payload = json.loads(request.body)
            response = requests.post(
                f"{JAVA_API_URL}/api/financial-terms-customer/save",
                json=payload,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                }
            )
            return JsonResponse(response.json(), status=response.status_code)
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=400)

@csrf_exempt
@check_auth
def financial_terms_customer_get(request):
    if request.method == 'GET':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
            gstin_number = request.GET.get('gstinNumber')
            auth_key = request.GET.get('authKey')
            if not gstin_number or not auth_key:
                return JsonResponse({'status': 'error', 'error': 'Missing required parameters'}, status=400)
            response = requests.get(
                f"{JAVA_API_URL}/api/financial-terms-customer/get",
                params={'gstinNumber': gstin_number, 'authKey': auth_key},
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                }
            )
            return JsonResponse(response.json(), status=response.status_code)
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=400)

@check_auth
def material_bom_page(request):
    """Standalone Material BOM generation page."""
    return render(request, 'pages/material-bom.html')

@check_auth
def material_list(request):
    if request.method == 'GET':
        materials = Material.objects.all()
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            data = [model_to_dict(m) for m in materials]
            return JsonResponse({'materials': data})
        return render(request, 'pages/materials.html', {'materials': materials})

@check_auth
@require_POST
def material_create(request):
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        form = MaterialForm(request.POST, request.FILES)
        if form.is_valid():
            material = form.save()
            return JsonResponse({'status': 'success', 'material': model_to_dict(material)})
        return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)
    return JsonResponse({'status': 'error', 'error': 'Invalid request'}, status=400)

@check_auth
@require_POST
def material_edit(request, pk):
    material = get_object_or_404(Material, pk=pk)
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        form = MaterialForm(request.POST, request.FILES, instance=material)
        if form.is_valid():
            material = form.save()
            return JsonResponse({'status': 'success', 'material': model_to_dict(material)})
        return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)
    return JsonResponse({'status': 'error', 'error': 'Invalid request'}, status=400)

@check_auth
@require_POST
def material_delete(request, pk):
    material = get_object_or_404(Material, pk=pk)
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        material.delete()
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error', 'error': 'Invalid request'}, status=400)

@csrf_exempt
@check_auth
def financial_terms_update(request):
    if request.method == 'POST':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
            payload = json.loads(request.body)
            response = requests.post(
                f"{JAVA_API_URL}/api/financial-terms/update",
                json=payload,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                }
            )
            return JsonResponse(response.json(), status=response.status_code)
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=400)

@csrf_exempt
@check_auth
def financial_terms_customer_update(request):
    if request.method == 'POST':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
            payload = json.loads(request.body)
            response = requests.post(
                f"{JAVA_API_URL}/api/financial-terms-customer/update",
                json=payload,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                }
            )
            return JsonResponse(response.json(), status=response.status_code)
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=400)

@csrf_exempt
@check_auth
def material_types_proxy(request):
    if request.method == 'GET':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
            response = requests.get(
                f"{JAVA_API_URL}/api/material-types",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                }
            )
            return JsonResponse(response.json(), status=response.status_code)
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=400)

@csrf_exempt
@check_auth
def base_units_proxy(request):
    if request.method == 'GET':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
            response = requests.get(
                f"{JAVA_API_URL}/api/base-units",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                }
            )
            return JsonResponse(response.json(), status=response.status_code)
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=400)

@csrf_exempt
@check_auth
def item_categories_proxy(request):
    if request.method == 'GET':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
            response = requests.get(
                f"{JAVA_API_URL}/api/item-categories",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                }
            )
            return JsonResponse(response.json(), status=response.status_code)
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=400)

@csrf_exempt
@check_auth
def item_subcategories_save_proxy(request):
    if request.method == 'POST':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
            payload = json.loads(request.body)
            response = requests.post(
                f"{JAVA_API_URL}/api/item-subcategories/save",
                json=payload,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                }
            )
            return JsonResponse(response.json(), status=response.status_code)
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=400)

@csrf_exempt
@check_auth
def item_subcategories_with_category_details_proxy(request):
    if request.method == 'GET':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)

            response = requests.get(
                f"{JAVA_API_URL}/api/item-subcategories/with-category-details",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                }
            )

            response.raise_for_status() 
            return JsonResponse(response.json())
        except requests.exceptions.HTTPError as http_err:
            logger.error(f"HTTP error occurred: {http_err} - {response.text}")
            return JsonResponse({'status': 'error', 'error': 'Failed to retrieve subcategories'}, status=response.status_code)
        except Exception as e:
            logger.error(f"An error occurred: {e}")
            return JsonResponse({'status': 'error', 'error': 'An internal server error occurred'}, status=500)

    return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=400)

@csrf_exempt
@check_auth
def material_detail_proxy(request, material_id):
    if request.method == 'GET':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
            
            response = requests.get(
                f"{JAVA_API_URL}/api/materials/{material_id}",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/json'
                }
            )
            
            logger.info(f"Java backend response status for material detail: {response.status_code}")
            # logger.info(f"Java backend response for material detail: {response.text}")

            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': '500',
                    'statusMsg': response.text or 'Invalid response from backend'
                }, status=500)
        except Exception as e:
            logger.error(f"Error in material_detail_proxy: {str(e)}")
            return JsonResponse({'status': '500', 'statusMsg': str(e)}, status=500)
    return JsonResponse({'status': '405', 'statusMsg': 'Method not allowed'}, status=405)

@csrf_exempt
@check_auth
def materials_list_proxy(request):
    if request.method == 'GET':
        try:
            # Get auth token from session
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)

            # Forward request to Java backend
            response = requests.get(
                f"{JAVA_API_URL}/api/materials",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/json'
                }
            )

            # Log response for debugging
            logger.info(f"Java backend response status: {response.status_code}")
            logger.info(f"Java backend response: {response.text}")

            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': '500',
                    'statusMsg': response.text or 'Invalid response from backend',
                    'errorCode': '500',
                    'data': {},
                    'dataString': ''
                }, status=500)
        except Exception as e:
            logger.error(f"Error in materials_list_proxy: {str(e)}")
            return JsonResponse({
                'status': '500',
                'statusMsg': str(e),
                'errorCode': '500',
                'data': {},
                'dataString': ''
            }, status=500)
    return JsonResponse({
        'status': '405',
        'statusMsg': 'Method not allowed',
        'errorCode': '405',
        'data': {},
        'dataString': ''
    }, status=405)

@csrf_exempt
@check_auth
@require_POST
def materials_save_proxy(request):
    try:
        auth_token = request.session.get('auth_token')
        if not auth_token:
            return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)

        # Prepare data and files for forwarding
        data_to_forward = request.POST.dict()
        files_to_forward = []

        if 'barcodeImage' in request.FILES:
            barcode = request.FILES['barcodeImage']
            files_to_forward.append(('barcodeImage', (barcode.name, barcode.read(), barcode.content_type)))
        
        if 'materialImages' in request.FILES:
            for img in request.FILES.getlist('materialImages'):
                files_to_forward.append(('materialImages', (img.name, img.read(), img.content_type)))

        # Log for debugging
        logger.info(f"Forwarding multipart request. Data keys: {data_to_forward.keys()}, Files: {[f[0] for f in files_to_forward]}")

        # Forward request to Java backend
        resp = requests.post(
            f"{JAVA_API_URL}/api/materials/save",
            data=data_to_forward,
            files=files_to_forward,
            headers={
                'Authorization': f'Bearer {auth_token}'
            }
        )

        logger.info(f"Java backend response status: {resp.status_code}")
        logger.info(f"Java backend response: {resp.text}")

        try:
            return JsonResponse(resp.json(), status=resp.status_code)
        except ValueError:
            return JsonResponse({
                'status': 'error',
                'statusMsg': resp.text or 'No response from backend',
                'errorCode': resp.status_code
            }, status=resp.status_code)

    except Exception as e:
        logger.error(f"Error in materials_save_proxy: {str(e)}")
        return JsonResponse({'status': '500', 'statusMsg': str(e)}, status=500)

@csrf_exempt
@check_auth
@require_POST
def materials_bulk_save_with_images_proxy(request):
    try:
        auth_token = request.session.get('auth_token')
        if not auth_token:
            return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)

        # Prepare data and files for forwarding
        data_to_forward = {}
        
        # Extract materialsJson from POST data
        if 'materialsJson' in request.POST:
            data_to_forward['materialsJson'] = request.POST['materialsJson']
        
        files_to_forward = []
        
        # Extract all material images
        if 'materialImages' in request.FILES:
            for img in request.FILES.getlist('materialImages'):
                files_to_forward.append(('materialImages', (img.name, img.read(), img.content_type)))

        # Log for debugging
        logger.info(f"Forwarding bulk save multipart request. Data keys: {data_to_forward.keys()}, Files: {len(files_to_forward)}")

        # Forward request to Java backend
        resp = requests.post(
            f"{JAVA_API_URL}/api/materials/bulk-save-with-images",
            data=data_to_forward,
            files=files_to_forward,
            headers={
                'Authorization': f'Bearer {auth_token}'
            }
        )

        logger.info(f"Java backend response status: {resp.status_code}")
        logger.info(f"Java backend response: {resp.text}")

        try:
            return JsonResponse(resp.json(), status=resp.status_code)
        except ValueError:
            return JsonResponse({
                'status': 'error',
                'statusMsg': resp.text or 'No response from backend',
                'errorCode': resp.status_code
            }, status=resp.status_code)

    except Exception as e:
        logger.error(f"Error in materials_bulk_save_with_images_proxy: {str(e)}")
        return JsonResponse({'status': '500', 'statusMsg': str(e)}, status=500)

@csrf_exempt
@check_auth
def materials_image_sequence_proxy(request):
    if request.method == 'PUT':
        try:
            # Get auth token from session
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)

            # Forward request to Java backend
            response = requests.put(
                f"{JAVA_API_URL}/api/materials/images/sequence",
                json=json.loads(request.body),
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                }
            )

            # Log response for debugging
            logger.info(f"Java backend response status: {response.status_code}")
            logger.info(f"Java backend response: {response.text}")

            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': '500',
                    'statusMsg': response.text or 'Invalid response from backend',
                    'errorCode': '500',
                    'data': {},
                    'dataString': ''
                }, status=500)
        except Exception as e:
            logger.error(f"Error in materials_image_sequence_proxy: {str(e)}")
            return JsonResponse({
                'status': '500',
                'statusMsg': str(e),
                'errorCode': '500',
                'data': {},
                'dataString': ''
            }, status=500)
    return JsonResponse({
        'status': '405',
        'statusMsg': 'Method not allowed',
        'errorCode': '405',
        'data': {},
        'dataString': ''
    }, status=405) 

@csrf_exempt
@check_auth
@require_POST
def attributes_bulk_proxy(request):
    try:
        auth_token = request.session.get('auth_token')
        if not auth_token:
            return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
        payload = json.loads(request.body)
        response = requests.post(
            f"{JAVA_API_URL}/api/attributes/bulk",
            json=payload,
            headers={
                'Authorization': f'Bearer {auth_token}',
                'Content-Type': 'application/json'
            }
        )
        return JsonResponse(response.json(), status=response.status_code)
    except Exception as e:
        return JsonResponse({'status': 'error', 'error': str(e)}, status=500) 

@csrf_exempt
@check_auth
def attributes_list_proxy(request):
    if request.method == 'GET':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
            response = requests.get(
                f"{JAVA_API_URL}/api/attributes",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                }
            )
            return JsonResponse(response.json(), status=response.status_code)
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=400) 

@csrf_exempt
@check_auth
def attributes_by_type_proxy(request, attr_type):
    if request.method == 'GET':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
            
            if attr_type.upper() not in ['VARIANT', 'GENERAL']:
                return JsonResponse({'status': 'error', 'error': 'Invalid attribute type'}, status=400)

            response = requests.get(
                f"{JAVA_API_URL}/api/attributes/by-type/{attr_type.upper()}",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                }
            )
            return JsonResponse(response.json(), status=response.status_code)
        except requests.exceptions.RequestException as e:
            return JsonResponse({'status': 'error', 'error': f'Failed to connect to backend service: {e}'}, status=502)
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=400) 

# New views for variant system
@check_auth
def variant_matrix(request):
    """Display the variant matrix creation interface"""
    materials = Material.objects.filter(material_type='FERT').order_by('material_name')
    variant_attributes = Attribute.objects.filter(type='VARIANT', is_active=True).order_by('name')
    
    context = {
        'materials': materials,
        'variant_attributes': variant_attributes,
    }
    return render(request, 'pages/variant_matrix.html', context)

@csrf_exempt
@check_auth
def generate_variants(request):
    """Generate variants based on the matrix input"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            material_id = data.get('material_id')
            attribute_values = data.get('attribute_values', {})
            
            if not material_id or not attribute_values:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Material ID and attribute values are required'
                }, status=400)
            
            material = get_object_or_404(Material, pk=material_id)
            
            # Generate all combinations
            attribute_names = list(attribute_values.keys())
            attribute_value_lists = list(attribute_values.values())
            
            # Filter out empty values
            filtered_combinations = []
            for combination in product(*attribute_value_lists):
                # Only include combinations where all values are non-empty
                if all(value.strip() for value in combination):
                    filtered_combinations.append(combination)
            
            # Generate variants
            created_variants = []
            for i, combination in enumerate(filtered_combinations, 1):
                # Generate variant code
                variant_code = f"{material.sku}-{i:04d}"
                
                # Create variant
                variant = MaterialVariant.objects.create(
                    variant_code=variant_code,
                    material=material,
                    mrp=data.get('default_mrp', 0),
                    sp=data.get('default_sp', 0),
                    cost=data.get('default_cost', 0),
                    barcode=f"{material.sku}{i:04d}"
                )
                
                # Create attribute values
                for attr_name, attr_value in zip(attribute_names, combination):
                    attribute, created = Attribute.objects.get_or_create(
                        name=attr_name,
                        defaults={'type': 'VARIANT'}
                    )
                    
                    MaterialVariantAttributeValue.objects.create(
                        variant=variant,
                        attribute=attribute,
                        value=attr_value.strip()
                    )
                
                created_variants.append({
                    'variant_code': variant.variant_code,
                    'attribute_values': dict(zip(attribute_names, combination))
                })
            
            return JsonResponse({
                'status': 'success',
                'message': f'Successfully created {len(created_variants)} variants',
                'variants': created_variants
            })
            
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

@check_auth
def variant_list(request, material_id=None):
    """Display list of variants for a material"""
    if material_id:
        material = get_object_or_404(Material, pk=material_id)
        variants = MaterialVariant.objects.filter(material=material).prefetch_related('attribute_values__attribute')
    else:
        material = None
        variants = MaterialVariant.objects.select_related('material').prefetch_related('attribute_values__attribute')
    
    context = {
        'material': material,
        'variants': variants,
    }
    return render(request, 'pages/variant_list.html', context)

@csrf_exempt
@check_auth
def variant_detail(request, variant_id):
    """Get or update variant details"""
    variant = get_object_or_404(MaterialVariant, pk=variant_id)
    
    if request.method == 'GET':
        attribute_values = {}
        for attr_val in variant.attribute_values.all():
            attribute_values[attr_val.attribute.name] = attr_val.value
        
        data = {
            'id': variant.id,
            'variant_code': variant.variant_code,
            'material_name': variant.material.material_name,
            'material_sku': variant.material.sku,
            'barcode': variant.barcode,
            'mrp': float(variant.mrp),
            'sp': float(variant.sp),
            'cost': float(variant.cost),
            'current_stock': float(variant.current_stock),
            'is_active': variant.is_active,
            'vendor_details': variant.vendor_details,
            'customer_details': variant.customer_details,
            'attribute_values': attribute_values,
            'created_at': variant.created_at.isoformat(),
            'updated_at': variant.updated_at.isoformat(),
        }
        return JsonResponse({'status': 'success', 'data': data})
    
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            # Update variant fields
            if 'mrp' in data:
                variant.mrp = data['mrp']
            if 'sp' in data:
                variant.sp = data['sp']
            if 'cost' in data:
                variant.cost = data['cost']
            if 'current_stock' in data:
                variant.current_stock = data['current_stock']
            if 'barcode' in data:
                variant.barcode = data['barcode']
            if 'is_active' in data:
                variant.is_active = data['is_active']
            if 'vendor_details' in data:
                variant.vendor_details = data['vendor_details']
            if 'customer_details' in data:
                variant.customer_details = data['customer_details']
            
            variant.save()
            
            return JsonResponse({
                'status': 'success',
                'message': 'Variant updated successfully'
            })
            
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

@csrf_exempt
@check_auth
def delete_variant(request, variant_id):
    """Delete a variant"""
    if request.method == 'POST':
        try:
            variant = get_object_or_404(MaterialVariant, pk=variant_id)
            variant_code = variant.variant_code
            variant.delete()
            
            return JsonResponse({
                'status': 'success',
                'message': f'Variant {variant_code} deleted successfully'
            })
            
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

@csrf_exempt
@check_auth
def bulk_update_variants(request, material_id):
    """Bulk update variants for a material"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            variants_data = data.get('variants', [])
            
            material = get_object_or_404(Material, pk=material_id)
            updated_count = 0
            
            for variant_data in variants_data:
                variant_id = variant_data.get('id')
                if variant_id:
                    try:
                        variant = MaterialVariant.objects.get(pk=variant_id, material=material)
                        
                        # Update fields
                        if 'mrp' in variant_data:
                            variant.mrp = variant_data['mrp']
                        if 'sp' in variant_data:
                            variant.sp = variant_data['sp']
                        if 'cost' in variant_data:
                            variant.cost = variant_data['cost']
                        if 'current_stock' in variant_data:
                            variant.current_stock = variant_data['current_stock']
                        if 'barcode' in variant_data:
                            variant.barcode = variant_data['barcode']
                        if 'is_active' in variant_data:
                            variant.is_active = variant_data['is_active']
                        
                        variant.save()
                        updated_count += 1
                        
                    except MaterialVariant.DoesNotExist:
                        continue
            
            return JsonResponse({
                'status': 'success',
                'message': f'Successfully updated {updated_count} variants'
            })
            
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405) 

@csrf_exempt
@check_auth
def material_variant_create_proxy(request, material_id):
    if request.method == 'POST':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
            payload = json.loads(request.body)
            resp = requests.post(
                f"{JAVA_API_URL}/api/materials/{material_id}/variants",
                json=payload,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                }
            )
            return JsonResponse(resp.json(), status=resp.status_code)
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=400) 

@csrf_exempt
@check_auth
def material_variant_bulk_create_proxy(request, material_id):
    if request.method == 'POST':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
            payload = json.loads(request.body)
            resp = requests.post(
                f"{JAVA_API_URL}/api/materials/{material_id}/variants/bulk",
                json=payload,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                }
            )
            return JsonResponse(resp.json(), status=resp.status_code)
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=400) 

@csrf_exempt
@check_auth
def material_variants_list_proxy(request):
    if request.method == 'GET':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
            resp = requests.get(
                f"{JAVA_API_URL}/api/materials/variants",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                }
            )
            return JsonResponse(resp.json(), status=resp.status_code)
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=400) 

@csrf_exempt
@check_auth
def material_variant_detail_proxy(request, variant_code):
    if request.method == 'GET':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
            resp = requests.get(
                f"{JAVA_API_URL}/api/materials/variants/{variant_code}",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                }
            )
            return JsonResponse(resp.json(), status=resp.status_code)
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
    elif request.method in ['PUT', 'POST']:
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)

            if request.content_type and request.content_type.startswith('multipart/form-data'):
                data_to_forward = request.POST.dict()
                files_to_forward = []
                for key in request.FILES:
                    file = request.FILES[key]
                    files_to_forward.append((key, (file.name, file.read(), file.content_type)))
                # Use POST or PUT to backend depending on method
                backend_method = requests.post if request.method == 'POST' else requests.put
                resp = backend_method(
                    f"{JAVA_API_URL}/api/materials/variants/{variant_code}",
                    data=data_to_forward,
                    files=files_to_forward,
                    headers={'Authorization': f'Bearer {auth_token}'}
                )
                
                # Handle multipart response properly
                try:
                    if resp.content:
                        return JsonResponse(resp.json(), status=resp.status_code)
                    else:
                        return JsonResponse({
                            'status': 'success',
                            'message': 'Variant updated successfully'
                        }, status=resp.status_code)
                except ValueError:
                    return JsonResponse({
                        'status': 'success' if resp.status_code == 200 else 'error',
                        'message': resp.text or 'Variant updated successfully'
                    }, status=resp.status_code)
            else:
                payload = json.loads(request.body)
                resp = requests.put(
                    f"{JAVA_API_URL}/api/materials/variants/{variant_code}",
                    json=payload,
                    headers={
                        'Authorization': f'Bearer {auth_token}',
                        'Content-Type': 'application/json'
                    }
                )
            
            # Handle response properly - check if it's JSON
            try:
                if resp.content:
                    return JsonResponse(resp.json(), status=resp.status_code)
                else:
                    # Empty response - return success message
                    return JsonResponse({
                        'status': 'success',
                        'message': 'Variant updated successfully'
                    }, status=resp.status_code)
            except ValueError:
                # Non-JSON response - return the raw content
                return JsonResponse({
                    'status': 'success' if resp.status_code == 200 else 'error',
                    'message': resp.text or 'Variant updated successfully'
                }, status=resp.status_code)
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=400) 

@csrf_exempt
@check_auth
def material_variant_active_status_proxy(request, variant_code):
    if request.method == 'PUT':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
            payload = json.loads(request.body)
            resp = requests.put(
                f"{JAVA_API_URL}/api/materials/variants/{variant_code}/active-status",
                json=payload,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                }
            )
            return JsonResponse(resp.json(), status=resp.status_code)
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=400) 

@csrf_exempt
@check_auth
def material_attributes_proxy(request, material_id):
    if request.method == 'GET':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
            resp = requests.get(
                f"{JAVA_API_URL}/api/materials/{material_id}/attributes",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                }
            )
            return JsonResponse(resp.json(), status=resp.status_code)
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=400)

@csrf_exempt
@check_auth
def material_bom_excel_save_proxy(request, material_id):
    if request.method == 'POST':
        try:
            # Get auth token from Authorization header first, then fall back to session
            auth_header = request.META.get('HTTP_AUTHORIZATION', '')
            if auth_header.startswith('Bearer '):
                auth_token = auth_header.split('Bearer ')[1]
            else:
                auth_token = request.session.get('auth_token')
            
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
            
            # Get the Excel file from request
            excel_file = request.FILES.get('excel_file')
            if not excel_file:
                return JsonResponse({'status': 'error', 'error': 'No file uploaded'}, status=400)
            
            # Prepare file for forwarding - read file content
            file_content = excel_file.read()
            file_name = excel_file.name
            file_content_type = excel_file.content_type or 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            
            # Reset file pointer if possible (for potential future reads)
            if hasattr(excel_file, 'seek'):
                excel_file.seek(0)
            
            # Prepare file for forwarding to Java backend
            files = {'excel_file': (file_name, file_content, file_content_type)}
            headers = {'Authorization': f'Bearer {auth_token}'}
            
            logger.info(f"Forwarding BOM Excel save request to Java backend for material {material_id}")
            
            # Forward request to Java backend
            resp = requests.post(
                f"{JAVA_API_URL}/api/materials/{material_id}/bom-excel/save",
                files=files,
                headers=headers,
                timeout=30
            )
            
            logger.info(f"Java backend response status: {resp.status_code}")
            
            try:
                response_data = resp.json()
                return JsonResponse(response_data, status=resp.status_code)
            except Exception as json_error:
                logger.error(f"Error parsing JSON response: {json_error}")
                return HttpResponse(resp.content, status=resp.status_code, content_type=resp.headers.get('Content-Type', 'application/json'))
        except requests.exceptions.RequestException as e:
            logger.error(f"Error connecting to Java backend: {e}")
            return JsonResponse({'status': 'error', 'error': f'Error connecting to backend service: {str(e)}'}, status=500)
        except Exception as e:
            logger.error(f"Error saving BOM Excel: {e}")
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=400)

@csrf_exempt
@check_auth
def material_bom_excel_get_proxy(request, material_id):
    if request.method == 'GET':
        try:
            # Get auth token from Authorization header first, then fall back to session
            auth_header = request.META.get('HTTP_AUTHORIZATION', '')
            if auth_header.startswith('Bearer '):
                auth_token = auth_header.split('Bearer ')[1]
            else:
                auth_token = request.session.get('auth_token')
            
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
            
            headers = {
                'Authorization': f'Bearer {auth_token}',
                'Accept': 'application/json'
            }
            
            logger.info(f"Forwarding BOM Excel get request to Java backend for material {material_id}")
            
            # Forward request to Java backend
            resp = requests.get(
                f"{JAVA_API_URL}/api/materials/{material_id}/bom-excel/get",
                headers=headers,
                timeout=30
            )
            
            logger.info(f"Java backend response status: {resp.status_code}")
            logger.info(f"Java backend response content: {resp.text[:500]}")  # Log first 500 chars
            
            # Check if response has content
            if not resp.text or resp.text.strip() == '':
                logger.warning("Empty response from Java backend")
                # Return a proper response indicating no file exists
                return JsonResponse({
                    'status': 'SUCCESS',
                    'statusMsg': 'No BOM Excel file found for this material',
                    'file_exists': False
                }, status=200)
            
            # Try to parse JSON response
            try:
                response_data = resp.json()
                return JsonResponse(response_data, status=resp.status_code)
            except (ValueError, json.JSONDecodeError) as json_error:
                # If response is not valid JSON, log and return appropriate response
                logger.error(f"Failed to parse JSON response: {json_error}")
                logger.error(f"Response text: {resp.text}")
                
                # If status is 200 but not JSON, assume no file exists
                if resp.status_code == 200:
                    return JsonResponse({
                        'status': 'SUCCESS',
                        'statusMsg': 'No BOM Excel file found for this material',
                        'file_exists': False
                    }, status=200)
                else:
                    # For error status codes, return error response
                    return JsonResponse({
                        'status': 'error',
                        'error': f'Backend returned invalid response: {resp.text[:200]}'
                    }, status=resp.status_code)
                    
        except requests.exceptions.RequestException as e:
            logger.error(f"Error connecting to Java backend: {e}")
            return JsonResponse({
                'status': 'error', 
                'error': f'Error connecting to backend service: {str(e)}'
            }, status=500)
        except Exception as e:
            logger.error(f"Error getting BOM Excel: {e}", exc_info=True)
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=400) 

@csrf_exempt
@check_auth
def material_variant_barcode_image_proxy(request, variant_code):
    if request.method in ['PUT', 'POST']:
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
            file = request.FILES.get('file')
            if not file:
                return JsonResponse({'status': 'error', 'error': 'No file uploaded'}, status=400)
            files = {'file': (file.name, file.read(), file.content_type)}
            headers = {'Authorization': f'Bearer {auth_token}'}
            resp = requests.put(
                f"{JAVA_API_URL}/api/materials/variants/{variant_code}/barcode-image",
                files=files,
                headers=headers
            )
            try:
                return JsonResponse(resp.json(), status=resp.status_code)
            except Exception:
                return HttpResponse(resp.content, status=resp.status_code, content_type=resp.headers.get('Content-Type', 'application/json'))
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=400) 

@csrf_exempt
@check_auth
def material_variant_image_proxy(request, variant_code):
    # Accept POST for backward-compat, but always forward as PUT to new upstream
    if request.method in ['POST', 'PUT']:
        try:
            # Forward the JWT token if present
            auth_token = request.session.get('auth_token')
            headers = {}
            if auth_token:
                headers['Authorization'] = f'Bearer {auth_token}'
            
            # Prepare files for forwarding
            files = {}
            for key in request.FILES:
                file_list = request.FILES.getlist(key)
                if len(file_list) == 1:
                    files[key] = (file_list[0].name, file_list[0], file_list[0].content_type)
                else:
                    # For multiple files
                    files[key] = [(f.name, f, f.content_type) for f in file_list]
            
            data = request.POST.dict()
            
            # Forward request to Java backend (new endpoint + PUT method)
            response = requests.put(
                f"{JAVA_API_URL}/api/materials/variants/code/{variant_code}/variant-image",
                data=data,
                files=files,
                headers=headers
            )
            
            return JsonResponse(response.json(), status=response.status_code)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error forwarding variant image request: {e}")
            return JsonResponse({
                'status': '500',
                'statusMsg': 'Error connecting to backend service'
            }, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)

@csrf_exempt
@check_auth
def material_update_proxy(request, material_id):
    if request.method == 'POST':
        try:
            # Forward the JWT token if present
            auth_token = request.session.get('auth_token')
            headers = {}
            if auth_token:
                headers['Authorization'] = f'Bearer {auth_token}'
            
            # Prepare files for forwarding
            files = {}
            for key in request.FILES:
                try:
                    file_list = request.FILES.getlist(key)
                    if len(file_list) == 1:
                        # Single file
                        file_obj = file_list[0]
                        # Ensure file name and content type are strings
                        file_name = str(file_obj.name) if file_obj.name else 'file'
                        content_type = str(file_obj.content_type) if file_obj.content_type else 'application/octet-stream'
                        file_content = file_obj.read()
                        files[key] = (file_name, file_content, content_type)
                        # Reset file pointer for potential future reads
                        file_obj.seek(0)
                    else:
                        # Multiple files
                        file_tuples = []
                        for file_obj in file_list:
                            # Ensure file name and content type are strings
                            file_name = str(file_obj.name) if file_obj.name else 'file'
                            content_type = str(file_obj.content_type) if file_obj.content_type else 'application/octet-stream'
                            file_content = file_obj.read()
                            file_tuples.append((file_name, file_content, content_type))
                            # Reset file pointer
                            file_obj.seek(0)
                        files[key] = file_tuples
                except Exception as file_error:
                    logger.error(f"Error processing file {key}: {file_error}")
                    continue
            
            # Process form data - handle JSON fields properly
            data = {}
            for key, value in request.POST.items():
                try:
                    if key in ['attributes', 'generalAttributes']:
                        # These should be JSON strings, ensure they're properly formatted
                        if isinstance(value, str):
                            # If it's already a JSON string, use it as is
                            data[key] = value
                        elif isinstance(value, (list, dict)):
                            # If it's a Python object, convert to JSON string
                            data[key] = json.dumps(value)
                        else:
                            # Fallback: convert to string
                            data[key] = str(value)
                    else:
                        # Regular form fields
                        if isinstance(value, tuple):
                            data[key] = ''.join(str(item) for item in value)
                        else:
                            data[key] = str(value)
                except Exception as data_error:
                    logger.error(f"Error processing form data {key}: {data_error}")
                    data[key] = str(value) if value else ''
            
            logger.info(f"Forwarding material update request to {JAVA_API_URL}/api/materials/update/{material_id}")
            logger.info(f"Data keys: {list(data.keys())}")
            logger.info(f"Files keys: {list(files.keys())}")
            
            # Forward request to Java backend
            response = requests.post(
                f"{JAVA_API_URL}/api/materials/update/{material_id}",
                data=data,
                files=files,
                headers=headers
            )
            
            return JsonResponse(response.json(), status=response.status_code)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error forwarding material update request: {e}")
            return JsonResponse({
                'status': '500',
                'statusMsg': 'Error connecting to backend service'
            }, status=500)
        except Exception as e:
            logger.error(f"Unexpected error in material_update_proxy: {e}")
            logger.error(f"Error type: {type(e)}")
            logger.error(f"Error details: {str(e)}")
            return JsonResponse({
                'status': '500',
                'statusMsg': f'Unexpected error: {str(e)}'
            }, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405) 

@csrf_exempt
@check_auth
def material_delete_proxy(request, material_id):
    if request.method == 'DELETE':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
            response = requests.delete(
                f"{JAVA_API_URL}/api/materials/{material_id}",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/json'
                }
            )
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': '500',
                    'statusMsg': response.text or 'Invalid response from backend'
                }, status=500)
        except Exception as e:
            logger.error(f"Error in material_delete_proxy: {str(e)}")
            return JsonResponse({'status': '500', 'statusMsg': str(e)}, status=500)
    return JsonResponse({'status': '405', 'statusMsg': 'Method not allowed'}, status=405) 

@csrf_exempt
@check_auth
def variant_delete_proxy(request, variant_code):
    if request.method == 'DELETE':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
            response = requests.delete(
                f"{JAVA_API_URL}/api/materials/variants/{variant_code}",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/json'
                }
            )
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({'status': 'error', 'error': 'Invalid response from API'}, status=500)
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=405) 

@csrf_exempt
@check_auth
def attribute_delete_proxy(request, attribute_id):
    if request.method == 'DELETE':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
            response = requests.delete(
                f"{JAVA_API_URL}/api/attributes/{attribute_id}",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/json'
                }
            )
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({'status': 'error', 'error': 'Invalid response from API'}, status=500)
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=405)

# Channel Management Views
@check_auth
def channels_list(request):
    """Display list of all channels from Java API (no dummy data)."""
    channels = []
    company_id = None

    try:
        auth_token = request.session.get('auth_token')
        if not auth_token:
            logger.warning("No auth token in session; channels list will be empty.")
        else:
            response = requests.get(
                f"{JAVA_API_URL}/api/channels/all",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/json'
                }
            )

            logger.info(f"Channels API status: {response.status_code}")
            try:
                payload = response.json()
            except ValueError:
                payload = {}
                logger.error("Channels API returned non-JSON response")

            # Expecting SUCCESS format
            if response.status_code == 200 and payload.get('status') in ['SUCCESS', '200']:
                data = payload.get('data') or {}
                company_id = data.get('companyId')
                api_channels = data.get('channels') or []

                # Map Java fields to template fields
                for ch in api_channels:
                    categories = ch.get('categories') or []
                    channels.append({
                        'id': ch.get('channelId'),
                        'channel_code': ch.get('channelCode'),
                        'channel_name': ch.get('channelName'),
                        'description': ch.get('description') or '',
                        'is_active': ch.get('isActive', True),
                        'categories_count': len(categories),
                        'categories': [
                            {
                                'category_code': c.get('categoryCode'),
                                'category_name': c.get('categoryName')
                            } for c in categories
                        ],
                    })
                logger.info(f"Mapped {len(channels)} channels from API response")
            else:
                logger.warning(f"Unexpected Channels API response: status={response.status_code}, body={payload}")
    except Exception as e:
        logger.error(f"Error in channels_list: {e}")

    context = {
        'channels': channels,
        'company_id': company_id,
        'user_data': request.session.get('user_data', {})
    }
    return render(request, 'pages/channels_list.html', context)

@check_auth
def channel_detail(request, channel_id):
    """Display channel details and its categories"""
    # Dummy data for now until API is ready
  
  
   
    
    # Try to get real data, fallback to dummy data
    try:
        channel = get_object_or_404(Channel, pk=channel_id)
        categories = ChannelCategory.objects.filter(channel=channel).order_by('category_name')
        material_assignments = MaterialChannelAssignment.objects.filter(channel=channel).select_related('material', 'channel_category', 'reporting_category')
    except Exception as e:
        logger.error(f"Error fetching channel data: {e}")
        messages.error(request, "Failed to load channel data")
        return redirect('channels_list')
    
    context = {
        'channel': channel,
        'categories': categories,
        'material_assignments': material_assignments,
        'user_data': request.session.get('user_data', {})
    }
    return render(request, 'pages/channel_detail.html', context)

@csrf_exempt
@check_auth
def channel_create(request):
    """Create a new channel by calling Java API"""
    if request.method == 'POST':
        try:
            # Get auth token from session
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Authentication required'
                }, status=401)

            # Parse the request data
            data = json.loads(request.body)
            
            # Data is already in camelCase format, use directly
            java_payload = {
                "channelName": data.get('channelName', ''),
                "channelCode": data.get('channelCode', ''),
                "description": data.get('description', ''),
                "isActive": data.get('isActive', True),
                "categories": []
            }
            
            # Transform categories if they exist
            if 'categories' in data and isinstance(data['categories'], list):
                for category in data['categories']:
                    java_category = {
                        "categoryCode": category.get('categoryCode', ''),
                        "categoryName": category.get('categoryName', ''),
                        "isActive": category.get('isActive', True)
                    }
                    java_payload['categories'].append(java_category)
            
            logger.info(f"Forwarding channel creation request to {JAVA_API_URL}/api/channels/create")
            logger.info(f"Java payload: {java_payload}")
            
            # Make request to Java backend
            response = requests.post(
                f"{JAVA_API_URL}/api/channels/create",
                json=java_payload,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                }
            )
            
            # Log the response status and content
            logger.info(f"Java backend response status: {response.status_code}")
            logger.info(f"Java backend response: {response.text}")
            
            if response.status_code == 200:
                try:
                    java_response = response.json()
                    return JsonResponse({
                        'status': 'success',
                        'message': 'Channel created successfully',
                        'data': java_response
                    })
                except ValueError:
                    return JsonResponse({
                        'status': 'success',
                        'message': 'Channel created successfully',
                        'data': {'message': response.text}
                    })
            else:
                try:
                    error_response = response.json()
                    return JsonResponse({
                        'status': 'error',
                        'message': error_response.get('message', 'Error creating channel'),
                        'errors': error_response.get('errors', {})
                    }, status=response.status_code)
                except ValueError:
                    return JsonResponse({
                        'status': 'error',
                        'message': response.text or 'Error creating channel'
                    }, status=response.status_code)
                    
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to connect to backend service: {e}")
            return JsonResponse({
                'status': 'error',
                'message': f'Failed to connect to backend service: {e}'
            }, status=502)
        except Exception as e:
            logger.error(f"Error in channel_create: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

@csrf_exempt
@check_auth
def channel_update(request, channel_id):
    """Update channel details by calling Java API"""
    if request.method in ['POST', 'PUT']:
        try:
            # Get auth token from session
            auth_token = request.session.get('auth_token')
            if not auth_token:
                logger.error("No auth token found in session")
                return JsonResponse({
                    'status': 'error',
                    'message': 'Authentication required'
                }, status=401)
            
            logger.info(f"Channel update request received for channel {channel_id}")
            logger.info(f"Request method: {request.method}")
            logger.info(f"Request headers: {dict(request.headers)}")

            # Parse the request data
            data = json.loads(request.body)
            
            # Transform the data to match Java API format
            java_payload = {
                "channelName": data.get('channel_name', ''),
                "channelCode": data.get('channel_code', ''),
                "description": data.get('description', ''),
                "isActive": data.get('isActive', True),
                "categories": []
            }
            
            # Transform categories if they exist
            if 'categories' in data and isinstance(data['categories'], list):
                for category in data['categories']:
                    java_category = {
                        "categoryCode": category.get('categoryCode', ''),
                        "categoryName": category.get('categoryName', ''),
                        "isActive": category.get('isActive', True)
                    }
                    # Include category ID if it exists (for existing categories)
                    if 'categoryId' in category and category['categoryId']:
                        java_category['categoryId'] = category['categoryId']
                    
                    java_payload['categories'].append(java_category)
            
            logger.info(f"Forwarding channel update request to {JAVA_API_URL}/api/channels/{channel_id}/update")
            logger.info(f"Java payload: {java_payload}")
            
            # Make request to Java backend
            response = requests.put(
                f"{JAVA_API_URL}/api/channels/{channel_id}/update",
                json=java_payload,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                }
            )
            
            # Log the response status and content
            logger.info(f"Java backend response status: {response.status_code}")
            logger.info(f"Java backend response: {response.text}")
            
            if response.status_code == 200:
                try:
                    java_response = response.json()
                    return JsonResponse({
                        'status': 'success',
                        'message': 'Channel updated successfully',
                        'data': java_response
                    })
                except ValueError:
                    return JsonResponse({
                        'status': 'success',
                        'message': 'Channel updated successfully',
                        'data': {'message': response.text}
                    })
            else:
                try:
                    error_response = response.json()
                    return JsonResponse({
                        'status': 'error',
                        'message': error_response.get('message', 'Error updating channel'),
                        'errors': error_response.get('errors', {})
                    }, status=response.status_code)
                except ValueError:
                    return JsonResponse({
                        'status': 'error',
                        'message': response.text or 'Error updating channel'
                    }, status=response.status_code)
                    
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to connect to backend service: {e}")
            return JsonResponse({
                'status': 'error',
                'message': f'Failed to connect to backend service: {e}'
            }, status=502)
        except Exception as e:
            logger.error(f"Error in channel_update: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

@csrf_exempt
@check_auth
def channel_delete(request, channel_id):
    """Delete a channel by calling Java API"""
    if request.method == 'POST':
        try:
            # Get auth token from session
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Authentication required'
                }, status=401)

            logger.info(f"Forwarding channel delete request to {JAVA_API_URL}/api/channels/{channel_id}/delete")
            
            # Make request to Java backend
            response = requests.delete(
                f"{JAVA_API_URL}/api/channels/{channel_id}/delete",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/json'
                }
            )
            
            # Log the response status and content
            logger.info(f"Java backend response status: {response.status_code}")
            logger.info(f"Java backend response: {response.text}")
            
            if response.status_code == 200:
                try:
                    java_response = response.json()
                    return JsonResponse({
                        'status': 'success',
                        'message': 'Channel deleted successfully',
                        'data': java_response
                    })
                except ValueError:
                    return JsonResponse({
                        'status': 'success',
                        'message': 'Channel deleted successfully',
                        'data': {'message': response.text}
                    })
            else:
                try:
                    error_response = response.json()
                    return JsonResponse({
                        'status': 'error',
                        'message': error_response.get('message', 'Error deleting channel'),
                        'errors': error_response.get('errors', {})
                    }, status=response.status_code)
                except ValueError:
                    return JsonResponse({
                        'status': 'error',
                        'message': response.text or 'Error deleting channel'
                    }, status=response.status_code)
                    
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to connect to backend service: {e}")
            return JsonResponse({
                'status': 'error',
                'message': f'Failed to connect to backend service: {e}'
            }, status=502)
        except Exception as e:
            logger.error(f"Error in channel_delete: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

@check_auth
def channel_categories_list(request, channel_id):
    """Display categories for a specific channel"""
 
    # Try to get real data, fallback to dummy data
    try:
        channel = get_object_or_404(Channel, pk=channel_id)
        categories = ChannelCategory.objects.filter(channel=channel).order_by('category_name')
    except Exception as e:
        logger.error(f"Error fetching channel categories: {e}")
        messages.error(request, "Failed to load channel categories")
        return redirect('channels_list')
    
    context = {
        'channel': channel,
        'categories': categories,
        'user_data': request.session.get('user_data', {})
    }
    return render(request, 'pages/channel_categories_list.html', context)

@csrf_exempt
@check_auth
def channel_category_create(request, channel_id):
    """Create a new category for a channel"""
    if request.method == 'POST':
        try:
            channel = get_object_or_404(Channel, pk=channel_id)
            data = json.loads(request.body)
            
            category = ChannelCategory.objects.create(
                channel=channel,
                category_code=data['category_code'],
                category_name=data['category_name'],
                description=data.get('description', ''),
                parent_category_id=data.get('parent_category_id'),
                is_active=data.get('is_active', True)
            )
            
            return JsonResponse({
                'status': 'success',
                'message': 'Category created successfully',
                'category': {
                    'id': category.id,
                    'category_code': category.category_code,
                    'category_name': category.category_name,
                    'description': category.description,
                    'parent_category': category.parent_category.category_name if category.parent_category else None
                }
            })
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=400)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

@csrf_exempt
@check_auth
def channel_category_update(request, category_id):
    """Update channel category details"""
    if request.method == 'POST':
        try:
            category = get_object_or_404(ChannelCategory, pk=category_id)
            data = json.loads(request.body)
            
            category.category_code = data['category_code']
            category.category_name = data['category_name']
            category.description = data.get('description', '')
            category.parent_category_id = data.get('parent_category_id')
            category.is_active = data.get('is_active', True)
            category.save()
            
            return JsonResponse({
                'status': 'success',
                'message': 'Category updated successfully'
            })
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=400)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

@csrf_exempt
@check_auth
def channel_category_delete(request, category_id):
    """Delete a channel category"""
    if request.method == 'POST':
        try:
            category = get_object_or_404(ChannelCategory, pk=category_id)
            category_name = category.category_name
            category.delete()
            
            return JsonResponse({
                'status': 'success',
                'message': f'Category {category_name} deleted successfully'
            })
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=400)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)



@check_auth
def material_channel_assignments_list(request):
    """Display material channel mapping interface with real API data"""
    channels = []
    
    try:
        # Get auth token from session
        auth_token = request.session.get('auth_token')
        if not auth_token:
            logger.warning("No auth token in session for material channel assignments")
        else:
            # Fetch channels from Java API
            response = requests.get(
                f"{JAVA_API_URL}/api/channels/all",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/json'
                }
            )
            
            logger.info(f"Material Channel Assignments API status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    payload = response.json()
                    logger.info(f"API Response: {payload}")
                    
                    # Parse SUCCESS format response
                    if payload.get('status') in ['SUCCESS', '200']:
                        data = payload.get('data', {})
                        api_channels = data.get('channels', [])
                        
                        # Map channels with their categories for the template
                        for ch in api_channels:
                            categories = ch.get('categories', [])
                            channels.append({
                                'id': ch.get('channelId'),
                                'channel_code': ch.get('channelCode'),
                                'channel_name': ch.get('channelName'),
                                'description': ch.get('description', ''),
                                'categories': [
                                    {
                                        'category_id': cat.get('categoryId'),
                                        'category_code': cat.get('categoryCode'),
                                        'category_name': cat.get('categoryName'),
                                        'is_active': cat.get('isActive', True)
                                    }
                                    for cat in categories if cat.get('isActive', True)
                                ]
                            })
                        
                        logger.info(f"Successfully mapped {len(channels)} channels for material assignments")
                    else:
                        logger.warning(f"Unexpected API response format: {payload}")
                except ValueError as e:
                    logger.error(f"Failed to parse API response: {e}")
            else:
                logger.warning(f"API returned status {response.status_code}")
                
    except Exception as e:
        logger.error(f"Error fetching channels for material assignments: {e}")
    
    context = {
        'channels': channels,
        'user_data': request.session.get('user_data', {})
    }
    return render(request, 'pages/material_channel_assignments_list.html', context)

@check_auth
def material_channel_assignment_create(request):
    """Display form to create material channel assignment"""
    # Dummy data for now until API is ready
    
    # Try to get real data, fallback to dummy data
    try:
        materials = Material.objects.all().order_by('material_name')
        channels = Channel.objects.filter(is_active=True).order_by('channel_name')
        
        if not materials.exists():
            materials = Material.objects.none()
        if not channels.exists():
            channels = Channel.objects.none()
    except Exception as e:
        logger.error(f"Error fetching materials/channels: {e}")
        materials = Material.objects.none()
        channels = Channel.objects.none()
    
    context = {
        'materials': materials,
        'channels': channels,
        'user_data': request.session.get('user_data', {})
    }
    return render(request, 'pages/material_channel_assignment_create.html', context)

@csrf_exempt
@check_auth
def material_channel_assignment_save(request):
    """Save material channel assignment"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            assignment = MaterialChannelAssignment.objects.create(
                material_id=data['material_id'],
                channel_id=data['channel_id'],
                channel_category_id=data['channel_category_id'],
                reporting_category_id=data['reporting_category_id'],
                selling_price=data['selling_price'],
                mrp=data.get('mrp'),
                cost_price=data.get('cost_price'),
                channel_sku=data.get('channel_sku'),
                channel_product_id=data.get('channel_product_id'),
                commission_percentage=data.get('commission_percentage'),
                shipping_cost=data.get('shipping_cost'),
                notes=data.get('notes'),
                is_active=data.get('is_active', True)
            )
            
            return JsonResponse({
                'status': 'success',
                'message': 'Material channel assignment created successfully',
                'assignment': {
                    'id': assignment.id,
                    'material_name': assignment.material.material_name,
                    'channel_name': assignment.channel.channel_name,
                    'selling_price': float(assignment.selling_price)
                }
            })
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=400)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

@csrf_exempt
@check_auth
def material_channel_assignment_update(request, assignment_id):
    """Update material channel assignment"""
    if request.method == 'POST':
        try:
            assignment = get_object_or_404(MaterialChannelAssignment, pk=assignment_id)
            data = json.loads(request.body)
            
            assignment.selling_price = data['selling_price']
            assignment.mrp = data.get('mrp')
            assignment.cost_price = data.get('cost_price')
            assignment.channel_sku = data.get('channel_sku')
            assignment.channel_product_id = data.get('channel_product_id')
            assignment.commission_percentage = data.get('commission_percentage')
            assignment.shipping_cost = data.get('shipping_cost')
            assignment.notes = data.get('notes')
            assignment.is_active = data.get('is_active', True)
            assignment.save()
            
            return JsonResponse({
                'status': 'success',
                'message': 'Material channel assignment updated successfully'
            })
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=400)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

@csrf_exempt
@check_auth
def material_channel_assignment_delete(request, assignment_id):
    """Delete material channel assignment"""
    if request.method == 'POST':
        try:
            assignment = get_object_or_404(MaterialChannelAssignment, pk=assignment_id)
            material_name = assignment.material.material_name
            channel_name = assignment.channel.channel_name
            assignment.delete()
            
            return JsonResponse({
                'status': 'success',
                'message': f'Assignment for {material_name} on {channel_name} deleted successfully'
            })
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=400)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

@csrf_exempt
@check_auth
def get_channel_categories(request, channel_id):
    """Get categories for a specific channel (AJAX endpoint)"""
    if request.method == 'GET':
        try:
            categories = ChannelCategory.objects.filter(
                channel_id=channel_id, 
                is_active=True
            ).order_by('category_name')
            
            data = [{
                'id': cat.id,
                'category_code': cat.category_code,
                'category_name': cat.category_name,
                'parent_category': cat.parent_category.category_name if cat.parent_category else None
            } for cat in categories]
            
            return JsonResponse({
                'status': 'success',
                'categories': data
            })
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=400)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

@csrf_exempt
@check_auth
def channels_list_proxy(request):
    """Proxy view to fetch channels from Java API and handle creation"""
    auth_token = request.session.get('auth_token')
    company_id = get_company_id(request)

    headers = {
        'Authorization': f'Bearer {auth_token}',
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }

    try:
        if request.method == 'GET':
            url = f"{JAVA_API_URL}/api/channels/company/{company_id}"
            resp = requests.get(url, headers=headers, timeout=30)
            try:
                return JsonResponse(resp.json(), status=resp.status_code)
            except ValueError:
                return JsonResponse({'status': 'ERROR', 'statusMsg': f'Invalid response from backend: {resp.text[:100]}'}, status=resp.status_code)
        elif request.method == 'POST':
            url = f"{JAVA_API_URL}/api/channels/create"
            payload = json.loads(request.body)
            # Cleanup: remove empty channelId for creation
            if 'channelId' in payload and not payload['channelId']:
                payload.pop('channelId')
            
            # Inject company context
            if 'companyId' not in payload:
                payload['companyId'] = company_id
                
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            try:
                return JsonResponse(resp.json(), status=resp.status_code)
            except ValueError:
                return JsonResponse({'status': 'ERROR', 'statusMsg': f'Invalid response from backend: {resp.text[:100]}'}, status=resp.status_code)
    except Exception as e:
        logger.error(f"Error in channels_list_proxy: {str(e)}")
        return JsonResponse({'status': 'ERROR', 'statusMsg': str(e)}, status=500)

@csrf_exempt
@check_auth
def channel_detail_proxy(request, channel_id):
    """Proxy view to fetch single channel details, update, toggle status, or delete"""
    auth_token = request.session.get('auth_token')
    
    headers = {
        'Authorization': f'Bearer {auth_token}',
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }

    try:
        if request.method == 'GET':
            url = f"{JAVA_API_URL}/api/channels/{channel_id}"
            resp = requests.get(url, headers=headers, timeout=30)
            try:
                return JsonResponse(resp.json(), status=resp.status_code)
            except ValueError:
                return JsonResponse({'status': 'ERROR', 'statusMsg': f'Invalid response: {resp.text[:100]}'}, status=resp.status_code)
        elif request.method == 'PUT':
            url = f"{JAVA_API_URL}/api/channels/{channel_id}"
            payload = json.loads(request.body)
            resp = requests.put(url, json=payload, headers=headers, timeout=30)
            try:
                return JsonResponse(resp.json(), status=resp.status_code)
            except ValueError:
                return JsonResponse({'status': 'ERROR', 'statusMsg': f'Invalid response: {resp.text[:100]}'}, status=resp.status_code)
        elif request.method == 'PATCH':
            url = f"{JAVA_API_URL}/api/channels/{channel_id}/toggle-status"
            resp = requests.patch(url, headers=headers, timeout=30)
            try:
                return JsonResponse(resp.json(), status=resp.status_code)
            except ValueError:
                return JsonResponse({'status': 'ERROR', 'statusMsg': f'Invalid response: {resp.text[:100]}'}, status=resp.status_code)
        elif request.method == 'DELETE':
            url = f"{JAVA_API_URL}/api/channels/{channel_id}"
            resp = requests.delete(url, headers=headers, timeout=30)
            try:
                return JsonResponse(resp.json(), status=resp.status_code)
            except ValueError:
                return JsonResponse({'status': 'ERROR', 'statusMsg': f'Invalid response: {resp.text[:100]}'}, status=resp.status_code)
    except Exception as e:
        logger.error(f"Error in channel_detail_proxy: {str(e)}")
        return JsonResponse({'status': 'ERROR', 'statusMsg': str(e)}, status=500)

@csrf_exempt
@check_auth
def material_mappings_get_proxy(request, material_id):
    """Proxy view to fetch material mappings from Java API"""
    if request.method == 'GET':
        try:
            # Get auth token from session
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
            
            response = requests.get(
                f"{JAVA_API_URL}/api/materials/{material_id}/mappings",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/json'
                }
            )
            
            logger.info(f"Material mappings API response status: {response.status_code}")
            logger.info(f"Material mappings API response: {response.text}")
            
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': '500',
                    'statusMsg': response.text or 'Invalid response from backend',
                    'errorCode': '500',
                    'data': {},
                    'dataString': ''
                }, status=500)
        except Exception as e:
            logger.error(f"Error in material_mappings_get_proxy: {str(e)}")
            return JsonResponse({
                'status': '500',
                'statusMsg': str(e),
                'errorCode': '500',
                'data': {},
                'dataString': ''
            }, status=500)
    return JsonResponse({
        'status': '405',
        'statusMsg': 'Method not allowed',
        'errorCode': '405',
        'data': {},
        'dataString': ''
    }, status=405)

@csrf_exempt
@check_auth
def material_mapping_delete_proxy(request, material_id, channel_id):
    """Proxy view to delete a specific material-channel mapping"""
    if request.method == 'DELETE':
        try:
            # Get auth token from session
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
            
            logger.info(f"Deleting material mapping: material_id={material_id}, channel_id={channel_id}")
            
            # Make request to Java backend
            response = requests.delete(
                f"{JAVA_API_URL}/api/materials/{material_id}/mappings/{channel_id}",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/json'
                }
            )
            
            logger.info(f"Delete mapping API response status: {response.status_code}")
            logger.info(f"Delete mapping API response: {response.text}")
            
            # Return the response from Java backend
            return JsonResponse(response.json(), status=response.status_code)
            
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error to Java backend: {e}")
            return JsonResponse({
                'status': 'error',
                'message': 'Could not connect to server. Please try again later.'
            }, status=503)
        except Exception as e:
            logger.error(f"Error deleting material mapping: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': f'Error deleting mapping: {str(e)}'
            }, status=500)
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)


@csrf_exempt
@check_auth
def channel_category_delete_proxy(request, channel_id, category_id):
    """Proxy view to delete a specific channel category"""
    logger.info(f"=== CHANNEL CATEGORY DELETE PROXY START ===")
    logger.info(f"Request method: {request.method}")
    logger.info(f"Channel ID: {channel_id}")
    logger.info(f"Category ID: {category_id}")
    logger.info(f"Request headers: {dict(request.headers)}")
    
    if request.method == 'DELETE':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                logger.error("No auth token found in session")
                return JsonResponse({'status': 'error', 'message': 'Authentication required'}, status=401)
            
            logger.info(f"Auth token found: {auth_token[:20]}...")
            logger.info(f"Making DELETE request to: {JAVA_API_URL}/api/channels/{channel_id}/categories/{category_id}")
            
            response = requests.delete(
                f"{JAVA_API_URL}/api/channels/{channel_id}/categories/{category_id}",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/json'
                },
                timeout=30
            )
            
            logger.info(f"Java backend response status: {response.status_code}")
            logger.info(f"Java backend response: {response.text}")
            logger.info(f"Response headers: {dict(response.headers)}")
            
            try:
                response_data = response.json()
                logger.info(f"Parsed response data: {response_data}")
                return JsonResponse(response_data, status=response.status_code)
            except ValueError as e:
                logger.error(f"Failed to parse JSON response: {e}")
                return JsonResponse({
                    'status': 'error',
                    'message': f'Invalid response format: {response.text}'
                }, status=500)
            
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error to Java backend: {e}")
            return JsonResponse({
                'status': 'error',
                'message': 'Could not connect to server. Please try again later.'
            }, status=503)
        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout error to Java backend: {e}")
            return JsonResponse({
                'status': 'error',
                'message': 'Request timeout. Please try again later.'
            }, status=408)
        except Exception as e:
            logger.error(f"Unexpected error during request: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return JsonResponse({
                'status': 'error',
                'message': f'Unexpected error: {str(e)}'
            }, status=500)
    
    logger.warning(f"Invalid request method: {request.method}")
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)


@csrf_exempt
@check_auth
def material_mappings_save_proxy(request, material_id):
    """Proxy view to save material mappings to Java API"""
    if request.method == 'POST':
        try:
            # Get auth token from session
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
            
            # Parse JSON data from request body
            try:
                data = json.loads(request.body)
            except ValueError:
                return JsonResponse({
                    'status': '400',
                    'statusMsg': 'Invalid JSON data',
                    'errorCode': '400',
                    'data': {},
                    'dataString': ''
                }, status=400)
            
            logger.info(f"Forwarding material mappings save request: {data}")
            
            # Forward request to Java backend
            response = requests.post(
                f"{JAVA_API_URL}/api/materials/{material_id}/mappings",
                json=data,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                }
            )
            
            logger.info(f"Material mappings save API response status: {response.status_code}")
            logger.info(f"Material mappings save API response: {response.text}")
            
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': '500',
                    'statusMsg': response.text or 'Invalid response from backend',
                    'errorCode': '500',
                    'data': {},
                    'dataString': ''
                }, status=500)
        except Exception as e:
            logger.error(f"Error in material_mappings_save_proxy: {str(e)}")
            return JsonResponse({
                'status': '500',
                'statusMsg': str(e),
                'errorCode': '500',
                'data': {},
                'dataString': ''
            }, status=500)
    return JsonResponse({
        'status': '405',
        'statusMsg': 'Method not allowed',
        'errorCode': '405',
        'data': {},
        'dataString': ''
    }, status=405) 


@csrf_exempt
@check_auth
def catalog_pdf_generate_proxy(request):
    """Proxy view for catalog PDF generation API"""
    if request.method == 'POST':
        try:
            # Get auth token from session
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
            # Parse JSON data from request body
            try:
                data = json.loads(request.body)
            except ValueError:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': 'Invalid JSON data'
                }, status=400)
            
            logger.info(f"Forwarding catalog PDF generation request: {data}")
            
            # Forward request to Java backend
            response = requests.post(
                f"{JAVA_API_URL}/api/catalog/generate-pdf-base64",
                json=data,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                }
            )
            
            logger.info(f"Catalog PDF generation API response status: {response.status_code}")
            logger.info(f"Catalog PDF generation API response: {response.text}")
            
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': response.text or 'Invalid response from backend'
                }, status=500)
        except Exception as e:
            logger.error(f"Error in catalog_pdf_generate_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    return JsonResponse({
        'status': 'ERROR',
        'statusMsg': 'Method not allowed'
    }, status=405)


@csrf_exempt
@check_auth
def cover_photo_upload_proxy(request):
    """Proxy view for cover photo upload API"""
    if request.method == 'POST':
        try:
            # Get auth token from session
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
            # Check if file is present
            if 'file' not in request.FILES:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'No file provided'}, status=400)
            
            uploaded_file = request.FILES['file']
            
            # Validate file size (5MB max)
            if uploaded_file.size > 5 * 1024 * 1024:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'File size must be less than 5MB'}, status=400)
            
            # Validate file type
            allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif']
            if uploaded_file.content_type not in allowed_types:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Invalid file type. Only JPG, PNG, and GIF are allowed'}, status=400)
            
            logger.info(f"Uploading cover photo: {uploaded_file.name}, size: {uploaded_file.size}, type: {uploaded_file.content_type}")
            
            # Prepare files for upload
            files = {
                'file': (uploaded_file.name, uploaded_file, uploaded_file.content_type)
            }
            
            # Make request to Java API
            response = requests.post(
                f"{JAVA_API_URL}/api/company/cover-photos/upload",
                files=files,
                headers={
                    'Authorization': f'Bearer {auth_token}'
                },
                timeout=30
            )
            
            logger.info(f"Cover photo upload API response status: {response.status_code}")
            logger.info(f"Cover photo upload API response: {response.text}")
            
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': response.text or 'Invalid response from backend'
                }, status=500)
                
        except Exception as e:
            logger.error(f"Error in cover_photo_upload_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    
    return JsonResponse({
        'status': 'ERROR',
        'statusMsg': 'Method not allowed'
    }, status=405)


@csrf_exempt
@check_auth
def cover_photos_list_proxy(request):
    """Proxy view for cover photos list API"""
    if request.method == 'GET':
        try:
            # Get auth token from session
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
            # Make request to Java backend
            response = requests.get(
                f"{JAVA_API_URL}/api/company/cover-photos/all",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                }
            )
            
            if response.status_code == 200:
                return JsonResponse(response.json())
            else:
                logger.error(f"Backend API error: {response.status_code} - {response.text}")
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': response.text or 'Invalid response from backend'
                }, status=500)
                
        except Exception as e:
            logger.error(f"Error in cover_photos_list_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    
    return JsonResponse({
        'status': 'ERROR',
        'statusMsg': 'Method not allowed'
    }, status=405)


# Cart API Proxy Views
@csrf_exempt
@check_auth
def cart_add_item_proxy(request):
    """Proxy view for adding items to cart"""
    if request.method == 'POST':
        try:
            # Get auth token from session
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': 'Unauthorized access',
                    'errorCode': 'UNAUTHORIZED',
                    'data': {}
                }, status=401)
            
            # Get request data
            data = json.loads(request.body)
            logger.info(f"Cart add item request: {data}")
            
            # Make API call to Java backend
            response = requests.post(
                f"{JAVA_API_URL}/api/cart/add-item",
                json=data,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                },
                timeout=30
            )
            
            logger.info(f"Cart API response status: {response.status_code}")
            
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': 'Invalid response from backend',
                    'errorCode': 'INVALID_RESPONSE',
                    'data': {}
                }, status=500)
                
        except Exception as e:
            logger.error(f"Error in cart_add_item_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e),
                'errorCode': 'INTERNAL_ERROR',
                'data': {}
            }, status=500)
    
    return JsonResponse({
        'status': 'ERROR',
        'statusMsg': 'Method not allowed',
        'errorCode': 'METHOD_NOT_ALLOWED',
        'data': {}
    }, status=405)

@csrf_exempt
@check_auth
def cart_items_proxy(request):
    """Proxy view for getting cart items"""
    if request.method == 'GET':
        try:
            # Get auth token from session
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': 'Unauthorized access',
                    'errorCode': 'UNAUTHORIZED',
                    'data': {}
                }, status=401)
            
            # Get query parameters
            channel_id = request.GET.get('channelId')
            company_id = request.GET.get('companyId')
            
            # Build API URL with query parameters
            api_url = f"{JAVA_API_URL}/api/cart/items"
            if channel_id:
                api_url += f"?channelId={channel_id}"
            if company_id:
                api_url += f"{'&' if channel_id else '?'}companyId={company_id}"
            
            logger.info(f"Cart items API URL: {api_url}")
            
            # Make API call to Java backend
            response = requests.get(
                api_url,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                },
                timeout=30
            )
            
            logger.info(f"Cart items API response status: {response.status_code}")
            
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': 'Invalid response from backend',
                    'errorCode': 'INVALID_RESPONSE',
                    'data': {}
                }, status=500)
                
        except Exception as e:
            logger.error(f"Error in cart_items_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e),
                'errorCode': 'INTERNAL_ERROR',
                'data': {}
            }, status=500)
    
    return JsonResponse({
        'status': 'ERROR',
        'statusMsg': 'Method not allowed',
        'errorCode': 'METHOD_NOT_ALLOWED',
        'data': {}
    }, status=405)

@csrf_exempt
@check_auth
def cart_update_quantity_proxy(request):
    """Proxy view for updating cart item quantity"""
    if request.method == 'PUT':
        try:
            # Get auth token from session
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': 'Unauthorized access',
                    'errorCode': 'UNAUTHORIZED',
                    'data': {}
                }, status=401)
            
            # Get request data
            data = json.loads(request.body)
            logger.info(f"Cart update quantity request: {data}")
            
            # Make API call to Java backend
            response = requests.put(
                f"{JAVA_API_URL}/api/cart/update-quantity",
                json=data,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                },
                timeout=30
            )
            
            logger.info(f"Cart update quantity API response status: {response.status_code}")
            
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': 'Invalid response from backend',
                    'errorCode': 'INVALID_RESPONSE',
                    'data': {}
                }, status=500)
                
        except Exception as e:
            logger.error(f"Error in cart_update_quantity_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e),
                'errorCode': 'INTERNAL_ERROR',
                'data': {}
            }, status=500)
    
    return JsonResponse({
        'status': 'ERROR',
        'statusMsg': 'Method not allowed',
        'errorCode': 'METHOD_NOT_ALLOWED',
        'data': {}
    }, status=405)

@csrf_exempt
@check_auth
def cart_remove_item_proxy(request):
    """Proxy view for removing items from cart"""
    if request.method == 'DELETE':
        try:
            # Get auth token from session
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': 'Unauthorized access',
                    'errorCode': 'UNAUTHORIZED',
                    'data': {}
                }, status=401)
            
            # Get request data
            data = json.loads(request.body)
            logger.info(f"Cart remove item request: {data}")
            
            # Make API call to Java backend
            response = requests.delete(
                f"{JAVA_API_URL}/api/cart/remove-item",
                json=data,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                },
                timeout=30
            )
            
            logger.info(f"Cart remove item API response status: {response.status_code}")
            
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': 'Invalid response from backend',
                    'errorCode': 'INVALID_RESPONSE',
                    'data': {}
                }, status=500)
                
        except Exception as e:
            logger.error(f"Error in cart_remove_item_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e),
                'errorCode': 'INTERNAL_ERROR',
                'data': {}
            }, status=500)
    
    return JsonResponse({
        'status': 'ERROR',
        'statusMsg': 'Method not allowed',
        'errorCode': 'METHOD_NOT_ALLOWED',
        'data': {}
    }, status=405)

@csrf_exempt
@check_auth
def cart_clear_proxy(request):
    """Proxy view for clearing cart"""
    if request.method == 'DELETE':
        try:
            # Get auth token from session
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': 'Unauthorized access',
                    'errorCode': 'UNAUTHORIZED',
                    'data': {}
                }, status=401)
            
            # Get query parameters
            channel_id = request.GET.get('channelId')
            company_id = request.GET.get('companyId')
            
            # Build API URL with query parameters
            api_url = f"{JAVA_API_URL}/api/cart/clear"
            if channel_id:
                api_url += f"?channelId={channel_id}"
            if company_id:
                api_url += f"{'&' if channel_id else '?'}companyId={company_id}"
            
            logger.info(f"Cart clear API URL: {api_url}")
            
            # Make API call to Java backend
            response = requests.delete(
                api_url,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                },
                timeout=30
            )
            
            logger.info(f"Cart clear API response status: {response.status_code}")
            
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': 'Invalid response from backend',
                    'errorCode': 'INVALID_RESPONSE',
                    'data': {}
                }, status=500)
                
        except Exception as e:
            logger.error(f"Error in cart_clear_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e),
                'errorCode': 'INTERNAL_ERROR',
                'data': {}
            }, status=500)
    
    return JsonResponse({
        'status': 'ERROR',
        'statusMsg': 'Method not allowed',
        'errorCode': 'METHOD_NOT_ALLOWED',
        'data': {}
    }, status=405)

@csrf_exempt
@check_auth
def cart_summary_proxy(request):
    """Proxy view for getting cart summary"""
    if request.method == 'GET':
        try:
            # Get auth token from session
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': 'Unauthorized access',
                    'errorCode': 'UNAUTHORIZED',
                    'data': {}
                }, status=401)
            
            # Get query parameters
            channel_id = request.GET.get('channelId')
            company_id = request.GET.get('companyId')
            
            # Build API URL with query parameters
            api_url = f"{JAVA_API_URL}/api/cart/summary"
            if channel_id:
                api_url += f"?channelId={channel_id}"
            if company_id:
                api_url += f"{'&' if channel_id else '?'}companyId={company_id}"
            
            logger.info(f"Cart summary API URL: {api_url}")
            
            # Make API call to Java backend
            response = requests.get(
                api_url,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                },
                timeout=30
            )
            
            logger.info(f"Cart summary API response status: {response.status_code}")
            
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': 'Invalid response from backend',
                    'errorCode': 'INVALID_RESPONSE',
                    'data': {}
                }, status=500)
                
        except Exception as e:
            logger.error(f"Error in cart_summary_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e),
                'errorCode': 'INTERNAL_ERROR',
                'data': {}
            }, status=500)
    
    return JsonResponse({
        'status': 'ERROR',
        'statusMsg': 'Method not allowed',
        'errorCode': 'METHOD_NOT_ALLOWED',
        'data': {}
    }, status=405)

@csrf_exempt
@check_auth
def channel_categories_proxy(request, channel_id):
    """Proxy view for channel categories API"""
    if request.method == 'GET':
        try:
            # Get auth token from session
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
            logger.info(f"Fetching categories for channel ID: {channel_id}")
            
            # Make request to Java API
            response = requests.get(
                f"{JAVA_API_URL}/api/channels/{channel_id}/categories",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/json'
                },
                timeout=30
            )
            
            logger.info(f"Channel categories API response status: {response.status_code}")
            
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': response.text or 'Invalid response from backend'
                }, status=500)
                
        except Exception as e:
            logger.error(f"Error in channel_categories_proxy GET: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    
    elif request.method == 'POST':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
            payload = json.loads(request.body)
            logger.info(f"Assigning category to channel ID: {channel_id}, payload: {payload}")
            
            response = requests.post(
                f"{JAVA_API_URL}/api/channels/{channel_id}/categories",
                json=payload,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                timeout=30
            )
            
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': response.text or 'Invalid response from backend'
                }, status=500)
        except Exception as e:
            logger.error(f"Error in channel_categories_proxy POST: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    
    return JsonResponse({
        'status': 'ERROR',
        'statusMsg': 'Method not allowed'
    }, status=405)


# Flipbook Proxy Views
@csrf_exempt
@check_auth
def flipbook_hotspots_save_proxy(request):
    """Proxy view for saving flipbook hotspots"""
    if request.method == 'POST':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
            data = json.loads(request.body)
            response = requests.post(
                f"{JAVA_API_URL}/api/flipbook/hotspots/save",
                json=data,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                },
                timeout=30
            )
            
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': response.text or 'Invalid response from backend'
                }, status=500)
        except Exception as e:
            logger.error(f"Error in flipbook_hotspots_save_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)

@csrf_exempt
@check_auth
def flipbook_hotspots_get_proxy(request):
    """Proxy view for getting flipbook hotspots"""
    if request.method == 'GET':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
            doc_key = request.GET.get('docKey')
            params = {}
            if doc_key:
                params['docKey'] = doc_key
            
            response = requests.get(
                f"{JAVA_API_URL}/api/flipbook/hotspots",
                params=params,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/json'
                },
                timeout=30
            )
            
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': response.text or 'Invalid response from backend'
                }, status=500)
        except Exception as e:
            logger.error(f"Error in flipbook_hotspots_get_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)

@csrf_exempt
@check_auth
def flipbook_pdf_upload_proxy(request):
    """Proxy view for uploading flipbook PDF"""
    if request.method == 'POST':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
            files = {}
            if 'file' in request.FILES:
                file_obj = request.FILES['file']
                files['file'] = (file_obj.name, file_obj.read(), file_obj.content_type)
            
            data = request.POST.dict()
            
            response = requests.post(
                f"{JAVA_API_URL}/api/flipbook/pdf/upload",
                data=data,
                files=files,
                headers={
                    'Authorization': f'Bearer {auth_token}'
                },
                timeout=60
            )
            
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': response.text or 'Invalid response from backend'
                }, status=500)
        except Exception as e:
            logger.error(f"Error in flipbook_pdf_upload_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)

@csrf_exempt
@check_auth
def flipbook_pdf_save_proxy(request):
    """Proxy view for saving flipbook PDF"""
    if request.method == 'POST':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
            files = {}
            if 'file' in request.FILES:
                file_obj = request.FILES['file']
                files['file'] = (file_obj.name, file_obj.read(), file_obj.content_type)
            
            data = request.POST.dict()
            
            response = requests.post(
                f"{JAVA_API_URL}/api/flipbook/pdf/save",
                data=data,
                files=files,
                headers={
                    'Authorization': f'Bearer {auth_token}'
                },
                timeout=60
            )
            
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': response.text or 'Invalid response from backend'
                }, status=500)
        except Exception as e:
            logger.error(f"Error in flipbook_pdf_save_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)

@csrf_exempt
@check_auth
def flipbook_pdf_load_proxy(request):
    """Proxy view for loading flipbook PDF"""
    if request.method == 'GET':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
            doc_key = request.GET.get('docKey')
            params = {}
            if doc_key:
                params['docKey'] = doc_key
            
            response = requests.get(
                f"{JAVA_API_URL}/api/flipbook/pdf/load",
                params=params,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/pdf'
                },
                timeout=30
            )
            
            if response.status_code == 200:
                return HttpResponse(response.content, content_type='application/pdf')
            else:
                try:
                    return JsonResponse(response.json(), status=response.status_code)
                except ValueError:
                    return JsonResponse({
                        'status': 'ERROR',
                        'statusMsg': response.text or 'Invalid response from backend'
                    }, status=response.status_code)
        except Exception as e:
            logger.error(f"Error in flipbook_pdf_load_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)

@csrf_exempt
@check_auth
def flipbook_pdf_delete_proxy(request):
    """Proxy view for deleting flipbook PDF"""
    if request.method == 'DELETE':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
            doc_key = request.GET.get('docKey')
            params = {}
            if doc_key:
                params['docKey'] = doc_key
            
            response = requests.delete(
                f"{JAVA_API_URL}/api/flipbook/pdf/delete",
                params=params,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/json'
                },
                timeout=30
            )
            
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': response.text or 'Invalid response from backend'
                }, status=500)
        except Exception as e:
            logger.error(f"Error in flipbook_pdf_delete_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)

@csrf_exempt
@check_auth
def flipbook_pdf_download_proxy(request):
    """Proxy view for downloading flipbook PDF"""
    if request.method == 'GET':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
            doc_key = request.GET.get('docKey')
            params = {}
            if doc_key:
                params['docKey'] = doc_key
            
            response = requests.get(
                f"{JAVA_API_URL}/api/flipbook/pdf/download",
                params=params,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/pdf'
                },
                timeout=30
            )
            
            if response.status_code == 200:
                return HttpResponse(response.content, content_type='application/pdf')
            else:
                try:
                    return JsonResponse(response.json(), status=response.status_code)
                except ValueError:
                    return JsonResponse({
                        'status': 'ERROR',
                        'statusMsg': response.text or 'Invalid response from backend'
                    }, status=response.status_code)
        except Exception as e:
            logger.error(f"Error in flipbook_pdf_download_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)

@csrf_exempt
@check_auth
def flipbook_pdf_download_with_hotspots_proxy(request):
    """Proxy view for downloading flipbook PDF with hotspots"""
    if request.method == 'GET':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
            doc_key = request.GET.get('docKey')
            params = {}
            if doc_key:
                params['docKey'] = doc_key
            
            response = requests.get(
                f"{JAVA_API_URL}/api/flipbook/pdf/download-with-hotspots",
                params=params,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/pdf'
                },
                timeout=30
            )
            
            if response.status_code == 200:
                return HttpResponse(response.content, content_type='application/pdf')
            else:
                try:
                    return JsonResponse(response.json(), status=response.status_code)
                except ValueError:
                    return JsonResponse({
                        'status': 'ERROR',
                        'statusMsg': response.text or 'Invalid response from backend'
                    }, status=response.status_code)
        except Exception as e:
            logger.error(f"Error in flipbook_pdf_download_with_hotspots_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)

# PDF Upload View
@csrf_exempt
@check_auth
def pdf_upload_view(request):
    """View for uploading PDF files"""
    if request.method == 'POST':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
            if 'file' not in request.FILES:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'No file provided'}, status=400)
            
            file_obj = request.FILES['file']
            files = {'file': (file_obj.name, file_obj.read(), file_obj.content_type)}
            data = request.POST.dict()
            
            response = requests.post(
                f"{JAVA_API_URL}/api/pdf/upload",
                data=data,
                files=files,
                headers={
                    'Authorization': f'Bearer {auth_token}'
                },
                timeout=60
            )
            
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': response.text or 'Invalid response from backend'
                }, status=500)
        except Exception as e:
            logger.error(f"Error in pdf_upload_view: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)

# Location Management Views
@check_auth
def locations_list(request):
    """View for displaying locations list"""
    user_data = request.session.get('user_data', {})
    return render(request, 'pages/locations.html', {'user_data': user_data})

@csrf_exempt
@check_auth
def locations_save_proxy(request):
    """Proxy view for saving locations"""
    if request.method == 'POST':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
            data = json.loads(request.body)
            response = requests.post(
                f"{JAVA_API_URL}/api/locations/save",
                json=data,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                },
                timeout=30
            )
            
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': response.text or 'Invalid response from backend'
                }, status=500)
        except Exception as e:
            logger.error(f"Error in locations_save_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)

@csrf_exempt
@check_auth
def locations_list_proxy(request):
    """Proxy view for listing locations"""
    if request.method == 'GET':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
            
            logger.info("Fetching locations from Java API")
            response = requests.get(
                f"{JAVA_API_URL}/api/locations",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                },
                timeout=30
            )
            
            logger.info(f"Locations API response status: {response.status_code}")
            try:
                response_data = response.json()
                # Use safe=False to allow non-dict objects (like lists) to be serialized
                return JsonResponse(response_data, status=response.status_code, safe=False)
            except (ValueError, json.JSONDecodeError) as e:
                logger.error(f"Failed to parse locations response: {e}")
                return JsonResponse({
                    'status': 'error',
                    'error': response.text or 'Invalid response from backend'
                }, status=500)
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error in locations_list_proxy: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'error': f'Failed to connect to backend: {str(e)}'
            }, status=500)
        except Exception as e:
            logger.error(f"Error in locations_list_proxy: {str(e)}", exc_info=True)
            return JsonResponse({
                'status': 'error',
                'error': str(e)
            }, status=500)
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=400)

@csrf_exempt
@check_auth
def location_detail_proxy(request, location_id):
    """Proxy view for getting location details"""
    if request.method == 'GET':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
            response = requests.get(
                f"{JAVA_API_URL}/api/locations/{location_id}",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/json'
                },
                timeout=30
            )
            
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': response.text or 'Invalid response from backend'
                }, status=500)
        except Exception as e:
            logger.error(f"Error in location_detail_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)

@csrf_exempt
@check_auth
def location_delete_proxy(request, location_id):
    """Proxy view for deleting locations"""
    if request.method == 'DELETE':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
            response = requests.delete(
                f"{JAVA_API_URL}/api/locations/{location_id}/delete",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/json'
                },
                timeout=30
            )
            
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': response.text or 'Invalid response from backend'
                }, status=500)
        except Exception as e:
            logger.error(f"Error in location_delete_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)

@csrf_exempt
@check_auth
def location_soft_delete_proxy(request, location_id):
    """Proxy view for soft deleting locations"""
    if request.method == 'DELETE':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
            response = requests.delete(
                f"{JAVA_API_URL}/api/locations/{location_id}/soft-delete",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/json'
                },
                timeout=30
            )
            
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': response.text or 'Invalid response from backend'
                }, status=500)
        except Exception as e:
            logger.error(f"Error in location_soft_delete_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)

# Auth and Connection Views
@csrf_exempt
@check_auth
def get_auth_token(request):
    """Proxy view for getting auth token"""
    if request.method == 'GET':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
            return JsonResponse({
                'status': 'SUCCESS',
                'token': auth_token
            })
        except Exception as e:
            logger.error(f"Error in get_auth_token: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)

@csrf_exempt
@check_auth
def test_java_connection(request):
    """Proxy view for testing Java backend connection"""
    if request.method == 'GET':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
            response = requests.get(
                f"{JAVA_API_URL}/api/health",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/json'
                },
                timeout=10
            )
            
            return JsonResponse({
                'status': 'SUCCESS' if response.status_code == 200 else 'ERROR',
                'statusCode': response.status_code,
                'message': 'Connection successful' if response.status_code == 200 else 'Connection failed'
            })
        except Exception as e:
            logger.error(f"Error in test_java_connection: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)

# Materials Bulk Upload Views
@check_auth
def materials_bulk_upload(request):
    """View for materials bulk upload"""
    user_data = request.session.get('user_data', {})
    return render(request, 'pages/materials_bulk_upload.html', {'user_data': user_data})

@csrf_exempt
@check_auth
def materials_bulk_payload_proxy(request):
    """Proxy view for materials bulk payload"""
    if request.method == 'POST':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
            data = json.loads(request.body)
            response = requests.post(
                f"{JAVA_API_URL}/api/materials/bulk-upload/payload",
                json=data,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                },
                timeout=60
            )
            
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': response.text or 'Invalid response from backend'
                }, status=500)
        except Exception as e:
            logger.error(f"Error in materials_bulk_payload_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)

@csrf_exempt
@check_auth
def master_bom_upload_proxy(request):
    """Proxy view for Master BOM Excel upload to Java backend"""
    if request.method == 'POST':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
            if 'file' not in request.FILES:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'No file uploaded'}, status=400)
            
            excel_file = request.FILES['file']
            
            # Forward to Java backend
            files = {'file': (excel_file.name, excel_file.read(), excel_file.content_type)}
            
            response = requests.post(
                f"{JAVA_API_URL}/api/v1/bom/master/upload",
                files=files,
                headers={
                    'Authorization': f'Bearer {auth_token}'
                },
                timeout=120 # Excel uploads might take longer
            )
            
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except (ValueError, json.JSONDecodeError):
                logger.error(f"Invalid JSON response from master_bom_upload: {response.status_code}")
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': response.text or 'Invalid response from Master BOM service',
                    'statusCode': response.status_code
                }, status=response.status_code if response.status_code != 200 else 500)
        except Exception as e:
            logger.error(f"Error in master_bom_upload_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)

@check_auth
def master_bom_fetch_proxy(request):
    """Proxy view for fetching BOM from Java backend by FG number"""
    if request.method == 'GET':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
            fg_number = request.GET.get('fg_number')
            if not fg_number:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'FG Number is required'}, status=400)
            
            params = {'fg_number': fg_number}
            file_id = request.GET.get('file_id')
            if file_id:
                params['file_id'] = file_id
            
            response = requests.get(
                f"{JAVA_API_URL}/api/v1/bom/master/fetch",
                params=params,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/json'
                },
                timeout=60
            )
            
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except (ValueError, json.JSONDecodeError):
                logger.error(f"Invalid JSON response from master_bom_fetch: {response.status_code}")
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': response.text or 'Invalid response from Master BOM service',
                    'statusCode': response.status_code
                }, status=response.status_code if response.status_code != 200 else 500)
        except Exception as e:
            logger.error(f"Error in master_bom_fetch_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)

@check_auth
def master_bom_files_list_proxy(request):
    """Proxy view for listing Master BOM files from Java backend"""
    if request.method == 'GET':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
            response = requests.get(
                f"{JAVA_API_URL}/api/v1/bom/master/files",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/json'
                },
                timeout=30
            )
            
            try:
                # Return the list directly (safe=False allowed for lists)
                return JsonResponse(response.json(), safe=False, status=response.status_code)
            except (ValueError, json.JSONDecodeError):
                logger.error(f"Invalid JSON response from master_bom_files_list: {response.status_code}")
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': response.text or 'Invalid response from Master BOM service',
                    'statusCode': response.status_code
                }, status=response.status_code if response.status_code != 200 else 500)
        except Exception as e:
            logger.error(f"Error in master_bom_files_list_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)

@csrf_exempt
@check_auth
def materials_template_download(request):
    """Proxy view for downloading materials template"""
    if request.method == 'GET':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
            response = requests.get(
                f"{JAVA_API_URL}/api/materials/template/download",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                },
                timeout=30
            )
            
            if response.status_code == 200:
                return HttpResponse(
                    response.content,
                    content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
            else:
                try:
                    return JsonResponse(response.json(), status=response.status_code)
                except ValueError:
                    return JsonResponse({
                        'status': 'ERROR',
                        'statusMsg': response.text or 'Invalid response from backend'
                    }, status=response.status_code)
        except Exception as e:
            logger.error(f"Error in materials_template_download: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)

# Vendor Catalogue Views
@csrf_exempt
@check_auth
def vendor_catalogue_check_proxy(request):
    """Proxy view for checking vendor catalogue"""
    if request.method == 'GET':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
            response = requests.get(
                f"{JAVA_API_URL}/api/vendor/catalogue/check",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/json'
                },
                timeout=30
            )
            
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': response.text or 'Invalid response from backend'
                }, status=500)
        except Exception as e:
            logger.error(f"Error in vendor_catalogue_check_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)

@csrf_exempt
@check_auth
def vendor_catalogue_upload_proxy(request):
    """Proxy view for uploading vendor catalogue"""
    if request.method == 'POST':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
            files = {}
            if 'file' in request.FILES:
                file_obj = request.FILES['file']
                files['file'] = (file_obj.name, file_obj.read(), file_obj.content_type)
            
            data = request.POST.dict()
            
            response = requests.post(
                f"{JAVA_API_URL}/api/vendor/catalogue/upload",
                data=data,
                files=files,
                headers={
                    'Authorization': f'Bearer {auth_token}'
                },
                timeout=60
            )
            
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': response.text or 'Invalid response from backend'
                }, status=500)
        except Exception as e:
            logger.error(f"Error in vendor_catalogue_upload_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)

@csrf_exempt
@check_auth
def vendor_catalogue_download_proxy(request):
    """Proxy view for downloading vendor catalogue"""
    if request.method == 'GET':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
            response = requests.get(
                f"{JAVA_API_URL}/api/vendor/catalogue/download",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                },
                timeout=30
            )
            
            if response.status_code == 200:
                return HttpResponse(
                    response.content,
                    content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
            else:
                try:
                    return JsonResponse(response.json(), status=response.status_code)
                except ValueError:
                    return JsonResponse({
                        'status': 'ERROR',
                        'statusMsg': response.text or 'Invalid response from backend'
                    }, status=response.status_code)
        except Exception as e:
            logger.error(f"Error in vendor_catalogue_download_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)

@csrf_exempt
@check_auth
def vendor_catalogue_replace_proxy(request):
    """Proxy view for replacing vendor catalogue"""
    if request.method == 'POST':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
            files = {}
            if 'file' in request.FILES:
                file_obj = request.FILES['file']
                files['file'] = (file_obj.name, file_obj.read(), file_obj.content_type)
            
            data = request.POST.dict()
            
            response = requests.post(
                f"{JAVA_API_URL}/api/vendor/catalogue/replace",
                data=data,
                files=files,
                headers={
                    'Authorization': f'Bearer {auth_token}'
                },
                timeout=60
            )
            
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': response.text or 'Invalid response from backend'
                }, status=500)
        except Exception as e:
            logger.error(f"Error in vendor_catalogue_replace_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)

# Inventory Management Views
@check_auth
def inventory_list(request):
    """View for displaying inventory list"""
    user_data = request.session.get('user_data', {})
    return render(request, 'pages/inventory.html', {'user_data': user_data})

@csrf_exempt
@check_auth
def inventory_list_proxy(request):
    """Proxy view for listing inventory"""
    if request.method == 'GET':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
            response = requests.get(
                f"{JAVA_API_URL}/api/inventory",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/json'
                },
                timeout=30
            )
            
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': response.text or 'Invalid response from backend'
                }, status=500)
        except Exception as e:
            logger.error(f"Error in inventory_list_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)

@csrf_exempt
@check_auth
def inventory_update_stock_proxy(request, material_id):
    """Proxy view for updating inventory stock"""
    if request.method in ['POST', 'PUT']:
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
            data = json.loads(request.body)
            # Use POST method for the backend API call regardless of frontend method
            response = requests.post(
                f"{JAVA_API_URL}/api/inventory/{material_id}/stock/",
                json=data,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                },
                timeout=30
            )
            
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': response.text or 'Invalid response from backend'
                }, status=500)
        except Exception as e:
            logger.error(f"Error in inventory_update_stock_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)

@csrf_exempt
@check_auth
def inventory_bulk_update_stock_proxy(request):
    """Proxy view for bulk updating inventory stock"""
    if request.method == 'POST':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
            data = json.loads(request.body)
            response = requests.post(
                f"{JAVA_API_URL}/api/inventory/bulk-update-stock",
                json=data,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                },
                timeout=60
            )
            
            try:
                return JsonResponse(response.json(), status=response.status_code)
            except ValueError:
                return JsonResponse({
                    'status': 'ERROR',
                    'statusMsg': response.text or 'Invalid response from backend'
                }, status=500)
        except Exception as e:
            logger.error(f"Error in inventory_bulk_update_stock_proxy: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)

@check_auth
def inventory_bulk_upload(request):
    """View for inventory bulk upload"""
    user_data = request.session.get('user_data', {})
    return render(request, 'pages/inventory_bulk_upload.html', {'user_data': user_data})

@csrf_exempt
@check_auth
def inventory_template_download(request):
    """Proxy view for downloading inventory template"""
    if request.method == 'GET':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
            response = requests.get(
                f"{JAVA_API_URL}/api/inventory/template/download",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                },
                timeout=30
            )
            
            if response.status_code == 200:
                return HttpResponse(
                    response.content,
                    content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
            else:
                try:
                    return JsonResponse(response.json(), status=response.status_code)
                except ValueError:
                    return JsonResponse({
                        'status': 'ERROR',
                        'statusMsg': response.text or 'Invalid response from backend'
                    }, status=response.status_code)
        except Exception as e:
            logger.error(f"Error in inventory_template_download: {str(e)}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': str(e)
            }, status=500)
    return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)

@check_auth
def product_detail_view(request, material_id):
    """View for displaying individual product details"""
    try:
        auth_token = request.session.get('auth_token')
        if not auth_token:
            logger.error("No auth token found in session")
            return redirect('pages:login')
        
        # Get URL parameters
        channel_id = request.GET.get('channelId')
        company_id = request.GET.get('companyId')
        
        # Get material details from API
        material_response = requests.get(
            f"{JAVA_API_URL}/api/materials/{material_id}",
            headers={
                'Authorization': f'Bearer {auth_token}',
                'Accept': 'application/json'
            }
        )
        
        if material_response.status_code != 200:
            logger.error(f"Failed to fetch material {material_id}: {material_response.status_code}")
            return render(request, 'pages/error.html', {
                'error_message': 'Product not found or access denied',
                'user_data': request.session.get('user_data', {})
            })
        
        material_data = material_response.json()
        if material_data.get('status') != 'SUCCESS':
            logger.error(f"API error for material {material_id}: {material_data.get('statusMsg')}")
            return render(request, 'pages/error.html', {
                'error_message': 'Product not found',
                'user_data': request.session.get('user_data', {})
            })
        
        material = material_data.get('data', {})
        
        return render(request, 'pages/product_detail.html', {
            'material': material,
            'channel_id': channel_id,
            'company_id': company_id,
            'user_data': request.session.get('user_data', {}),
            'auth_token': request.session.get('auth_token', '')
        })
        
    except Exception as e:
        logger.error(f"Error in product_detail_view: {str(e)}")
        return render(request, 'pages/error.html', {
            'error_message': 'An error occurred while loading the product',
            'user_data': request.session.get('user_data', {})
        })


@csrf_exempt
@check_auth
def catalog_view(request, channel_code=None):
    """View for displaying catalog of materials by channel"""
    
    try:
        auth_token = request.session.get('auth_token')
        if not auth_token:
            logger.error("No auth token found in session")
            return redirect('pages:login')
        
        # Get channels for dropdown
        channels_response = requests.get(
            f"{JAVA_API_URL}/api/channels/all",
            headers={
                'Authorization': f'Bearer {auth_token}',
                'Accept': 'application/json'
            }
        )
        
        company_id = None
        if channels_response.status_code != 200:
            logger.error(f"Failed to fetch channels: {channels_response.status_code}")
            channels = []
        else:
            channels_data = channels_response.json()
            if channels_data.get('status') in ['SUCCESS', '200']:
                data = channels_data.get('data', {})
                company_id = data.get('companyId')
                channels = data.get('channels', [])
                logger.info(f"Fetched {len(channels)} channels, company_id: {company_id}")
            else:
                logger.error(f"Unexpected channels API response: {channels_data}")
                channels = []
        
        # Get materials for the selected channel
        materials = []
        
        # If no channel is selected, default to the first channel
        if not channel_code and channels:
            channel_code = channels[0]['channelCode']
            logger.info(f"No channel selected, defaulting to first channel: {channel_code}")
        
        if channel_code:
            # Find the channel ID for the selected channel code
            selected_channel = None
            for channel in channels:
                if channel['channelCode'] == channel_code:
                    selected_channel = channel
                    break
            
            if selected_channel:
                # Use the new API endpoint to get channel-specific materials
                channel_id = selected_channel['channelId']
                materials_response = requests.get(
                    f"{JAVA_API_URL}/api/channels/{channel_id}/materials",
                    headers={
                        'Authorization': f'Bearer {auth_token}',
                        'Accept': 'application/json'
                    }
                )
                
                if materials_response.status_code == 200:
                    materials_data = materials_response.json()
                    materials = materials_data.get('data', {}).get('materials', [])
                    logger.info(f"Fetched {len(materials)} materials for channel {channel_code} (ID: {channel_id})")
                else:
                    logger.error(f"Failed to fetch materials for channel {channel_code}: {materials_response.status_code}")
                    logger.error(f"Materials API response: {materials_response.text}")
            else:
                logger.error(f"Channel not found for code: {channel_code}")
        
        # If no materials found, show empty list
        if not materials and channel_code:
            logger.warning("No materials found from API")
            materials = []
        
        # Get user_data from session
        user_data = request.session.get('user_data', {})
        
        context = {
            'channels': channels,
            'materials': materials,
            'selected_channel': channel_code,
            'user_data': user_data,
            'company_id': company_id,
            'auth_token': request.session.get('auth_token', ''),
            'base_url': request.build_absolute_uri('/')
        }
        
        return render(request, 'pages/catalog.html', context)
        
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error to Java backend: {e}")
        messages.error(request, 'Could not connect to server. Please try again later.')
        
        # Set default channel even in error case
        default_channel = channels[0]['channelCode'] if channels else None
        return render(request, 'pages/catalog.html', {
            'channels': channels,
            'materials': [],
            'selected_channel': default_channel,
            'user_data': request.session.get('user_data', {}),
            'auth_token': request.session.get('auth_token', ''),
            'base_url': request.build_absolute_uri('/')
        })
    except Exception as e:
        logger.error(f"Error in catalog view: {str(e)}")
        messages.error(request, f'An error occurred: {str(e)}')
        
        # Set default channel even in error case
        default_channel = channels[0]['channelCode'] if channels else None
        return render(request, 'pages/catalog.html', {
            'channels': channels,
            'materials': [],
            'selected_channel': default_channel,
            'user_data': request.session.get('user_data', {}),
            'auth_token': request.session.get('auth_token', ''),
            'base_url': request.build_absolute_uri('/')
        })

# Procurement PR Proxy Views
@csrf_exempt
@check_auth
def purchase_requisitions_proxy(request):
    if request.method == 'GET':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
            response = requests.get(
                f"{JAVA_API_URL}/api/purchase-requisitions",
                params=request.GET.dict(),
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/json'
                }
            )
            return JsonResponse(response.json(), status=response.status_code)
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
    
    elif request.method == 'POST':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
            payload = json.loads(request.body)
            logger.info(f"PURCHASE REQUISITION PROXY PAYLOAD: {payload}")
            print(f"PURCHASE REQUISITION PROXY PAYLOAD: {payload}", flush=True)
            response = requests.post(
                f"{JAVA_API_URL}/api/purchase-requisitions",
                json=payload,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                }
            )
            try:
                data = response.json()
            except ValueError:
                data = {'message': response.text}
            
            if response.status_code in [200, 201]:
                # Extract prNumber
                pr_number = None
                if isinstance(data, dict):
                    pr_number = data.get('prNumber') or data.get('data', {}).get('prNumber') or data.get('pr_number') or data.get('data', {}).get('pr_number')
                
                # Database fallback
                if not pr_number:
                    try:
                        import pymysql
                        conn = pymysql.connect(host='127.0.0.1', user='root', password='GstCheck2025', database='multimedia_governance')
                        with conn.cursor() as cur:
                            cur.execute("SELECT pr_number FROM purchase_requisitions ORDER BY id DESC LIMIT 1")
                            res = cur.fetchone()
                            if res:
                                pr_number = res[0]
                        conn.close()
                    except Exception as db_err:
                        logger.error(f"Error fetching latest pr_number from database: {db_err}")
                
                if pr_number:
                    try:
                        wf_payload = {
                            "title": f"{pr_number} Requested ",
                            "workflow_id": 10,
                            "request_type": "invoice",
                            "metadata": None,
                            "request_metadata": None
                        }
                        user_id = request.session.get('user_data', {}).get('superAdminId', 1)
                        wf_url = f"http://localhost:8001/api/requests?user_id={user_id}"
                        logger.info(f"Triggering workflow 10 for PR: {wf_url} with payload {wf_payload}")
                        wf_response = requests.post(wf_url, json=wf_payload, headers={'Content-Type': 'application/json'}, timeout=10)
                        logger.info(f"Workflow Engine response for PR: {wf_response.status_code} - {wf_response.text}")
                    except Exception as wf_err:
                        logger.error(f"Failed to trigger workflow 10 for PR {pr_number}: {wf_err}")

            return JsonResponse(data, status=response.status_code)
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
    
    return JsonResponse({'status': 'error', 'error': 'Method not allowed'}, status=405)

@csrf_exempt
@check_auth
def purchase_requisition_detail_proxy(request, pr_id):
    auth_token = request.session.get('auth_token')
    if not auth_token:
        return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
        
    url = f"{JAVA_API_URL}/api/purchase-requisitions/{pr_id}"
    headers = {
        'Authorization': f'Bearer {auth_token}',
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    
    try:
        if request.method == 'GET':
            response = requests.get(url, headers=headers)
        elif request.method == 'PUT':
            payload = json.loads(request.body)
            response = requests.put(url, json=payload, headers=headers)
        elif request.method == 'DELETE':
            response = requests.delete(url, headers=headers)
        else:
            return JsonResponse({'status': 'error', 'error': 'Method not allowed'}, status=405)
            
        if response.status_code == 204:
            return HttpResponse(status=204)
        return JsonResponse(response.json(), status=response.status_code)
    except Exception as e:
        return JsonResponse({'status': 'error', 'error': str(e)}, status=500)

@csrf_exempt
@check_auth
def purchase_requisition_status_proxy(request, pr_id):
    if request.method == 'POST':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
            payload = json.loads(request.body)
            response = requests.post(
                f"{JAVA_API_URL}/api/purchase-requisitions/{pr_id}/status",
                json=payload,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                }
            )
            return JsonResponse(response.json(), status=response.status_code)
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'error': 'Method not allowed'}, status=405)

@csrf_exempt
@check_auth
def vendors_list_proxy(request):
    if request.method == 'GET':
        try:
            # Fetch from FastAPI vendor_master (port 8001) — these have the real vendor_id
            # that the Vendor Portal uses for filtering, e.g. 1381 for Mark Jhon Supplies.
            # The Java /api/vendors/all returns companyId from company_details which is a
            # DIFFERENT table and different numbering — that was causing wrong vendor assignment.
            response = requests.get("http://127.0.0.1:8001/api/vendors/all", timeout=10)
            raw = response.json()  # returns list of {vendor_id, bp_no, name}

            # Normalize: set both 'vendor_id' and 'companyId' to the same vendor_master ID
            # so the dropdown in pr_create.html (which reads companyId) submits the right ID.
            normalized_vendors = []
            vendor_list = raw if isinstance(raw, list) else raw.get('data', [])
            for v in vendor_list:
                vid = v.get('vendor_id')
                normalized_vendors.append({
                    'vendor_id': vid,
                    'companyId': vid,           # pr_create.html reads companyId
                    'companyName': v.get('name'),
                    'name': v.get('name'),
                    'bp_no': v.get('bp_no'),
                })

            return JsonResponse({'status': 'SUCCESS', 'data': {'vendors': normalized_vendors}}, status=200)
        except Exception as e:
            logger.error(f"Vendors API Proxy Error: {e}")
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'error': 'Method not allowed'}, status=405)

@csrf_exempt
@require_http_methods(["POST"])
@check_auth
def image_describe_proxy(request):
    try:
        # Reconstruct files dict with content type and filename
        files = {}
        for name, file in request.FILES.items():
            # Reset file pointer to ensure we read everything
            file.seek(0)
            files[name] = (file.name, file.read(), file.content_type)
        
        # Forward the request to the backend service
        response = requests.post(
            f"{JAVA_API_URL}/api/image/image_describe/describes",
            files=files,
            data=request.POST
        )

        try:
            return JsonResponse(response.json(), status=response.status_code)
        except (ValueError, json.JSONDecodeError):
            logger.error(f"Invalid JSON response from image_describe: {response.status_code}")
            return JsonResponse({
                'status': 'error',
                'statusMsg': response.text or 'Invalid response from image description service',
                'statusCode': response.status_code
            }, status=response.status_code if response.status_code != 200 else 500)
    except Exception as e:
        logger.error(f"Image Describe Proxy Error: {e}")
        return JsonResponse({'status': 'error', 'statusMsg': str(e)}, status=500)

# @csrf_exempt
# # @require_http_methods(["POST"])
# # @check_auth
# def bom_aerospace_json_proxy(request):
#     """Proxy for CAD-based BOM generation (port 8080)"""
#     try:
#         # auth_token = request.session.get('auth_token')
#         # if not auth_token:
#         #     return JsonResponse({'status': 'ERROR', 'statusMsg': 'Authentication required'}, status=401)
            
#         files = {}
#         for name, file in request.FILES.items():
#             file.seek(0)
#             files[name] = (file.name, file.read(), file.content_type)
            
#         response = requests.post(
#             f"{JAVA_API_URL}/api/v1/bom/generate-from-cad",
#             files=files,
#             data=request.POST,
#             headers={'Authorization': f'Bearer {auth_token}'},
#             timeout=600
#         )
        
#         try:
#             return JsonResponse(response.json(), status=response.status_code)
#         except (ValueError, json.JSONDecodeError):
#             return JsonResponse({
#                 'status': 'ERROR',
#                 'statusMsg': response.text or 'Invalid response from BOM service',
#                 'statusCode': response.status_code
#             }, status=response.status_code if response.status_code != 200 else 500)
#     except Exception as e:
#         logger.error(f"BOM Aerospace Proxy Error: {e}")
#         return JsonResponse({'status': 'ERROR', 'statusMsg': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
@check_auth
def bom_aerospace_json_proxy(request):
    """Proxy for CAD-based BOM generation — forwards to Image_Describer FastAPI (port 5000)"""
    try:
        logger.info("=== BOM AEROSPACE PROXY START ===")
        logger.info(f"Files in request: {list(request.FILES.keys())}")
        logger.info(f"POST data keys: {list(request.POST.keys())}")

        # Build multipart files for FastAPI
        files = {}
        # The frontend sends 'file' key for CAD image
        cad_file = request.FILES.get('file') or request.FILES.get('image')
        if cad_file:
            cad_file.seek(0)
            files['image'] = (cad_file.name, cad_file.read(), cad_file.content_type)

        # Optional: Master BOM Excel file
        bom_excel = request.FILES.get('bom_excel_file')
        if bom_excel:
            bom_excel.seek(0)
            files['bom_excel'] = (bom_excel.name, bom_excel.read(), bom_excel.content_type)

        # Build the form data for FastAPI parameters
        data = {}
        field_map = [
            'part_type', 'mfg_method', 'stock_shape', 'stock_size',
            'machining_allowance', 'face_allowance', 'scrap_percentage',
            'bom_structure', 'input_mode', 'prompt', 'blank_length'
        ]
        for field in field_map:
            val = request.POST.get(field)
            if val is not None and val != '':
                data[field] = val

        # Forward to FastAPI Image_Describer service on port 5000
        target_url = "http://127.0.0.1:5000/bom-aerospace-json"
        
        # Route advanced multi-level extraction to the new Hybrid OCR pipeline
        if data.get('bom_structure') == 'Multi-level':
            target_url = "http://127.0.0.1:5000/bom-ocr-multi-level"
            
        logger.info(f"Forwarding to: {target_url}")

        response = requests.post(
            target_url,
            files=files,
            data=data,
            timeout=600
        )

        logger.info(f"FastAPI response status: {response.status_code}")

        try:
            return JsonResponse(response.json(), status=response.status_code, safe=False)
        except (ValueError, json.JSONDecodeError):
            logger.error(f"Invalid JSON from BOM aerospace endpoint: {response.status_code}")
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': response.text or 'Invalid response from BOM service',
                'statusCode': response.status_code
            }, status=response.status_code if response.status_code != 200 else 500)
    except requests.exceptions.ConnectionError:
        logger.error("BOM Aerospace Proxy: Cannot connect to Image_Describer service on port 5000")
        return JsonResponse({
            'status': 'ERROR',
            'statusMsg': 'BOM generation service is not available. Please ensure the Image_Describer service is running.'
        }, status=503)
    except Exception as e:
        logger.error(f"BOM Aerospace Proxy Error: {e}")
        return JsonResponse({'status': 'ERROR', 'statusMsg': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
@check_auth
def bom_image_json_proxy(request):
    """Proxy for Image-based BOM generation — forwards to Image_Describer FastAPI (port 5000)"""
    try:
        # Build multipart files for FastAPI
        files = {}
        img_file = request.FILES.get('file') or request.FILES.get('image')
        if img_file:
            img_file.seek(0)
            files['image'] = (img_file.name, img_file.read(), img_file.content_type)

        data = {}
        prompt = request.POST.get('prompt')
        if prompt:
            data['prompt'] = prompt

        # Forward to FastAPI Image_Describer service on port 5000
        target_url = "http://127.0.0.1:5000/bom-image-json"
        response = requests.post(
            target_url,
            files=files,
            data=data,
            timeout=300
        )

        try:
            return JsonResponse(response.json(), status=response.status_code, safe=False)
        except (ValueError, json.JSONDecodeError):
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': response.text or 'Invalid response from BOM service',
                'statusCode': response.status_code
            }, status=response.status_code if response.status_code != 200 else 500)
    except requests.exceptions.ConnectionError:
        logger.error("BOM Image Proxy: Cannot connect to Image_Describer service on port 5000")
        return JsonResponse({
            'status': 'ERROR',
            'statusMsg': 'BOM generation service is not available. Please ensure the Image_Describer service is running.'
        }, status=503)
    except Exception as e:
        logger.error(f"BOM Image Proxy Error: {e}")
        return JsonResponse({'status': 'ERROR', 'statusMsg': str(e)}, status=500)


# ------------------- Organization Module Views (Dummy Data) -------------------
def get_organization_mock_data(module):
    if module == 'companies':
        return [
            {
                'id': 1,
                'companyCode': 'NIT',
                'companyName': 'Northwind Technologies',
                'name': 'Northwind Technologies',
                'status': 'ACTIVE',
                'country': {'countryId': 1, 'countryName': 'India'},
                'currency': {'currencyId': 1, 'currencyCode': 'INR'}
            }
        ]
    elif module == 'countries':
        return [
            {
                'id': 1,
                'countryId': 1,
                'countryName': 'India',
                'isoCode': 'IN',
                'phoneCode': '+91',
                'status': 'ACTIVE'
            },
            {
                'id': 2,
                'countryId': 2,
                'countryName': 'United States',
                'isoCode': 'US',
                'phoneCode': '+1',
                'status': 'ACTIVE'
            }
        ]
    elif module == 'currencies':
        return [
            {
                'id': 1,
                'currencyId': 1,
                'currencyCode': 'INR',
                'currencyName': 'Indian Rupee',
                'symbol': '₹',
                'status': 'ACTIVE'
            },
            {
                'id': 2,
                'currencyId': 2,
                'currencyCode': 'USD',
                'currencyName': 'US Dollar',
                'symbol': '$',
                'status': 'ACTIVE'
            }
        ]
    elif module == 'channels':
        return [
            {
                'id': 1,
                'channelId': 1,
                'channelName': 'Online',
                'name': 'Online',
                'status': 'ACTIVE'
            },
            {
                'id': 2,
                'channelId': 2,
                'channelName': 'Retail',
                'name': 'Retail',
                'status': 'ACTIVE'
            }
        ]
    return None

@csrf_exempt
@check_auth
def organization_api_proxy(request, module, pk=None):
    """Generic proxy for Organization Module APIs (Countries, Currencies, Companies, Channels)"""
    from .models import Department

    if module == 'departments':
        try:
            if request.method == 'GET':
                depts = Department.objects.all()
                data = []
                for d in depts:
                    data.append({
                        'id': d.id,
                        'code': d.code,
                        'name': d.name,
                        'projects_count': d.projects_count,
                        'activities_count': d.activities_count,
                        'approved_budget': float(d.approved_budget)
                    })
                return JsonResponse({'status': 'SUCCESS', 'data': {'departments': data}})

            elif request.method == 'POST':
                payload = json.loads(request.body)
                d = Department.objects.create(
                    code=payload.get('code'),
                    name=payload.get('name') or payload.get('department'),
                    projects_count=payload.get('projects_count', 0),
                    activities_count=payload.get('activities_count', 0),
                    approved_budget=payload.get('approved_budget', 0.0)
                )
                return JsonResponse({'status': 'SUCCESS', 'data': {
                    'id': d.id,
                    'code': d.code,
                    'name': d.name,
                    'projects_count': d.projects_count,
                    'activities_count': d.activities_count,
                    'approved_budget': float(d.approved_budget)
                }})

            elif request.method == 'PUT':
                if not pk:
                    return JsonResponse({'status': 'ERROR', 'statusMsg': 'ID required for update'}, status=400)
                payload = json.loads(request.body)
                d = Department.objects.get(pk=pk)
                d.code = payload.get('code', d.code)
                d.name = payload.get('name', d.name) or payload.get('department', d.name)
                d.projects_count = payload.get('projects_count', d.projects_count)
                d.activities_count = payload.get('activities_count', d.activities_count)
                d.approved_budget = payload.get('approved_budget', d.approved_budget)
                d.save()
                return JsonResponse({'status': 'SUCCESS', 'data': {
                    'id': d.id,
                    'code': d.code,
                    'name': d.name,
                    'projects_count': d.projects_count,
                    'activities_count': d.activities_count,
                    'approved_budget': float(d.approved_budget)
                }})

            elif request.method == 'DELETE':
                if not pk:
                    return JsonResponse({'status': 'ERROR', 'statusMsg': 'ID required for delete'}, status=400)
                d = Department.objects.get(pk=pk)
                d.delete()
                return JsonResponse({'status': 'SUCCESS'})

            else:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)

        except Department.DoesNotExist:
            return JsonResponse({'status': 'ERROR', 'statusMsg': 'Department not found'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'ERROR', 'statusMsg': str(e)}, status=500)

    auth_token = request.session.get('auth_token')
    if not auth_token and 'HTTP_AUTHORIZATION' in request.META:
        auth_header = request.META.get('HTTP_AUTHORIZATION')
        if auth_header.startswith('Bearer '):
            auth_token = auth_header.split(' ')[1]
            
    company_id = get_company_id(request)

    url = f"{JAVA_API_URL}/api/organization/{module}"
    if pk:
        url = f"{JAVA_API_URL}/api/organization/{module}/{pk}"

    headers = {
        'Authorization': f'Bearer {auth_token}',
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }

    try:
        if request.method == 'GET':
            resp = requests.get(url, headers=headers, timeout=30)
        elif request.method == 'POST':
            payload = json.loads(request.body)
            if module == 'companies':
                if 'countryId' in payload:
                    payload['country'] = {'countryId': int(payload.pop('countryId'))}
                if 'currencyId' in payload:
                    payload['currency'] = {'currencyId': int(payload.pop('currencyId'))}
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
        elif request.method == 'PUT':
            payload = json.loads(request.body)
            resp = requests.put(url, json=payload, headers=headers, timeout=30)
        elif request.method == 'DELETE':
            resp = requests.delete(url, headers=headers, timeout=30)
        else:
            return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)

        # Check if response failed or returned 403 / 502 / 503
        if resp.status_code not in [200, 201]:
            mock_data = get_organization_mock_data(module)
            if mock_data is not None:
                return JsonResponse({'status': 'SUCCESS', 'data': {module: mock_data}})

        try:
            body = resp.json()
            return JsonResponse(body, status=resp.status_code)
        except ValueError:
            return JsonResponse({
                'status': 'ERROR',
                'statusMsg': resp.text or 'Invalid response from backend'
            }, status=502 if resp.status_code == 200 else resp.status_code)

    except requests.exceptions.RequestException as e:
        logger.error(f"Organization API Proxy Error ({module}): {str(e)}")
        mock_data = get_organization_mock_data(module)
        if mock_data is not None:
            return JsonResponse({'status': 'SUCCESS', 'data': {module: mock_data}})
        return JsonResponse({'status': 'ERROR', 'statusMsg': 'Unable to reach backend service'}, status=502)
    except Exception as e:
        logger.error(f"Unexpected Proxy Error: {str(e)}")
        return JsonResponse({'status': 'ERROR', 'statusMsg': str(e)}, status=500)

@check_auth
def departments_list(request):
    user_data = request.session.get('user_data', {})
    return render(request, 'pages/departments.html', {'user_data': user_data})

@check_auth
def countries_list(request):
    user_data = request.session.get('user_data', {})
    return render(request, 'pages/countries.html', {'user_data': user_data})

@check_auth
def currencies_list(request):
    user_data = request.session.get('user_data', {})
    return render(request, 'pages/currencies.html', {'user_data': user_data})

@check_auth
def companies_list(request):
    user_data = request.session.get('user_data', {})
    return render(request, 'pages/companies.html', {'user_data': user_data})

@check_auth
def channels_list_org(request):
    user_data = request.session.get('user_data', {})
    return render(request, 'pages/channels.html', {'user_data': user_data})

@check_auth
def categories_list(request):
    """View for displaying hierarchical categories list"""
    user_data = request.session.get('user_data', {})
    return render(request, 'pages/categories.html', {'user_data': user_data})

@csrf_exempt
@check_auth
def categories_proxy(request, pk=None):
    """Proxy view for Categories API (mapped to item-categories)"""
    auth_token = request.session.get('auth_token')
    company_id = get_company_id(request)
    
    headers = {
        'Authorization': f'Bearer {auth_token}',
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }

    try:
        if request.method == 'GET':
            url = f"{JAVA_API_URL}/api/item-categories/{pk}" if pk else f"{JAVA_API_URL}/api/item-categories/all"
            resp = requests.get(url, headers=headers, timeout=30)
        elif request.method == 'POST':
            url = f"{JAVA_API_URL}/api/item-categories/save"
            payload = json.loads(request.body)
            if 'companyId' not in payload: payload['companyId'] = company_id
            # Fix SQL Error: 1048 - Column 'description' cannot be null
            if 'description' not in payload or not payload['description']:
                payload['description'] = payload.get('categoryName', payload.get('name', 'No description provided'))
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
        elif request.method == 'PUT' or (request.method == 'POST' and pk):
            url = f"{JAVA_API_URL}/api/item-categories/{pk}"
            payload = json.loads(request.body)
            resp = requests.put(url, json=payload, headers=headers, timeout=30)
        elif request.method == 'DELETE':
            url = f"{JAVA_API_URL}/api/item-categories/{pk}"
            resp = requests.delete(url, headers=headers, timeout=30)
        else:
            return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)

        try:
            return JsonResponse(resp.json(), status=resp.status_code)
        except ValueError:
            return JsonResponse({'status': 'ERROR', 'statusMsg': f'Invalid response: {resp.text[:100]}'}, status=resp.status_code)
    except Exception as e:
        logger.error(f"Categories Proxy Error: {str(e)}")
        return JsonResponse({'status': 'ERROR', 'statusMsg': str(e)}, status=500)

@csrf_exempt
@check_auth
def subcategories_proxy(request, pk=None):
    """Proxy view for Subcategories API (mapped to item-subcategories)"""
    auth_token = request.session.get('auth_token')
    company_id = get_company_id(request)
    
    headers = {
        'Authorization': f'Bearer {auth_token}',
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }

    try:
        if request.method == 'GET':
            url = f"{JAVA_API_URL}/api/item-subcategories/{pk}" if pk else f"{JAVA_API_URL}/api/item-subcategories/all"
            resp = requests.get(url, headers=headers, timeout=30)
        elif request.method == 'POST':
            payload = json.loads(request.body)
            # Cleanup payload
            sub_id = payload.get('id') or payload.get('subCategoryId')
            if not sub_id:
                payload.pop('id', None)
                payload.pop('subCategoryId', None)
            
            # Fix SQL Error: 1048 - Column 'description' cannot be null
            if 'description' not in payload or not payload['description']:
                payload['description'] = payload.get('subCategoryName', payload.get('name', 'No description provided'))

            if sub_id:
                url = f"{JAVA_API_URL}/api/item-subcategories/update"
                # Map to Java DTO fields if needed
                if 'itemSubcategoryId' not in payload: payload['itemSubcategoryId'] = sub_id
                if 'itemSubcategoryName' not in payload: payload['itemSubcategoryName'] = payload.get('name')
                resp = requests.post(url, json=payload, headers=headers, timeout=30)
            else:
                url = f"{JAVA_API_URL}/api/item-subcategories/save"
                if 'itemSubcategoryName' not in payload: payload['itemSubcategoryName'] = payload.get('name')
                if 'companyId' not in payload: payload['companyId'] = company_id
                resp = requests.post(url, json=payload, headers=headers, timeout=30)
        elif request.method == 'DELETE':
            url = f"{JAVA_API_URL}/api/item-subcategories/{pk}"
            resp = requests.delete(url, headers=headers, timeout=30)
        else:
            return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)

        try:
            return JsonResponse(resp.json(), status=resp.status_code)
        except ValueError:
            return JsonResponse({'status': 'ERROR', 'statusMsg': f'Invalid response: {resp.text[:100]}'}, status=resp.status_code)
    except Exception as e:
        logger.error(f"Subcategories Proxy Error: {str(e)}")
        return JsonResponse({'status': 'ERROR', 'statusMsg': str(e)}, status=500)

@csrf_exempt
@check_auth
def subcategories_bulk_proxy(request):
    """Proxy view for Bulk Subcategories API"""
    auth_token = request.session.get('auth_token')
    company_id = get_company_id(request)
    
    url = f"{JAVA_API_URL}/api/item-subcategories/bulk"
    headers = {
        'Authorization': f'Bearer {auth_token}',
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }

    try:
        if request.method == 'POST':
            payload = json.loads(request.body)
            # Ensure each item in bulk has companyId
            if isinstance(payload, list):
                for item in payload:
                    if 'companyId' not in item: item['companyId'] = company_id
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            try:
                return JsonResponse(resp.json(), status=resp.status_code)
            except ValueError:
                return JsonResponse({'status': 'ERROR', 'statusMsg': f'Invalid response: {resp.text[:100]}'}, status=resp.status_code)
        return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)
    except Exception as e:
        logger.error(f"Subcategories Bulk Proxy Error: {str(e)}")
        return JsonResponse({'status': 'ERROR', 'statusMsg': str(e)}, status=500)

@csrf_exempt
@check_auth
def subcategories_tree_proxy(request, category_id):
    """Proxy view for Subcategory Tree API"""
    auth_token = request.session.get('auth_token')
    
    url = f"{JAVA_API_URL}/api/item-subcategories/tree/{category_id}"
    headers = {
        'Authorization': f'Bearer {auth_token}',
        'Accept': 'application/json'
    }

    try:
        if request.method == 'GET':
            resp = requests.get(url, headers=headers, timeout=30)
            try:
                return JsonResponse(resp.json(), status=resp.status_code)
            except ValueError:
                return JsonResponse({'status': 'ERROR', 'statusMsg': f'Invalid response: {resp.text[:100]}'}, status=resp.status_code)
        return JsonResponse({'status': 'ERROR', 'statusMsg': 'Method not allowed'}, status=405)
    except Exception as e:
        logger.error(f"Subcategories Tree Proxy Error: {str(e)}")
        return JsonResponse({'status': 'ERROR', 'statusMsg': str(e)}, status=500)

@csrf_exempt
@check_auth
def org_item_categories_proxy(request):
    """Proxy view for ERP Item Categories (L1)"""
    auth_token = request.session.get('auth_token')
    company_id = get_company_id(request)
    
    headers = {
        'Authorization': f'Bearer {auth_token}',
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }

    try:
        if request.method == 'POST':
            payload = json.loads(request.body)
            # Cleanup payload: remove empty ID fields to avoid Java backend issues
            cat_id = payload.get('id') or payload.get('categoryId')
            if not cat_id:
                payload.pop('id', None)
                payload.pop('categoryId', None)
            
            # Fix SQL Error: 1048 - Column 'description' cannot be null
            if 'description' not in payload or not payload['description']:
                payload['description'] = payload.get('categoryName', payload.get('name', 'No description provided'))
            
            # Ensure parentId is null if empty
            if 'parentId' in payload and not payload['parentId']:
                payload['parentId'] = None

            if cat_id:
                url = f"{JAVA_API_URL}/api/item-categories/{cat_id}"
                resp = requests.put(url, json=payload, headers=headers, timeout=30)
            else:
                url = f"{JAVA_API_URL}/api/item-categories/save"
                if 'companyId' not in payload: payload['companyId'] = company_id
                resp = requests.post(url, json=payload, headers=headers, timeout=30)
            
            try:
                return JsonResponse(resp.json(), status=resp.status_code)
            except ValueError:
                # Log detailed error for debugging
                logger.error(f"Java API Error ({resp.status_code}) on {url}: {resp.text}")
                return JsonResponse({
                    'status': 'ERROR', 
                    'statusMsg': f'Backend Error ({resp.status_code}): {resp.text[:100]}',
                    'path': url
                }, status=resp.status_code)
        elif request.method == 'GET':
            url = f"{JAVA_API_URL}/api/item-categories/all"
            resp = requests.get(url, headers=headers, timeout=30)
            try:
                return JsonResponse(resp.json(), status=resp.status_code)
            except ValueError:
                logger.error(f"Java API Error ({resp.status_code}) on {url}: {resp.text}")
                return JsonResponse({
                    'status': 'ERROR', 
                    'statusMsg': f'Backend Error ({resp.status_code}): {resp.text[:100]}',
                    'path': url
                }, status=resp.status_code)
    except Exception as e:
        logger.error(f"Error in org_item_categories_proxy: {str(e)}")
        return JsonResponse({'status': 'ERROR', 'statusMsg': str(e)}, status=500)

@csrf_exempt
@check_auth
def org_item_subcategories_proxy(request):
    """Proxy view for ERP Item Subcategories (L2/L3)"""
    auth_token = request.session.get('auth_token')
    company_id = get_company_id(request)
    
    headers = {
        'Authorization': f'Bearer {auth_token}',
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }

    try:
        if request.method == 'POST':
            payload = json.loads(request.body)
            # Cleanup payload
            sub_id = payload.get('id') or payload.get('subCategoryId')
            if not sub_id:
                payload.pop('id', None)
                payload.pop('subCategoryId', None)
            
            # Fix SQL Error: 1048 - Column 'description' cannot be null
            if 'description' not in payload or not payload['description']:
                payload['description'] = payload.get('subCategoryName', payload.get('name', 'No description provided'))

            if sub_id:
                url = f"{JAVA_API_URL}/api/item-subcategories/update"
                if 'itemSubcategoryId' not in payload: payload['itemSubcategoryId'] = sub_id
                if 'itemSubcategoryName' not in payload: payload['itemSubcategoryName'] = payload.get('name')
                resp = requests.post(url, json=payload, headers=headers, timeout=30)
            else:
                url = f"{JAVA_API_URL}/api/item-subcategories/save"
                if 'itemSubcategoryName' not in payload: payload['itemSubcategoryName'] = payload.get('name')
                if 'companyId' not in payload: payload['companyId'] = company_id
                resp = requests.post(url, json=payload, headers=headers, timeout=30)
            
            try:
                return JsonResponse(resp.json(), status=resp.status_code)
            except ValueError:
                logger.error(f"Java API Error ({resp.status_code}) on {url}: {resp.text}")
                return JsonResponse({
                    'status': 'ERROR', 
                    'statusMsg': f'Backend Error ({resp.status_code}): {resp.text[:100]}',
                    'path': url
                }, status=resp.status_code)
        elif request.method == 'GET':
            parent_code = request.GET.get('parentCode')
            url = f"{JAVA_API_URL}/api/item-subcategories/category/{parent_code}" if parent_code else f"{JAVA_API_URL}/api/item-subcategories/all"
            resp = requests.get(url, headers=headers, timeout=30)
            try:
                return JsonResponse(resp.json(), status=resp.status_code)
            except ValueError:
                logger.error(f"Java API Error ({resp.status_code}) on {url}: {resp.text}")
                return JsonResponse({
                    'status': 'ERROR', 
                    'statusMsg': f'Backend Error ({resp.status_code}): {resp.text[:100]}',
                    'path': url
                }, status=resp.status_code)
    except Exception as e:
        logger.error(f"Error in org_item_subcategories_proxy: {str(e)}")
        return JsonResponse({'status': 'ERROR', 'statusMsg': str(e)}, status=500)

@csrf_exempt
@check_auth
def org_channel_categories_proxy(request, channel_id):
    """Proxy for Marketplace Taxonomy"""
    auth_token = request.session.get('auth_token')
    company_id = get_company_id(request)
    
    headers = {
        'Authorization': f'Bearer {auth_token}',
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }

    try:
        mode = request.GET.get('mode', 'all')
        if mode == 'tree':
            url = f"{JAVA_API_URL}/api/channel-categories/tree/{channel_id}"
        elif mode == 'leaf':
            url = f"{JAVA_API_URL}/api/channel-categories/leaf/{channel_id}"
        else:
            url = f"{JAVA_API_URL}/api/channel-categories/channel/{channel_id}"
            
        params = {'companyId': company_id}
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        try:
            return JsonResponse(resp.json(), status=resp.status_code)
        except ValueError:
            return JsonResponse({'status': 'ERROR', 'statusMsg': f'Invalid response: {resp.text[:100]}'}, status=resp.status_code)
    except Exception as e:
        logger.error(f"Error in org_channel_categories_proxy: {str(e)}")
        return JsonResponse({'status': 'ERROR', 'statusMsg': str(e)}, status=500)

@csrf_exempt
@check_auth
def org_category_mappings_proxy(request):
    """Proxy for Category-Channel Mappings"""
    auth_token = request.session.get('auth_token')
    company_id = get_company_id(request)
    
    headers = {
        'Authorization': f'Bearer {auth_token}',
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }

    try:
        if request.method == 'POST':
            url = f"{JAVA_API_URL}/api/category-channel-mappings"
            payload = json.loads(request.body)
            if 'companyId' not in payload:
                payload['companyId'] = company_id
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            try:
                return JsonResponse(resp.json(), status=resp.status_code)
            except ValueError:
                return JsonResponse({'status': 'ERROR', 'statusMsg': f'Invalid response: {resp.text[:100]}'}, status=resp.status_code)
        elif request.method == 'GET':
            channel_id = request.GET.get('channelId')
            url = f"{JAVA_API_URL}/api/category-channel-mappings/channel/{channel_id}"
            params = {'companyId': company_id}
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            try:
                return JsonResponse(resp.json(), status=resp.status_code)
            except ValueError:
                return JsonResponse({'status': 'ERROR', 'statusMsg': f'Invalid response: {resp.text[:100]}'}, status=resp.status_code)
    except Exception as e:
        logger.error(f"Error in org_category_mappings_proxy: {str(e)}")
        return JsonResponse({'status': 'ERROR', 'statusMsg': str(e)}, status=500)

@csrf_exempt
@check_auth
def org_material_listings_proxy(request):
    """Proxy for Material Listings (Product Listings)"""
    auth_token = request.session.get('auth_token')
    company_id = get_company_id(request)
    
    headers = {
        'Authorization': f'Bearer {auth_token}',
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }

    try:
        if request.method == 'POST':
            url = f"{JAVA_API_URL}/api/material-listings"
            payload = json.loads(request.body)
            if 'companyId' not in payload:
                payload['companyId'] = company_id
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            try:
                return JsonResponse(resp.json(), status=resp.status_code)
            except ValueError:
                return JsonResponse({'status': 'ERROR', 'statusMsg': f'Invalid response: {resp.text[:100]}'}, status=resp.status_code)
        elif request.method == 'PATCH':
            listing_id = request.GET.get('listingId')
            status = request.GET.get('status')
            url = f"{JAVA_API_URL}/api/material-listings/{listing_id}/status"
            params = {'status': status, 'companyId': company_id}
            resp = requests.patch(url, headers=headers, params=params, timeout=30)
            try:
                return JsonResponse(resp.json(), status=resp.status_code)
            except ValueError:
                return JsonResponse({'status': 'ERROR', 'statusMsg': f'Invalid response: {resp.text[:100]}'}, status=resp.status_code)
        elif request.method == 'GET':
            material_id = request.GET.get('materialId')
            channel_id = request.GET.get('channelId')
            params = {'companyId': company_id}
            
            if material_id:
                url = f"{JAVA_API_URL}/api/material-listings/material/{material_id}"
            elif channel_id:
                url = f"{JAVA_API_URL}/api/material-listings/channel/{channel_id}"
            else:
                return JsonResponse({'status': 'ERROR', 'statusMsg': 'materialId or channelId required'}, status=400)
                
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            try:
                return JsonResponse(resp.json(), status=resp.status_code)
            except ValueError:
                return JsonResponse({'status': 'ERROR', 'statusMsg': f'Invalid response: {resp.text[:100]}'}, status=resp.status_code)
    except Exception as e:
        logger.error(f"Error in org_material_listings_proxy: {str(e)}")
        return JsonResponse({'status': 'ERROR', 'statusMsg': str(e)}, status=500)

@check_auth
def coming_soon(request, module_name):
    user_data = request.session.get('user_data')
    # Clean up module name (e.g., from "purchase-requisition" to "Purchase Requisition")
    display_name = module_name.replace('-', ' ').title()
    
    return render(request, 'pages/coming_soon.html', {
        'user_data': user_data,
        'module_name': display_name
    })

@check_auth
def workflows(request):
    user_data = request.session.get('user_data')
    return render(request, 'pages/workflows.html', {'user_data': user_data})

@check_auth
def workflow_dashboard(request):
    user_data = request.session.get('user_data')
    return render(request, 'pages/workflow_dashboard.html', {'user_data': user_data})

@check_auth
def workflow_requests(request):
    user_data = request.session.get('user_data')
    return render(request, 'pages/workflow_requests.html', {'user_data': user_data})

@check_auth
def workflow_groups(request):
    user_data = request.session.get('user_data')
    return render(request, 'pages/workflow_groups.html', {'user_data': user_data})

@check_auth
def workflow_analytics(request):
    user_data = request.session.get('user_data')
    return render(request, 'pages/workflow_analytics.html', {'user_data': user_data})

@check_auth
def workflow_settings(request):
    user_data = request.session.get('user_data')
    return render(request, 'pages/workflow_settings.html', {'user_data': user_data})

def workflow_email_action(request, token=None):
    if not token:
        token = request.GET.get('token', '')
    user_data = request.session.get('user_data')
    return render(request, 'pages/workflow_email_action.html', {
        'user_data': user_data,
        'token': token
    })

@check_auth
def vendor_portal_preview(request):
    user_data = request.session.get('user_data')
    # Set session variable to persist the vendor view
    request.session['is_vendor_portal'] = True
    return render(request, 'pages/vendor_dashboard.html', {
        'user_data': user_data,
        'is_vendor_portal': True
    })

@check_auth
def purchase_requisitions(request):
    user_data = request.session.get('user_data')
    auth_token = request.session.get('auth_token')
    
    prs_list = []
    
    try:
        if auth_token:
            role = user_data.get('role', '').upper() if user_data else ''
            api_endpoint = f"{JAVA_API_URL}/api/vendor/purchase-requisitions/details" if role == 'VENDOR' else f"{JAVA_API_URL}/api/purchase-requisitions"
            
            response = requests.get(
                api_endpoint,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/json'
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Robust extraction just like the JS frontend
                content = []
                if isinstance(data, dict):
                    if 'content' in data:
                        content = data['content']
                    elif 'data' in data and isinstance(data['data'], dict) and 'content' in data['data']:
                        content = data['data']['content']
                    elif 'data' in data and isinstance(data['data'], list):
                        content = data['data']
                elif isinstance(data, list):
                    content = data
                
                for item in content:
                    status = item.get('status', 'CREATED')
                    
                    status_badge = 'info'
                    if status == 'RELEASED' or status == 'APPROVED': status_badge = 'success'
                    elif status == 'PARTIALLY_RELEASED': status_badge = 'warning'
                    elif status == 'REJECTED': status_badge = 'danger'
                    
                    items = item.get('items') or []
                    
                    # Parse created date
                    created_date_formatted = item.get('createdAt', '')
                    if created_date_formatted:
                        try:
                            from datetime import datetime
                            # basic split for 'T'
                            d_str = created_date_formatted.split('T')[0]
                            created_date_formatted = datetime.strptime(d_str, '%Y-%m-%d').strftime('%d %b %Y')
                        except:
                            created_date_formatted = str(created_date_formatted)[:10]
                    else:
                        created_date_formatted = item.get('requiredDate', '')
                    
                    prs_list.append({
                        'pr_number': item.get('prNumber', ''),
                        'pr_status': status,
                        'status_slug': status.lower(),
                        'status_badge': status_badge,
                        'created_by': f"User #{item.get('requestedBy', 'Unknown')}",
                        'created_date_formatted': created_date_formatted,
                        'line_count': item.get('itemCount', len(items))
                    })
    except Exception as e:
        logger.error(f"Error fetching PRs from API: {e}")
    
    all_count = len(prs_list)
    released_count = sum(1 for pr in prs_list if pr['status_slug'] in ['released', 'approved'])
    in_process_count = sum(1 for pr in prs_list if pr['status_slug'] == 'partially_released')
    open_count = sum(1 for pr in prs_list if pr['status_slug'] in ['created', 'draft', 'submitted'])
    
    return render(request, 'pages/purchase_requisitions.html', {
        'user_data': user_data,
        'prs': prs_list,
        'has_custom_data': False,
        'all_count': all_count,
        'released_count': released_count,
        'in_process_count': in_process_count,
        'open_count': open_count
    })

@check_auth
def purchase_requisition_detail(request, pr_id):
    user_data = request.session.get('user_data')
    auth_token = request.session.get('auth_token')
    
    # Check session first for backward compatibility (excel upload)
    raw_data = request.session.get('custom_pr_data', [])
    session_items = [item for item in raw_data if item.get('pr_number') == pr_id]
    
    api_data = None
    if not session_items:
        # Fetch from API
        try:
            response = requests.get(
                f"{JAVA_API_URL}/api/purchase-requisitions/pr-number/{pr_id}",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/json'
                }
            )
            if response.status_code == 200:
                api_data = response.json()
        except Exception as e:
            logger.error(f"Error fetching PR {pr_id}: {e}")
            
        if not api_data:
            return render(request, 'pages/purchase_requisition_detail.html', {
                'user_data': user_data,
                'pr_id': pr_id,
                'error': True
            })
            
        # Parse API response
        status_map = {
            'OPEN': ('info', 'Open', 'open'),
            'SUBMITTED': ('primary', 'Submitted', 'submitted'),
            'RELEASED': ('success', 'Released', 'released'),
            'APPROVED': ('success', 'Approved', 'approved'),
            'REJECTED': ('danger', 'Rejected', 'rejected'),
            'DRAFT': ('secondary', 'Draft', 'draft'),
        }
        
        raw_status = api_data.get('status', 'OPEN')
        status_badge, pr_status_display, status_slug = status_map.get(raw_status, ('info', raw_status.title(), raw_status.lower()))

        def format_date(d_str):
            if not d_str: return ''
            try:
                from datetime import datetime
                d = d_str.split('T')[0]
                return datetime.strptime(d, '%Y-%m-%d').strftime('%d %b %Y')
            except:
                return str(d_str)[:10]

        pr = {
            'pr_number': api_data.get('prNumber', pr_id),
            'pr_status': pr_status_display,
            'status_slug': status_slug,
            'status_badge': status_badge,
            'created_by': api_data.get('requestedBy', ''),
            'created_date_formatted': format_date(api_data.get('createdAt')),
            'header_notes': api_data.get('remarks', ''),
            'last_changed': format_date(api_data.get('updatedAt'))
        }
        
        line_items = []
        for idx, item in enumerate(api_data.get('items', [])):
            line_num = (idx + 1) * 10
            line_items.append({
                'item_number': line_num,
                'material_description': item.get('sku', ''),
                'material_number': item.get('materialId', ''),
                'hsn_sac_code': '',
                'quantity': item.get('quantity', 0),
                'uom': item.get('uom', ''),
                'plant': api_data.get('locationName', ''),
                'delivery_date_formatted': format_date(api_data.get('requiredDate')),
                'fixed_vendor': 'Open',
                'account_assignment': '',
                'gl_account': '',
                'item_status': 'Open'
            })
            
        api_json = json.dumps(api_data, indent=4)
        
    else:
        # Legacy session parsing
        first_item = session_items[0]
        pr = {
            'pr_number': pr_id,
            'pr_status': first_item.get('pr_status_display', 'Open'),
            'status_slug': first_item.get('status_slug', 'open'),
            'status_badge': first_item.get('status_badge', 'info'),
            'created_by': first_item.get('created_by', ''),
            'created_date_formatted': first_item.get('created_date_formatted', ''),
            'header_notes': first_item.get('header_notes', ''),
            'last_changed': first_item.get('created_date_formatted', '')
        }
        
        line_items = []
        for idx, item in enumerate(session_items):
            line_num = (idx + 1) * 10
            line_items.append({
                'item_number': line_num,
                'material_description': item.get('material_description', ''),
                'material_number': item.get('material_number', ''),
                'hsn_sac_code': item.get('hsn_sac_code', ''),
                'quantity': item.get('quantity', 0),
                'uom': item.get('uom', ''),
                'plant': item.get('plant', ''),
                'delivery_date_formatted': item.get('delivery_date_formatted', ''),
                'fixed_vendor': item.get('fixed_vendor') if item.get('fixed_vendor') else 'Open',
                'account_assignment': item.get('account_assignment', ''),
                'gl_account': item.get('gl_account', ''),
                'item_status': item.get('item_status', 'Open').title() if item.get('item_status') else 'Open'
            })
            
        api_items = []
        for li in line_items:
            try:
                qty = float(li['quantity'])
                if qty.is_integer():
                    qty = int(qty)
            except:
                qty = li['quantity']
            api_items.append({
                "line": li['item_number'],
                "material": li['material_description'],
                "quantity": qty,
                "uom": li['uom'],
                "hsn_sac_code": li['hsn_sac_code'],
                "plant": li['plant'],
                "delivery_date": li['delivery_date_formatted']
            })
            
        api_json_data = {
            "pr_number": pr_id,
            "status": pr['status_slug'],
            "items": api_items
        }
        api_json = json.dumps(api_json_data, indent=4)
    
    return render(request, 'pages/purchase_requisition_detail.html', {
        'user_data': user_data,
        'pr_id': pr_id,
        'pr': pr,
        'line_items': line_items,
        'lines_count': len(line_items),
        'api_json': api_json
    })

@csrf_exempt
@require_POST
@check_auth
def upload_pr_excel(request):
    excel_file = request.FILES.get('excel_file')
    if not excel_file:
        return JsonResponse({'status': 'error', 'message': 'No file uploaded'}, status=400)
        
    try:
        from .utils.excel_parser import parse_pr_excel
        pr_items = parse_pr_excel(excel_file)
        
        request.session['custom_pr_data'] = pr_items
        request.session['has_custom_pr_data'] = True
        request.session.modified = True
        
        return JsonResponse({'status': 'success', 'message': 'File uploaded and parsed successfully'})
    except Exception as e:
        logger.error(f"Error parsing uploaded file: {str(e)}")
        return JsonResponse({'status': 'error', 'message': f'Failed to parse Excel file: {str(e)}'}, status=500)

@check_auth
def download_pr_template(request):
    import io
    import pandas as pd
    from django.http import HttpResponse

    columns = [
        "vendor_id", "vendor_name", "pr_number", "pr_status", "created_by", 
        "created_date", "material_number", "material_description", "hsn_sac_code", 
        "quantity", "uom", "delivery_date", "plant", "fixed_vendor", 
        "account_assignment", "gl_account", "item_status", "header_notes"
    ]
    df = pd.DataFrame(columns=columns)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='PR Template')
    
    output.seek(0)
    response = HttpResponse(
        output.read(), 
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="PR_Template.xlsx"'
    return response

@check_auth
def reset_pr_data(request):
    if 'custom_pr_data' in request.session:
        del request.session['custom_pr_data']
    if 'has_custom_pr_data' in request.session:
        del request.session['has_custom_pr_data']
    request.session.modified = True
    return redirect('pages:purchase_requisitions')

@check_auth
def quotations(request):
    user_data = request.session.get('user_data')
    auth_token = request.session.get('auth_token')
    
    prs_list = []
    
    vendor_quotations = []
    
    try:
        if auth_token:
            role = user_data.get('role', '').upper() if user_data else ''
            # Fetch released PRs for the modal
            pr_api_endpoint = f"{JAVA_API_URL}/api/vendor/purchase-requisitions/details" if role == 'VENDOR' else f"{JAVA_API_URL}/api/purchase-requisitions"
            
            pr_response = requests.get(
                pr_api_endpoint,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/json'
                }
            )
            
            if pr_response.status_code == 200:
                data = pr_response.json()
                content = data.get('content', data) if isinstance(data, dict) else data
                if isinstance(data, dict) and 'data' in data:
                    content = data['data'].get('content', data['data']) if isinstance(data['data'], dict) else data['data']
                
                for item in content:
                    status = item.get('status', 'CREATED')
                    if status != 'RELEASED': continue
                        
                    items = item.get('items') or []
                    desc_parts = []
                    if items and items[0].get('sku'): desc_parts.append(items[0].get('sku'))
                    remarks = item.get('remarks')
                    if remarks: desc_parts.append(remarks)
                    description = " — ".join(desc_parts) if desc_parts else 'Standard PR'
                    
                    prs_list.append({
                        'id': item.get('id'),
                        'pr_number': item.get('prNumber', ''),
                        'description': description,
                        'line_count': item.get('itemCount', len(items))
                    })
                    
            # Fetch quotations
            if role == 'VENDOR':
                qtn_api_endpoint = f"{JAVA_API_URL}/api/vendor/quotations"
            else:
                vendor_id = request.GET.get('vendor_id')
                pr_id = request.GET.get('pr_id')
                if vendor_id:
                    qtn_api_endpoint = f"{JAVA_API_URL}/api/admin/quotations/vendor/{vendor_id}"
                elif pr_id:
                    qtn_api_endpoint = f"{JAVA_API_URL}/api/admin/quotations/pr/{pr_id}"
                else:
                    # Fallback if no specific filter is provided
                    qtn_api_endpoint = None
            
            if qtn_api_endpoint:
                qtn_response = requests.get(
                    qtn_api_endpoint,
                    headers={
                        'Authorization': f'Bearer {auth_token}',
                        'Accept': 'application/json'
                    }
                )
                
                if qtn_response.status_code == 200:
                    q_data = qtn_response.json()
                    vendor_quotations = q_data if isinstance(q_data, list) else []
                    
                    # Fetch vendor names to build vendors map if Admin
                    vendors_map = {}
                    if role != 'VENDOR':
                        try:
                            vendors_resp = requests.get(
                                f"{JAVA_API_URL}/api/vendors/all",
                                headers={'Authorization': f'Bearer {auth_token}', 'Accept': 'application/json'},
                                timeout=10
                            )
                            if vendors_resp.status_code == 200:
                                vendors_data = vendors_resp.json()
                                v_list = vendors_data.get('data', []) if isinstance(vendors_data, dict) else vendors_data
                                for v in v_list:
                                    v_id = v.get('companyId') or v.get('id')
                                    if v_id:
                                        vendors_map[str(v_id)] = v.get('companyName') or v.get('name')
                        except Exception as ex:
                            logger.error(f"Error fetching vendors for quotations list: {ex}")
                    
                    # If filtered by PR, sort by grand total ascending
                    if role != 'VENDOR' and request.GET.get('pr_id'):
                        try:
                            vendor_quotations.sort(key=lambda x: float(x.get('grand_total') or 0.0))
                        except Exception as sort_ex:
                            logger.error(f"Error sorting quotations by price: {sort_ex}")
            else:
                vendor_quotations = []
                
            # Map some fields for the template if needed
            for qtn in vendor_quotations:
                header = qtn.get('quotation_header', {})
                qtn['display_number'] = header.get('quotation_number', f"QTN-{qtn.get('quotation_id')}")
                qtn['display_date'] = header.get('quotation_date', qtn.get('created_at', ''))[:10]
                qtn['display_valid_until'] = header.get('valid_until', '')[:10]
                qtn['line_count'] = len(qtn.get('line_items', []))
                
                vendor_id = str(qtn.get('vendor_id', ''))
                qtn['vendor_name'] = vendors_map.get(vendor_id, f"Vendor #{vendor_id}")
                
                status = qtn.get('status', 'DRAFT')
                qtn['status_lower'] = status.lower()
                if status == 'SUBMITTED':
                    qtn['status_badge'] = 'info'
                elif status == 'AWARDED':
                    qtn['status_badge'] = 'success'
                elif status == 'REJECTED':
                    qtn['status_badge'] = 'danger'
                else:
                    qtn['status_badge'] = 'warning'
                        
    except Exception as e:
        logger.error(f"Error fetching data for quotations view: {e}")

    return render(request, 'pages/quotations.html', {
        'user_data': user_data,
        'released_prs': prs_list,
        'quotations': vendor_quotations
    })

@check_auth
def new_quotation(request):
    user_data = request.session.get('user_data')
    auth_token = request.session.get('auth_token')
    pr_id = request.GET.get('pr_id')
    
    pr_data = None
    if pr_id and auth_token:
        try:
            # We assume role is VENDOR or this endpoint allows fetching PR details
            api_endpoint = f"{JAVA_API_URL}/api/vendor/purchase-requisitions/details"
            
            response = requests.get(
                api_endpoint,
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/json'
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                
                content = []
                if isinstance(data, dict):
                    if 'content' in data:
                        content = data['content']
                    elif 'data' in data and isinstance(data['data'], dict) and 'content' in data['data']:
                        content = data['data']['content']
                    elif 'data' in data and isinstance(data['data'], list):
                        content = data['data']
                elif isinstance(data, list):
                    content = data
                
                # Find the specific PR in the vendor's assigned list
                for item in content:
                    if item.get('prNumber') == pr_id:
                        pr_data = item
                        break
        except Exception as e:
            logger.error(f"Error fetching PR {pr_id} for new quotation: {e}")

    return render(request, 'pages/new_quotation.html', {
        'user_data': user_data,
        'pr_id': pr_id,
        'pr_data': pr_data
    })

@check_auth
def quotation_detail(request, qtn_id):
    user_data = request.session.get('user_data')
    auth_token = request.session.get('auth_token')
    
    qtn_data = None
    role = user_data.get('role', '').upper() if user_data else ''
    
    try:
        if auth_token:
            # Check if qtn_id is a database ID (numeric) or a quotation number (string)
            is_numeric = False
            try:
                int(str(qtn_id))
                is_numeric = True
            except ValueError:
                is_numeric = False

            if role == 'VENDOR':
                if is_numeric:
                    api_url = f"{JAVA_API_URL}/api/vendor/quotations/{qtn_id}"
                else:
                    api_url = f"{JAVA_API_URL}/api/vendor/quotations/number/{qtn_id}"
            else:
                if is_numeric:
                    api_url = f"{JAVA_API_URL}/api/admin/quotations/{qtn_id}"
                else:
                    api_url = f"{JAVA_API_URL}/api/admin/quotations/number/{qtn_id}"
                
            logger.info(f"Fetching quotation detail from Java: {api_url}")
            response = requests.get(
                api_url,
                headers={'Authorization': f'Bearer {auth_token}', 'Accept': 'application/json'},
                timeout=10
            )
            logger.info(f"Java backend response status for quotation detail: {response.status_code}")
            
            if response.status_code == 200:
                resp_json = response.json()
                if isinstance(resp_json, dict):
                    if 'data' in resp_json and isinstance(resp_json['data'], dict):
                        qtn_data = resp_json['data']
                    else:
                        qtn_data = resp_json
                
                # Pre-calculate line totals and subtotal/grand_total if needed
                if qtn_data and 'line_items' in qtn_data:
                    subtotal = 0.0
                    for item in qtn_data['line_items']:
                        qty = float(item.get('quoted_qty') or 0.0)
                        price = float(item.get('unit_price') or 0.0)
                        line_total = qty * price
                        item['line_total'] = line_total
                        subtotal += line_total
                    qtn_data['subtotal'] = subtotal
                    
                    gst_total = float(qtn_data.get('gst_total') or 0.0)
                    freight_total = float(qtn_data.get('freight_total') or 0.0)
                    if 'grand_total' not in qtn_data or qtn_data['grand_total'] is None:
                        qtn_data['grand_total'] = subtotal + gst_total + freight_total
            else:
                logger.error(f"Failed to fetch quotation from Java: Status {response.status_code}, Body: {response.text}")
    except Exception as e:
        logger.error(f"Error fetching quotation details: {e}")

    return render(request, 'pages/quotation_detail.html', {
        'user_data': user_data,
        'qtn_id': qtn_id,
        'quotation': qtn_data
    })

@csrf_exempt
@require_http_methods(["POST"])
@check_auth
def award_quotation(request, qtn_id):
    user_data = request.session.get('user_data', {})
    auth_token = request.session.get('auth_token')
    
    if not auth_token:
        return JsonResponse({'status': 'error', 'message': 'Authentication required'}, status=401)
        
    try:
        import json
        remarks = ""
        if request.body:
            try:
                payload = json.loads(request.body)
                remarks = payload.get('remarks', '')
            except ValueError:
                pass
            
        api_url = f"{JAVA_API_URL}/api/admin/quotations/{qtn_id}/award"
        
        response = requests.post(
            api_url,
            json={"remarks": remarks},
            headers={
                'Authorization': f'Bearer {auth_token}',
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            timeout=10
        )
        
        if response.status_code in [200, 201]:
            return JsonResponse({
                'status': 'success',
                'message': 'Quotation awarded successfully.'
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': f"Backend error: {response.status_code}",
                'details': response.text
            }, status=response.status_code)
            
    except Exception as e:
        logger.error(f"Error awarding quotation: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@check_auth
def asn(request):
    user_data = request.session.get('user_data')
    return render(request, 'pages/asn.html', {
        'user_data': user_data
    })

@check_auth
def purchase_order_detail(request, po_id="4500012345"):
    user_data = request.session.get('user_data')
    auth_token = request.session.get('auth_token')
    role = user_data.get('role', '').upper() if user_data else ''
    
    po_details = {
        'po_id': po_id,
        'po_number': po_id,
        'po_status_display': 'Not Found',
        'status_slug': 'not-found',
        'lines': [],
        'line_count': 0
    }
    
    # Try fetching from Java API first
    if auth_token:
        try:
            is_numeric = False
            try:
                int(str(po_id))
                is_numeric = True
            except ValueError:
                pass
                
            if role != 'VENDOR':
                api_url = f"{JAVA_API_URL}/api/purchase-orders/{po_id}" if is_numeric else f"{JAVA_API_URL}/api/purchase-orders/number/{po_id}"
            else:
                api_url = f"{JAVA_API_URL}/api/vendor/purchase-orders/{po_id}" if is_numeric else f"{JAVA_API_URL}/api/vendor/purchase-orders/number/{po_id}"
            response = requests.get(
                api_url,
                headers={'Authorization': f'Bearer {auth_token}', 'Accept': 'application/json'},
                timeout=10
            )
            if response.status_code == 200:
                po_data = response.json()
                vendor_info = po_data.get('vendor') or {}
                payment_info = po_data.get('paymentTerms') or {}
                
                # Map items
                mapped_lines = []
                for idx, line in enumerate(po_data.get('items', [])):
                    mapped_lines.append({
                        'line_number': line.get('lineNumber', idx + 1),
                        'material_number': line.get('materialNumber', ''),
                        'material_description': line.get('materialDescription', ''),
                        'quantity': line.get('quantity', 0.0),
                        'uom': line.get('uom', 'PCS'),
                        'net_price': f"{line.get('unitPrice', 0.0):.2f}",
                        'net_value': f"{line.get('netValue', 0.0):.2f}",
                        'tax_percent': f"{line.get('taxPercent', 0.0):.2f}",
                        'tax_amount': f"{line.get('taxAmount', 0.0):.2f}",
                        'total_value': f"{line.get('totalValue', 0.0):.2f}",
                    })
                    
                status = po_data.get('status', 'CREATED')
                po_details = {
                    'po_id': po_data.get('poId'),
                    'po_number': po_data.get('poNumber'),
                    'po_date_formatted': format_api_date(po_data.get('poDate')),
                    'po_type': 'Standard',
                    'company_code': '1000',
                    'company_name': 'Aequm Industries',
                    'currency': po_data.get('currency', 'INR'),
                    'payment_terms': payment_info.get('name', 'Net 30 Days'),
                    'po_status_display': status,
                    'status_badge': 'success' if status in ['CREATED', 'RELEASED'] else 'danger' if status == 'CANCELLED' else 'warning',
                    'status_slug': status.lower(),
                    'vendor_id': vendor_info.get('vendorId'),
                    'vendor_code': vendor_info.get('vendorCode'),
                    'vendor_name': vendor_info.get('vendorName'),
                    'delivery_address': po_data.get('deliveryAddress'),
                    'goods_receipt_plant': 'Plant 1',
                    'requested_delivery_date_formatted': format_api_date(po_data.get('requestedDeliveryDate')),
                    'shipping_instructions': po_data.get('shippingInstructions'),
                    'gstin': vendor_info.get('gstin'),
                    'lines': mapped_lines,
                    'sum_net_value': f"{po_data.get('subtotal', 0.0):,.2f}",
                    'sum_tax_amount': f"{po_data.get('gstTotal', 0.0):,.2f}",
                    'sum_total_value': f"{po_data.get('grandTotal', 0.0):,.2f}",
                    'line_count': len(mapped_lines),
                    'is_live': True
                }
            else:
                logger.error(f"Failed to fetch live PO detail {api_url}: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"Error fetching live PO detail: {e}")
            
    # Fallback to session data if not found or API failed
    if po_details.get('status_slug') == 'not-found':
        po_data = request.session.get('custom_po_data', [])
        if po_data:
            po_lines = [item for item in po_data if str(item.get('po_number')) == str(po_id)]
            
            if po_lines:
                header = po_lines[0]
                total_net_value = sum(float(str(line.get('net_value', '0')).replace(',', '')) if line.get('net_value') else 0 for line in po_lines)
                total_tax_amount = sum(float(str(line.get('tax_amount', '0')).replace(',', '')) if line.get('tax_amount') else 0 for line in po_lines)
                total_order_value = sum(float(str(line.get('total_value', '0')).replace(',', '')) if line.get('total_value') else 0 for line in po_lines)
                
                po_details = {
                    'po_id': header.get('po_number'),
                    'po_number': header.get('po_number'),
                    'po_date_formatted': header.get('po_date_formatted'),
                    'po_type': header.get('po_type'),
                    'company_code': header.get('company_code'),
                    'company_name': header.get('company_name'),
                    'currency': header.get('currency'),
                    'payment_terms': header.get('payment_terms'),
                    'po_status_display': header.get('po_status_display'),
                    'status_badge': header.get('status_badge'),
                    'status_slug': header.get('status_slug'),
                    'vendor_id': header.get('vendor_id'),
                    'vendor_code': header.get('vendor_code'),
                    'vendor_name': header.get('vendor_name'),
                    'delivery_address': header.get('delivery_address'),
                    'goods_receipt_plant': header.get('goods_receipt_plant'),
                    'requested_delivery_date_formatted': header.get('requested_delivery_date_formatted'),
                    'shipping_instructions': header.get('shipping_instructions'),
                    'gstin': header.get('gstin'),
                    'lines': po_lines,
                    'sum_net_value': f"{total_net_value:,.2f}",
                    'sum_tax_amount': f"{total_tax_amount:,.2f}",
                    'sum_total_value': f"{total_order_value:,.2f}",
                    'line_count': len(po_lines),
                    'is_live': False
                }
                
    return render(request, 'pages/purchase_order_detail.html', {
        'user_data': user_data,
        'po_id': po_id,
        'po': po_details
    })

@check_auth
def service_purchase_order_detail(request, po_id="4600001122"):
    user_data = request.session.get('user_data')
    
    # Process Service PO items from session
    raw_pos = request.session.get('custom_service_po_data', [])
    po_details = None
    
    # Find matching PO
    for item in raw_pos:
        if str(item.get('service_po_number')) == str(po_id):
            po_details = item
            break
            
    if not po_details and raw_pos:
        # Default to first if specific not found but we have data
        po_details = raw_pos[0]
        po_id = po_details.get('service_po_number')
        
    return render(request, 'pages/service_purchase_order_detail.html', {
        'user_data': user_data,
        'po_id': po_id,
        'po': po_details
    })

@check_auth
def subcontracting_purchase_order_detail(request, po_id="4700000891"):
    user_data = request.session.get('user_data')
    
    raw_pos = request.session.get('custom_subcon_po_data', [])
    po_details = None
    
    for item in raw_pos:
        if str(item.get('subcon_po_number')) == str(po_id):
            if not po_details:
                po_details = item.copy()
                po_details['components'] = {}
                po_details['movements'] = {}
            
            # Deduplicate components by component_line_no
            comp_line = str(item.get('component_line_no'))
            if comp_line and comp_line not in po_details['components']:
                po_details['components'][comp_line] = {
                    'line_no': comp_line,
                    'material_no': item.get('component_material_no'),
                    'description': item.get('component_description'),
                    'req_qty_per_unit': item.get('required_qty_per_unit'),
                    'total_issued': item.get('total_issued_qty'),
                    'stock_at_vendor': item.get('stock_at_vendor'),
                    'stock_capacity': item.get('total_stock_capacity'),
                    'uom': item.get('component_uom'),
                    'scrap': item.get('scrap_percent')
                }
            
            # Deduplicate movements by movement_doc_number
            mvt_doc = str(item.get('movement_doc_number'))
            if mvt_doc and mvt_doc not in po_details['movements']:
                po_details['movements'][mvt_doc] = {
                    'doc_number': mvt_doc,
                    'type': item.get('movement_type'),
                    'description': item.get('movement_description'),
                    'material': item.get('movement_material'),
                    'qty': item.get('movement_qty'),
                    'date_formatted': item.get('movement_date_formatted')
                }
                
    if po_details:
        po_details['components'] = list(po_details['components'].values())
        po_details['movements'] = list(po_details['movements'].values())
    
    return render(request, 'pages/subcontracting_purchase_order_detail.html', {
        'user_data': user_data,
        'po_id': po_id,
        'po': po_details
    })

@csrf_exempt
@require_POST
@check_auth
def upload_po_excel(request):
    excel_file = request.FILES.get('excel_file')
    if not excel_file:
        return JsonResponse({'status': 'error', 'message': 'No file uploaded'}, status=400)
        
    try:
        from .utils.excel_parser import parse_po_excel
        po_items = parse_po_excel(excel_file)
        
        request.session['custom_po_data'] = po_items
        request.session['has_custom_po_data'] = True
        request.session.modified = True
        
        return JsonResponse({'status': 'success', 'message': 'File uploaded and parsed successfully'})
    except Exception as e:
        logger.error(f"Error parsing uploaded file: {str(e)}")
        return JsonResponse({'status': 'error', 'message': f'Failed to parse Excel file: {str(e)}'}, status=500)

@check_auth
def reset_po_data(request):
    if 'custom_po_data' in request.session:
        del request.session['custom_po_data']
    if 'has_custom_po_data' in request.session:
        del request.session['has_custom_po_data']
    request.session.modified = True
    return redirect('pages:purchase_orders')

@check_auth
def download_po_template(request):
    import io
    import pandas as pd
    from django.http import HttpResponse

    columns = [
        "vendor_id", "vendor_code", "vendor_name", "po_number", "po_date", 
        "po_type", "company_code", "company_name", "currency", "payment_terms", 
        "po_status", "delivery_address", "goods_receipt_plant", 
        "requested_delivery_date", "shipping_instructions", "line_number", 
        "material_number", "material_description", "quantity", "uom", 
        "net_price", "net_value", "tax_percent", "tax_amount", "total_value", 
        "confirm_delivery_date", "gstin"
    ]
    df = pd.DataFrame(columns=columns)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='PO Template')
    
    output.seek(0)
    response = HttpResponse(
        output.read(), 
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="PO_Template.xlsx"'
    return response

@csrf_exempt
@require_POST
@check_auth
def upload_subcon_po_excel(request):
    excel_file = request.FILES.get('excel_file')
    if not excel_file:
        return JsonResponse({'status': 'error', 'message': 'No file uploaded'}, status=400)
        
    try:
        from .utils.excel_parser import parse_subcon_po_excel
        subcon_pos = parse_subcon_po_excel(excel_file)
        
        request.session['custom_subcon_po_data'] = subcon_pos
        request.session['has_custom_subcon_po_data'] = True
        request.session.modified = True
        
        return JsonResponse({'status': 'success', 'message': 'File uploaded and parsed successfully'})
    except Exception as e:
        logger.error(f"Error parsing uploaded file: {str(e)}")
        return JsonResponse({'status': 'error', 'message': f'Failed to parse Excel file: {str(e)}'}, status=500)

@check_auth
def reset_subcon_po_data(request):
    if 'custom_subcon_po_data' in request.session:
        del request.session['custom_subcon_po_data']
    if 'has_custom_subcon_po_data' in request.session:
        del request.session['has_custom_subcon_po_data']
    request.session.modified = True
    return redirect('pages:subcontracting_purchase_orders')

@check_auth
def download_subcon_po_template(request):
    import io
    import pandas as pd
    from django.http import HttpResponse

    columns = [
        "vendor_id", "vendor_code", "vendor_name", "subcon_po_number", "po_status", 
        "po_date", "company_code", "company_name", "currency", "payment_terms", 
        "incoterms", "fg_line_item_no", "fg_material_number", "fg_description", 
        "fg_ordered_qty", "fg_uom", "processing_charge_per_unit", "total_processing_value", 
        "required_delivery_date", "component_line_no", "component_material_no", 
        "component_description", "required_qty_per_unit", "total_issued_qty", 
        "stock_at_vendor", "total_stock_capacity", "component_uom", "scrap_percent", 
        "movement_doc_number", "movement_type", "movement_description", 
        "movement_material", "movement_qty", "movement_date"
    ]
    df = pd.DataFrame(columns=columns)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Subcon PO Template')
    
    output.seek(0)
    response = HttpResponse(
        output.read(), 
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="Subcon_PO_Template.xlsx"'
    return response

@csrf_exempt
@require_POST
@check_auth
def upload_service_po_excel(request):
    excel_file = request.FILES.get('excel_file')
    if not excel_file:
        return JsonResponse({'status': 'error', 'message': 'No file uploaded'}, status=400)
        
    try:
        from .utils.excel_parser import parse_service_po_excel
        service_pos = parse_service_po_excel(excel_file)
        
        request.session['custom_service_po_data'] = service_pos
        request.session['has_custom_service_po_data'] = True
        request.session.modified = True
        
        return JsonResponse({'status': 'success', 'message': 'File uploaded and parsed successfully'})
    except Exception as e:
        logger.error(f"Error parsing uploaded file: {str(e)}")
        return JsonResponse({'status': 'error', 'message': f'Failed to parse Excel file: {str(e)}'}, status=500)

@check_auth
def reset_service_po_data(request):
    if 'custom_service_po_data' in request.session:
        del request.session['custom_service_po_data']
    if 'has_custom_service_po_data' in request.session:
        del request.session['has_custom_service_po_data']
    request.session.modified = True
    return redirect('pages:service_purchase_orders')

@check_auth
def download_service_po_template(request):
    import io
    import pandas as pd
    from django.http import HttpResponse

    columns = [
        "service_po_number", "po_status", "po_date", "service_period_from", 
        "service_period_to", "company_code", "company_name", "currency", 
        "payment_terms", "vendor_id", "vendor_code", "vendor_name", 
        "vendor_address", "gst_number", "pan_number", "line_number", 
        "service_number", "service_description", "quantity", "uom", 
        "rate", "net_value", "cost_centre", "ses_number", "ses_status", 
        "ses_month"
    ]
    df = pd.DataFrame(columns=columns)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Service PO Template')
    
    output.seek(0)
    response = HttpResponse(
        output.read(), 
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="Service_PO_Template.xlsx"'
    return response

def format_api_date(date_str):
    if not date_str:
        return ""
    try:
        from datetime import datetime
        if 'T' in date_str:
            dt = datetime.strptime(date_str.split('T')[0], "%Y-%m-%d")
        else:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%d %b %Y")
    except Exception:
        return date_str

@check_auth
def purchase_orders(request):
    user_data = request.session.get('user_data', {})
    auth_token = request.session.get('auth_token')
    role = user_data.get('role', '').upper() if user_data else ''
    logger.info(f"Accessing Standard POs - Role: {role}, Session: {request.session.session_key}")
    
    pos = []
    
    # 1. Fetch live POs from Java microservice
    if auth_token:
        try:
            api_url = f"{JAVA_API_URL}/api/purchase-orders" if role != 'VENDOR' else f"{JAVA_API_URL}/api/vendor/purchase-orders"
            response = requests.get(
                api_url,
                headers={'Authorization': f'Bearer {auth_token}', 'Accept': 'application/json'},
                timeout=10
            )
            if response.status_code == 200:
                live_pos = response.json()
                if isinstance(live_pos, list):
                    for po in live_pos:
                        po_status = po.get('status', 'CREATED')
                        pos.append({
                            'po_id': po.get('poId'),
                            'po_number': po.get('poNumber'),
                            'po_status': po_status,
                            'status_slug': po_status.lower(),
                            'status_badge': 'success' if po_status in ['CREATED', 'RELEASED'] else 'danger' if po_status == 'CANCELLED' else 'warning',
                            'po_date_formatted': format_api_date(po.get('poDate')),
                            'vendor_name': po.get('vendor', {}).get('vendorName') if isinstance(po.get('vendor'), dict) else po.get('vendorName') or 'Vendor',
                            'delivery_address': po.get('deliveryAddress') or 'Warehouse',
                            'line_count': po.get('itemCount', len(po.get('items', [])) if po.get('items') else 1),
                            'items_summary': po.get('itemsSummary') or (", ".join([it.get('materialDescription') for it in po.get('items') if it.get('materialDescription')][:2]) if po.get('items') else 'Items from Quotation'),
                            'total_value': float(po.get('grandTotal') or 0.0),
                            'total_value_formatted': f"{float(po.get('grandTotal') or 0.0):,.2f}",
                            'is_live': True
                        })
        except Exception as e:
            logger.error(f"Error fetching live POs: {e}")
            
    # 2. Process session-based POs
    raw_pos = request.session.get('custom_po_data', [])
    grouped_pos = {}
    
    for item in raw_pos:
        po_num = str(item.get('po_number'))
        if not po_num: continue
            
        if po_num not in grouped_pos:
            grouped_pos[po_num] = {
                'po_id': po_num,
                'po_number': po_num,
                'po_status': item.get('po_status_display'),
                'status_slug': item.get('status_slug'),
                'status_badge': item.get('status_badge'),
                'po_date_formatted': item.get('po_date_formatted'),
                'vendor_name': item.get('vendor_name'),
                'vendor_code': item.get('vendor_code'),
                'delivery_address': item.get('delivery_address'),
                'lines': [],
                'total_value': 0.0,
                'is_live': False
            }
            
        grouped_pos[po_num]['lines'].append(item)
        val = str(item.get('total_value', '0')).replace(',', '')
        grouped_pos[po_num]['total_value'] += float(val) if val else 0
        
    for po_num, data in grouped_pos.items():
        if any(p['po_number'] == po_num for p in pos):
            continue
        data['line_count'] = len(data['lines'])
        descriptions = [line.get('material_description') for line in data['lines'] if line.get('material_description')]
        items_summary = ", ".join(descriptions[:2])
        if len(descriptions) > 2:
            items_summary += f", and {len(descriptions)-2} more"
        data['items_summary'] = items_summary
        data['total_value_formatted'] = f"{data['total_value']:,.2f}"
        pos.append(data)
        
    # Sort pos by PO number descending
    pos.sort(key=lambda x: str(x['po_number']), reverse=True)
    
    return render(request, 'pages/purchase_orders.html', {
        'user_data': user_data,
        'pos': pos,
        'has_custom_data': request.session.get('has_custom_po_data', False)
    })

@check_auth
def get_awarded_quotations(request):
    user_data = request.session.get('user_data', {})
    auth_token = request.session.get('auth_token')
    
    if not auth_token:
        return JsonResponse({'status': 'error', 'message': 'Authentication required'}, status=401)
        
    try:
        api_url = f"{JAVA_API_URL}/api/admin/quotations/awarded"
        response = requests.get(
            api_url,
            headers={'Authorization': f'Bearer {auth_token}', 'Accept': 'application/json'},
            timeout=10
        )
        
        if response.status_code != 200:
            return JsonResponse({'status': 'error', 'message': f"Failed to fetch awarded quotations: status {response.status_code}"}, status=response.status_code)
            
        awarded_qtns = response.json()
        
        # Resolve vendor names to display them nicely
        vendors_map = {}
        try:
            vendors_resp = requests.get(
                f"{JAVA_API_URL}/api/vendors/all",
                headers={'Authorization': f'Bearer {auth_token}', 'Accept': 'application/json'},
                timeout=10
            )
            if vendors_resp.status_code == 200:
                vendors_data = vendors_resp.json()
                v_list = vendors_data.get('data', []) if isinstance(vendors_data, dict) else vendors_data
                for v in v_list:
                    v_id = v.get('companyId') or v.get('id')
                    if v_id:
                        vendors_map[str(v_id)] = v.get('companyName') or v.get('name')
        except Exception as ex:
            logger.error(f"Error fetching vendors in get_awarded_quotations: {ex}")
            
        mapped_qtns = []
        for qtn in awarded_qtns:
            header = qtn.get('quotation_header') or {}
            vendor_id = str(qtn.get('vendor_id', ''))
            vendor_name = vendors_map.get(vendor_id, f"Vendor #{vendor_id}")
            
            mapped_qtns.append({
                'quotation_id': qtn.get('quotation_id'),
                'quotation_number': header.get('quotation_number', f"QTN-{qtn.get('quotation_id')}"),
                'pr_number': f"PR-{qtn.get('pr_id')}" if qtn.get('pr_id') else 'N/A',
                'vendor_name': vendor_name,
                'grand_total': qtn.get('grand_total', 0.0),
                'currency': header.get('currency', 'INR'),
                'delivery_details': qtn.get('delivery_details', {}),
                'line_items': qtn.get('line_items', [])
            })
            
        return JsonResponse(mapped_qtns, safe=False)
    except Exception as e:
        logger.error(f"Error in get_awarded_quotations: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@check_auth
@csrf_exempt
@require_http_methods(["POST"])
def create_po_from_awarded_quotation(request, quotation_id):
    user_data = request.session.get('user_data', {})
    auth_token = request.session.get('auth_token')
    
    if not auth_token:
        return JsonResponse({'status': 'error', 'message': 'Authentication required'}, status=401)
        
    try:
        import json
        payload = json.loads(request.body)
        delivery_address = payload.get('deliveryAddress')
        shipping_instructions = payload.get('shippingInstructions', '')
        remarks = payload.get('remarks', '')
        
        if not delivery_address:
            return JsonResponse({'status': 'error', 'message': 'Delivery address is required'}, status=400)
            
        api_url = f"{JAVA_API_URL}/api/purchase-orders/from-awarded-quotation/{quotation_id}"
        
        response = requests.post(
            api_url,
            json={
                "deliveryAddress": delivery_address,
                "shippingInstructions": shipping_instructions,
                "remarks": remarks
            },
            headers={
                'Authorization': f'Bearer {auth_token}',
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            timeout=15
        )
        
        if response.status_code in [200, 201]:
            resp_data = response.json()
            return JsonResponse({
                'status': 'success',
                'message': 'Purchase Order Created Successfully',
                'poId': resp_data.get('poId'),
                'poNumber': resp_data.get('poNumber')
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': f"Failed to create PO: status {response.status_code}",
                'details': response.text
            }, status=response.status_code)
            
    except Exception as e:
        logger.error(f"Error creating PO from awarded quotation: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@check_auth
@csrf_exempt
@require_http_methods(["POST"])
def cancel_purchase_order_proxy(request, po_id):
    user_data = request.session.get('user_data', {})
    auth_token = request.session.get('auth_token')
    
    if not auth_token:
        return JsonResponse({'status': 'error', 'message': 'Authentication required'}, status=401)
        
    try:
        api_url = f"{JAVA_API_URL}/api/purchase-orders/{po_id}/cancel"
        response = requests.post(
            api_url,
            headers={'Authorization': f'Bearer {auth_token}', 'Accept': 'application/json'},
            timeout=10
        )
        
        if response.status_code in [200, 204]:
            return JsonResponse({
                'status': 'success',
                'message': 'Purchase Order Cancelled Successfully'
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': f"Failed to cancel PO: status {response.status_code}",
                'details': response.text
            }, status=response.status_code)
            
    except Exception as e:
        logger.error(f"Error cancelling Purchase Order: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@check_auth
def verify_quotation_for_po(request):
    user_data = request.session.get('user_data', {})
    auth_token = request.session.get('auth_token')
    
    if not auth_token:
        return JsonResponse({'status': 'error', 'message': 'Authentication required'}, status=401)
        
    qtn_id = request.GET.get('qtn_id')
    if not qtn_id:
        return JsonResponse({'status': 'error', 'message': 'Quotation Number/ID is required'}, status=400)
        
    try:
        # Determine if qtn_id is numeric or string
        is_numeric = False
        try:
            int(str(qtn_id))
            is_numeric = True
        except ValueError:
            is_numeric = False

        if is_numeric:
            api_url = f"{JAVA_API_URL}/api/admin/quotations/{qtn_id}"
        else:
            api_url = f"{JAVA_API_URL}/api/admin/quotations/number/{qtn_id}"
            
        response = requests.get(
            api_url,
            headers={'Authorization': f'Bearer {auth_token}', 'Accept': 'application/json'},
            timeout=10
        )
        
        if response.status_code != 200:
            return JsonResponse({
                'status': 'error', 
                'message': f"Quotation not found: status {response.status_code}"
            }, status=response.status_code)
            
        resp_json = response.json()
        qtn_data = resp_json.get('data') if isinstance(resp_json, dict) and 'data' in resp_json else resp_json
        
        if not qtn_data:
            return JsonResponse({'status': 'error', 'message': 'Quotation not found'}, status=404)
            
        vendor_id = qtn_data.get('vendor_id')
        vendor_name = f"Vendor #{vendor_id}"
        
        try:
            vendors_resp = requests.get(
                f"{JAVA_API_URL}/api/vendors/all",
                headers={'Authorization': f'Bearer {auth_token}', 'Accept': 'application/json'},
                timeout=10
            )
            if vendors_resp.status_code == 200:
                vendors_data = vendors_resp.json()
                v_list = vendors_data.get('data', []) if isinstance(vendors_data, dict) else vendors_data
                for v in v_list:
                    v_id = v.get('companyId') or v.get('id')
                    if str(v_id) == str(vendor_id):
                        vendor_name = v.get('companyName') or v.get('name') or vendor_name
                        break
        except Exception as ex:
            logger.error(f"Error fetching vendor name for verification: {ex}")
            
        header = qtn_data.get('quotation_header') or {}
        line_items = qtn_data.get('line_items') or []
        
        return JsonResponse({
            'status': 'success',
            'quotation_number': header.get('quotation_number', f"QTN-{qtn_data.get('quotation_id')}"),
            'vendor_name': vendor_name,
            'grand_total': qtn_data.get('grand_total', 0.0),
            'currency': header.get('currency', 'INR'),
            'item_count': len(line_items),
            'quotation_date': header.get('quotation_date', '')
        })
    except Exception as e:
        logger.error(f"Error verifying quotation: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@check_auth
@csrf_exempt
@require_http_methods(["POST"])
def create_po_from_quotation(request):
    user_data = request.session.get('user_data', {})
    auth_token = request.session.get('auth_token')
    
    if not auth_token:
        return JsonResponse({'status': 'error', 'message': 'Authentication required'}, status=401)
        
    try:
        import json
        payload = json.loads(request.body)
        qtn_id = payload.get('qtn_id')
        if not qtn_id:
            return JsonResponse({'status': 'error', 'message': 'Quotation Number/ID is required'}, status=400)
            
        # Determine if qtn_id is numeric or string
        is_numeric = False
        try:
            int(str(qtn_id))
            is_numeric = True
        except ValueError:
            is_numeric = False

        # Admin fetches details
        if is_numeric:
            api_url = f"{JAVA_API_URL}/api/admin/quotations/{qtn_id}"
        else:
            api_url = f"{JAVA_API_URL}/api/admin/quotations/number/{qtn_id}"
            
        response = requests.get(
            api_url,
            headers={'Authorization': f'Bearer {auth_token}', 'Accept': 'application/json'},
            timeout=10
        )
        
        if response.status_code != 200:
            return JsonResponse({
                'status': 'error', 
                'message': f"Failed to retrieve quotation details: status {response.status_code}"
            }, status=response.status_code)
            
        resp_json = response.json()
        qtn_data = resp_json.get('data') if isinstance(resp_json, dict) and 'data' in resp_json else resp_json
        
        if not qtn_data:
            return JsonResponse({'status': 'error', 'message': 'Quotation not found'}, status=404)
            
        vendor_id = qtn_data.get('vendor_id')
        
        # Look up vendor name
        vendor_name = f"Vendor #{vendor_id}"
        vendor_code = f"VND-{vendor_id}"
        try:
            vendors_resp = requests.get(
                f"{JAVA_API_URL}/api/vendors/all",
                headers={'Authorization': f'Bearer {auth_token}', 'Accept': 'application/json'},
                timeout=10
            )
            if vendors_resp.status_code == 200:
                vendors_data = vendors_resp.json()
                v_list = vendors_data.get('data', []) if isinstance(vendors_data, dict) else vendors_data
                for v in v_list:
                    v_id = v.get('companyId') or v.get('id')
                    if str(v_id) == str(vendor_id):
                        vendor_name = v.get('companyName') or v.get('name') or vendor_name
                        vendor_code = v.get('vendorCode') or v.get('code') or vendor_code
                        break
        except Exception as ex:
            logger.error(f"Error fetching vendor details for PO creation: {ex}")
            
        # Get/generate PO Number
        existing_pos = request.session.get('custom_po_data', [])
        highest_po = 4500000000
        for po in existing_pos:
            try:
                # Remove non-digit chars
                num_str = ''.join(c for c in str(po.get('po_number', '')) if c.isdigit())
                if num_str:
                    num = int(num_str)
                    if num > highest_po:
                        highest_po = num
            except ValueError:
                continue
        
        new_po_number = str(highest_po + 1)
        
        # Build PO items
        from datetime import datetime
        today_str = datetime.now().strftime("%Y-%m-%d")
        today_formatted = datetime.now().strftime("%d %b %Y")
        
        line_items = qtn_data.get('line_items') or []
        if not line_items:
            return JsonResponse({'status': 'error', 'message': 'Selected quotation has no line items'}, status=400)
            
        from .utils.excel_parser import format_date_str
        
        po_items = []
        for idx, item in enumerate(line_items):
            qty = float(item.get('quoted_qty') or 0.0)
            price = float(item.get('unit_price') or 0.0)
            net_val = qty * price
            
            gst_percent = float(item.get('gst_percent') or 0.0)
            gst_amount = net_val * (gst_percent / 100.0)
            total_val = net_val + gst_amount
            
            header = qtn_data.get('quotation_header') or {}
            delivery = qtn_data.get('delivery_details') or {}
            payment = qtn_data.get('payment_terms') or {}
            
            po_item = {
                "vendor_id": str(vendor_id),
                "vendor_code": vendor_code,
                "vendor_name": vendor_name,
                "po_number": new_po_number,
                "po_date": today_str,
                "po_date_formatted": today_formatted,
                "po_type": "Standard",
                "company_code": "1000",
                "company_name": "Aequm Industries",
                "currency": header.get('currency', 'INR'),
                "payment_terms": f"Advance {payment.get('advance_required_percent', 0.0):g}%" if payment.get('advance_required_percent') else "Net 45 Days",
                "po_status": "Released",
                "po_status_display": "Released",
                "status_slug": "released",
                "status_badge": "success",
                "delivery_address": delivery.get('named_place') or "Main Warehouse",
                "goods_receipt_plant": "Plant 1",
                "requested_delivery_date": delivery.get('quoted_delivery_date') or today_str,
                "requested_delivery_date_formatted": format_date_str(delivery.get('quoted_delivery_date') or today_str),
                "shipping_instructions": delivery.get('shipping_mode') or "ROAD",
                "line_number": str(item.get('pr_line_id') or (idx + 1)),
                "material_number": item.get('item_code') or "",
                "material_description": item.get('description') or "",
                "quantity": str(qty),
                "uom": item.get('uom') or "PCS",
                "net_price": str(price),
                "net_value": f"{net_val:.2f}",
                "tax_percent": str(gst_percent),
                "tax_amount": f"{gst_amount:.2f}",
                "total_value": f"{total_val:.2f}",
                "confirm_delivery_date": item.get('delivery_date') or today_str,
                "confirm_delivery_date_formatted": format_date_str(item.get('delivery_date') or today_str),
                "gstin": ""
            }
            po_items.append(po_item)
            
        # Add to session list
        existing_pos.extend(po_items)
        request.session['custom_po_data'] = existing_pos
        request.session['has_custom_po_data'] = True
        request.session.modified = True
        
        return JsonResponse({
            'status': 'success', 
            'message': f'Purchase Order PO-{new_po_number} successfully created from Quotation.',
            'po_number': new_po_number
        })
    except Exception as e:
        logger.error(f"Error creating PO from Quotation: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@check_auth
def subcontracting_purchase_orders(request):
    user_data = request.session.get('user_data', {})
    logger.info(f"Accessing Subcontracting POs - Role: {user_data.get('role')}")
    
    # Process Subcon PO items from session
    raw_pos = request.session.get('custom_subcon_po_data', [])
    grouped_pos = {}
    
    for item in raw_pos:
        po_num = str(item.get('subcon_po_number'))
        if not po_num: continue
            
        if po_num not in grouped_pos:
            grouped_pos[po_num] = {
                'subcon_po_number': po_num,
                'po_status': item.get('po_status_display'),
                'status_slug': item.get('status_slug'),
                'status_badge': item.get('status_badge'),
                'po_date_formatted': item.get('po_date_formatted'),
                'vendor_name': item.get('vendor_name'),
                'vendor_code': item.get('vendor_code'),
                'company_name': item.get('company_name'),
                'fg_material_number': item.get('fg_material_number'),
                'total_processing_value': item.get('total_processing_value'),
            }
            
    subcon_pos = []
    for po_num, data in grouped_pos.items():
        try:
            val = float(str(data['total_processing_value']).replace(',', ''))
            data['total_value_formatted'] = f"{val:,.2f}"
        except:
            data['total_value_formatted'] = "0.00"
        subcon_pos.append(data)
        
    subcon_pos.sort(key=lambda x: x['subcon_po_number'], reverse=True)
    
    return render(request, 'pages/subcontracting_purchase_orders.html', {
        'user_data': user_data,
        'subcon_pos': subcon_pos,
        'has_custom_data': request.session.get('has_custom_subcon_po_data', False)
    })

@check_auth
def scheduling_agreements(request):
    user_data = request.session.get('user_data', {})
    logger.info(f"Accessing Scheduling Agreements - Role: {user_data.get('role')}")
    return render(request, 'pages/scheduling_agreements.html', {
        'user_data': user_data
    })

@check_auth
def service_purchase_orders(request):
    user_data = request.session.get('user_data', {})
    logger.info(f"Accessing Service POs - Role: {user_data.get('role')}")
    
    # Process Service PO items from session
    raw_pos = request.session.get('custom_service_po_data', [])
    
    return render(request, 'pages/service_purchase_orders.html', {
        'user_data': user_data,
        'service_pos': raw_pos,
        'has_custom_data': request.session.get('has_custom_service_po_data', False)
    })

@check_auth
def credit_payments(request):
    user_data = request.session.get('user_data', {})
    logger.info(f"Accessing Credit Payments - Role: {user_data.get('role')}")
    return render(request, 'pages/credit_payments.html', {
        'user_data': user_data
    })

@check_auth
def create_asn(request, po_id="PO-2026-04512"):
    user_data = request.session.get('user_data')
    return render(request, 'pages/create_asn.html', {
        'user_data': user_data,
        'po_id': po_id
    })

@csrf_exempt
@require_POST
@check_auth
def upload_payment_excel(request):
    excel_file = request.FILES.get('excel_file')
    if not excel_file:
        return JsonResponse({'status': 'error', 'message': 'No file uploaded'}, status=400)
        
    try:
        from .utils.excel_parser import parse_payment_excel
        payments = parse_payment_excel(excel_file)
        
        request.session['custom_payment_data'] = payments
        request.session['has_custom_payment_data'] = True
        request.session.modified = True
        
        return JsonResponse({'status': 'success', 'message': 'File uploaded and parsed successfully'})
    except Exception as e:
        logger.error(f"Error parsing uploaded file: {str(e)}")
        return JsonResponse({'status': 'error', 'message': f'Failed to parse Excel file: {str(e)}'}, status=500)

@check_auth
def reset_payment_data(request):
    if 'custom_payment_data' in request.session:
        del request.session['custom_payment_data']
    if 'has_custom_payment_data' in request.session:
        del request.session['has_custom_payment_data']
    request.session.modified = True
    return redirect('pages:payments')

@check_auth
def download_payment_template(request):
    import io
    import pandas as pd
    from django.http import HttpResponse

    columns = [
        "document_number", "gross_amount", "tds_deducted", "net_paid", 
        "payment_status", "payment_method", "vendor_code", "vendor_name", 
        "fiscal_year", "invoice_reference", "invoice_date", "payment_date", 
        "utr_cheque_number", "house_bank", "company_code", "currency", 
        "overdue_days", "sync_timestamp", "doc_type", "reconciliation_account", 
        "payment_run_date", "payment_run_id", "beneficiary_name", "account_number", 
        "ifsc_code", "bank_name", "branch_name", "penny_drop_status", 
        "timeline_invoice_posted", "timeline_payment_proposal", "timeline_tds_deducted", 
        "timeline_bank_transfer", "timeline_payment_confirmed", "sap_raw_response"
    ]
    df = pd.DataFrame(columns=columns)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Payment Template')
    
    output.seek(0)
    response = HttpResponse(
        output.read(), 
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="Payment_Template.xlsx"'
    return response

@check_auth
def vendor_payments_view(request):
    user_data = request.session.get('user_data', {})
    logger.info(f"Accessing Vendor Payments - Role: {user_data.get('role')}")
    
    raw_payments = request.session.get('custom_payment_data', [])
    
    context = {
        'user_data': user_data,
        'payments': raw_payments,
        'has_custom_data': request.session.get('has_custom_payment_data', False)
    }
    
    if raw_payments:
        total_payments = len(raw_payments)
        total_gross = sum(float(p['gross_amount_raw']) for p in raw_payments)
        
        in_process = [p for p in raw_payments if p['status_slug'] in ['in_process', 'pending']]
        in_process_total = sum(float(p['gross_amount_raw']) for p in in_process)
        
        paid = [p for p in raw_payments if p['status_slug'] == 'paid']
        paid_total = sum(float(p['gross_amount_raw']) for p in paid)
        
        overdue = [p for p in raw_payments if int(p.get('overdue_days', 0) or 0) > 0 and p['status_slug'] != 'paid']
        overdue_total = sum(float(p['gross_amount_raw']) for p in overdue)
        
        tds_total = sum(float(p.get('tds_deducted_raw', 0) or 0) for p in raw_payments)
        
        def format_lakhs(val):
            if val >= 100000:
                return f"₹{val/100000:.1f}L"
            elif val >= 1000:
                return f"₹{val/1000:.1f}K"
            return f"₹{val:,.0f}"
            
        context['kpi'] = {
            'total_gross_display': format_lakhs(total_gross),
            'total_count': total_payments,
            'paid_display': format_lakhs(paid_total),
            'paid_count': len(paid),
            'in_process_display': format_lakhs(in_process_total),
            'in_process_count': len(in_process),
            'overdue_display': format_lakhs(overdue_total),
            'overdue_count': len(overdue),
            'tds_display': format_lakhs(tds_total)
        }
    
    return render(request, 'pages/invoices-management/payments.html', context)

@csrf_exempt
@check_auth
def vendor_purchase_requisitions_proxy(request):
    """Proxy view for the vendor portal to get their assigned PR items"""
    if request.method == 'GET':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
                
            response = requests.get(
                f"{JAVA_API_URL}/api/vendor/purchase-requisitions",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/json'
                }
            )
            
            if response.status_code in [200, 201]:
                data = response.json()
                
                # Fetch workflow requests status for workflow_id = 10 (PR Approval)
                try:
                    import pymysql
                    conn = pymysql.connect(host='127.0.0.1', user='root', password='GstCheck2025', database='multimedia_governance')
                    with conn.cursor() as cur:
                        cur.execute("SELECT title, status FROM workflow_requests WHERE workflow_id = 10")
                        wf_reqs = {row[0].strip().lower(): row[1] for row in cur.fetchall()}
                    conn.close()
                except Exception as db_err:
                    logger.error(f"Error fetching workflow requests: {db_err}")
                    wf_reqs = {}

                def filter_prs(prs):
                    if not isinstance(prs, list):
                        return prs
                    filtered = []
                    for item in prs:
                        pr_number = item.get('prNumber')
                        if pr_number:
                            # Match f"{pr_number} Requested" case-insensitively without spaces
                            key = f"{pr_number} Requested".strip().lower()
                            status = wf_reqs.get(key)
                            if status:
                                if status == "approved":
                                    filtered.append(item)
                            else:
                                # Show legacy/existing PRs with no workflow request
                                filtered.append(item)
                        else:
                            filtered.append(item)
                    return filtered

                if isinstance(data, list):
                    data = filter_prs(data)
                elif isinstance(data, dict):
                    if 'content' in data:
                        data['content'] = filter_prs(data['content'])
                    elif 'data' in data:
                        if isinstance(data['data'], list):
                            data['data'] = filter_prs(data['data'])
                        elif isinstance(data['data'], dict) and 'content' in data['data']:
                            data['data']['content'] = filter_prs(data['data']['content'])
                
                return JsonResponse(data, safe=False, status=response.status_code)
                
            return JsonResponse(response.json(), safe=False, status=response.status_code)
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
    
    return JsonResponse({'status': 'error', 'error': 'Method not allowed'}, status=405)

@csrf_exempt
@check_auth
def vendor_purchase_requisition_detail_proxy(request):
    """Proxy view for the vendor portal to get their assigned PR details"""
    if request.method == 'GET':
        try:
            auth_token = request.session.get('auth_token')
            if not auth_token:
                return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
                
            pr_number = request.GET.get('prNumber')
            if not pr_number:
                return JsonResponse({'status': 'error', 'error': 'PR Number is required'}, status=400)
                
            response = requests.get(
                f"{JAVA_API_URL}/api/vendor/purchase-requisitions/details?prNumber={pr_number}",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/json'
                }
            )
            return JsonResponse(response.json(), safe=False, status=response.status_code)
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
    
    return JsonResponse({'status': 'error', 'error': 'Method not allowed'}, status=405)

@csrf_exempt
@check_auth
def vendor_pr_respond_proxy(request, pr_id, action=None):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'error': 'Method not allowed'}, status=405)
        
    auth_token = request.session.get('auth_token')
    if not auth_token:
        return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
        
    # Determine the action from URL path or query parameter
    if not action:
        # Check path first (e.g. from accept/reject url mapping)
        if request.path.endswith('/accept'):
            action = 'ACCEPT'
        elif request.path.endswith('/reject'):
            action = 'REJECT'
        else:
            # Check query parameter (action=ACCEPT or action=REJECT)
            action = request.GET.get('action', '').upper()
            
    if action not in ['ACCEPT', 'REJECT']:
        return JsonResponse({'status': 'error', 'error': 'Invalid action. Must be ACCEPT or REJECT'}, status=400)
        
    # Map action to Java PurchaseRequisitionStatus
    target_status = 'APPROVED' if action == 'ACCEPT' else 'REJECTED'
    
    try:
        # 1. Fetch the PR by prNumber to get its database ID
        response = requests.get(
            f"{JAVA_API_URL}/api/purchase-requisitions/pr-number/{pr_id}",
            headers={
                'Authorization': f'Bearer {auth_token}',
                'Accept': 'application/json'
            }
        )
        if response.status_code != 200:
            return JsonResponse({
                'status': 'error', 
                'error': f'Failed to retrieve PR details from backend: {response.status_code}'
            }, status=response.status_code)
            
        pr_data = response.json()
        db_id = pr_data.get('id')
        if not db_id:
            return JsonResponse({'status': 'error', 'error': 'PR database ID not found in backend response'}, status=500)
            
        # 2. Call the Java endpoint to change the status
        status_response = requests.post(
            f"{JAVA_API_URL}/api/vendor/purchase-requisitions/{db_id}/{action.lower()}",
            headers={
                'Authorization': f'Bearer {auth_token}',
                'Content-Type': 'application/json'
            }
        )
        
        if status_response.status_code in [200, 201, 204]:
            return JsonResponse({
                'status': 'success',
                'message': f'Purchase Requisition {pr_id} successfully acknowledged ({action.lower()}ed).'
            })
        else:
            try:
                err_detail = status_response.json()
            except:
                err_detail = status_response.text
            return JsonResponse({
                'status': 'error',
                'error': f'Backend status update failed: {status_response.status_code}',
                'details': err_detail
            }, status=status_response.status_code)
            
    except Exception as e:
        logger.exception('Vendor PR respond proxy error')
        return JsonResponse({'status': 'error', 'error': str(e)}, status=500)


@check_auth
@csrf_exempt
def submit_quotation(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Method not allowed'}, status=405)
        
    auth_token = request.session.get('auth_token')
    if not auth_token:
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=401)
        
    try:
        import json
        payload = json.loads(request.body)
        
        api_endpoint = f"{JAVA_API_URL}/api/vendor/quotations"
        
        response = requests.post(
            api_endpoint,
            json=payload,
            headers={
                'Authorization': f'Bearer {auth_token}',
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
        )
        
        if response.status_code in [200, 201]:
            return JsonResponse({'status': 'success', 'data': response.json()})
        else:
            return JsonResponse({
                'status': 'error', 
                'message': f"Backend error: {response.status_code}",
                'details': response.text
            }, status=response.status_code)
            
    except Exception as e:
        logger.error(f"Error submitting quotation: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

import uuid
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings

@csrf_exempt
def vendor_register_request(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            vendor_name = data.get('vendor_name')
            address = data.get('address')
            contact_name = data.get('contact_name')
            designation = data.get('designation')
            email = data.get('email')
            phone = data.get('phone')
            token = data.get('token')
            admin_id = data.get('admin_id') or data.get('adminId') or 1
            
            if not all([vendor_name, address, contact_name, designation, email, phone]):
                return JsonResponse({'status': 'error', 'error': 'All fields are required.'}, status=400)
                
            # Check if already exists
            if VendorRegistration.objects.filter(email=email).exists():
                existing_reg = VendorRegistration.objects.filter(email=email).first()
                if existing_reg.status in ['ACTIVE', 'DOCUMENTS_SUBMITTED', 'UNDER_VERIFICATION', 'REGISTRATION_SUBMITTED', 'REGISTRATION_APPROVED', 'PENDING_LINK', 'LINK_GENERATED']:
                    return JsonResponse({'status': 'error', 'error': f'A registration request or vendor with this email already exists (Status: {existing_reg.status}).'}, status=400)
                existing_reg.delete()
                
            invite = None
            status = 'PENDING_APPROVAL'
            
            if token:
                try:
                    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
                    token_email = payload.get('email')
                    
                    if token_email != email:
                        return JsonResponse({'status': 'error', 'error': 'Registration email does not match invitation email.'}, status=400)
                        
                    invite = SupplierInvitation.objects.filter(token=token, status='INVITED').first()
                    if not invite:
                        return JsonResponse({'status': 'error', 'error': 'This invitation token is invalid or has already been used.'}, status=400)
                        
                    if invite.expiry_date < timezone.now():
                        invite.status = 'EXPIRED'
                        invite.save()
                        return JsonResponse({'status': 'error', 'error': 'This invitation token has expired.'}, status=400)
                        
                    status = 'REGISTRATION_SUBMITTED'
                except jwt.ExpiredSignatureError:
                    return JsonResponse({'status': 'error', 'error': 'This invitation link has expired.'}, status=400)
                except jwt.InvalidTokenError:
                    return JsonResponse({'status': 'error', 'error': 'Invalid invitation token.'}, status=400)
            
            # Hit the Java Onboarding API first
            java_url = f"{JAVA_API_URL}/api/public/registration/onboarding-request"
            java_payload = {
                "vendorLegalEntityName": vendor_name,
                "vendorAddress": address,
                "vendorContactName": contact_name,
                "vendorDesignation": designation,
                "vendorEmail": email,
                "vendorPhoneNumber": phone,
                "adminId": int(admin_id)
            }
            logger.info(f"Hitting Java onboarding-request: {java_url} with payload {java_payload}")
            
            java_user_id = None
            try:
                response = requests.post(java_url, json=java_payload, headers={'Content-Type': 'application/json'}, timeout=10)
                logger.info(f"Java onboarding-request status: {response.status_code}")
                if response.status_code in [200, 201]:
                    resp_data = response.json()
                    logger.info(f"Java onboarding-request response body: {resp_data}")
                    onb_req = resp_data.get('data', {}).get('onboardingRequest', {})
                    java_user_id = onb_req.get('userId') or resp_data.get('userId')
                    java_password = resp_data.get('password') or onb_req.get('password') or "User@123"
                    status = onb_req.get('onboardingStatus', status)
                else:
                    logger.warning(f"Java onboarding-request returned non-200: {response.text}")
                    error_msg = f"Java onboarding-request failed (Status {response.status_code}): {response.text}"
                    try:
                        resp_json = response.json()
                        if resp_json.get('errorMessage'):
                            error_msg = resp_json.get('errorMessage')
                    except:
                        pass
                    return JsonResponse({'status': 'error', 'error': error_msg}, status=400)
            except Exception as e:
                logger.error(f"Error calling Java onboarding-request API: {e}")
                return JsonResponse({'status': 'error', 'error': f"Failed to connect to the onboarding service: {str(e)}"}, status=502)
            
            reg = VendorRegistration.objects.create(
                vendor_name=vendor_name,
                address=address,
                contact_name=contact_name,
                designation=designation,
                email=email,
                phone=phone,
                status=status,
                invitation=invite,
                user_id=java_user_id
            )
            
            if invite:
                invite.status = 'USED'
                invite.save()
            
            # Call the workflow engine request API to trigger a pre-boarding workflow request
            try:
                wf_payload = {
                    "title": vendor_name,
                    "description": "We got new vendor For approval",
                    "workflow_id": 9,
                    "request_type": "invoice",
                    "metadata": None,
                    "request_metadata": {
                        "vendor_email": email, 
                        "vendor_password": locals().get('java_password', 'User@123'),
                        "vendor_name": vendor_name,
                        "contact_name": contact_name
                    }
                }
                wf_user_id = java_user_id if java_user_id else 1
                wf_url = f"http://localhost:8001/api/requests?user_id={wf_user_id}"
                logger.info(f"Triggering Workflow Request for new vendor: {wf_url} with payload {wf_payload}")
                wf_response = requests.post(wf_url, json=wf_payload, headers={'Content-Type': 'application/json'}, timeout=10)
                logger.info(f"Workflow Engine response status: {wf_response.status_code}")
                if wf_response.status_code not in [200, 201]:
                    logger.warning(f"Workflow Engine returned non-200/201 response: {wf_response.text}")
            except Exception as e:
                logger.error(f"Failed to trigger onboarding workflow in Workflow Engine: {e}")
                
            return JsonResponse({'status': 'success', 'message': 'Registration request submitted successfully!'})
        except Exception as e:
            logger.error(f"Error in vendor_register_request: {e}")
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
            
    return redirect('/login/')


@check_auth
def admin_vendor_registration_dashboard(request):
    # Check if admin
    user_role = request.session.get('user_data', {}).get('role', '')
    if str(user_role).upper() not in ['SUPER_ADMIN', 'ADMIN']:
        return redirect('/vendor/dashboard/')
        
    auth_token = request.session.get('auth_token')
    headers = {
        'Authorization': f'Bearer {auth_token}',
        'Content-Type': 'application/json'
    }
    api_url = f"{JAVA_API_URL}/api/vendor-onboarding/requests"
    logger.info(f"Fetching pending onboarding requests from Java: {api_url}")
    
    try:
        response = requests.get(api_url, headers=headers, timeout=10)
        logger.info(f"Java pending requests status: {response.status_code}")
        if response.status_code == 200:
            resp_data = response.json()
            requests_list = resp_data.get('data', {}).get('requests', [])
            logger.info(f"Retrieved {len(requests_list)} pending requests from Java.")
            for r in requests_list:
                email = r.get('vendorEmail')
                if not email:
                    continue
                reg, created = VendorRegistration.objects.get_or_create(
                    email=email,
                    defaults={
                        'vendor_name': r.get('vendorLegalEntityName', ''),
                        'address': r.get('vendorAddress', ''),
                        'contact_name': r.get('vendorContactName', ''),
                        'designation': r.get('vendorDesignation', ''),
                        'phone': r.get('vendorPhoneNumber', ''),
                        'status': r.get('onboardingStatus', 'PENDING_LINK'),
                        'user_id': r.get('userId')
                    }
                )
                if not created:
                    reg.user_id = r.get('userId')
                    reg.status = r.get('onboardingStatus', reg.status)
                    reg.save()
        else:
            logger.warning(f"Java pending requests returned non-200: {response.text}")
    except Exception as e:
        logger.error(f"Error fetching pending requests from Java: {e}")
        
    pending_approvals = VendorRegistration.objects.filter(status__in=['PENDING_APPROVAL', 'PENDING_LINK', 'REGISTRATION_SUBMITTED']).order_by('-created_date')
    pending_kyc = VendorRegistration.objects.filter(status__in=['DOCUMENT_SUBMITTED', 'UNDER_VERIFICATION', 'DOCUMENTS_SUBMITTED']).order_by('-created_date')
    active_vendors = VendorRegistration.objects.filter(status='ACTIVE').order_by('-approved_date')
    
    admin_id = request.session.get('user_data', {}).get('superAdminId', 1)
    
    context = {
        'pending_approvals': pending_approvals,
        'pending_kyc': pending_kyc,
        'active_vendors': active_vendors,
        'pending_approvals_count': pending_approvals.count(),
        'pending_kyc_count': pending_kyc.count(),
        'active_count': active_vendors.count(),
        'admin_id': admin_id
    }
    return render(request, 'pages/vendor_registration_dashboard.html', context)


@csrf_exempt
@check_auth
def admin_approve_vendor(request, registration_id):
    user_role = request.session.get('user_data', {}).get('role', '')
    if str(user_role).upper() not in ['SUPER_ADMIN', 'ADMIN']:
        return JsonResponse({'status': 'error', 'error': 'Unauthorized'}, status=403)
        
    if request.method == 'POST':
        try:
            reg = get_object_or_404(VendorRegistration, id=registration_id)
            
            action = 'approve'
            if request.body:
                try:
                    body = json.loads(request.body)
                    action = body.get('action', 'approve')
                except:
                    pass
            
            if action == 'reject':
                reg.status = 'REJECTED'
                reg.save()
                return JsonResponse({'status': 'success', 'message': 'Registration request rejected.'})
            
            # Default token generation (fallback)
            admin_id = request.session.get('user_data', {}).get('superAdminId') or 101
            expiry_date = timezone.now() + timezone.timedelta(days=7)  # 7 days expiry
            payload = {
                "adminId": admin_id,
                "vendorId": reg.id,
                "type": "ONBOARDING",
                "expiry": expiry_date.isoformat()
            }
            token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
            if isinstance(token, bytes):
                token = token.decode('utf-8')
            
            status = 'REGISTRATION_APPROVED'
            
            # Hit Java API if reg has user_id
            if reg.user_id:
                auth_token = request.session.get('auth_token')
                headers = {
                    'Authorization': f'Bearer {auth_token}',
                    'Content-Type': 'application/json'
                }
                java_url = f"{JAVA_API_URL}/api/vendor-onboarding/generate-link/{reg.user_id}"
                logger.info(f"Hitting Java generate-link API: {java_url}")
                try:
                    response = requests.post(java_url, headers=headers, json={}, timeout=10)
                    logger.info(f"Java generate-link response status: {response.status_code}")
                    if response.status_code == 200:
                        resp_data = response.json()
                        logger.info(f"Java generate-link response: {resp_data}")
                        link_data = resp_data.get('data', {}).get('linkData', {})
                        token = link_data.get('onboardingToken')
                        status = link_data.get('onboardingStatus', 'LINK_GENERATED')
                    else:
                        logger.warning(f"Java generate-link returned non-200: {response.text}")
                except Exception as e:
                    logger.error(f"Error calling Java generate-link API: {e}")
            
            reg.onboarding_token = token
            reg.status = status
            reg.approved_by = request.session.get('user_data', {}).get('email', 'Admin')
            reg.approved_date = timezone.now()
            reg.save()
            
            # Send Email (Printed to console/logs)
            onboarding_link = f"{request.build_absolute_uri('/vendor/onboarding/')}?token={token}"
            subject = "Vendor Registration Approved"
            body = f"""Dear Vendor,
 
Your registration request for {reg.vendor_name} has been approved.
Please complete your onboarding by setting up your password and uploading documents using the link below:
{onboarding_link}
 
Best regards,
Procurement Team"""
            
            # Print to stdout/terminal for verification
            print("\n" + "="*80)
            print(f"EMAIL TO: {reg.email}")
            print(f"SUBJECT: {subject}")
            print(body)
            print("="*80 + "\n")
            
            try:
                send_mail(
                    subject,
                    body,
                    settings.DEFAULT_FROM_EMAIL or 'noreply@company.com',
                    [reg.email],
                    fail_silently=True
                )
            except Exception as email_err:
                logger.error(f"Failed sending email: {email_err}")
                
            return JsonResponse({
                'status': 'success',
                'token': token
            })
        except Exception as e:
            logger.error(f"Error in admin_approve_vendor: {e}")
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'error': 'Method not allowed'}, status=405)


def _handle_onboarding_details(request, reg, token):
    if reg.status not in ['REGISTRATION_APPROVED', 'CORRECTION_REQUIRED', 'LINK_GENERATED']:
        return render(request, 'pages/vendor_public_onboarding.html', {
            'token_validated': False,
            'error': 'This onboarding token is not active or has been revoked.',
            'token': token
        })
        
    # If POST: save compliance details
    if request.method == 'POST':
        try:
            password = request.POST.get('password')
            gstin = request.POST.get('gstin')
            pan = request.POST.get('pan')
            msme = request.POST.get('msme', '')
            cin = request.POST.get('cin', '')
            account_number = request.POST.get('account_number')
            ifsc_code = request.POST.get('ifsc_code')
            bank_name = request.POST.get('bank_name')
            
            if not all([password, gstin, pan, account_number, ifsc_code, bank_name]):
                return JsonResponse({'status': 'error', 'error': 'All required fields must be completed.'}, status=400)
                
            reg.password = password
            reg.gst_number = gstin
            reg.pan_number = pan
            reg.msme_number = msme
            reg.cin_number = cin
            reg.account_number = account_number
            reg.ifsc_code = ifsc_code
            reg.bank_name = bank_name
            
            # Check for files
            if 'gstFile' in request.FILES:
                reg.gst_certificate = request.FILES['gstFile']
            if 'panFile' in request.FILES:
                reg.pan_card = request.FILES['panFile']
            if 'msmeFile' in request.FILES:
                reg.msme_certificate = request.FILES['msmeFile']
            if 'chequeFile' in request.FILES:
                reg.cancelled_cheque = request.FILES['chequeFile']
            if 'coiFile' in request.FILES:
                reg.coi_certificate = request.FILES['coiFile']
                
            reg.status = 'DOCUMENTS_SUBMITTED'
            reg.save()
            
            # Call the workflow engine request API to trigger a vendor approval workflow request
            try:
                wf_payload = {
                    "title": reg.vendor_name,
                    "description": "We got new vendor For approval",
                    "workflow_id": 8,
                    "request_type": "invoice",
                    "metadata": None,
                    "request_metadata": {
                        "vendor_email": reg.email, 
                        "vendor_password": password,
                        "vendor_name": reg.vendor_name,
                        "contact_name": reg.contact_name
                    }
                }
                wf_user_id = reg.user_id if reg.user_id else 1
                wf_url = f"http://localhost:8001/api/requests?user_id={wf_user_id}"
                logger.info(f"Triggering Workflow Request for vendor approval: {wf_url} with payload {wf_payload}")
                wf_response = requests.post(wf_url, json=wf_payload, headers={'Content-Type': 'application/json'}, timeout=10)
                logger.info(f"Workflow Engine response status: {wf_response.status_code}")
                if wf_response.status_code not in [200, 201]:
                    logger.warning(f"Workflow Engine returned non-200/201 response: {wf_response.text}")
            except Exception as e:
                logger.error(f"Failed to trigger vendor approval workflow in Workflow Engine: {e}")
            
            return JsonResponse({
                'status': 'success',
                'message': 'Onboarding details submitted successfully.'
            })
        except Exception as save_err:
            logger.error(f"Error saving onboarding details: {save_err}")
            return JsonResponse({'status': 'error', 'error': str(save_err)}, status=500)
            
    # If GET: show registration form
    return render(request, 'pages/vendor_public_onboarding.html', {
        'token_validated': True,
        'onboarding_completed': False,
        'token': token,
        'reg': reg
    })


@csrf_exempt
def vendor_onboarding_token(request):
    token = request.GET.get('token') or request.POST.get('token')
    
    if not token:
        return render(request, 'pages/vendor_public_onboarding.html', {
            'token_validated': False
        })
        
    # First, try validating via Java API
    java_url = f"{JAVA_API_URL}/api/public/registration/onboarding-details"
    logger.info(f"Validating token via Java API: {java_url} for token {token}")
    try:
        response = requests.get(java_url, params={'token': token}, timeout=5)
        logger.info(f"Java token validation response status: {response.status_code}")
        if response.status_code == 200:
            resp_data = response.json()
            logger.info(f"Java token validation response body: {resp_data}")
            details = resp_data.get('data', {}).get('onboardingDetails', {})
            if details:
                email = details.get('vendorEmail')
                reg, created = VendorRegistration.objects.get_or_create(
                    email=email,
                    defaults={
                        'vendor_name': details.get('vendorLegalEntityName', ''),
                        'address': details.get('vendorAddress', ''),
                        'contact_name': details.get('vendorContactName', ''),
                        'designation': details.get('vendorDesignation', ''),
                        'phone': details.get('vendorPhoneNumber', ''),
                        'status': 'REGISTRATION_APPROVED',
                        'user_id': details.get('userId')
                    }
                )
                if not created:
                    reg.user_id = details.get('userId')
                    reg.save()
                
                # Check if already completed
                if reg.status in ['DOCUMENTS_SUBMITTED', 'UNDER_VERIFICATION']:
                    return render(request, 'pages/vendor_public_onboarding.html', {
                        'token_validated': True,
                        'onboarding_completed': True,
                        'token': token,
                        'reg': reg
                    })
                    
                if reg.status == 'ACTIVE':
                    return render(request, 'pages/vendor_public_onboarding.html', {
                        'token_validated': True,
                        'onboarding_completed': True,
                        'already_active': True,
                        'token': token,
                        'reg': reg
                    })
                
                return _handle_onboarding_details(request, reg, token)
    except Exception as e:
        logger.error(f"Error calling Java token validation API, falling back to local JWT validation: {e}")

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        vendor_id = payload.get('vendorId')
        token_type = payload.get('type')
        
        if not vendor_id or token_type != 'ONBOARDING':
            if 'email' in payload:
                return redirect(f'/register/?token={token}')
            return render(request, 'pages/vendor_public_onboarding.html', {
                'token_validated': False,
                'error': 'Invalid token type.',
                'token': token
            })
            
        reg = get_object_or_404(VendorRegistration, id=vendor_id)
        
        # Check if already completed
        if reg.status in ['DOCUMENTS_SUBMITTED', 'UNDER_VERIFICATION']:
            return render(request, 'pages/vendor_public_onboarding.html', {
                'token_validated': True,
                'onboarding_completed': True,
                'token': token,
                'reg': reg
            })
            
        if reg.status == 'ACTIVE':
            return render(request, 'pages/vendor_public_onboarding.html', {
                'token_validated': True,
                'onboarding_completed': True,
                'already_active': True,
                'token': token,
                'reg': reg
            })
            
        return _handle_onboarding_details(request, reg, token)
        
    except jwt.ExpiredSignatureError:
        return render(request, 'pages/vendor_public_onboarding.html', {
            'token_validated': False,
            'error': 'This onboarding token has expired. Please contact support.',
            'token': token
        })
    except jwt.InvalidTokenError:
        return render(request, 'pages/vendor_public_onboarding.html', {
            'token_validated': False,
            'error': 'Invalid onboarding token.',
            'token': token
        })
    except Exception as e:
        logger.error(f"Error in vendor_onboarding_token view: {e}")
        return render(request, 'pages/vendor_public_onboarding.html', {
            'token_validated': False,
            'error': f'An error occurred: {str(e)}',
            'token': token
        })


@csrf_exempt
@check_auth
def vendor_kyc_upload(request):
    reg_id = request.session.get('user_data', {}).get('superAdminId')
    reg = get_object_or_404(VendorRegistration, id=reg_id)
    return redirect(f'/onboarding/?token={reg.onboarding_token}')


@csrf_exempt
@check_auth
def admin_verify_kyc_detail(request, registration_id):
    user_role = request.session.get('user_data', {}).get('role', '')
    if str(user_role).upper() not in ['SUPER_ADMIN', 'ADMIN']:
        return redirect('/vendor/dashboard/')
        
    reg = get_object_or_404(VendorRegistration, id=registration_id)
    
    # Auto-transition status to UNDER_VERIFICATION when admin views a DOCUMENTS_SUBMITTED request
    if reg.status == 'DOCUMENTS_SUBMITTED':
        reg.status = 'UNDER_VERIFICATION'
        reg.save()
        
    if request.method == 'POST':
        try:
            body = json.loads(request.body)
            action = body.get('action')
            notes = body.get('notes', '')
            
            if action == 'activate':
                # Generate unique Vendor Code if not already exists
                if not reg.vendor_code:
                    last_vendor = VendorRegistration.objects.exclude(vendor_code__isnull=True).exclude(vendor_code='').order_by('-vendor_code').first()
                    if last_vendor and last_vendor.vendor_code.startswith('V-'):
                        try:
                            num = int(last_vendor.vendor_code.split('-')[1])
                            new_num = num + 1
                            vendor_code = f"V-{new_num:06d}"
                        except:
                            vendor_code = "V-000001"
                    else:
                        vendor_code = "V-000001"
                    reg.vendor_code = vendor_code
                    
                reg.status = 'ACTIVE'
                reg.verification_notes = notes
                reg.save()
                
                # Send activation email
                subject = "aequm Supplier Portal - Account Activated"
                body_text = f"Dear Vendor,\n\nYour compliance documents have been verified and your account is now ACTIVE.\n\nYour Vendor Code: {reg.vendor_code}\n\nYou can log in to the portal at: {request.build_absolute_uri('/login/')}\n\nBest regards,\nProcurement Team"
                
                try:
                    send_mail(
                        subject,
                        body_text,
                        settings.DEFAULT_FROM_EMAIL or 'noreply@company.com',
                        [reg.email],
                        fail_silently=True
                    )
                except Exception as email_err:
                    logger.error(f"Failed sending activation email: {email_err}")
                    
                return JsonResponse({'status': 'success', 'vendor_code': reg.vendor_code})
                
            elif action == 'correction':
                reg.status = 'CORRECTION_REQUIRED'
                reg.verification_notes = notes
                reg.save()
                
                # Send email requesting correction
                subject = "Action Required - Onboarding Document Correction Needed"
                body_text = f"Dear Vendor,\n\nOur compliance team reviewed your uploaded documents and requires corrections:\n\nFeedback: {notes}\n\nPlease update your details at: {request.build_absolute_uri('/onboarding/')}?token={reg.onboarding_token}\n\nBest regards,\nProcurement Team"
                
                try:
                    send_mail(
                        subject,
                        body_text,
                        settings.DEFAULT_FROM_EMAIL or 'noreply@company.com',
                        [reg.email],
                        fail_silently=True
                    )
                except Exception as email_err:
                    logger.error(f"Failed sending correction email: {email_err}")
                    
                return JsonResponse({'status': 'success'})
                
            elif action == 'reject':
                reg.status = 'REJECTED'
                reg.verification_notes = notes
                reg.save()
                
                # Send rejection email
                subject = "Onboarding Request Rejected"
                body_text = f"Dear Vendor,\n\nWe regret to inform you that your supplier onboarding request has been rejected.\n\nReason: {notes}\n\nBest regards,\nProcurement Team"
                
                try:
                    send_mail(
                        subject,
                        body_text,
                        settings.DEFAULT_FROM_EMAIL or 'noreply@company.com',
                        [reg.email],
                        fail_silently=True
                    )
                except Exception as email_err:
                    logger.error(f"Failed sending rejection email: {email_err}")
                    
                return JsonResponse({'status': 'success'})
                
            return JsonResponse({'status': 'error', 'error': 'Invalid action'}, status=400)
        except Exception as e:
            logger.error(f"Error in admin_verify_kyc_detail POST: {e}")
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
            
    return render(request, 'pages/vendor_kyc_verify_detail.html', {'reg': reg})


@csrf_exempt
@check_auth
def admin_create_invitation(request):
    user_role = request.session.get('user_data', {}).get('role', '')
    if str(user_role).upper() not in ['SUPER_ADMIN', 'ADMIN']:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
            return JsonResponse({'status': 'error', 'error': 'Unauthorized'}, status=403)
        return redirect('/vendor/dashboard/')

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            email = data.get('supplier_email')
            name = data.get('supplier_name', '')
            expiry_days = int(data.get('expiry_days', 3))

            if not email:
                return JsonResponse({'status': 'error', 'error': 'Supplier Email is required.'}, status=400)

            # Check if email already registered or invited
            if SupplierInvitation.objects.filter(supplier_email=email, status='INVITED').exists():
                SupplierInvitation.objects.filter(supplier_email=email, status='INVITED').delete()

            expiry_date = timezone.now() + timezone.timedelta(days=expiry_days)
            admin_id = request.session.get('user_data', {}).get('id') or 101

            # Generate token
            payload = {
                "adminId": admin_id,
                "email": email,
                "expiry": expiry_date.isoformat()
            }
            token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
            if isinstance(token, bytes):
                token = token.decode('utf-8')

            # Create invitation record
            invitation = SupplierInvitation.objects.create(
                admin_id=admin_id,
                supplier_email=email,
                token=token,
                expiry_date=expiry_date,
                status='INVITED'
            )

            invite_url = request.build_absolute_uri('/register/') + '?token=' + token

            # Send Email (simulated)
            subject = "Invitation to Register on aequm Procurement Portal"
            message = f"Dear Supplier,\n\nYou have been invited to register on the aequm portal.\n\nPlease click the link below to complete your registration request:\n\n{invite_url}\n\nThis invitation is valid for {expiry_days} days.\n\nBest regards,\nProcurement Team"
            
            try:
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL or 'noreply@company.com',
                    [email],
                    fail_silently=True
                )
            except Exception as mail_err:
                logger.error(f"Failed to send mail: {mail_err}")

            return JsonResponse({
                'status': 'success',
                'invite_url': invite_url,
                'email': email
            })
        except Exception as e:
            logger.error(f"Error in admin_create_invitation: {e}")
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)

    return render(request, 'pages/admin_create_invitation.html')


@check_auth
def admin_list_invitations(request):
    user_role = request.session.get('user_data', {}).get('role', '')
    if str(user_role).upper() not in ['SUPER_ADMIN', 'ADMIN']:
        return redirect('/vendor/dashboard/')

    invitations = SupplierInvitation.objects.all().order_by('-created_at')
    # Build full URLs
    for inv in invitations:
        inv.invite_url = request.build_absolute_uri('/register/') + '?token=' + inv.token

    return render(request, 'pages/admin_list_invitations.html', {'invitations': invitations})


@csrf_exempt
@check_auth
@require_http_methods(["GET"])
def api_vendor_onboarding_requests_proxy(request):
    auth_token = request.session.get('auth_token')
    headers = {
        'Authorization': f'Bearer {auth_token}',
        'Content-Type': 'application/json'
    }
    api_url = f"{JAVA_API_URL}/api/vendor-onboarding/requests"
    logger.info(f"Proxying pending onboarding requests from Java: {api_url}")
    
    try:
        response = requests.get(api_url, headers=headers, timeout=10)
        return JsonResponse(response.json(), status=response.status_code)
    except Exception as e:
        logger.error(f"Error fetching pending requests from Java proxy: {e}")
        return JsonResponse({'status': '500', 'statusMsg': str(e), 'errorCode': '500', 'data': {}}, status=500)


@csrf_exempt
@check_auth
@require_http_methods(["POST"])
def api_vendor_onboarding_generate_link_proxy(request, user_id):
    auth_token = request.session.get('auth_token')
    headers = {
        'Authorization': f'Bearer {auth_token}',
        'Content-Type': 'application/json'
    }
    api_url = f"{JAVA_API_URL}/api/vendor-onboarding/generate-link/{user_id}"
    logger.info(f"Proxying generate-link to Java: {api_url}")
    
    try:
        body = json.loads(request.body) if request.body else {}
    except Exception:
        body = {}
        
    try:
        response = requests.post(api_url, headers=headers, json=body, timeout=10)
        if response.status_code == 200:
            resp_data = response.json()
            link_data = resp_data.get('data', {}).get('linkData', {})
            token = link_data.get('onboardingToken')
            status = link_data.get('onboardingStatus', 'LINK_GENERATED')
            
            # Find local VendorRegistration and update
            reg = VendorRegistration.objects.filter(user_id=user_id).first()
            if reg:
                reg.onboarding_token = token
                reg.status = status
                reg.approved_date = timezone.now()
                reg.approved_by = request.session.get('user_data', {}).get('email', 'Admin')
                reg.save()
                
            return JsonResponse(resp_data, status=200)
        return JsonResponse(response.json(), status=response.status_code)
    except Exception as e:
        logger.error(f"Error calling Java generate-link proxy: {e}")
        return JsonResponse({'status': '500', 'statusMsg': str(e), 'errorCode': '500', 'data': {}}, status=500)


@check_auth
def vendor_prospects(request):
    user_role = request.session.get('user_data', {}).get('role', '')
    if str(user_role).upper() not in ['SUPER_ADMIN', 'ADMIN']:
        return redirect('/vendor/dashboard/')
    return render(request, 'pages/vendor_prospects.html')


@csrf_exempt
@check_auth
def verification_proxy(request, doc_type):
    auth_token = request.session.get('auth_token')
    if not auth_token:
        return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
        
    headers = {
        'Authorization': f'Bearer {auth_token}',
    }
    
    # Forward query parameters if present
    query_string = request.META.get('QUERY_STRING', '')
    api_url = f"{JAVA_API_URL}/api/verification/{doc_type}"
    if query_string:
        api_url = f"{api_url}?{query_string}"
        
    logger.info(f"Proxying verification {request.method} request for {doc_type} to Java: {api_url}")
    
    try:
        if request.method == 'GET':
            response = requests.get(
                api_url,
                headers=headers,
                timeout=30
            )
        else:
            # Forward the files
            files_to_send = {}
            for key, file_obj in request.FILES.items():
                files_to_send[key] = (file_obj.name, file_obj.read(), file_obj.content_type)
            
            # Always collect POST form fields
            data_to_send = request.POST.dict()
                
            if files_to_send:
                response = requests.post(
                    api_url,
                    headers=headers,
                    files=files_to_send,
                    data=data_to_send,
                    timeout=30
                )
            else:
                response = requests.post(
                    api_url,
                    headers=headers,
                    data=data_to_send,
                    timeout=30
                )
        
        logger.info(f"Java backend verification response status: {response.status_code}")
        
        try:
            resp_json = response.json()
            if doc_type == 'company' and response.status_code == 200:
                data = resp_json.get('data', {}) or {}
                company_reg = data.get('companyRegistration')
                if company_reg:
                    user_data = request.session.get('user_data', {})
                    user_data['isDocumentsPresent'] = True
                    request.session['user_data'] = user_data
                    request.session.modified = True
                    logger.info("Automatically set isDocumentsPresent to True in session because company document is verified.")
            return JsonResponse(resp_json, status=response.status_code)
        except Exception:
            from django.http import HttpResponse
            return HttpResponse(response.content, status=response.status_code, content_type=response.headers.get('content-type', 'application/json'))
            
    except Exception as e:
        logger.error(f"Error calling Java verification proxy for {doc_type}: {e}")
        return JsonResponse({'status': '500', 'statusMsg': str(e), 'errorCode': '500'}, status=500)


@csrf_exempt
@check_auth
def verification_submit_proxy(request, doc_type):
    auth_token = request.session.get('auth_token')
    if not auth_token:
        return JsonResponse({'status': 'error', 'error': 'Authentication required'}, status=401)
        
    headers = {
        'Authorization': f'Bearer {auth_token}',
        'Content-Type': 'application/json'
    }
    
    body_data = request.body
    
    api_url = f"{JAVA_API_URL}/api/verification/{doc_type}/submit"
    logger.info(f"Proxying verification submit request for {doc_type} to Java: {api_url}")
    
    try:
        response = requests.post(
            api_url,
            headers=headers,
            data=body_data,
            timeout=30
        )
        logger.info(f"Java backend verification submit response status: {response.status_code}")
        
        try:
            resp_json = response.json()
            if doc_type == 'company' and response.status_code == 200:
                if resp_json.get('errorCode') == '0' or resp_json.get('status') == 'success' or resp_json.get('success') == True or resp_json.get('status') == '200':
                    user_data = request.session.get('user_data', {})
                    user_data['isDocumentsPresent'] = True
                    request.session['user_data'] = user_data
                    request.session.modified = True
                    logger.info("Automatically set isDocumentsPresent to True in session because company document was submitted successfully.")
                    
                    # TRIGGER WORKFLOW FOR LOGGED IN VENDOR AFTER ALL DOCUMENTS UPLOADED
                    try:
                        user_email = user_data.get('email') or ''
                        user_first_name = user_data.get('firstName') or ''
                        user_last_name = user_data.get('lastName') or ''
                        vendor_name = f"{user_first_name} {user_last_name}".strip()
                        if not vendor_name or vendor_name == "None None":
                            vendor_name = user_data.get('authName') or "Vendor"
                            
                        user_id = user_data.get('superAdminId') or 1

                        wf_payload = {
                            "title": vendor_name,
                            "description": "We got new vendor For approval",
                            "workflow_id": 8,
                            "request_type": "invoice",
                            "metadata": None,
                            "request_metadata": {
                                "vendor_email": user_email,
                                "vendor_password": "****** (Your current password)",
                                "vendor_name": vendor_name,
                                "contact_name": vendor_name
                            }
                        }
                        wf_url = f"http://localhost:8001/api/requests?user_id={user_id}"
                        logger.info(f"Triggering Workflow Request for Vendor Approval (logged in flow): {wf_url} with payload {wf_payload}")
                        wf_response = requests.post(wf_url, json=wf_payload, headers={'Content-Type': 'application/json'}, timeout=10)
                        logger.info(f"Workflow Engine response status: {wf_response.status_code}")
                        if wf_response.status_code not in [200, 201]:
                            logger.warning(f"Workflow Engine returned non-200/201 response: {wf_response.text}")
                    except Exception as e:
                        logger.error(f"Failed to trigger vendor approval workflow in Workflow Engine (logged in flow): {e}")

            return JsonResponse(resp_json, status=response.status_code)
        except Exception:
            from django.http import HttpResponse
            return HttpResponse(response.content, status=response.status_code, content_type=response.headers.get('content-type', 'application/json'))
            
    except Exception as e:
        logger.error(f"Error calling Java verification submit proxy for {doc_type}: {e}")
        return JsonResponse({'status': '500', 'statusMsg': str(e), 'errorCode': '500'}, status=500)


@check_auth
def indents(request):
    user_data = request.session.get('user_data')
    auth_token = request.session.get('auth_token')
    
    indents_list = []
    
    try:
        if auth_token:
            # Connect to Workflow service to get Indent Approval requests (workflow_id = 12)
            import requests
            response = requests.get(
                f"{FASTAPI_URL}/requests/?workflow_id=12&user_id=1",
                headers={
                    'Authorization': f'Bearer {auth_token}',
                    'Accept': 'application/json'
                }
            )
            
            if response.status_code == 200:
                indents_list = response.json()
    except Exception as e:
        print("Error fetching indents:", e)
        
    return render(request, 'pages/indents.html', {
        'user_data': user_data,
        'indents': indents_list
    })

@csrf_exempt
@check_auth
def budget_upload(request):
    from .models import Department, BudgetAllocation
    import pandas as pd
    if request.method == 'POST':
        if 'file' not in request.FILES:
            return JsonResponse({'status': 'ERROR', 'message': 'No file uploaded'}, status=400)
        
        file = request.FILES['file']
        dept_code = request.POST.get('dept_code')
        fiscal_year = request.POST.get('fiscal_year', 'FY26-27')
        
        if not dept_code:
            return JsonResponse({'status': 'ERROR', 'message': 'Department code is required'}, status=400)
            
        try:
            dept = Department.objects.get(code=dept_code)
        except Department.DoesNotExist:
            return JsonResponse({'status': 'ERROR', 'message': 'Department not found'}, status=404)
            
        try:
            df = pd.read_excel(file)
            
            # Clear old allocations for this dept and year? (Optional, let's just append or replace)
            # BudgetAllocation.objects.filter(department=dept, fiscal_year=fiscal_year).delete()
            
            for index, row in df.iterrows():
                # Extract values with fallback to 0
                def get_val(col_names):
                    for col in col_names:
                        if col in df.columns:
                            val = row[col]
                            if pd.isna(val):
                                return 0
                            return float(val)
                    return 0

                BudgetAllocation.objects.create(
                    department=dept,
                    fiscal_year=fiscal_year,
                    project_code=str(row.get('Project Code', '')),
                    project_name=str(row.get('Project', '')),
                    activity_name=str(row.get('Activity', '')),
                    wbs=str(row.get('WBS', '')),
                    cost_center=str(row.get('Cost Center', ''))[:15],
                    apr=get_val(['Apr', 'April']),
                    may=get_val(['May']),
                    jun=get_val(['Jun', 'June']),
                    jul=get_val(['Jul', 'July']),
                    aug=get_val(['Aug', 'August']),
                    sep=get_val(['Sep', 'September']),
                    oct=get_val(['Oct', 'October']),
                    nov=get_val(['Nov', 'November']),
                    dec=get_val(['Dec', 'December']),
                    jan=get_val(['Jan', 'January']),
                    feb=get_val(['Feb', 'February']),
                    mar=get_val(['Mar', 'March'])
                )
                
            return JsonResponse({'status': 'SUCCESS', 'message': 'Budget uploaded successfully'})
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({'status': 'ERROR', 'message': str(e)}, status=500)
            
    return JsonResponse({'status': 'ERROR', 'message': 'Invalid method'}, status=405)


@csrf_exempt
@check_auth
def department_budget_status(request):
    from .models import Department, BudgetAllocation
    import datetime
    
    if request.method == 'GET':
        dept_code = request.GET.get('dept_code')
        if not dept_code:
            return JsonResponse({'status': 'ERROR', 'message': 'Department code required'}, status=400)
            
        try:
            dept = Department.objects.get(code=dept_code)
        except Department.DoesNotExist:
            return JsonResponse({'status': 'ERROR', 'message': 'Department not found'}, status=404)
            
        # Determine current month and quarter
        # FY starts in April, but let's just use calendar month for simplicity mapping
        today = datetime.datetime.now()
        month = today.month
        
        # Quarter mapping:
        # Q1: Jan, Feb, Mar (If Calendar)
        # Q1: Apr, May, Jun (If FY starting April) -> typically used in India.
        # Let's use standard FY starting April.
        if month in [4, 5, 6]:
            q_months = ['apr', 'may', 'jun']
        elif month in [7, 8, 9]:
            q_months = ['jul', 'aug', 'sep']
        elif month in [10, 11, 12]:
            q_months = ['oct', 'nov', 'dec']
        else:
            q_months = ['jan', 'feb', 'mar']
            
        month_map = {1: 'jan', 2: 'feb', 3: 'mar', 4: 'apr', 5: 'may', 6: 'jun', 7: 'jul', 8: 'aug', 9: 'sep', 10: 'oct', 11: 'nov', 12: 'dec'}
        current_month_str = month_map[month]
        
        allocations = BudgetAllocation.objects.filter(department=dept)
        
        current_month_allocated = 0
        current_quarter_allocated = 0
        
        for alloc in allocations:
            current_month_allocated += float(getattr(alloc, current_month_str, 0))
            for qm in q_months:
                current_quarter_allocated += float(getattr(alloc, qm, 0))
                
        # If no allocations, fallback to approved budget logic or 0
        if current_month_allocated == 0 and current_quarter_allocated == 0:
            pass # Keep it 0 if it's strictly from DB. Or we can just fallback if no records exist.
            
        return JsonResponse({
            'status': 'SUCCESS',
            'data': {
                'current_month_allocated': current_month_allocated,
                'current_quarter_allocated': current_quarter_allocated,
                'department_approved': float(dept.approved_budget)
            }
        })
        
    return JsonResponse({'status': 'ERROR', 'message': 'Invalid method'}, status=405)
