(() => {
  'use strict';
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  document.querySelectorAll('[data-face-realtime]').forEach(host=>{
    const mode=host.dataset.faceRealtime, attendance=mode==='attendance';
    const configNode=document.getElementById('location-config');
    const config=configNode?JSON.parse(configNode.textContent):{};
    let needGPS=attendance&&config.mode!=='FACE_ONLY', showGPS=!attendance||needGPS, needFace=!attendance||config.mode!=='GPS_ONLY';
    const ui=window.FaceUI;
    const video=host.querySelector('video'), status=host.querySelector('.face-status'), result=host.querySelector('[data-face-result]');
    let stream=null,watch=null,point=null,pointTime=0,faceTime=0,faceOK=false,generation=0,busy=false,geoAllowed=false;
    const text=(selector,value)=>{const node=host.querySelector(selector);if(node)node.textContent=value;};
    const post=async(url,data,method='POST')=>{
      const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),60000);
      try {
        const response=await fetch(url,{method,credentials:'same-origin',redirect:'follow',signal:controller.signal,headers:{'Content-Type':'application/json','X-CSRFToken':host.querySelector('[name=csrfmiddlewaretoken]').value},body:method==='GET'?undefined:JSON.stringify(data)});
        const type=response.headers.get('Content-Type')||'';
        const body=type.includes('application/json')?await response.json():null;
        const detail=body?.error;
        if(response.redirected||response.status===401)throw new Error('Phi\u00ean \u0111\u0103ng nh\u1eadp h\u1ebft h\u1ea1n. Vui l\u00f2ng \u0111\u0103ng nh\u1eadp l\u1ea1i.');
        if(!response.ok||!body||typeof body!=='object'||Array.isArray(body)){
          const hint=response.status===403?'Quy\u1ec1n truy c\u1eadp ho\u1eb7c CSRF kh\u00f4ng h\u1ee3p l\u1ec7.':[502,504].includes(response.status)?'Render gateway l\u1ed7i ho\u1eb7c h\u1ebft th\u1eddi gian ch\u1edd.':response.status>=500?'D\u1ecbch v\u1ee5 FaceID tr\u00ean m\u00e1y ch\u1ee7 g\u1eb7p l\u1ed7i. C\u1ea7n ki\u1ec3m tra Render Logs.':'Ph\u1ea3n h\u1ed3i FaceID kh\u00f4ng h\u1ee3p l\u1ec7.';
          const error=new Error(`${detail||hint} [HTTP ${response.status}; ${type||'unknown'}; ${url}]`);error.body=body;throw error;
        }
        return body;
      } catch(error) {
        if(error.name==='AbortError')throw new Error('FaceID timeout (60s). Chưa xác định kết quả; kiểm tra lịch sử chấm công trước khi thử lại. Cần kiểm tra model, RAM và Render Logs.');
        throw error;
      } finally {clearTimeout(timer);}
    };
    const phase=value=>host.querySelector('.face-camera')?.setAttribute('data-phase',value);
    function fitCamera(){
      const viewport=host.querySelector('.face-camera-viewport'),guide=host.querySelector('[data-guide]');
      if(!viewport||!guide||!video.videoWidth||!video.videoHeight)return;
      const height=Math.min(innerWidth<600?520:600,viewport.clientWidth*video.videoHeight/video.videoWidth);
      viewport.style.height=height+'px';video.style.height=height+'px';
      const scale=Math.min(viewport.clientWidth/video.videoWidth,height/video.videoHeight);
      const width=Math.min(video.videoWidth*scale*.76,video.videoHeight*scale*.62);
      guide.style.width=width+'px';guide.style.height=Math.min(width*1.35,video.videoHeight*scale*.85)+'px';
    }
    let policyFresh=!host.dataset.statusUrl;
    function progress(value,total){const p=host.querySelector('[data-sample-progress]');if(p){p.max=total;p.value=value;}text('[data-sample-label]',value?`Đã thu ${value}/${total} frame`:'Chưa thu mẫu');}
    function qualityFeedback(q){
      if(!q||!Number.isFinite(q.face_width)||!Number.isFinite(q.face_height))throw new Error('API chất lượng chưa trả số đo khuôn mặt hợp lệ.');
      let hint='Đã phát hiện khuôn mặt trong frame vừa kiểm tra';
      if(Number.isFinite(q.center_x)&&Number.isFinite(q.center_y)&&(Math.abs(q.center_x-.5)>.2||Math.abs(q.center_y-.47)>.23))hint='Đưa khuôn mặt vào giữa khung';
      else if(q.face_width/q.frame_width>.8||q.face_height/q.frame_height>.8)hint='Lùi xa camera một chút';
      else if(q.face_width/q.frame_width<.22)hint='Tiến gần camera một chút';
      text('.face-guide-caption',hint);
      const box=host.querySelector('[data-detection-box]'),viewport=host.querySelector('.face-camera-viewport');
      if(box&&viewport&&[q.frame_width,q.frame_height,q.face_x,q.face_y].every(Number.isFinite)){
        const scale=Math.min(viewport.clientWidth/q.frame_width,viewport.clientHeight/q.frame_height);
        Object.assign(box.style,{left:((viewport.clientWidth-q.frame_width*scale)/2+q.face_x*scale)+'px',top:((viewport.clientHeight-q.frame_height*scale)/2+q.face_y*scale)+'px',width:(q.face_width*scale)+'px',height:(q.face_height*scale)+'px'});box.hidden=false;setTimeout(()=>box.hidden=true,3000);
      }
    }
    async function syncStatus(){
      if(!attendance||!host.dataset.statusUrl)return;
      try{
        const body=await post(host.dataset.statusUrl,undefined,'GET');
        if(!body.config||!Array.isArray(body.schedules))throw new Error('Không đọc được chính sách và ca làm hiện tại.');
        const changed=['latitude','longitude','radius','max_accuracy','mode','configured'].some(key=>config[key]!==body.config[key]);Object.assign(config,body.config);
        needGPS=config.mode!=='FACE_ONLY';needFace=config.mode!=='GPS_ONLY';showGPS=needGPS;policyFresh=true;
        if(changed){geoAllowed=false;text('[data-server-distance]','Cấu hình mới; cần kiểm tra lại khoảng cách máy chủ.');}
        text('[data-radius]',`Bán kính nhà hàng: ${config.radius??'—'} m`);text('[data-restaurant-location]',`${config.name||'Nhà hàng'} · ${config.address||'Chưa cập nhật địa chỉ'}`);
        text('[data-policy-message]',config.configured?'Khuôn mặt, vị trí và ca làm được kiểm tra riêng.':config.error);
        text('[data-restaurant-coordinates]',`${config.latitude??'—'}, ${config.longitude??'—'}`);
        window.attendanceMap?.configure(config);
        const guide=host.querySelector('[data-guide]');if(guide)guide.hidden=!needFace;host.querySelector('.face-guide-caption').hidden=!needFace;
        if(!needGPS)text('.geo-status','Kh\u00f4ng y\u00eau c\u1ea7u v\u1ecb tr\u00ed theo ch\u00ednh s\u00e1ch hi\u1ec7n t\u1ea1i.');
        const select=host.querySelector('[data-schedule]'),selected=select.value;select.replaceChildren();
        for(const item of body.schedules){const option=document.createElement('option');option.value=item.id;option.textContent=item.label;select.append(option);}
        if(!body.schedules.length){const option=document.createElement('option');option.value='';option.textContent='Chưa có ca đã duyệt';select.append(option);}
        if([...select.options].some(o=>o.value===selected))select.value=selected;
        text('[data-schedule-reason]',body.schedule_reason);const reason=host.querySelector('[data-schedule-reason]');if(reason)reason.dataset.code=body.schedule_status;
        host.querySelector('[data-recognize]').disabled=!needFace||busy;
        host.querySelector('[data-location-start]').disabled=!needGPS;host.querySelector('[data-location-server]').disabled=!needGPS;
      }catch(error){policyFresh=false;text('[data-schedule-reason]','Không đồng bộ được chính sách/ca làm: '+ui.message(error.message));throw error;}
      finally{ready();}
    }
    const clock=()=>text('[data-live-time]',new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(new Date()));
    clock();let ticker=setInterval(()=>{clock();ready();},1000);
    const faceState=(label,state='pending')=>{text('[data-face-state]',label);host.querySelector('[data-face-hud]')?.setAttribute('data-state',state);host.querySelector('[data-guide]')?.classList.toggle('detected',state==='success');};
    const guidance=message=>{const value=ui.message(message).toLocaleLowerCase('vi');text('.face-guide-caption',value.includes('quá nhỏ')?'Tiến gần camera một chút':value.includes('mờ')?'Ảnh hơi mờ':value.includes('ánh sáng')?'Ánh sáng chưa đủ':value.includes('hướng mặt')||value.includes('quay đầu')?'Giữ khuôn mặt thẳng':value.includes('không phát hiện')?'Đưa khuôn mặt vào giữa':'Xem thông báo lỗi bên dưới');};
    const show=(body,error=false)=>{
      result.hidden=false;result.classList.toggle('error',error);result.replaceChildren();
      const title=document.createElement('h3');title.textContent=error?'XÁC THỰC CHƯA HOÀN TẤT':body.attendance_id?'CHẤM CÔNG THÀNH CÔNG':'NHẬN DIỆN THÀNH CÔNG';result.append(title);
      for(const [key,label] of Object.entries({employee:'Nhân viên',employee_code:'Mã nhân viên',position:'Chức vụ',similarity:'Độ tương đồng',threshold:'Ngưỡng nhận diện',threshold_type:'Loại ngưỡng',timestamp:'Thời gian',message:'Thông báo',error:'Lý do'}))if(body[key]!==undefined){const row=document.createElement('p');const value=key==='timestamp'?ui.timestamp(body[key]):key==='threshold_type'?ui.label(body[key]):['error','message'].includes(key)?ui.message(body[key]):body[key];row.textContent=label+': '+value;result.append(row);}
    };
    const updateFace=body=>{if(!body.success||typeof body.employee!=='string'||!body.employee_code||typeof body.similarity!=='number'||!Number.isFinite(body.similarity)||typeof body.threshold!=='number'||!Number.isFinite(body.threshold))throw new Error('Ph\u1ea3n h\u1ed3i nh\u1eadn di\u1ec7n thi\u1ebfu th\u00f4ng tin h\u1ee3p l\u1ec7. Ch\u01b0a x\u00e1c th\u1ef1c khu\u00f4n m\u1eb7t.');faceOK=true;faceTime=Date.now();faceState('ĐÃ NHẬN DIỆN','success');text('[data-face-identity]','Nhân viên: '+body.employee+' · '+body.employee_code);text('[data-face-score]','Độ tương đồng: '+Number(body.similarity).toFixed(3));text('[data-face-threshold]','Ngưỡng nhận diện: '+Number(body.threshold).toFixed(3));text('[data-face-threshold-type]','Loại ngưỡng: '+ui.label(body.threshold_type));};
    function ready(){
      if(!attendance)return;
      const fresh=point&&Date.now()-pointTime<20000;
      const reason=!policyFresh?'Ch\u01b0a \u0111\u1ed3ng b\u1ed9 ch\u00ednh s\u00e1ch':!config.configured?'Chưa cấu hình chính sách':!host.querySelector('[data-schedule]').value?'Chưa có ca đã duyệt':busy?'Đang xử lý':needGPS&&!fresh?'Đang chờ vị trí mới':needGPS&&!geoAllowed?'Ngoài phạm vi hoặc Độ chính xác GPS thấp':needFace&&(!faceOK||Date.now()-faceTime>30000)?'Chưa xác thực khuôn mặt':'Sẵn sàng chấm công';
      text('[data-ready]',reason);host.querySelectorAll('[data-punch]').forEach(button=>button.disabled=reason!=='Sẵn sàng chấm công');
    }
    function stop(){generation++;phase('idle');progress(0,5);const box=host.querySelector('[data-detection-box]');if(box)box.hidden=true;stream?.getTracks().forEach(track=>track.stop());stream=null;video.srcObject=null;if(watch!==null)navigator.geolocation.clearWatch(watch);watch=null;point=null;geoAllowed=false;faceOK=false;text('[data-camera-label]','CAMERA ĐÃ DỪNG');faceState('CHƯA PHÁT HIỆN');ready();}
    const camera=async()=>{
      if(!navigator.mediaDevices?.getUserMedia)throw new Error('Camera cần HTTPS hoặc localhost.');
      status.textContent='Đang mở camera...';
      const token=generation;
      if(!stream){try{const opened=await navigator.mediaDevices.getUserMedia({video:{width:640,height:480,facingMode:'user'},audio:false});if(token!==generation){opened.getTracks().forEach(track=>track.stop());throw new Error('Đã hủy mở camera.');}stream=opened;}catch(error){throw new Error(error.name==='NotAllowedError'?'Vui lòng cấp quyền camera cho trình duyệt.':error.name==='NotFoundError'?'Không tìm thấy camera.':ui.message(error.message));}}
      video.srcObject=stream;await video.play();fitCamera();text('[data-camera-label]','● CAMERA TRỰC TIẾP');await sleep(350);
    };
    const frame=()=>{
      if(!stream||video.readyState<2||!video.videoWidth||!video.videoHeight)throw new Error('Camera ch\u01b0a c\u00f3 frame h\u1ee3p l\u1ec7. Vui l\u00f2ng ch\u1edd r\u1ed3i th\u1eed l\u1ea1i.');
      const canvas=document.createElement('canvas'),scale=Math.min(1,640/Math.max(video.videoWidth,video.videoHeight));
      canvas.width=Math.round(video.videoWidth*scale);canvas.height=Math.round(video.videoHeight*scale);
      canvas.getContext('2d').drawImage(video,0,0,canvas.width,canvas.height);return canvas.toDataURL('image/jpeg',.85);
    };
    async function recognize(){
      phase('quality');progress(0,5);await camera();const token=generation;
      status.textContent='Đang kiểm tra vị trí khuôn mặt, ánh sáng và độ nét...';faceState('ĐANG KIỂM TRA FRAME');
      const checked=await post(attendance?'/work/faceid/quality/':'/management/ai/faces/quality/',{frame:frame()});
      if(token!==generation)throw new Error('Đã hủy xác thực.');
      if(checked.accepted!==true)throw new Error('Chất lượng frame chưa được máy chủ chấp nhận.');
      qualityFeedback(checked.quality);faceState('ĐÃ PHÁT HIỆN · CHƯA XÁC THỰC');
      const challenge=await post(host.dataset.challengeUrl,{});
      if(token!==generation)throw new Error('Đã hủy xác thực.');
      text('.face-instruction',challenge.instruction);
      const batch=[],count=challenge.require_liveness?25:5;progress(0,count);phase('capturing');
      for(let index=0;index<count;index++){
        if(token!==generation)throw new Error('Đã hủy thu mẫu.');
        batch.push(frame());progress(batch.length,count);status.textContent=`Đang thu mẫu ${batch.length}/${count}...`;await sleep(240);
      }
      if(token!==generation)throw new Error('Đã hủy xác thực.');
      phase('verifying');status.textContent='Đã thu đủ frame. Đang chờ máy chủ xác thực...';faceState('ĐANG XÁC THỰC');
      return {challenge:challenge.id,frames:batch};
    }
    // UI estimate only. The server independently recomputes Haversine on explicit
    // checks and attendance attempts; watch callbacks never post coordinates.
    const distance=(lat,lng)=>{const rad=x=>x*Math.PI/180,p1=rad(lat),p2=rad(config.latitude),a=Math.sin(rad(config.latitude-lat)/2)**2+Math.cos(p1)*Math.cos(p2)*Math.sin(rad(config.longitude-lng)/2)**2;return 6371008.8*2*Math.atan2(Math.sqrt(Math.min(1,a)),Math.sqrt(Math.max(0,1-a)));};
    function watchLocation(){
      if(!showGPS)return;
      if(attendance&&!config.configured){text('.geo-status','Chưa cấu hình chính sách và tọa độ nhà hàng.');return;}
      if(!navigator.geolocation){text('.geo-status','Không lấy được vị trí · Trình duyệt không hỗ trợ vị trí.');return;}
      if(watch!==null)return;
      text('.geo-status','Đang lấy vị trí...');host.querySelector('[data-geo-hud]')?.setAttribute('data-state','pending');
      watch=navigator.geolocation.watchPosition(position=>{
        point={latitude:position.coords.latitude,longitude:position.coords.longitude,accuracy:position.coords.accuracy};pointTime=Number(position.timestamp);
        if(!Number.isFinite(pointTime)||Date.now()-pointTime>=20000||Date.now()-pointTime < -5000){point=null;geoAllowed=false;host.querySelector('[data-geo-hud]')?.setAttribute('data-state','pending');text('.geo-status','GPS \u0111\u00e3 c\u0169; \u0111ang ch\u1edd v\u1ecb tr\u00ed m\u1edbi.');ready();return;}
        const valid=Date.now()-pointTime>=-5000&&Date.now()-pointTime<20000&&Object.values(point).every(Number.isFinite)&&Math.abs(point.latitude)<=90&&Math.abs(point.longitude)<=180&&point.accuracy>=0;
        if(valid)window.attendanceMap?.update(point);
        const meters=valid&&attendance?distance(point.latitude,point.longitude):NaN;
        geoAllowed=valid&&point.accuracy<=config.max_accuracy&&meters<=config.radius;
        text('[data-location-text]',`Vĩ độ: ${point.latitude.toFixed(6)} · Kinh độ: ${point.longitude.toFixed(6)}`);
        text('[data-geo-distance]',`Khoảng cách ước tính trên giao diện: ${meters.toFixed(1)} m`);text('[data-geo-accuracy]',`Độ chính xác GPS: ±${point.accuracy.toFixed(1)} m`);
        text('.geo-status',!valid?'Vị trí không hợp lệ':point.accuracy>config.max_accuracy?'Độ chính xác GPS chưa đạt · Tín hiệu GPS chưa đủ chính xác, vui lòng thử lại.':geoAllowed?'Trong phạm vi · Bạn đang ở trong phạm vi chấm công.':`Ngoài phạm vi · Cách điểm chấm công ${meters.toFixed(0)} m, vượt bán kính ${config.radius} m.`);
        host.querySelector('[data-geo-hud]')?.setAttribute('data-state',geoAllowed?'success':point.accuracy>config.max_accuracy?'pending':'error');ready();
        if(!attendance){text('.geo-status',valid?'Đã lấy vị trí · chỉ phục vụ hiển thị':'Vị trí không hợp lệ');host.querySelector('[data-geo-hud]')?.setAttribute('data-state',valid?'success':'error');}
      },error=>{geoAllowed=false;point=null;if(watch!==null)navigator.geolocation.clearWatch(watch);watch=null;text('.geo-status',error.code===1?'Không lấy được vị trí · Không thể lấy vị trí. Vui lòng cấp quyền vị trí cho trình duyệt.':'Không lấy được vị trí · Không lấy được vị trí, vui lòng thử lại.');host.querySelector('[data-geo-hud]')?.setAttribute('data-state','error');ready();},{enableHighAccuracy:true,maximumAge:0,timeout:20000});
    }
    host.querySelector('[data-location-start]')?.addEventListener('click',watchLocation);
    host.querySelector('[data-location-server]')?.addEventListener('click',async()=>{
      try{
        await syncStatus();
        if(!point||Date.now()-pointTime>=20000)throw new Error('Chờ vị trí GPS mới trước khi kiểm tra.');
        const checked=await post(host.dataset.locationUrl,{location:point});
        text('[data-server-distance]',`Khoảng cách hệ thống xác định: ${checked.calculated_distance.toFixed(1)} m · ${ui.timestamp(checked.checked_at)}`);
        text('.geo-status',checked.message);geoAllowed=checked.geo_status==='ALLOWED';ready();
      }catch(error){text('.geo-status',ui.message(error.message));}
    });
    host.querySelector('[data-stop]')?.addEventListener('click',()=>{stop();status.textContent='Đã dừng camera/vị trí và xóa mẫu tạm.';});
    host.querySelector('[data-recognize]')?.addEventListener('click',async event=>{
      if(busy)return;busy=true;faceOK=false;faceTime=0;event.target.disabled=true;
      text('[data-face-identity]','Nhân viên: —');text('[data-face-score]','Độ tương đồng: —');text('[data-face-threshold]','Ngưỡng nhận diện: —');text('[data-face-threshold-type]','Loại ngưỡng: —');ready();
      try{await syncStatus();if(showGPS)watchLocation();const batch=await recognize();const attempt=generation;const body=await post(attendance?host.dataset.selfUrl:host.dataset.verifyUrl,batch);if(attempt!==generation)throw new Error('Camera \u0111\u00e3 d\u1eebng; kh\u00f4ng d\u00f9ng k\u1ebft qu\u1ea3 c\u0169.');updateFace(body);phase('success');show(body);status.textContent='Nhận diện thành công.';}
      catch(error){faceOK=false;faceState('XÁC THỰC CHƯA HOÀN TẤT','error');guidance(error.message);show({...error.body,error:ui.message(error.message)},true);status.textContent=ui.message(error.message);}
      finally{busy=false;phase(faceOK?'success':'idle');event.target.disabled=attendance&&!needFace;ready();}
    });
    host.querySelectorAll('[data-punch]').forEach(button=>button.addEventListener('click',async()=>{
      if(busy||button.disabled)return;busy=true;ready();
      try{
        await syncStatus();
        if(needGPS&&(!point||Date.now()-pointTime>=20000))throw new Error('Vị trí đã cũ; chờ GPS mới.');
        if(needGPS){const checked=await post(host.dataset.locationUrl,{location:point});text('[data-server-distance]',`Khoảng cách hệ thống xác định: ${checked.calculated_distance.toFixed(1)} m`);if(checked.geo_status!=='ALLOWED')throw new Error(checked.message);}
        const batch=needFace?await recognize():{};
        if(needGPS&&(!point||Date.now()-pointTime>=20000))throw new Error('Vị trí đã cũ; chờ GPS mới.');
        const body=await post(host.dataset.verifyUrl,{...batch,location:needGPS?point:null,schedule:host.querySelector('[data-schedule]').value,action:button.dataset.punch});
        if(!Number.isInteger(body.attendance_id)||body.attendance_id<=0)throw new Error('Ph\u1ea3n h\u1ed3i ch\u1ea5m c\u00f4ng thi\u1ebfu m\u00e3 k\u1ebft qu\u1ea3; ki\u1ec3m tra l\u1ecbch s\u1eed tr\u01b0\u1edbc khi th\u1eed l\u1ea1i.');
        if(body.face)updateFace({success:true,...body.face});if(body.distance!==null)text('[data-server-distance]',`Khoảng cách hệ thống xác định: ${Number(body.distance).toFixed(1)} m`);
        show({...body,...body.face});status.textContent=body.message;faceOK=false;
      }catch(error){faceState('XÁC THỰC CHƯA HOÀN TẤT','error');guidance(error.message);show({...error.body,error:ui.message(error.message)},true);status.textContent=ui.message(error.message);faceOK=false;}
      finally{busy=false;phase('idle');ready();}
    }));
    host.querySelector('[data-schedule]')?.addEventListener('change',ready);
    if(attendance&&!needGPS){text('.geo-status','Không yêu cầu vị trí');host.querySelector('[data-location-start]').disabled=true;host.querySelector('[data-location-server]').disabled=true;}
    if(attendance&&!needFace){text('.face-instruction','Chỉ xác thực vị trí, không yêu cầu camera');host.querySelector('[data-recognize]').disabled=true;faceState('KHÔNG YÊU CẦU NHẬN DIỆN');host.querySelector('[data-guide]').hidden=true;host.querySelector('.face-guide-caption').hidden=true;}
    window.addEventListener('resize',()=>{if(stream)fitCamera();});
    window.addEventListener('pageshow',event=>{if(event.persisted){clearInterval(ticker);ticker=setInterval(()=>{clock();ready();},1000);syncStatus().catch(()=>{});}});
    window.addEventListener('focus',()=>{if(!busy)syncStatus().catch(()=>{});});
    if(attendance)syncStatus().catch(()=>{});
    window.addEventListener('pagehide',()=>{stop();clearInterval(ticker);});ready();
  });
})();
