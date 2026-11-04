/* Shared helpers (design system v1): escaping, JSON calls with sign-in redirect, text size, toast. */
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pref=k=>{try{return localStorage.getItem(k)}catch(e){return null}},setPref=(k,v)=>{try{localStorage.setItem(k,v)}catch(e){}};
async function api(url,body,{signinUrl}={}){
 const r=await fetch(url,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 let j=null;try{j=await r.json()}catch(e){}
 if(r.status===401&&signinUrl&&!url.includes('/login')){location.replace(signinUrl);throw new Error('signed out')}
 if(!r.ok){const d=j&&j.detail;const m=typeof d==='string'?d:Array.isArray(d)?'입력한 내용을 다시 확인해 주세요.':'문제가 생겼어요. 잠시 뒤에 다시 해 주세요.';const e=new Error(m);e.status=r.status;throw e}
 return j}
function toast(msg){const t=document.createElement('div');t.className='toast';t.setAttribute('role','status');t.textContent=msg;document.body.appendChild(t);setTimeout(()=>t.remove(),3200)}
function applyTextSize(){const v=+pref('coach_fs')||17;document.documentElement.style.setProperty('--fs',v+'px');return v}
