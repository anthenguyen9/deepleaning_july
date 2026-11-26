const form = document.getElementById('location-form');
if (form) {
  const country = document.getElementById('country');
  const province = document.getElementById('province');
  const ward = document.getElementById('ward');
  const street = document.getElementById('street');
  const selected = document.getElementById('location-id');
  const widgets = new Map();
  const requests = new Map();

  const fold = (value) => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd').replace(/Đ/g, 'D').toLowerCase();

  const enhance = (select, searchLabel) => {
    const container = document.createElement('div');
    container.className = 'location-picker';
    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'location-picker-trigger';
    trigger.setAttribute('aria-haspopup', 'listbox');
    trigger.setAttribute('aria-expanded', 'false');
    const value = document.createElement('span');
    const arrow = document.createElement('span');
    arrow.setAttribute('aria-hidden', 'true');
    arrow.textContent = '⌄';
    trigger.append(value, arrow);
    const panel = document.createElement('div');
    panel.className = 'location-picker-panel';
    panel.hidden = true;
    const search = document.createElement('input');
    search.type = 'search';
    search.placeholder = 'Tìm theo tên…';
    search.setAttribute('aria-label', searchLabel);
    search.autocomplete = 'off';
    const list = document.createElement('div');
    list.className = 'location-picker-list';
    list.id = `${select.id}-choices`;
    list.setAttribute('role', 'listbox');
    trigger.setAttribute('aria-controls', list.id);
    const hint = document.createElement('p');
    hint.className = 'location-picker-hint';
    panel.append(search, list, hint);
    container.append(trigger, panel);
    select.after(container);
    select.hidden = true;

    const close = () => {
      panel.hidden = true;
      panel.classList.remove('open-up');
      trigger.setAttribute('aria-expanded', 'false');
    };
    const render = () => {
      const options = Array.from(select.options);
      const query = fold(search.value.trim());
      const matches = options.filter((option) => !query || !option.value || fold(option.textContent).includes(query));
      list.replaceChildren();
      for (const option of matches.slice(0, 60)) {
        const item = document.createElement('button');
        item.type = 'button';
        item.className = 'location-picker-option';
        item.setAttribute('role', 'option');
        item.setAttribute('aria-selected', String(option.value === select.value));
        item.textContent = option.textContent;
        item.title = option.textContent;
        item.addEventListener('click', () => {
          select.value = option.value;
          select.dispatchEvent(new Event('change', { bubbles: true }));
          value.textContent = option.textContent;
          close();
          trigger.focus();
        });
        list.append(item);
      }
      if (!matches.length) {
        const empty = document.createElement('p');
        empty.className = 'location-picker-empty';
        empty.textContent = 'Không tìm thấy địa điểm phù hợp.';
        list.append(empty);
      }
      hint.textContent = matches.length > 60 ? `Hiển thị 60 / ${matches.length} địa điểm. Nhập thêm để lọc.` : '';
      value.textContent = select.selectedOptions[0]?.textContent || 'Có thể bỏ qua';
      trigger.setAttribute('aria-label', `${select.labels[0]?.textContent.trim() || searchLabel}: ${value.textContent}`);
    };
    trigger.addEventListener('click', () => {
      const opening = panel.hidden;
      for (const widget of widgets.values()) widget.close();
      if (opening) {
        search.value = '';
        render();
        panel.hidden = false;
        trigger.setAttribute('aria-expanded', 'true');
        panel.classList.toggle('open-up', window.innerHeight - trigger.getBoundingClientRect().bottom < panel.getBoundingClientRect().height + 8 && trigger.getBoundingClientRect().top > panel.getBoundingClientRect().height);
        search.focus();
      }
    });
    search.addEventListener('input', render);
    search.addEventListener('keydown', (event) => {
      if (event.key === 'ArrowDown') { event.preventDefault(); list.querySelector('button')?.focus(); }
      if (event.key === 'Enter') { event.preventDefault(); list.querySelector('button:not([aria-selected=true])')?.click(); }
      if (event.key === 'Escape') { close(); trigger.focus(); }
    });
    panel.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') { close(); trigger.focus(); }
    });
    document.addEventListener('click', (event) => { if (!container.contains(event.target)) close(); });
    select.addEventListener('change', render);
    widgets.set(select, { close, render });
    render();
  };

  enhance(ward, 'Tìm phường, xã hoặc đặc khu');
  enhance(street, 'Tìm đường');
  const refresh = (select) => widgets.get(select)?.render();
  const reset = (select, label) => { select.replaceChildren(new Option(label, '')); refresh(select); };
  const load = async (parent, select, label, filter) => {
    const request = (requests.get(select) || 0) + 1;
    requests.set(select, request);
    reset(select, label);
    if (!parent) return;
    try {
      const response = await fetch(`${form.dataset.api}?parent=${encodeURIComponent(parent)}`);
      if (!response.ok) throw new Error('Không tải được địa điểm.');
      const items = await response.json();
      if (requests.get(select) !== request) return;
      for (const item of items) {
        if (!filter || item.level === filter) select.add(new Option(item.name, item.id));
      }
      refresh(select);
    } catch (error) { if (requests.get(select) === request) alert(error.message); }
  };
  country.addEventListener('change', async () => {
    selected.value = country.value;
    requests.set(ward, (requests.get(ward) || 0) + 1);
    requests.set(street, (requests.get(street) || 0) + 1);
    reset(ward, 'Có thể bỏ qua'); reset(street, 'Có thể bỏ qua');
    await load(country.value, province, 'Chọn tỉnh / thành phố', 'province');
  });
  province.addEventListener('change', async () => {
    selected.value = province.value;
    await Promise.all([load(province.value, ward, 'Có thể bỏ qua', 'ward'),
      load(province.value, street, 'Có thể bỏ qua', 'street')]);
  });
  ward.addEventListener('change', () => {
    if (ward.value) street.value = '';
    selected.value = ward.value || province.value;
    refresh(street);
  });
  street.addEventListener('change', () => {
    if (street.value) ward.value = '';
    selected.value = street.value || province.value;
    refresh(ward);
  });
}
