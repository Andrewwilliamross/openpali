const group=document.querySelector('.specimens');
for(const button of document.querySelectorAll('[data-state]')) button.addEventListener('click',()=>{group.dataset.preview=button.dataset.state;for(const peer of document.querySelectorAll('[data-state]'))peer.setAttribute('aria-pressed',String(peer===button));});
