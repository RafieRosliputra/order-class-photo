// Global: discourage saving preview images, toast helper, cart badge.
(function () {
  // Block right-click / drag-save on protected images (previews shown via CSS bg).
  document.addEventListener('contextmenu', function (e) {
    if (e.target.closest('.cell, .thumb, .lightbox, .img')) e.preventDefault();
  });
  document.addEventListener('dragstart', function (e) {
    if (e.target.closest('.cell, .thumb, .lightbox')) e.preventDefault();
  });

  window.jsToast = function (msg) {
    var t = document.getElementById('toast');
    if (!t) {
      t = document.createElement('div');
      t.id = 'toast';
      t.className = 'toast';
      document.body.appendChild(t);
    }
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(window.__toastT);
    window.__toastT = setTimeout(function () { t.classList.remove('show'); }, 2600);
  };

  // Confirm before destructive actions. data-confirm = first question;
  // data-confirm2 = second question (double confirm) — only then the hidden
  // "confirm2" field gets the order number the server checks.
  document.addEventListener('submit', function (e) {
    var f = e.target;
    if (!f.dataset || !f.dataset.confirm) return;
    if (!window.confirm(f.dataset.confirm)) { e.preventDefault(); return; }
    if (f.dataset.confirm2) {
      if (!window.confirm(f.dataset.confirm2)) { e.preventDefault(); return; }
      var h = f.querySelector('input[name="confirm2"]');
      if (h) h.value = f.dataset.orderNo || '';
    }
  }, true);

  // Checkbox that shows/hides a related box (admin delivery options).
  document.querySelectorAll('input[data-toggle]').forEach(function (cb) {
    var box = document.querySelector(cb.dataset.toggle);
    if (!box) return;
    cb.addEventListener('change', function () { box.classList.toggle('hidden', !cb.checked); });
  });

  // "Copy link" buttons.
  // Read-only field that copies itself when clicked (admin share links / password).
  document.querySelectorAll('input[data-copy-click]').forEach(function (inp) {
    inp.addEventListener('click', function () {
      inp.select();
      var done = function () {
        inp.classList.add('copied');
        var hint = document.querySelector('.copy-hint');
        if (hint) { hint.dataset.orig = hint.dataset.orig || hint.textContent; hint.textContent = '✓ Disalin: ' + inp.value; }
        setTimeout(function () { inp.classList.remove('copied'); if (hint) hint.textContent = hint.dataset.orig; }, 1800);
      };
      if (navigator.clipboard) navigator.clipboard.writeText(inp.value).then(done, function () { document.execCommand('copy'); done(); });
      else { document.execCommand('copy'); done(); }
    });
  });

  document.querySelectorAll('[data-copy]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var src = document.querySelector(btn.dataset.copy);
      if (!src) return;
      var text = src.value || src.textContent;
      var done = function () { var o = btn.textContent; btn.textContent = '✓'; setTimeout(function () { btn.textContent = o; }, 1500); };
      if (navigator.clipboard) navigator.clipboard.writeText(text).then(done, function () { src.select(); document.execCommand('copy'); done(); });
      else { src.select(); document.execCommand('copy'); done(); }
    });
  });

  window.setCartBadge = function (n) {
    var b = document.getElementById('cart-badge');
    if (!b) return;
    b.textContent = n;
    b.classList.toggle('hidden', !n);
    b.classList.remove('bump'); void b.offsetWidth; b.classList.add('bump');
  };

  // Tap any [data-zoom] thumbnail (cart, order) to see the photo large.
  var zoomBox = null;
  function openZoom(url, label) {
    if (!zoomBox) {
      zoomBox = document.createElement('div');
      zoomBox.className = 'lightbox';
      zoomBox.setAttribute('role', 'dialog');
      zoomBox.setAttribute('aria-modal', 'true');
      zoomBox.innerHTML = '<button class="close" type="button" aria-label="×">×</button>' +
        '<img class="zimg" alt="" draggable="false">';
      document.body.appendChild(zoomBox);
      zoomBox.addEventListener('click', function (e) {
        if (e.target.classList.contains('zimg')) return;
        zoomBox.classList.remove('show');
      });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') zoomBox.classList.remove('show');
      });
    }
    var img = zoomBox.querySelector('.zimg');
    img.src = url; img.alt = label || '';
    zoomBox.classList.add('show');
    zoomBox.querySelector('.close').focus();
  }
  document.addEventListener('click', function (e) {
    var z = e.target.closest('[data-zoom]');
    if (!z) return;
    e.preventDefault();
    openZoom(z.dataset.zoom, z.getAttribute('aria-label'));
  });
})();
