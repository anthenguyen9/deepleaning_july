const form = document.getElementById('location-form');
if (form) {
  const country = document.getElementById('country');
  const province = document.getElementById('province');
  const ward = document.getElementById('ward');
  const street = document.getElementById('street');
  const selected = document.getElementById('location-id');
  const reset = (select, label) => { select.replaceChildren(new Option(label, '')); };
  const load = async (parent, select, label, filter) => {
    reset(select, label);
    if (!parent) return;
    try {
      const response = await fetch(`${form.dataset.api}?parent=${encodeURIComponent(parent)}`);
      if (!response.ok) throw new Error('Không tải được địa điểm.');
      for (const item of await response.json()) {
        if (!filter || item.level === filter) select.add(new Option(item.name, item.id));
      }
    } catch (error) { alert(error.message); }
  };
  country.addEventListener('change', async () => {
    selected.value = country.value;
    reset(ward, 'Có thể bỏ qua'); reset(street, 'Có thể bỏ qua');
    await load(country.value, province, 'Chọn tỉnh / thành phố', 'province');
  });
  province.addEventListener('change', async () => {
    selected.value = province.value;
    await Promise.all([load(province.value, ward, 'Có thể bỏ qua', 'ward'),
      load(province.value, street, 'Có thể bỏ qua', 'street')]);
  });
  ward.addEventListener('change', () => { if (ward.value) street.value = ''; selected.value = ward.value || province.value; });
  street.addEventListener('change', () => { if (street.value) ward.value = ''; selected.value = street.value || province.value; });
}
