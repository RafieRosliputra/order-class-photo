// Cart & editable order: small animations around add / change / remove.
// Forms still post normally (server-rendered); we animate before leaving and
// highlight the changed photo after the page comes back.
(function () {
  var KEY = 'js-cart-anim';
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function remember(line, kind) {
    try {
      sessionStorage.setItem(KEY, JSON.stringify({
        path: location.pathname, pid: line ? line.dataset.pid : '', kind: kind, y: window.scrollY
      }));
    } catch (e) { /* storage blocked: no highlight, still works */ }
  }

  // Remove: shrink and fade the row, then submit.
  document.querySelectorAll('form.js-remove').forEach(function (f) {
    f.addEventListener('submit', function (e) {
      var line = f.closest('.line');
      if (!line || reduce || f.dataset.go) { remember(line, 'remove'); return; }
      e.preventDefault();
      remember(line, 'remove');
      line.style.height = line.offsetHeight + 'px';
      line.classList.add('leaving');
      requestAnimationFrame(function () { line.style.height = '0px'; });
      setTimeout(function () { f.dataset.go = '1'; f.submit(); }, 280);
    });
  });

  // Size / qty / add-size: press feedback, then highlight after reload.
  document.querySelectorAll('form.js-anim').forEach(function (f) {
    f.addEventListener('submit', function (e) {
      var line = f.closest('.line');
      var btn = e.submitter || f.querySelector('button');
      if (btn) btn.classList.add('pressed');
      // keep the clicked button's value (forms submitted via submitter keep it natively)
      remember(line, 'change');
      if (line) line.classList.add('busy');
    });
  });

  // After reload: restore scroll and flash the photo that changed.
  var raw = null;
  try { raw = sessionStorage.getItem(KEY); sessionStorage.removeItem(KEY); } catch (e) { raw = null; }
  if (!raw) return;
  var st;
  try { st = JSON.parse(raw); } catch (e) { return; }
  if (!st || st.path !== location.pathname) return;
  if (typeof st.y === 'number' && !location.hash) window.scrollTo(0, st.y);
  if (st.kind === 'change' && st.pid) {
    document.querySelectorAll('.line[data-pid="' + st.pid + '"]').forEach(function (l) {
      l.classList.add('flash');
      setTimeout(function () { l.classList.remove('flash'); }, 1200);
    });
  }
})();
