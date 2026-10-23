// Gallery: select photos, filter/search, add-to-cart, lightbox zoom.
(function () {
  var grid = document.getElementById('grid');
  if (!grid) return;
  var eventId = parseInt(grid.dataset.eventId, 10);
  var selected = new Set();

  var selbar = document.getElementById('selbar');
  var selcount = document.getElementById('selcount');
  var addBtn = document.getElementById('add-btn');
  var clearBtn = document.getElementById('clear-sel');

  function refresh() {
    if (selcount) selcount.textContent = selected.size;
    if (selbar) selbar.classList.toggle('show', selected.size > 0);
  }

  grid.addEventListener('click', function (e) {
    var zoom = e.target.closest('.zoom');
    var cell = e.target.closest('.cell');
    if (!cell) return;
    if (zoom) { openLightbox(cell.dataset.large, cell.dataset.fname); return; }
    var id = cell.dataset.id;
    if (selected.has(id)) { selected.delete(id); cell.classList.remove('sel'); }
    else { selected.add(id); cell.classList.add('sel'); }
    refresh();
  });

  if (clearBtn) clearBtn.addEventListener('click', function () {
    selected.forEach(function (id) {
      var c = grid.querySelector('.cell[data-id="' + id + '"]');
      if (c) c.classList.remove('sel');
    });
    selected.clear(); refresh();
  });

  if (addBtn) addBtn.addEventListener('click', function () {
    if (!selected.size) return;
    addBtn.disabled = true;
    fetch('/cart/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ event_id: eventId, photo_ids: Array.from(selected).map(Number) })
    }).then(function (r) { return r.json(); }).then(function (d) {
      addBtn.disabled = false;
      if (d.error) { jsToast('⚠ ' + d.error); return; }
      window.setCartBadge(d.count);
      jsToast(selected.size + ' ' + (grid.dataset.addedLabel || 'added'));
      clearBtn && clearBtn.click();
    }).catch(function () { addBtn.disabled = false; jsToast('⚠'); });
  });

  // filters
  var fSchool = document.getElementById('f-school');
  var fClass = document.getElementById('f-class');
  var fSearch = document.getElementById('f-search');
  function applyFilter() {
    var s = fSchool ? fSchool.value : '';
    var c = fClass ? fClass.value : '';
    var q = (fSearch ? fSearch.value : '').toLowerCase().trim();
    grid.querySelectorAll('.cell').forEach(function (cell) {
      var ok = (!s || cell.dataset.school === s) &&
               (!c || cell.dataset.class === c) &&
               (!q || cell.dataset.fname.toLowerCase().indexOf(q) !== -1);
      cell.style.display = ok ? '' : 'none';
    });
  }
  [fSchool, fClass, fSearch].forEach(function (el) {
    if (el) el.addEventListener('input', applyFilter);
  });

  // lightbox
  var lb = document.getElementById('lightbox');
  function openLightbox(url, name) {
    if (!lb) return;
    lb.querySelector('.img').style.backgroundImage = 'url(' + url + ')';
    lb.classList.add('show');
  }
  if (lb) {
    lb.addEventListener('click', function (e) {
      if (e.target.closest('.img')) return;
      lb.classList.remove('show');
    });
  }
})();
