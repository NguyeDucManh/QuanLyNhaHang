(() => {
  'use strict';
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  document.querySelectorAll('[data-face-realtime]').forEach(host=>{
    const mode=host.dataset.faceRealtime, attendance=mode==='attendance';
    const configNode=document.getElementById('attendance-config');
    const config=configNode?JSON.parse(configNode.textContent):{};
    const ui=window.FaceUI;
    const video=host.querySelector('video'), status=host.querySelector('.face-status'), result=host.querySelector('[data-face-result]');
    let stream=null,faceTime=0,faceOK=false,generation=0,busy=false;
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
        Object.assign(config,body.config);policyFresh=true;
        text('[data-policy-message]','Xác minh khuôn mặt và ca làm đã duyệt.');
        const select=host.querySelector('[data-schedule]'),selected=select.value;select.replaceChildren();
        for(const item of body.schedules){const option=document.createElement('option');option.value=item.id;option.textContent=item.label;select.append(option);}
        if(!body.schedules.length){const option=document.createElement('option');option.value='';option.textContent='Chưa có ca đã duyệt';select.append(option);}
        if([...select.options].some(o=>o.value===selected))select.value=selected;
        text('[data-schedule-reason]',body.schedule_reason);const reason=host.querySelector('[data-schedule-reason]');if(reason)reason.dataset.code=body.schedule_status;
        host.querySelector('[data-recognize]').disabled=busy||!body.schedules.length;
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
      const reason=!policyFresh?'Ch\u01b0a \u0111\u1ed3ng b\u1ed9 ch\u00ednh s\u00e1ch':!config.configured?'Chưa cấu hình chính sách':!host.querySelector('[data-schedule]').value?'Chưa có ca đã duyệt':busy?'Đang xử lý':(!faceOK||Date.now()-faceTime>30000)?'Chưa xác thực khuôn mặt':'Sẵn sàng chấm công';
      host.querySelector('[data-recognize]').disabled=busy||!policyFresh||!host.querySelector('[data-schedule]').value;
      text('[data-ready]',reason);host.querySelectorAll('[data-punch]').forEach(button=>button.disabled=reason!=='Sẵn sàng chấm công');
    }
    function stop(){generation++;phase('idle');progress(0,5);const box=host.querySelector('[data-detection-box]');if(box)box.hidden=true;stream?.getTracks().forEach(track=>track.stop());stream=null;video.srcObject=null;faceOK=false;text('[data-camera-label]','CAMERA ĐÃ DỪNG');faceState('CHƯA PHÁT HIỆN');ready();}
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
    host.querySelector('[data-stop]')?.addEventListener('click',()=>{stop();status.textContent='Đã dừng camera và xóa mẫu tạm.';});
    host.querySelector('[data-recognize]')?.addEventListener('click',async event=>{
      if(busy)return;busy=true;faceOK=false;faceTime=0;event.target.disabled=true;
      text('[data-face-identity]','Nhân viên: —');text('[data-face-score]','Độ tương đồng: —');text('[data-face-threshold]','Ngưỡng nhận diện: —');text('[data-face-threshold-type]','Loại ngưỡng: —');ready();
      try{await syncStatus();if(attendance&&!host.querySelector('[data-schedule]').value)throw new Error('Chưa có ca đã duyệt trong thời gian chấm công.');const batch=await recognize();const attempt=generation;const body=await post(attendance?host.dataset.selfUrl:host.dataset.verifyUrl,batch);if(attempt!==generation)throw new Error('Camera \u0111\u00e3 d\u1eebng; kh\u00f4ng d\u00f9ng k\u1ebft qu\u1ea3 c\u0169.');updateFace(body);phase('success');show(body);status.textContent='Nhận diện thành công.';}
      catch(error){faceOK=false;faceState('XÁC THỰC CHƯA HOÀN TẤT','error');guidance(error.message);show({...error.body,error:ui.message(error.message)},true);status.textContent=ui.message(error.message);}
      finally{busy=false;phase(faceOK?'success':'idle');event.target.disabled=false;ready();}
    });
    host.querySelectorAll('[data-punch]').forEach(button=>button.addEventListener('click',async()=>{
      if(busy||button.disabled)return;busy=true;ready();
      try{
        await syncStatus();
        if(!host.querySelector('[data-schedule]').value)throw new Error('Chưa có ca đã duyệt trong thời gian chấm công.');
        const batch=await recognize();
        const body=await post(host.dataset.verifyUrl,{...batch,schedule:host.querySelector('[data-schedule]').value,action:button.dataset.punch});
        if(!Number.isInteger(body.attendance_id)||body.attendance_id<=0)throw new Error('Ph\u1ea3n h\u1ed3i ch\u1ea5m c\u00f4ng thi\u1ebfu m\u00e3 k\u1ebft qu\u1ea3; ki\u1ec3m tra l\u1ecbch s\u1eed tr\u01b0\u1edbc khi th\u1eed l\u1ea1i.');
        if(!body.face)throw new Error('Máy chủ đã trả mã chấm công nhưng thiếu bằng chứng xác minh; kiểm tra lịch sử trước khi thử lại.');
        updateFace({success:true,...body.face});
        show({...body,...body.face});status.textContent=body.message;faceOK=false;
      }catch(error){faceState('XÁC THỰC CHƯA HOÀN TẤT','error');guidance(error.message);show({...error.body,error:ui.message(error.message)},true);status.textContent=ui.message(error.message);faceOK=false;}
      finally{busy=false;phase('idle');ready();}
    }));
    host.querySelector('[data-schedule]')?.addEventListener('change',ready);
    window.addEventListener('resize',()=>{if(stream)fitCamera();});
    window.addEventListener('pageshow',event=>{if(event.persisted){clearInterval(ticker);ticker=setInterval(()=>{clock();ready();},1000);syncStatus().catch(()=>{});}});
    window.addEventListener('focus',()=>{if(!busy)syncStatus().catch(()=>{});});
    if(attendance)syncStatus().catch(()=>{});
    window.addEventListener('pagehide',()=>{stop();clearInterval(ticker);});ready();
  });
})();
