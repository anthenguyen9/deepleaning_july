(() => {
  const drawer = document.getElementById('mobile-drawer');
  const backdrop = document.getElementById('drawer-backdrop');
  const openButton = document.getElementById('menu-open');
  const closeButton = document.getElementById('menu-close');
  if (!drawer || !backdrop || !openButton || !closeButton) return;
  let priorFocus = null;
  const close = () => {
    drawer.hidden = true;
    backdrop.hidden = true;
    openButton.setAttribute('aria-expanded', 'false');
    (priorFocus || openButton).focus();
  };
  openButton.addEventListener('click', () => {
    priorFocus = document.activeElement;
    drawer.hidden = false;
    backdrop.hidden = false;
    openButton.setAttribute('aria-expanded', 'true');
    closeButton.focus();
  });
  closeButton.addEventListener('click', close);
  backdrop.addEventListener('click', close);
  drawer.addEventListener('keydown', event => {
    if (event.key === 'Escape') { event.preventDefault(); close(); }
    if (event.key !== 'Tab') return;
    const controls = [...drawer.querySelectorAll('a,button')].filter(item => item.offsetParent !== null);
    const first = controls[0], last = controls[controls.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });
  drawer.querySelectorAll('a').forEach(link => link.addEventListener('click', () => {
    drawer.hidden = backdrop.hidden = true;
    openButton.setAttribute('aria-expanded', 'false');
  }));
  document.getElementById('mobile-favorites-nav')?.addEventListener('click', close);
})();
