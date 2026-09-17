const log = document.querySelector('.chat-log');
if (log) log.scrollTop = log.scrollHeight;

const form = document.getElementById('assistant-form');
if (form) {
  form.addEventListener('submit', () => {
    const button = document.getElementById('assistant-submit');
    button.disabled = true;
    button.textContent = 'Đang xử lý…';
  });
}
