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

  window.setCartBadge = function (n) {
    var b = document.getElementById('cart-badge');
    if (!b) return;
    b.textContent = n;
    b.classList.toggle('hidden', !n);
  };
})();
