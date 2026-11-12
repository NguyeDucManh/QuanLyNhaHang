"""Inspect provenance without importing NumPy, sklearn, torch or a model."""
from .artifacts import latest, read_json


def operational_forecast_metadata():
    try:
        meta=read_json(latest('forecast')/'metadata.json')
    except (ValueError,OSError):
        return None,'Chưa có model dự báo sẵn sàng; số liệu thực tế vẫn có trong Báo cáo.'
    provenance=meta.get('data_provenance',{})
    if provenance.get('synthetic_days',0) or provenance.get('real_days',0)<28:
        return None,'Artifact hiện chỉ phục vụ nghiên cứu, chưa đủ chuỗi dữ liệu thật để dự báo vận hành. Không hiển thị kết quả mô phỏng như doanh thu thực.'
    return meta,''
