(() => {
  'use strict';
  const node=document.getElementById('location-config'),host=document.querySelector('[data-location-map]');
  if(!node||!host||!window.L)return;
  let config=JSON.parse(node.textContent),current=null,marker=null,circle=null,employeeMarker=null,accuracyCircle=null,follow=true;
  const latInput=document.getElementById('id_latitude'),lngInput=document.getElementById('id_longitude'),radiusInput=document.getElementById('id_attendance_radius_m');
  const valid=(lat,lng)=>lat!==null&&lng!==null&&lat!==''&&lng!==''&&Number.isFinite(Number(lat))&&Number.isFinite(Number(lng))&&Math.abs(Number(lat))<=90&&Math.abs(Number(lng))<=180;
  const map=L.map(host).setView(valid(config.latitude,config.longitude)?[config.latitude,config.longitude]:[0,0],valid(config.latitude,config.longitude)?15:2);
  map.attributionControl.addAttribution('<a href="https://openfreemap.org/">OpenFreeMap</a> © <a href="https://openmaptiles.org/">OpenMapTiles</a> · Data © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors');
  // OpenFreeMap is an independent, keyless service. No proxy or OSM block bypass.
  let tiles=null,tileFailure=false,mapLoaded=false,notice=null;
  host.dataset.basemapState='pending';
  function fallback(){
    if(tileFailure)return;tileFailure=true;host.dataset.basemapState='error';
    notice=document.createElement('p');notice.className='map-unavailable';notice.setAttribute('role','status');notice.textContent='Không tải đầy đủ nền OpenFreeMap. Kiểm tra kết nối, CSP hoặc WebGL trong trình duyệt. Tọa độ, marker GPS và xác thực máy chủ vẫn hoạt động. Không tự dùng vị trí mặc định hoặc đổi sang dịch vụ trả phí.';host.after(notice);host.classList.add('map-fallback');
  }
  try{
    if(!window.maplibregl||!L.maplibreGL||!host.dataset.mapWorker)throw new Error('Basemap renderer unavailable');
    maplibregl.setWorkerUrl(host.dataset.mapWorker);
    maplibregl.setWorkerCount(1);
    tiles=L.maplibreGL({style:'https://tiles.openfreemap.org/styles/liberty',interactive:false,attributionControl:false,
      attribution:'<a href="https://openfreemap.org/">OpenFreeMap</a> © <a href="https://openmaptiles.org/">OpenMapTiles</a> · Data © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(map);
    const renderer=tiles.getMaplibreMap();
    renderer.on('error',fallback);
    renderer.once('idle',()=>{mapLoaded=true;host.dataset.basemapState='ready';notice?.remove();host.classList.remove('map-fallback');tileFailure=false;});
  }catch(error){fallback();}
  setTimeout(()=>{if(!mapLoaded)fallback();},15000);
  const icon=L.icon({iconUrl:host.dataset.markerIcon,iconRetinaUrl:host.dataset.markerRetina,shadowUrl:host.dataset.markerShadow,iconSize:[25,41],iconAnchor:[12,41],popupAnchor:[1,-34],shadowSize:[41,41]});
  function restaurant(lat,lng,radius){
    if(!valid(lat,lng))return;
    const coords=[Number(lat),Number(lng)];
    if(marker)marker.setLatLng(coords);
    else {marker=L.marker(coords,{draggable:host.dataset.editable==='true',icon}).addTo(map).bindPopup('Điểm chấm công nhà hàng');
      marker.on('dragend',()=>{const point=marker.getLatLng();if(latInput)latInput.value=point.lat.toFixed(6);if(lngInput)lngInput.value=point.lng.toFixed(6);circle?.setLatLng(point);});}
    if(circle)circle.setLatLng(coords).setRadius(Number(radius)||150);
    else circle=L.circle(coords,{radius:Number(radius)||150,color:'#1d5a4b',fillOpacity:.1}).addTo(map);
  }
  restaurant(latInput?.value??config.latitude,lngInput?.value??config.longitude,radiusInput?.value??config.radius);
  function both(){follow=false;if(current&&marker)map.fitBounds(L.latLngBounds([marker.getLatLng(),[current.latitude,current.longitude]]).pad(.25),{maxZoom:17});}
  window.attendanceMap={
    update(point){
      if(!valid(point.latitude,point.longitude))return;
      const first=!current;current=point;const coords=[point.latitude,point.longitude];
      if(employeeMarker)employeeMarker.setLatLng(coords);else employeeMarker=L.circleMarker(coords,{radius:8,color:'#286783',fillOpacity:1}).addTo(map).bindPopup('Vị trí hiện tại của bạn (GPS)');
      if(accuracyCircle)accuracyCircle.setLatLng(coords).setRadius(point.accuracy);else accuracyCircle=L.circle(coords,{radius:point.accuracy,color:'#286783',fillOpacity:.05}).addTo(map);
      if(first)map.setView(coords,16);
      else if(follow)map.panTo(coords,{animate:false});
    },
    clear(){current=null;if(employeeMarker)map.removeLayer(employeeMarker);if(accuracyCircle)map.removeLayer(accuracyCircle);employeeMarker=null;accuracyCircle=null;},
    configure(value){config=value;if(valid(value.latitude,value.longitude))restaurant(value.latitude,value.longitude,value.radius);else{if(marker)map.removeLayer(marker);if(circle)map.removeLayer(circle);marker=null;circle=null;}}
  };
  document.querySelector('[data-map-self]')?.addEventListener('click',()=>{follow=true;if(current)map.setView([current.latitude,current.longitude],16);});
  document.querySelector('[data-map-both]')?.addEventListener('click',both);
  document.querySelector('[data-map-restaurant]')?.addEventListener('click',()=>{follow=false;if(marker)map.setView(marker.getLatLng(),16);});
  document.querySelector('[data-location-edit]')?.addEventListener('click',()=>{
    const fields=document.querySelector('[data-location-fields]');if(fields)fields.disabled=false;
    marker?.dragging?.enable();host.dataset.editable='true';
  });
  document.getElementById('location-settings-form')?.addEventListener('submit',event=>{
    if(!window.confirm('Xác nhận lưu vị trí cố định nhà hàng và chính sách chấm công?'))event.preventDefault();
  });
  function sync(){restaurant(latInput?.value,lngInput?.value,radiusInput?.value);}
  [latInput,lngInput,radiusInput].forEach(input=>input?.addEventListener('change',sync));
  setTimeout(()=>map.invalidateSize(),250);
})();
