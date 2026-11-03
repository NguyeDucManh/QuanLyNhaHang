(() => {
  'use strict';
  const csrf = () => document.querySelector('[name=csrfmiddlewaretoken]')?.value;
  async function post(url, data) {
    const r = await fetch(url, {method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},body:JSON.stringify(data)});
    const value=await r.json(); if(!r.ok) throw new Error(value.error || 'Yêu cầu bị từ chối.'); return value;
  }
  const form=document.getElementById('ai-chat-form');
  if(form) {
    const log=document.getElementById('ai-messages'),input=document.getElementById('ai-message');
    const message=(role,text)=>{const p=document.createElement('p');p.textContent=role+': '+text;log.append(p);p.scrollIntoView({block:'nearest'});};
    form.addEventListener('submit',async e=>{e.preventDefault();const button=form.querySelector('button'),question=input.value;button.disabled=true;message('Bạn',question);input.value='';try{const result=await post(form.action,{message:question});message('AI',result.answer);if(result.sources?.length){const p=document.createElement('small');p.textContent='Nguồn: '+result.sources.map(s=>s.title||s.source_type+' #'+s.source_id).join(', ');log.append(p);}}catch(error){message('AI',error.message);}finally{button.disabled=false;input.focus();}});
  }
  let stream=null,upload=null;
  const video=document.getElementById('face-video'),progress=document.getElementById('face-progress');
  async function camera(){if(!navigator.mediaDevices)throw new Error('Camera cần localhost hoặc HTTPS.');if(!stream)stream=await navigator.mediaDevices.getUserMedia({video:{width:640,height:480},audio:false});video.srcObject=stream;await video.play();}
  function stop(){if(stream)stream.getTracks().forEach(t=>t.stop());stream=null;}
  document.getElementById('face-stop')?.addEventListener('click',stop);window.addEventListener('pagehide',stop);
  const sleep=ms=>new Promise(r=>setTimeout(r,ms));
  async function capture(count, interval) {
    const canvas=document.createElement('canvas');canvas.width=640;canvas.height=480;const context=canvas.getContext('2d'),frames=[];
    for(let i=0;i<count;i++){if(!stream)throw new Error('Camera đã dừng.');context.drawImage(video,0,0,640,480);frames.push(canvas.toDataURL('image/jpeg',.85));progress.textContent=`${i+1}/${count}`;await sleep(interval);}
    return frames;
  }
  document.querySelectorAll('[data-enroll-url]').forEach(button=>button.addEventListener('click',async()=>{upload=button.dataset.enrollUrl;document.getElementById('face-camera').hidden=false;document.getElementById('face-title').textContent='Đăng ký: '+button.dataset.employee;try{await camera();}catch(error){progress.textContent=error.message;}}));
  document.getElementById('face-capture')?.addEventListener('click',async e=>{e.target.disabled=true;try{const frames=[],qualityUrl=document.getElementById('face-camera').dataset.quality;for(let attempt=0;attempt<60&&frames.length<15;attempt++){const [frame]=await capture(1,250);try{await post(qualityUrl,{frame});frames.push(frame);progress.textContent=`${frames.length}/15 frame đạt chất lượng`;}catch(error){progress.textContent=`${frames.length}/15 · ${error.message}`;}}if(frames.length<15)throw new Error('Chưa đủ frame đạt chất lượng; điều chỉnh ánh sáng và thử lại.');const result=await post(upload,{frames});progress.textContent=result.message;}catch(error){progress.textContent=error.message;}finally{e.target.disabled=false;stop();}});
  document.getElementById('face-verify')?.addEventListener('click',async e=>{e.target.disabled=true;const attendance=document.getElementById('face-attendance');try{await camera();const challenge=await post(attendance.dataset.challenge,{});progress.textContent=challenge.instruction;await sleep(2500);const frames=await capture(25,240);const result=await post(attendance.dataset.verify,{challenge:challenge.id,frames,schedule:document.getElementById('face-schedule').value,action:document.getElementById('face-action').value});progress.textContent=result.message;}catch(error){progress.textContent=error.message;}finally{e.target.disabled=false;stop();}});
  const canvas=document.getElementById('forecast-chart'),data=document.getElementById('forecast-test-data');
  if(canvas&&data){const series=Object.values(JSON.parse(data.textContent))[0]||[],ctx=canvas.getContext('2d');if(series.length){const maximum=Math.max(1,...series.flatMap(r=>[r.actual,r.predicted]));ctx.fillStyle='#243447';ctx.font='14px sans-serif';ctx.fillText(new Intl.NumberFormat('vi-VN').format(maximum),10,20);ctx.fillText(series[0].date,50,305);ctx.fillText(series.at(-1).date,770,305);for(const [field,color] of [['actual','#2475ff'],['predicted','#ff6b0b']]){ctx.strokeStyle=color;ctx.lineWidth=2;ctx.beginPath();series.forEach((r,i)=>{const x=70+i*790/Math.max(1,series.length-1),y=280-r[field]/maximum*250;i?ctx.lineTo(x,y):ctx.moveTo(x,y);});ctx.stroke();}}}
})();
