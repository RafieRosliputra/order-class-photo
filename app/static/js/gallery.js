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
    document.body.classList.toggle('has-selbar', selected.size > 0);
  }

  grid.addEventListener('click', function (e) {
    var zoom = e.target.closest('.zoom');
    var cell = e.target.closest('.cell');
    if (!cell) return;
    if (zoom) { openLightbox(cell); return; }
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
      if (d.error) {
        var key = 'err' + d.error.replace(/(^|_)([a-z])/g, function (m, a, c) { return c.toUpperCase(); });
        jsToast('⚠ ' + (grid.dataset[key] || grid.dataset.errGeneric || d.error)); return;
      }
      window.setCartBadge(d.count);
      jsToast(selected.size + ' ' + (grid.dataset.addedLabel || 'added'));
      clearBtn && clearBtn.click();
    }).catch(function () { addBtn.disabled = false; jsToast('⚠ ' + (grid.dataset.errGeneric || '')); });
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
  function openLightbox(cell) {
    if (!lb) return;
    var img = lb.querySelector('.img');
    var w = parseInt(cell.dataset.w, 10), h = parseInt(cell.dataset.h, 10);
    // follow the photo's real shape (portrait or landscape)
    img.style.aspectRatio = (w > 0 && h > 0) ? (w + ' / ' + h) : (cell.classList.contains('land') ? '3 / 2' : '3 / 4');
    img.classList.toggle('land', cell.classList.contains('land'));
    img.style.backgroundImage = 'url(' + cell.dataset.large + ')';
    lb.classList.add('show');
  }

  // Photos whose size isn't known yet: measure the thumbnail once it loads.
  grid.querySelectorAll('.cell').forEach(function (cell) {
    if (parseInt(cell.dataset.w, 10) > 0) return;
    var m = /url\(['"]?([^'")]+)/.exec(cell.style.backgroundImage);
    if (!m) return;
    var probe = new Image();
    probe.onload = function () {
      cell.dataset.w = probe.naturalWidth; cell.dataset.h = probe.naturalHeight;
      if (probe.naturalWidth > probe.naturalHeight) cell.classList.add('land');
    };
    probe.src = m[1];
  });
  if (lb) {
    lb.addEventListener('click', function (e) {
      if (e.target.closest('.img')) return;
      lb.classList.remove('show');
    });
  }
})();
