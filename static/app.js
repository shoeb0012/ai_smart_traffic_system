let stream = null;
let countdown = 42;

let signalPhase = "GREEN";

let greenDuration = 30;
let yellowDuration = 5;
let redDuration = 40;

let chart;

const $ = id => document.getElementById(id);


function updateSignalUI() {

  $("currentSignal").textContent = signalPhase;
  $("remaining").textContent = countdown;

  const red = document.querySelector(".red-light");
  const yellow = document.querySelector(".yellow-light");
  const green = document.querySelector(".green-light");

  red.classList.toggle("active", signalPhase === "RED");
  yellow.classList.toggle("active", signalPhase === "YELLOW");
  green.classList.toggle("active", signalPhase === "GREEN");

  $("currentSignal").style.color =
    signalPhase === "RED" ? "var(--red)" :
    signalPhase === "YELLOW" ? "var(--amber)" :
    "var(--green)";
}


function advanceSignal() {

  if (signalPhase === "GREEN") {

    signalPhase = "YELLOW";
    countdown = yellowDuration;

  } else if (signalPhase === "YELLOW") {

    signalPhase = "RED";
    countdown = redDuration;

  } else {

    signalPhase = "GREEN";
    countdown = greenDuration;

  }

  updateSignalUI();
}


function tickClock() {

  const now = new Date();

  $("clock").textContent =
    now.toLocaleString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit"
    });

  if (countdown > 0) {
    countdown--;
  }

  if (countdown <= 0) {
    advanceSignal();
  } else {
    updateSignalUI();
  }
}


setInterval(tickClock, 1000);

updateSignalUI();

tickClock();

function animateValue(el, value){
  const old = Number(el.textContent) || 0;
  const diff = value-old, start = performance.now(), duration = 450;
  function step(t){
    const p=Math.min(1,(t-start)/duration);
    el.textContent=Math.round(old+diff*(1-Math.pow(1-p,3)));
    if(p<1) requestAnimationFrame(step);
  }
  el.classList.remove("pulse"); void el.offsetWidth; el.classList.add("pulse");
  requestAnimationFrame(step);
}

function setIncident(a){
  $("confidence").textContent = `${a.confidence || 0}%`;
  $("accidentLocation").textContent = a.location || "Road Junction A";
  $("accidentTime").textContent = a.time || "--:--";
  if(a.detected){
    $("accidentBadge").textContent="ALERT"; $("accidentBadge").className="badge";
    $("accidentBadge").style.color="var(--red)";
    $("accidentBadge").style.borderColor="#ff526355";
    $("accidentState").className="incident-state danger";
    $("accidentState").innerHTML="<span>⚠</span><div><strong>ACCIDENT DETECTED</strong><small>Possible incident — review CCTV</small></div>";
    $("alertStatus").textContent="SENT";
    ["ambulance","police","response"].forEach(id=>{$(id).textContent=id==="response"?"ACTIVE":"ALERTED";$(id).className="sent"});
  } else {
    $("accidentBadge").textContent="CLEAR"; $("accidentBadge").className="badge green"; $("accidentBadge").style="";
    $("accidentState").className="incident-state clear";
    $("accidentState").innerHTML="<span>✓</span><div><strong>No Accident Detected</strong><small>AI scene analysis active</small></div>";
    $("alertStatus").textContent="STANDBY";
    ["ambulance","police","response"].forEach(id=>{$(id).textContent="STANDBY";$(id).className=""});
  }
}

function apply(data){
  $("cityName").textContent=data.city; $("junction").textContent=data.accident?.location || "";
  $("engine").textContent=data.engine || "DEMO";
  for(const k of ["total","cars","buses","trucks","motorcycles"]) animateValue($(k), data.vehicles[k] || 0);
  $("density").textContent=`${data.density}%`;
  $("densityBar").style.width=`${data.density}%`;
  const level=data.traffic_level || "HIGH";
  $("trafficLevel").textContent=level; $("trafficLevel").className=`traffic-pill ${level.toLowerCase()}`;
  const degrees=Math.round(data.density*3.6);
  document.querySelector(".gauge").style.background=`conic-gradient(var(--cyan) 0deg,var(--cyan) ${degrees}deg,#152a33 ${degrees}deg)`;
  greenDuration = Number(data.signal.recommended_green) || 30;

redDuration = Number(data.signal.recommended_red) || 40;

$("recommendedGreen").textContent = greenDuration;

$("recommendedRed").textContent = redDuration;

if (signalPhase === "GREEN" && countdown > greenDuration) {
  countdown = greenDuration;
}

if (signalPhase === "RED" && countdown > redDuration) {
  countdown = redDuration;
}

updateSignalUI();

$("recommendation").textContent =
  level === "HIGH"
    ? "Increase Green Signal Time"
    : level === "MEDIUM"
    ? "Balance Green / Red Time"
    : "Maintain Normal Timing";
  setIncident(data.accident || {detected:false});
  $("csvLink").href=`/api/analytics.csv?city=${encodeURIComponent(data.city)}`;
}

