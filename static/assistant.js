(() => {
  const dataNode = document.getElementById('assistant-data');
  if (!dataNode) return;
  const restaurants = JSON.parse(dataNode.textContent);
  const byId = new Map(restaurants.map(item => [item.id, item]));
  const cards = [...document.querySelectorAll('.fl-card')];
  const list = document.getElementById('restaurant-list');
  const mobile = window.matchMedia('(max-width: 1199px)');
  const detail = document.getElementById('mobile-details');
  let selectedId = restaurants[0]?.id || null;
  let favoritesOnly = false;
  let favorites;
  try { favorites = new Set(JSON.parse(localStorage.getItem('foodlens-favorites') || '[]')); }
  catch { favorites = new Set(); }
  const maps = new Map();
  let visible = [...restaurants];

  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
  };
  const replace = (id, nodes) => {
    const host = document.getElementById(id);
    host.replaceChildren(...nodes);
  };
  const dateLabel = value => value ? String(value).slice(0, 10) : 'Chưa rõ ngày';

  function reviewNodes(item, limit = 5) {
    if (!item?.evidence?.length) return [el('p', 'fl-dim', 'Chưa có review có nội dung cho quán này.')];
    return item.evidence.slice(0, limit).map(review => {
      const article = el('article', 'fl-review');
      article.append(el('p', '', `“${review.text}”`));
      const meta = el('div', 'fl-review-meta');
      if (review.rating != null) meta.append(el('span', 'stars', `★ ${review.rating}/5`));
      meta.append(el('span', '', dateLabel(review.date)));
      if (review.source_url) {
        const link = el('a', '', 'Đọc nguồn ↗');
        link.href = review.source_url;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        meta.append(link);
      }
      article.append(meta);
      return article;
    });
  }

  function aspectNodes(item) {
    if (!item?.aspects?.length) return [el('p', 'fl-dim', 'Chưa đủ nhãn khía cạnh để tính tỷ lệ tích cực.')];
    return item.aspects.map(aspect => {
      const row = el('div', 'fl-aspect-row');
      row.append(el('span', '', aspect.label));
      const bar = el('progress');
      bar.value = aspect.percent;
      bar.max = 100;
      bar.setAttribute('aria-label', `${aspect.label}: ${aspect.percent}% nhãn tích cực`);
      row.append(bar, el('strong', '', `${aspect.percent}%`));
      return row;
    });
  }

  function trendNodes(item) {
    if (!item?.months?.length) return [el('p', 'fl-dim', 'Chưa có ngày review nguồn để hiển thị xu hướng.')];
    const max = Math.max(...item.months.map(month => month.count), 1);
    return item.months.map(month => {
      const row = el('div', 'fl-trend-row');
      row.append(el('span', '', month.month));
      const bar = el('div', 'fl-trend-bar');
      const fill = el('span');
      fill.style.width = `${Math.round(month.count / max * 100)}%`;
      bar.append(fill);
      row.append(bar, el('strong', '', `${month.count} review`));
      return row;
    });
  }

  function updateEvidence() {
    const item = byId.get(selectedId);
    document.getElementById('evidence-name').textContent = item?.name || '';
    const initialReviews = reviewNodes(item, 2);
    if (item?.evidence?.length > 2) {
      const more = el('button', 'fl-review-more', 'Xem thêm bình luận');
      more.type = 'button';
      more.addEventListener('click', () => {
        const expanded = more.textContent === 'Xem thêm bình luận';
        replace('review-evidence', [...reviewNodes(item, expanded ? 5 : 2), more]);
        more.textContent = expanded ? 'Thu gọn' : 'Xem thêm bình luận';
      });
      initialReviews.push(more);
    }
    replace('review-evidence', initialReviews);
    replace('aspect-summary', aspectNodes(item));
    replace('trend-summary', trendNodes(item));
    document.getElementById('detail-title').textContent = item?.name || 'Nhà hàng';
    replace('detail-reviews', reviewNodes(item));
    const overview = [];
    if (item) {
      overview.push(el('div', 'fl-detail-score', item.score.toFixed(3)));
      overview.push(el('p', 'fl-dim', 'Điểm xếp hạng theo mô hình hiện có; không phải xác suất hài lòng.'));
      overview.push(el('p', 'fl-detail-address', item.address || 'Chưa có địa chỉ'));
      overview.push(...aspectNodes(item));
      if (item.sourceUrl) {
        const link = el('a', 'fl-detail-source', 'Mở trên Google Maps ↗');
        link.href = item.sourceUrl;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        overview.push(link);
      }
    }
    replace('detail-overview', overview);
    refreshMaps();
  }

  function updateSelection(id, openMobile = true) {
    if (!byId.has(id)) return;
    selectedId = id;
    cards.forEach(card => {
      const active = card.dataset.id === id;
      card.classList.toggle('selected', active);
      card.setAttribute('aria-pressed', String(active));
    });
    updateEvidence();
    if (openMobile && mobile.matches && !detail.open) detail.showModal();
  }

  function mapFor(id) {
    if (maps.has(id)) return maps.get(id);
    const host = document.getElementById(id);
    if (!host || !window.L || !host.getClientRects().length) return null;
    const map = L.map(host, {scrollWheelZoom: false, tap: true});
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);
    maps.set(id, map);
    return map;
  }

  function refreshMaps() {
    for (const id of ['map-preview', 'map-large', 'map-mobile']) {
      const host = document.getElementById(id);
      if (!host?.getClientRects().length) continue;
      const positioned = visible.filter(item => item.location);
      const empty = document.getElementById(`${id}-empty`);
      host.hidden = !positioned.length;
      if (empty) empty.hidden = Boolean(positioned.length);
      if (!positioned.length) continue;
      const map = mapFor(id);
      if (!map) continue;
      if (map.foodlensMarkers) map.foodlensMarkers.forEach(marker => map.removeLayer(marker));
      map.foodlensMarkers = positioned.map(item => {
        const rank = visible.indexOf(item) + 1;
        const marker = L.marker([item.location.lat, item.location.lng], {
          icon: L.divIcon({className: '', html: `<span class="fl-map-pin ${item.id === selectedId ? 'selected' : ''}">${rank}</span>`, iconSize: [30, 30], iconAnchor: [15, 15]})
        }).addTo(map);
        marker.on('click', () => {
          updateSelection(item.id, id !== 'map-mobile');
          if (id === 'map-preview') document.querySelector(`.fl-card[data-id="${CSS.escape(item.id)}"]`)?.scrollIntoView({block: 'nearest', behavior: 'smooth'});
        });
        marker.bindTooltip(item.name, {direction: 'top'});
        return marker;
      });
      const bounds = L.latLngBounds(positioned.map(item => [item.location.lat, item.location.lng]));
      map.invalidateSize();
      if (positioned.length === 1) map.setView(bounds.getCenter(), 14);
      else map.fitBounds(bounds.pad(.22), {maxZoom: 14});
    }
  }

  function applyFilters() {
    const sort = document.getElementById('sort-results')?.value || 'score';
    const limit = document.getElementById('count-results')?.value || 'all';
    const rank = {score: 'score', rating: 'rating', reviews: 'reviewCount'}[sort];
    visible = restaurants.filter(item => !favoritesOnly || favorites.has(item.id))
      .sort((a, b) => (b[rank] || 0) - (a[rank] || 0))
      .slice(0, limit === 'all' ? undefined : Number(limit));
    const visibleIds = new Set(visible.map(item => item.id));
    visible.forEach((item, index) => {
      const card = cards.find(node => node.dataset.id === item.id);
      card.hidden = false;
      card.querySelector('.fl-rank').textContent = index + 1;
      list.append(card);
    });
    cards.filter(card => !visibleIds.has(card.dataset.id)).forEach(card => { card.hidden = true; list.append(card); });
    document.getElementById('visible-count').textContent = visible.length;
    const favoriteFilter = document.getElementById('favorites-filter');
    if (favoriteFilter) favoriteFilter.hidden = !favoritesOnly;
    document.getElementById('filtered-empty').hidden = Boolean(visible.length) || !restaurants.length;
    if (visible.length && !visibleIds.has(selectedId)) updateSelection(visible[0].id, false);
    refreshMaps();
  }

  cards.forEach(card => {
    card.addEventListener('click', event => {
      if (event.target.closest('button,a')) return;
      updateSelection(card.dataset.id);
    });
    card.addEventListener('keydown', event => {
      if ((event.key === 'Enter' || event.key === ' ') && event.target === card) {
        event.preventDefault(); updateSelection(card.dataset.id);
      }
    });
  });
  document.querySelectorAll('.fl-favorite').forEach(button => {
    const id = button.dataset.id;
    const sync = () => { button.textContent = favorites.has(id) ? '♥' : '♡'; button.setAttribute('aria-pressed', String(favorites.has(id))); };
    sync();
    button.addEventListener('click', event => {
      event.stopPropagation();
      if (favorites.has(id)) favorites.delete(id); else favorites.add(id);
      localStorage.setItem('foodlens-favorites', JSON.stringify([...favorites]));
      sync(); applyFilters();
    });
  });
  ['sort-results', 'count-results'].forEach(id => document.getElementById(id)?.addEventListener('change', applyFilters));
  const showFavorites = () => { favoritesOnly = !favoritesOnly; applyFilters(); document.getElementById('results').scrollIntoView({behavior: 'smooth'}); closeMenu(); };
  document.getElementById('favorites-nav')?.addEventListener('click', showFavorites);
  document.getElementById('mobile-favorites-nav')?.addEventListener('click', showFavorites);
  document.getElementById('clear-filter')?.addEventListener('click', () => { favoritesOnly = false; applyFilters(); });
  document.getElementById('favorites-filter')?.addEventListener('click', () => { favoritesOnly = false; applyFilters(); });

  document.querySelectorAll('[data-panel]').forEach(button => button.addEventListener('click', () => {
    document.querySelectorAll('[data-panel]').forEach(tab => { const active = tab === button; tab.classList.toggle('active', active); tab.setAttribute('aria-selected', String(active)); });
    document.querySelectorAll('.fl-tab-panel').forEach(panel => { panel.hidden = panel.id !== `evidence-${button.dataset.panel}`; });
    requestAnimationFrame(refreshMaps);
  }));
  document.querySelectorAll('[data-detail-tab]').forEach(button => button.addEventListener('click', () => {
    document.querySelectorAll('[data-detail-tab]').forEach(tab => { const active = tab === button; tab.classList.toggle('active', active); tab.setAttribute('aria-selected', String(active)); });
    document.querySelectorAll('[data-detail-panel]').forEach(panel => { panel.hidden = panel.dataset.detailPanel !== button.dataset.detailTab; });
    if (button.dataset.detailTab === 'map') requestAnimationFrame(refreshMaps);
  }));
  document.getElementById('detail-close').addEventListener('click', () => detail.close());
  detail.addEventListener('click', event => { if (event.target === detail) detail.close(); });
  window.addEventListener('resize', () => requestAnimationFrame(refreshMaps));

  const drawer = document.getElementById('mobile-drawer');
  const backdrop = document.getElementById('drawer-backdrop');
  const menuOpen = document.getElementById('menu-open');
  function closeMenu() { drawer.hidden = backdrop.hidden = true; menuOpen.setAttribute('aria-expanded', 'false'); }
  menuOpen.addEventListener('click', () => { drawer.hidden = backdrop.hidden = false; menuOpen.setAttribute('aria-expanded', 'true'); document.getElementById('menu-close').focus(); });
  document.getElementById('menu-close').addEventListener('click', closeMenu);
  backdrop.addEventListener('click', closeMenu);
  drawer.addEventListener('keydown', event => { if (event.key === 'Escape') { closeMenu(); menuOpen.focus(); } });
  drawer.querySelectorAll('a').forEach(link => link.addEventListener('click', closeMenu));

  const input = document.getElementById('assistant-message');
  document.querySelectorAll('[data-suggestion]').forEach(button => button.addEventListener('click', () => {
    input.value = button.dataset.suggestion;
    input.focus();
  }));
  document.getElementById('assistant-form').addEventListener('submit', () => {
    document.getElementById('assistant-submit').disabled = true;
    document.getElementById('restaurant-list').hidden = true;
    document.getElementById('loading-cards').hidden = false;
  });
  document.querySelectorAll('.fl-card-media img').forEach(image => image.addEventListener('error', () => { image.hidden = true; }));
  updateEvidence();
  applyFilters();
})();
