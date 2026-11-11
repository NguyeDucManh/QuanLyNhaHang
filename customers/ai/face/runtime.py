"""Portable model lookup and a stable, non-sensitive API failure contract."""
import logging
from functools import wraps
from pathlib import Path

from django.core.exceptions import PermissionDenied
from django.http import JsonResponse, Http404

logger = logging.getLogger(__name__)


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
