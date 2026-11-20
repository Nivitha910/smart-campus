const menuToggle=document.getElementById("menuToggle");
const sidebar=document.querySelector(".sidebar");
if(menuToggle&&sidebar){menuToggle.addEventListener("click",()=>sidebar.classList.toggle("open"))}

const complaintCanvas=document.getElementById("complaintChart");
if(complaintCanvas){
  new Chart(complaintCanvas,{type:"doughnut",data:{labels:["Pending","In Progress","Resolved","Rejected"],datasets:[{data:[complaintCanvas.dataset.pending,complaintCanvas.dataset.progress,complaintCanvas.dataset.resolved,complaintCanvas.dataset.rejected],backgroundColor:["#f97316","#6366f1","#22c55e","#ef4444"],borderWidth:0}]},options:{responsive:true,cutout:"68%",plugins:{legend:{position:"bottom"}}}});
}
const categoryCanvas=document.getElementById("categoryChart");
if(categoryCanvas){
  new Chart(categoryCanvas,{type:"bar",data:{labels:JSON.parse(categoryCanvas.dataset.labels),datasets:[{label:"Complaints",data:JSON.parse(categoryCanvas.dataset.values),backgroundColor:"#4f46e5",borderRadius:6}]},options:{responsive:true,plugins:{legend:{display:false}},scales:{y:{beginAtZero:true,ticks:{precision:0}}}}});
}
