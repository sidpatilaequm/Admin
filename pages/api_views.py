from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
import json
import os
import threading
import time
import base64
from datetime import datetime
from typing import Dict, List

from pages.utils.pdf_images import extract_images_to_dir

# In-memory job registry. For production, move to DB or cache.
_JOBS: Dict[str, Dict] = {}

def _job_dir(job_id: str) -> str:
    return os.path.join(settings.MEDIA_ROOT, 'pdf_jobs', job_id)

def _job_images_dir(job_id: str) -> str:
    return os.path.join(_job_dir(job_id), 'images')

def _background_extract(job_id: str, pdf_path: str, params: Dict):
    try:
        _JOBS[job_id]['status'] = 'processing'
        out_dir = _job_images_dir(job_id)
        os.makedirs(out_dir, exist_ok=True)
        items = extract_images_to_dir(pdf_path, out_dir, params=params)
        # Persist simple manifest for later pagination without re-reading all files
        manifest = []
        for it in items:
            manifest.append({
                'page': it['page'],
                'index': it['index'],
                'kind': it['kind'],
                'relpath': it['relpath'],
                'ext': it['ext'],
                'drawn_width_pt': it['drawn_width_pt'],
                'drawn_height_pt': it['drawn_height_pt'],
            })
        _JOBS[job_id]['manifest'] = manifest
        _JOBS[job_id]['total'] = len(manifest)
        _JOBS[job_id]['status'] = 'completed'
        _JOBS[job_id]['updated_at'] = time.time()
    except Exception as e:
        _JOBS[job_id]['status'] = 'failed'
        _JOBS[job_id]['error'] = str(e)
        _JOBS[job_id]['updated_at'] = time.time()

