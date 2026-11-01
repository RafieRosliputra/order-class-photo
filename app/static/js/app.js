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

  // Checkbox that shows/hides a related box (admin delivery options).
  document.querySelectorAll('input[data-toggle]').forEach(function (cb) {
    var box = document.querySelector(cb.dataset.toggle);
    if (!box) return;
    cb.addEventListener('change', function () { box.classList.toggle('hidden', !cb.checked); });
  });

  // "Copy link" buttons.
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
  };
})();
