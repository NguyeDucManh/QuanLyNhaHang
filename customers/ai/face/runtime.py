"""Portable model lookup and a stable, non-sensitive API failure contract."""
import logging
import threading
from functools import wraps
from pathlib import Path

from django.core.exceptions import PermissionDenied
from django.http import JsonResponse, Http404

logger = logging.getLogger(__name__)
_face_capacity = threading.BoundedSemaphore(1)


class FaceServiceUnavailable(RuntimeError):
    pass


def asset_path(folder, name, entry):
    # Prefer deployment-local files. A developer's absolute cache path is only
    # usable on that developer's machine, never a requirement for Linux hosting.
    local = folder / name
    if local.is_file():
        return local
    configured = entry.get('local_path')
    if configured and Path(configured).is_file():
        return Path(configured)
    raise FaceServiceUnavailable('Thiếu model FaceID: ' + name + '. Cần cài đúng bộ model đã xác minh trên máy chủ.')


def face_api(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        guarded = request.method == 'POST' and getattr(request.user,'is_authenticated',False) and any(
            key in request.path for key in ('quality','verify','enroll','/test/'))
        acquired = not guarded or _face_capacity.acquire(blocking=False)
        if not acquired:
            response = JsonResponse({'success':False,'code':'FACE_BUSY',
                'error':'Máy chủ đang xử lý một yêu cầu FaceID khác. Vui lòng thử lại sau vài giây; yêu cầu này chưa được thực hiện.'},status=429)
            response['Cache-Control']='no-store';response['Retry-After']='2'
            return response
        try:
            response = view(request, *args, **kwargs)
        except Http404:
            response = JsonResponse({'success': False, 'code': 'FACE_RESOURCE_NOT_FOUND',
                'error': 'Không tìm thấy hồ sơ nhân viên phù hợp với tài khoản hoặc quyền hiện tại.'}, status=404)
        except PermissionDenied:
            response = JsonResponse({'success': False, 'code': 'FACE_FORBIDDEN',
                'error': 'Bạn không có quyền thực hiện thao tác FaceID này.'}, status=403)
        except (FaceServiceUnavailable, ImportError, OSError) as error:
            logger.exception('FaceID runtime unavailable at %s', request.path)
            response = JsonResponse({'success': False, 'code': 'FACE_RUNTIME_UNAVAILABLE',
                'error': str(error) if isinstance(error, FaceServiceUnavailable) else
                'Không khởi tạo được thư viện/model FaceID trên máy chủ. Cần kiểm tra Render Logs.'}, status=503)
        except Exception:
            logger.exception('FaceID unexpected failure at %s', request.path)
            response = JsonResponse({'success': False, 'code': 'FACE_INTERNAL_ERROR',
                'error': 'Lỗi xử lý FaceID trên máy chủ. Cần kiểm tra Render Logs.'}, status=500)
        finally:
            if guarded and acquired:_face_capacity.release()
        if response.status_code in (301, 302) and not request.user.is_authenticated:
            response = JsonResponse({'success': False, 'code': 'FACE_SESSION_EXPIRED',
                'error': 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.'}, status=401)
        elif response.status_code == 405:
            allowed = response.get('Allow', 'POST')
            response = JsonResponse({'success': False, 'code': 'FACE_METHOD_NOT_ALLOWED',
                'error': 'Phương thức API không hợp lệ; sử dụng ' + allowed + '.'}, status=405)
            response['Allow'] = allowed
        response['Cache-Control'] = 'no-store'
        return response
    return wrapped
