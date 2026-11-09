/* Account lifecycle and CSRF-aware fetch wrapper. No credentials in localStorage. */
(() => {
  'use strict';
  let csrf = null;
  let mode = 'login';
  let authMode = 'demo';
  let publicDemo = false;
  const $ = selector => document.querySelector(selector);

  function openAuth() {
    $('#auth-backdrop').classList.remove('hidden');
    $('#auth-email').focus();
  }
  function closeAuth() { $('#auth-backdrop').classList.add('hidden'); $('#auth-error').textContent=''; }

  function setMode(next) {
    mode = next;
    const register = mode === 'register';
    $('#auth-title').textContent = register ? 'Create a private workspace' : 'Sign in to Floatwise';
    $('#auth-login-tab').classList.toggle('active', !register);
    $('#auth-register-tab').classList.toggle('active', register);
    $('#auth-submit').textContent = register ? 'Create secure workspace' : 'Sign in securely';
    $('#auth-password').autocomplete = register ? 'new-password' : 'current-password';
    $('#auth-error').textContent='';
  }

  async function refreshIdentity() {
    const response = await fetch('/api/auth/me');
    if (!response.ok) return;
    const identity = await response.json();
    csrf = identity.csrf_token;
    authMode = identity.mode;
    publicDemo = identity.read_only && !identity.login_enabled;
    document.body.classList.toggle('public-demo',publicDemo);
    $('#auth-register-tab').classList.toggle('hidden', !identity.signup_enabled);
    const signedIn = identity.authenticated;
    $('#auth-open').classList.toggle('hidden',signedIn || authMode==='off' || publicDemo);
    $('#auth-logout').classList.toggle('hidden',!signedIn);
    $('#auth-open').textContent = signedIn ? identity.email : 'Sign in';
    $('.mode-tag').textContent = signedIn ? 'PRIVATE WORKSPACE' : authMode === 'off' ? 'LOCAL DEV' : 'READ-ONLY DEMO';
    $('#settings-form').querySelectorAll('input,button').forEach(element=>{element.disabled=publicDemo;});
  }

  async function authenticatedFetch(path, options={}) {
    const headers=new Headers(options.headers||{});
    if (options.method && !['GET','HEAD','OPTIONS'].includes(options.method.toUpperCase()) && csrf) {
      headers.set('X-CSRF-Token',csrf);
    }
    const response = await fetch(path,{...options,headers});
    if(response.status===401 && !path.startsWith('/api/auth/') && !publicDemo)openAuth();
    return response;
  }

  async function submit(event) {
    event.preventDefault();
    $('#auth-error').textContent='';
    const body=JSON.stringify({email:$('#auth-email').value,password:$('#auth-password').value});
    try {
      const response=await fetch(`/api/auth/${mode==='register'?'register':'login'}`,
        {method:'POST',headers:{'Content-Type':'application/json'},body});
      if(!response.ok)throw new Error((await response.json()).detail||'Unable to sign in');
      $('#auth-password').value='';
      closeAuth();
      await refreshIdentity();
      window.dispatchEvent(new Event('floatwise:updated'));
    }catch(error){$('#auth-error').textContent=error.message;}
  }

  async function logout() {
    try{
      await authenticatedFetch('/api/auth/logout',{method:'POST'});
      csrf=null;
      await refreshIdentity();
      window.dispatchEvent(new Event('floatwise:updated'));
    }catch{ /* Session may already have expired: reload the public demo. */ window.location.reload(); }
  }

  window.FloatwiseAuth = {fetch:authenticatedFetch, prompt:openAuth};
  document.addEventListener('DOMContentLoaded',()=>{
    $('#auth-open').addEventListener('click',openAuth);
    $('#auth-logout').addEventListener('click',logout);
    $('#auth-close').addEventListener('click',closeAuth);
    $('#auth-backdrop').addEventListener('click',event=>{if(event.target.id==='auth-backdrop')closeAuth();});
    $('#auth-login-tab').addEventListener('click',()=>setMode('login'));
    $('#auth-register-tab').addEventListener('click',()=>setMode('register'));
    $('#auth-form').addEventListener('submit',submit);
    document.addEventListener('keydown',event=>{if(event.key==='Escape')closeAuth();});
    refreshIdentity();
  });
})();
