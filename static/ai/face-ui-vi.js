(() => {
  'use strict';
  const labels={PROVISIONAL:'Ngưỡng tạm thời',CALIBRATED:'Ngưỡng đã hiệu chỉnh',GPS_ALLOWED:'Trong phạm vi',GPS_DENIED:'Ngoài phạm vi',GPS_ACCURACY_LOW:'Độ chính xác GPS chưa đạt',GPS_UNAVAILABLE:'Không lấy được vị trí',GPS_INVALID:'Vị trí không hợp lệ',FACE_ONLY:'Chỉ nhận diện khuôn mặt',GPS_ONLY:'Chỉ xác thực vị trí',FACE_AND_GPS:'Khuôn mặt và vị trí'};
  const timestamp=value=>{const date=new Date(value);return Number.isNaN(date.getTime())?'Chưa có thời gian':new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(date);};
  const message=value=>{
    let result=String(value||'Không thể hoàn tất yêu cầu.');
    if(/pretrained|download_ai_models|model hash/i.test(result))return 'Mô hình nhận diện chưa sẵn sàng hoặc chưa được kiểm chứng. Vui lòng liên hệ quản lý.';
    Object.entries(labels).forEach(([code,label])=>{result=result.replaceAll(code,label);});
    for(const [word,label] of [['Similarity','Độ tương đồng'],['threshold','ngưỡng nhận diện'],['Employee','nhân viên'],['FaceID','nhận diện khuôn mặt'],['frame','khung hình'],['liveness','kiểm tra người thật'],['Pose','Hướng mặt'],['consent','sự đồng ý'],['validation','kiểm định'],['calibration','hiệu chỉnh'],['challenge','thử thách'],['server','hệ thống']])result=result.replace(new RegExp('\\b'+word+'\\b','gi'),label);
    if(/failed to fetch|networkerror|load failed/i.test(result))return 'Không thể kết nối hệ thống. Vui lòng thử lại.';
    if(/permission denied|notallowederror/i.test(result))return 'Trình duyệt chưa được cấp quyền truy cập.';
    if(/could not start video|notreadableerror|device.*not found/i.test(result))return 'Không mở được camera. Kiểm tra thiết bị và quyền sử dụng camera.';
    return result;
  };
  window.FaceUI={label:value=>labels[value]||value,timestamp,message};
})();
