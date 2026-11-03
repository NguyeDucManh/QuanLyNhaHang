(() => {
  'use strict';
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  document.querySelectorAll('[data-face-realtime]').forEach(host=>{
    const mode=host.dataset.faceRealtime, attendance=mode==='attendance';
    const configNode=document.getElementById('location-config');
    const config=configNode?JSON.parse(configNode.textContent):{};
    const needGPS=attendance&&config.mode!=='FACE_ONLY', showGPS=!attendance||needGPS, needFace=!attendance||config.mode!=='GPS_ONLY';
    const ui=window.FaceUI;
    const video=host.querySelector('video'), status=host.querySelector('.face-status'), result=host.querySelector('[data-face-result]');
    let stream=null,watch=null,point=null,pointTime=0,faceTime=0,faceOK=false,generation=0,busy=false,geoAllowed=false;
    const text=(selector,value)=>{const node=host.querySelector(selector);if(node)node.textContent=value;};
    const post=async(url,data)=>{
      const response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':host.querySelector('[name=csrfmiddlewaretoken]').value},body:JSON.stringify(data)});
      const body=await response.json().catch(()=>({error:response.status===403?'Không có quyền hoặc phiên đã hết hạn.':'Server chưa trả kết quả hợp lệ.'}));
      if(!response.ok)throw new Error(ui.message(body.error||'Yêu cầu bị từ chối.'));return body;
    };
    const clock=()=>text('[data-live-time]',new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(new Date()));
    clock();const ticker=setInterval(()=>{clock();ready();},1000);
    const faceState=(label,state='pending')=>{text('[data-face-state]',label);host.querySelector('[data-face-hud]')?.setAttribute('data-state',state);host.querySelector('[data-guide]')?.classList.toggle('detected',state==='success');};
    const guidance=message=>{const value=ui.message(message).toLocaleLowerCase('vi');text('.face-guide-caption',value.includes('quá nhỏ')?'Tiến gần camera một chút':value.includes('mờ')?'Ảnh hơi mờ':value.includes('ánh sáng')?'Ánh sáng chưa đủ':value.includes('hướng mặt')||value.includes('quay đầu')?'Giữ khuôn mặt thẳng':value.includes('không phát hiện')?'Đưa khuôn mặt vào giữa':'Không nhận diện được');};
    const show=(body,error=false)=>{
      result.hidden=false;result.classList.toggle('error',error);result.replaceChildren();
      const title=document.createElement('h3');title.textContent=error?'KHÔNG NHẬN DIỆN / CHẤM CÔNG ĐƯỢC':body.attendance_id?'CHẤM CÔNG THÀNH CÔNG':'NHẬN DIỆN THÀNH CÔNG';result.append(title);
      for(const [key,label] of Object.entries({employee:'Nhân viên',employee_code:'Mã nhân viên',position:'Chức vụ',similarity:'Độ tương đồng',threshold:'Ngưỡng nhận diện',threshold_type:'Loại ngưỡng',timestamp:'Thời gian',message:'Thông báo',error:'Lý do'}))if(body[key]!==undefined){const row=document.createElement('p');const value=key==='timestamp'?ui.timestamp(body[key]):key==='threshold_type'?ui.label(body[key]):['error','message'].includes(key)?ui.message(body[key]):body[key];row.textContent=label+': '+value;result.append(row);}
    };
    const updateFace=body=>{faceOK=true;faceTime=Date.now();faceState('ĐÃ NHẬN DIỆN','success');text('[data-face-identity]','Nhân viên: '+body.employee+' · '+body.employee_code);text('[data-face-score]','Độ tương đồng: '+Number(body.similarity).toFixed(3));text('[data-face-threshold]','Ngưỡng nhận diện: '+Number(body.threshold).toFixed(3));text('[data-face-threshold-type]','Loại ngưỡng: '+ui.label(body.threshold_type));};
    function ready(){
      if(!attendance)return;
      const fresh=point&&Date.now()-pointTime<20000;
      const reason=!config.configured?'Chưa cấu hình chính sách':!host.querySelector('[data-schedule]').value?'Chưa có ca đã duyệt':busy?'Đang xử lý':needGPS&&!fresh?'Đang chờ vị trí mới':needGPS&&!geoAllowed?'Ngoài phạm vi hoặc Độ chính xác GPS thấp':needFace&&(!faceOK||Date.now()-faceTime>30000)?'Chưa xác thực khuôn mặt':'Sẵn sàng chấm công';
      text('[data-ready]',reason);host.querySelectorAll('[data-punch]').forEach(button=>button.disabled=reason!=='Sẵn sàng chấm công');
    }
    function stop(){generation++;stream?.getTracks().forEach(track=>track.stop());stream=null;video.srcObject=null;if(watch!==null)navigator.geolocation.clearWatch(watch);watch=null;point=null;geoAllowed=false;faceOK=false;text('[data-camera-label]','CAMERA ĐÃ DỪNG');faceState('CHƯA PHÁT HIỆN');ready();}
    const camera=async()=>{
      if(!navigator.mediaDevices?.getUserMedia)throw new Error('Camera cần HTTPS hoặc localhost.');
      status.textContent='Đang mở camera...';
      const token=generation;
      if(!stream){try{const opened=await navigator.mediaDevices.getUserMedia({video:{width:640,height:480,facingMode:'user'},audio:false});if(token!==generation){opened.getTracks().forEach(track=>track.stop());throw new Error('Đã hủy mở camera.');}stream=opened;}catch(error){throw new Error(error.name==='NotAllowedError'?'Vui lòng cấp quyền camera cho trình duyệt.':error.name==='NotFoundError'?'Không tìm thấy camera.':ui.message(error.message));}}
      video.srcObject=stream;await video.play();text('[data-camera-label]','● CAMERA TRỰC TIẾP');await sleep(350);
    };
    const frame=()=>{if(!stream)throw new Error('Camera đã dừng.');const canvas=document.createElement('canvas');canvas.width=640;canvas.height=480;canvas.getContext('2d').drawImage(video,0,0,640,480);return canvas.toDataURL('image/jpeg',.85);};
    async function recognize(url){
      await camera();const token=generation;
      const challenge=await post(host.dataset.challengeUrl,{});
      text('.face-instruction',challenge.instruction);faceState('ĐANG XÁC THỰC');
      status.textContent='Đang tìm khuôn mặt / kiểm tra chất lượng...';
      const first=frame();const checked=await post('/work/faceid/quality/',{frame:first});
      if(token!==generation)throw new Error('Đã hủy xác thực.');
      faceState('ĐÃ PHÁT HIỆN KHUÔN MẶT','success');
      text('.face-guide-caption',checked.quality?.face_width>550||checked.quality?.face_height>410?'Lùi xa camera một chút':'Đã phát hiện khuôn mặt');
      if(challenge.require_liveness)await sleep(1800);
      const batch=[],count=challenge.require_liveness?25:5;
      for(let index=0;index<count;index++){
        if(token!==generation)throw new Error('Đã hủy thu mẫu.');
        status.textContent=`Đang thu mẫu ${index+1}/${count}...`;batch.push(frame());await sleep(240);
      }
      status.textContent='Đang xác thực...';faceState('ĐANG XÁC THỰC');
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
        point={latitude:position.coords.latitude,longitude:position.coords.longitude,accuracy:position.coords.accuracy};pointTime=Date.now();
        const valid=Object.values(point).every(Number.isFinite)&&Math.abs(point.latitude)<=90&&Math.abs(point.longitude)<=180&&point.accuracy>=0;
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
        if(!point||Date.now()-pointTime>=20000)throw new Error('Chờ vị trí GPS mới trước khi kiểm tra.');
        const checked=await post(host.dataset.locationUrl,{location:point});
        text('[data-server-distance]',`Khoảng cách hệ thống xác định: ${checked.calculated_distance.toFixed(1)} m · ${ui.timestamp(checked.checked_at)}`);
        text('.geo-status',checked.message);geoAllowed=checked.geo_status==='ALLOWED';ready();
      }catch(error){text('.geo-status',ui.message(error.message));}
    });
    host.querySelector('[data-stop]')?.addEventListener('click',()=>{stop();status.textContent='Đã dừng camera/vị trí và xóa mẫu tạm.';});
    host.querySelector('[data-recognize]')?.addEventListener('click',async event=>{
      if(busy)return;busy=true;event.target.disabled=true;ready();
      try{if(showGPS)watchLocation();const batch=await recognize();const body=await post(attendance?host.dataset.selfUrl:host.dataset.verifyUrl,batch);updateFace(body);show(body);status.textContent='Nhận diện thành công.';}
      catch(error){faceOK=false;faceState('KHÔNG NHẬN DIỆN ĐƯỢC','error');guidance(error.message);show({error:ui.message(error.message)},true);status.textContent=ui.message(error.message);}
      finally{busy=false;event.target.disabled=false;ready();}
    });
    host.querySelectorAll('[data-punch]').forEach(button=>button.addEventListener('click',async()=>{
      if(busy||button.disabled)return;busy=true;ready();
      try{
        if(needGPS&&(!point||Date.now()-pointTime>=20000))throw new Error('Vị trí đã cũ; chờ GPS mới.');
        if(needGPS){const checked=await post(host.dataset.locationUrl,{location:point});text('[data-server-distance]',`Khoảng cách hệ thống xác định: ${checked.calculated_distance.toFixed(1)} m`);if(checked.geo_status!=='ALLOWED')throw new Error(checked.message);}
        const batch=needFace?await recognize():{};
        if(needGPS&&(!point||Date.now()-pointTime>=20000))throw new Error('Vị trí đã cũ; chờ GPS mới.');
        const body=await post(host.dataset.verifyUrl,{...batch,location:needGPS?point:null,schedule:host.querySelector('[data-schedule]').value,action:button.dataset.punch});
        if(body.face)updateFace(body.face);if(body.distance!==null)text('[data-server-distance]',`Khoảng cách hệ thống xác định: ${Number(body.distance).toFixed(1)} m`);
        show({...body,...body.face});status.textContent=body.message;faceOK=false;
      }catch(error){show({error:ui.message(error.message)},true);status.textContent=ui.message(error.message);faceOK=false;}
      finally{busy=false;ready();}
    }));
    host.querySelector('[data-schedule]')?.addEventListener('change',ready);
    if(attendance&&!needGPS){text('.geo-status','Không yêu cầu vị trí');host.querySelector('[data-location-start]').disabled=true;host.querySelector('[data-location-server]').disabled=true;}
    if(attendance&&!needFace){text('.face-instruction','Chỉ xác thực vị trí, không yêu cầu camera');host.querySelector('[data-recognize]').disabled=true;faceState('KHÔNG YÊU CẦU NHẬN DIỆN');host.querySelector('[data-guide]').hidden=true;host.querySelector('.face-guide-caption').hidden=true;}
    window.addEventListener('pagehide',()=>{stop();clearInterval(ticker);});ready();
  });
})();
