document.querySelectorAll('.search-form').forEach(form=>form.addEventListener('submit',()=>{
  form.querySelector('button').disabled=true;
  form.querySelector('.loading').hidden=false;
}));
const historyQuery=document.getElementById('history-query');
historyQuery?.addEventListener('input',()=>{
  const normalized=value=>value.normalize('NFD').replace(/[\u0300-\u036f]/g,'')
    .replace(/đ/g,'d').toLocaleLowerCase();
  const term=normalized(historyQuery.value.trim());
  let count=0;
  document.querySelectorAll('#history-list .history').forEach(item=>{
    item.hidden=!normalized(item.dataset.historyArea).includes(term);
    if(!item.hidden) count++;
  });
  document.getElementById('history-no-match').hidden=Boolean(count);
});
