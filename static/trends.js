(() => {
  const chartScroll = document.querySelector('.trend-chart-scroll');
  if (chartScroll) chartScroll.scrollLeft = chartScroll.scrollWidth;
  const query = document.getElementById('trend-area-query');
  query?.addEventListener('input', () => {
    const term = query.value.trim().normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase();
    let shown = 0;
    document.querySelectorAll('.trend-area-row').forEach(row => {
      const name = row.dataset.areaName.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase();
      row.hidden = !name.includes(term);
      if (!row.hidden) shown++;
    });
    document.getElementById('trend-area-no-match').hidden = Boolean(shown);
  });
  const host = document.getElementById('trend-map');
  const data = document.getElementById('trend-map-data');
  if (!host || !data || !window.L) return;
  const points = JSON.parse(data.textContent).filter(item =>
    Number.isFinite(item.location?.lat) && Number.isFinite(item.location?.lng));
  if (!points.length) return;
  const map = L.map(host, {scrollWheelZoom: false});
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19, attribution: '&copy; OpenStreetMap contributors'
  }).addTo(map);
  const bounds = [];
  points.forEach((item, index) => {
    const position = [item.location.lat, item.location.lng];
    bounds.push(position);
    const marker = L.marker(position, {
      icon: L.divIcon({
        className: 'trend-pin-wrap',
        html: '<span class="trend-pin"><span>' + (index + 1) + '</span></span>',
        iconSize: [30, 30], iconAnchor: [15, 15]
      })
    }).addTo(map);
    const label = document.createElement('span');
    label.textContent = item.name;
    marker.bindTooltip(label);
    if (item.maps_url) {
      const popup = document.createElement('div');
      const heading = document.createElement('strong');
      heading.textContent = item.name;
      const link = document.createElement('a');
      link.href = item.maps_url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = 'Xem Google Maps ↗';
      popup.append(heading, document.createElement('br'), link);
      marker.bindPopup(popup);
    }
  });
  if (bounds.length === 1) map.setView(bounds[0], 14);
  else map.fitBounds(bounds, {padding: [26, 26], maxZoom: 14});
})();
