
const imgs = ["https://picsum.photos/seed/reel-mood-studio-hero-0/960/540", "https://loremflickr.com/960/540/video%2CReel%2Ctechnology%2Cneon?lock=3", "https://picsum.photos/seed/reel-mood-studio-gallery-1-1/960/540", "https://loremflickr.com/960/540/video%2CReel%2Ctechnology%2Cneon?lock=4", "https://picsum.photos/seed/reel-mood-studio-gallery-2-2/960/540", "https://loremflickr.com/960/540/video%2CReel%2Ctechnology%2Cneon?lock=5", "https://picsum.photos/seed/reel-mood-studio-gallery-3-3/960/540", "https://loremflickr.com/960/540/video%2CReel%2Ctechnology%2Cneon?lock=6"];
const caps = ["slideshow video reel from research images", "Reel Mood Studio \u2014 scene 1", "Reel Mood Studio \u2014 scene 2", "Reel Mood Studio \u2014 scene 3", "Reel Mood Studio \u2014 scene 4"];
let i = 0, playing = true, ms = 2200, timer = null;
const frame = document.getElementById("frame");
const cap = document.getElementById("cap");
function show(){
  frame.src = imgs[i % imgs.length];
  cap.textContent = caps[i % caps.length] || ("Scene " + ((i%imgs.length)+1));
}
function tick(){ if(!playing) return; i = (i+1) % imgs.length; show(); }
function arm(){ clearInterval(timer); timer = setInterval(tick, ms); }
show(); arm();
document.getElementById("play").onclick=()=>{ playing=true; arm(); };
document.getElementById("pause").onclick=()=>{ playing=false; clearInterval(timer); };
document.getElementById("prev").onclick=()=>{ i=(i+imgs.length-1)%imgs.length; show(); };
document.getElementById("next").onclick=()=>{ i=(i+1)%imgs.length; show(); };
document.getElementById("slower").onclick=()=>{ ms=Math.min(5000, ms+400); arm(); };
document.getElementById("faster").onclick=()=>{ ms=Math.max(600, ms-400); arm(); };
document.getElementById("export").onclick=()=>{
  const a=document.createElement("a"); a.href=frame.src; a.download="reel-mood-studio-frame.png"; a.click();
};
