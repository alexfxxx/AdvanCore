"use strict";
const form=document.getElementById('credentials'),state=document.getElementById('connection-status'),result=document.getElementById('credential-result'),saveButton=document.getElementById('save-credentials'),removeButton=document.getElementById('remove-credentials');
let busy=false,saved=false;
async function action(path,payload){
  const sessionResponse=await fetch('/api/session',{cache:'no-store'});
  if(!sessionResponse.ok)throw Error('Local session unavailable.');
  const session=await sessionResponse.json();
  const response=await fetch('/api/supplier-credentials/santa/'+path,{method:'POST',cache:'no-store',headers:{'Content-Type':'application/json','X-AdvanCore-Action-Token':session.action_token},body:JSON.stringify(payload)});
  const data=await response.json();
  if(!response.ok)throw Error(data.detail||'Secure storage request failed.');
  return data;
}
function showStatus(value){saved=value;state.textContent=saved?'Credentials saved in macOS Keychain · Supplier login not yet verified · Monthly download not enabled':'No Santa credentials saved. Monthly download is not enabled.';removeButton.disabled=busy||!saved;}
function lock(value){busy=value;saveButton.disabled=value;removeButton.disabled=value||!saved;}
action('status',{}).then(d=>showStatus(d.saved)).catch(e=>{state.textContent=e.message;});
form.addEventListener('submit',async event=>{
  event.preventDefault();if(busy||!form.reportValidity())return;
  if(!window.confirm(saved?'Replace the saved Santa credentials in this Mac’s Keychain?':'Save these Santa credentials in this Mac’s Keychain?'))return;
  lock(true);result.textContent='Saving to Keychain…';
  try{const request=action('save',{username:form.elements.username.value,password:form.elements.password.value,confirmed:true});form.reset();const data=await request;showStatus(data.saved);result.textContent='Saved securely. This does not yet connect or schedule supplier downloads.';}
  catch(e){result.textContent=e.message+' Re-enter credentials to retry.';}
  finally{form.reset();lock(false);}
});
removeButton.addEventListener('click',async()=>{if(busy||!window.confirm('Remove only the Santa credentials saved by AdvanCore? This will not delete your supplier account or imported data.'))return;lock(true);try{const data=await action('remove',{confirmed:true});showStatus(data.saved);form.reset();result.textContent='Saved credentials removed from Keychain.';}catch(e){result.textContent=e.message;}finally{lock(false);}});
window.addEventListener('pagehide',()=>form.reset());
