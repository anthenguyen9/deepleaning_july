document.querySelectorAll('.search-form').forEach(form=>form.addEventListener('submit',()=>{
  form.querySelector('button').disabled=true;
  form.querySelector('.loading').hidden=false;
}));