async function refresh(){
  try{
    const city=$("city").value;
    const r=await fetch(`/api/status?city=${encodeURIComponent(city)}`);
    apply(await r.json());
  }catch(e){console.error(e)}
}
$("city").addEventListener("change",refresh);
refresh();

$("startCam").onclick=async()=>{
  try{
    stream=await navigator.mediaDevices.getUserMedia({video:true,audio:false});
    $("webcam").srcObject=stream;
    $("webcam").classList.add("active"); $("cameraPlaceholder").style.display="none";
    $("detectStatus").textContent="CAMERA ACTIVE"; $("detectStatus").className="badge green";
    $("fps").textContent="FPS LIVE";
  }catch(e){alert("Camera permission was not granted. You can still upload a video/image.");}
};
$("stopCam").onclick=()=>{
  if(stream) stream.getTracks().forEach(t=>t.stop());
  stream=null; $("webcam").classList.remove("active"); $("cameraPlaceholder").style.display="flex";
  $("detectStatus").textContent="READY"; $("fps").textContent="FPS --";
};

function uploadFile(file, endpoint){
  const form=new FormData(); form.append("file",file); form.append("city",$("city").value);
  $("uploadProgress").classList.remove("hidden"); $("progressBar").style.width="15%"; $("progressText").textContent="Uploading and running AI detection...";
  const xhr=new XMLHttpRequest(); xhr.open("POST",endpoint);
  xhr.upload.onprogress=e=>{if(e.lengthComputable) $("progressBar").style.width=(15+e.loaded/e.total*55)+"%";};
  xhr.onload=()=>{
    $("progressBar").style.width="100%";
    try{
      const data=JSON.parse(xhr.responseText);
      if(data.error) throw new Error(data.error);
      apply(data); $("engine").textContent=data.engine;
      if(data.image){$("processedImage").src=data.image;$("processedImage").classList.add("active");$("webcam").classList.remove("active");$("processedVideo").classList.remove("active");}
      if(data.video_url){$("processedVideo").src=data.video_url;$("processedVideo").classList.add("active");$("processedImage").classList.remove("active");$("webcam").classList.remove("active");$("processedVideo").play().catch(()=>{});$("fps").textContent=`FPS ${data.processed_fps}`;}
      $("detectStatus").textContent="AI ANALYSIS COMPLETE";
      $("progressText").textContent="Processing complete";
    }catch(e){alert(e.message);$("progressText").textContent="Processing failed";}
    setTimeout(()=>$("uploadProgress").classList.add("hidden"),1400);
  };
  xhr.onerror=()=>{alert("Upload failed");$("uploadProgress").classList.add("hidden")};
  xhr.send(form);
}
$("imageInput").onchange=e=>{if(e.target.files[0]) uploadFile(e.target.files[0],"/api/process-image")};
$("videoInput").onchange=e=>{if(e.target.files[0]) uploadFile(e.target.files[0],"/api/process-video")};

$("testAlert").onclick=()=>{
  const detected=!$("accidentState").classList.contains("danger");
  setIncident({detected,confidence:detected?94:0,location:$("junction").textContent,time:new Date().toLocaleTimeString(),alerts:detected});
};

const ctx=$("trafficChart").getContext("2d");
chart=new Chart(ctx,{type:"line",data:{labels:["10:00","10:05","10:10","10:15","10:20","10:25","10:30","10:35","10:40","10:45"],datasets:[{label:"Vehicles",data:[18,25,31,28,38,45,42,51,47,49],borderWidth:2,tension:.35,fill:true}]},options:{responsive:true,plugins:{legend:{display:false}},scales:{x:{grid:{color:"#17303a"},ticks:{color:"#6f8992"}},y:{grid:{color:"#17303a"},ticks:{color:"#6f8992"},beginAtZero:true}}}});