@csrf_exempt
@require_http_methods(["POST"])
def upload_vendor_files(request):
    try:
        # Get the uploaded files
        gst_certificate = request.FILES.get('gst_certificate')
        pan_card = request.FILES.get('pan_card')
        bank_cheque = request.FILES.get('bank_cheque')
        incorporation_certificate = request.FILES.get('incorporation_certificate')

        # Save the files to a specific directory
        upload_dir = 'media/vendor_documents/'
        os.makedirs(upload_dir, exist_ok=True)

        file_paths = {}
        if gst_certificate:
            file_paths['gst_certificate'] = os.path.join(upload_dir, f'gst_{datetime.now().strftime("%Y%m%d_%H%M%S")}_{gst_certificate.name}')
            with open(file_paths['gst_certificate'], 'wb+') as destination:
                for chunk in gst_certificate.chunks():
                    destination.write(chunk)

        if pan_card:
            file_paths['pan_card'] = os.path.join(upload_dir, f'pan_{datetime.now().strftime("%Y%m%d_%H%M%S")}_{pan_card.name}')
            with open(file_paths['pan_card'], 'wb+') as destination:
                for chunk in pan_card.chunks():
                    destination.write(chunk)

        if bank_cheque:
            file_paths['bank_cheque'] = os.path.join(upload_dir, f'cheque_{datetime.now().strftime("%Y%m%d_%H%M%S")}_{bank_cheque.name}')
            with open(file_paths['bank_cheque'], 'wb+') as destination:
                for chunk in bank_cheque.chunks():
                    destination.write(chunk)

        if incorporation_certificate:
            file_paths['incorporation_certificate'] = os.path.join(upload_dir, f'incorp_{datetime.now().strftime("%Y%m%d_%H%M%S")}_{incorporation_certificate.name}')
            with open(file_paths['incorporation_certificate'], 'wb+') as destination:
                for chunk in incorporation_certificate.chunks():
                    destination.write(chunk)

        # Process the files and extract data (you'll need to implement this based on your requirements)
        # For now, returning a success response
        return JsonResponse({
            'status': 'success',
            'message': 'Files uploaded successfully',
            'file_paths': file_paths
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def pdf_extract_start(request: HttpRequest):
    try:
        if 'file' not in request.FILES:
            return JsonResponse({'status': 'ERROR', 'message': 'file is required'}, status=400)

        f = request.FILES['file']
        # Save under MEDIA/pdf_jobs/<job_id>/source.pdf
        job_id = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
        job_path = _job_dir(job_id)
        os.makedirs(job_path, exist_ok=True)
        pdf_path = os.path.join(job_path, 'source.pdf')
        with open(pdf_path, 'wb+') as dest:
            for chunk in f.chunks():
                dest.write(chunk)

        # Optional params via form fields
        params = {}
        preset = request.POST.get('preset')
        # Preset thresholds to catch smaller thumbnails/icons
        if preset == 'small':
            params.update({
                'min_drawn_width_pt': 60,
                'min_drawn_height_pt': 60,
                'min_drawn_area_pt2': 5000,
                'aspect_min': 0.5,
                'aspect_max': 4.0,
                'min_effective_dpi': 30,
                'merge_tol_pt': 12,
                'crop_margin_pt': 6,
            })
        elif preset == 'tiny':
            params.update({
                'min_drawn_width_pt': 30,
                'min_drawn_height_pt': 30,
                'min_drawn_area_pt2': 900,
                'aspect_min': 0.4,
                'aspect_max': 5.0,
                'min_effective_dpi': 20,
                'merge_tol_pt': 10,
                'crop_margin_pt': 5,
            })
        for key in ['min_drawn_width_pt','min_drawn_height_pt','min_drawn_area_pt2','aspect_min','aspect_max','min_effective_dpi','top_k_per_page','merge_tol_pt','crop_margin_pt','crop_scale']:
            if key in request.POST:
                try:
                    val = float(request.POST[key])
                    if key in ['top_k_per_page']:
                        val = int(val)
                    params[key] = int(val) if val.is_integer() else val
                except Exception:
                    continue

        _JOBS[job_id] = {
            'status': 'queued',
            'created_at': time.time(),
            'updated_at': time.time(),
            'total': 0,
            'manifest': [],
        }

        t = threading.Thread(target=_background_extract, args=(job_id, pdf_path, params), daemon=True)
        t.start()

        return JsonResponse({'status': 'SUCCESS', 'job_id': job_id})
    except Exception as e:
        return JsonResponse({'status': 'ERROR', 'message': str(e)}, status=500)


@require_http_methods(["GET"])
def pdf_extract_status(request: HttpRequest, job_id: str):
    job = _JOBS.get(job_id)
    if not job:
        return JsonResponse({'status': 'ERROR', 'message': 'job not found'}, status=404)
    return JsonResponse({'status': 'SUCCESS', 'job': {k: v for k, v in job.items() if k != 'manifest'}})


@require_http_methods(["GET"])
def pdf_extract_images(request: HttpRequest, job_id: str):
    job = _JOBS.get(job_id)
    if not job:
        return JsonResponse({'status': 'ERROR', 'message': 'job not found'}, status=404)
    if job['status'] not in ['completed', 'processing']:
        return JsonResponse({'status': 'ERROR', 'message': f"job status is {job['status']}"}, status=400)

    # pagination
    try:
        page = int(request.GET.get('page', '1'))
        page_size = int(request.GET.get('page_size', '50'))
        page = max(page, 1)
        page_size = max(min(page_size, 100), 1)
    except Exception:
        page, page_size = 1, 50

    manifest = job.get('manifest', [])
    total = job.get('total', len(manifest))
    start = (page - 1) * page_size
    end = min(start + page_size, total)
    items = manifest[start:end]

    format_mode = request.GET.get('format', 'urls')  # 'urls' | 'base64'
    images_resp: List[Dict] = []
    base_url = request.build_absolute_uri('/')
    images_dir = _job_images_dir(job_id)

    for it in items:
        file_path = os.path.join(images_dir, it['relpath'])
        if format_mode == 'base64':
            try:
                with open(file_path, 'rb') as f:
                    b64 = base64.b64encode(f.read()).decode('ascii')
            except Exception:
                b64 = None
            images_resp.append({
                'page': it['page'],
                'index': it['index'],
                'kind': it['kind'],
                'ext': it['ext'],
                'image_base64': b64,
                'drawn_width_pt': it['drawn_width_pt'],
                'drawn_height_pt': it['drawn_height_pt'],
            })
        else:
            # build media URL
            rel_media_path = os.path.relpath(file_path, settings.MEDIA_ROOT).replace('\\', '/')
            url = settings.MEDIA_URL.rstrip('/') + '/' + rel_media_path
            images_resp.append({
                'page': it['page'],
                'index': it['index'],
                'kind': it['kind'],
                'ext': it['ext'],
                'url': url,
                'drawn_width_pt': it['drawn_width_pt'],
                'drawn_height_pt': it['drawn_height_pt'],
            })

    return JsonResponse({
        'status': 'SUCCESS',
        'job_id': job_id,
        'page': page,
        'page_size': page_size,
        'total': total,
        'results': images_resp,
        'format': format_mode,
    })


@csrf_exempt
@require_http_methods(["DELETE"])
def pdf_extract_cleanup(request: HttpRequest, job_id: str):
    # remove job directory and registry entry
    job = _JOBS.pop(job_id, None)
    job_path = _job_dir(job_id)
    try:
        if os.path.isdir(job_path):
            # best-effort recursive delete
            for root, dirs, files in os.walk(job_path, topdown=False):
                for name in files:
                    try:
                        os.remove(os.path.join(root, name))
                    except Exception:
                        pass
                for name in dirs:
                    try:
                        os.rmdir(os.path.join(root, name))
                    except Exception:
                        pass
            try:
                os.rmdir(job_path)
            except Exception:
                pass
        return JsonResponse({'status': 'SUCCESS', 'message': 'job cleaned'})
    except Exception as e:
        return JsonResponse({'status': 'ERROR', 'message': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def process_vendor_data(request):
    try:
        # Get the file paths from the request
        data = json.loads(request.body)
        file_paths = data.get('file_paths', {})

        # Process the files and extract data
        # TODO: Implement actual data extraction logic from uploaded files
        # For now, return empty data structure
        vendor_data = {}

        return JsonResponse({
            'status': 'success',
            'data': vendor_data
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)

@csrf_exempt
@require_http_methods(["POST"])
def submit_vendor_data(request):
    try:
        # Get the final vendor data
        data = json.loads(request.body)
        
        # Save the data to your database
        # This is where you'll implement your database saving logic
        
        return JsonResponse({
            'status': 'success',
            'message': 'Vendor data submitted successfully'
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400) 