// Receipt upload: show a progress overlay while the server reads and checks the
// receipt (about 4-8 s), and block a second submit of the same receipt.
(function () {
  var form = document.getElementById('receipt-form');
  var box = document.getElementById('chk');
  if (!form || !box) return;
  var fill = document.getElementById('chk-fill');
  var bar = box.querySelector('.chk-bar');
  var steps = box.querySelectorAll('.chk-steps li');
  var busy = false;

  function show(pct) {
    fill.style.width = pct + '%';
    bar.setAttribute('aria-valuenow', Math.round(pct));
    steps.forEach(function (li, i) {
      var at = +li.dataset.at, next = steps[i + 1] ? +steps[i + 1].dataset.at : 101;
      li.classList.toggle('done', pct >= next);
      li.classList.toggle('now', pct >= at && pct < next);
    });
  }

  form.addEventListener('submit', function (e) {
    if (busy) { e.preventDefault(); return; }
    var input = form.querySelector('input[type=file]');
    if (input && !input.files.length) return;      // let the browser say "choose a file"
    busy = true;
    form.querySelectorAll('button').forEach(function (b) { b.disabled = true; });
    box.hidden = false;
    document.body.classList.add('chk-lock');
    // Upload phase follows real progress where the browser reports it; after
    // that the bar eases toward 95% (~8 s) and the next page finishes it.
    var start = Date.now();
    show(3);
    var timer = setInterval(function () {
      var t = (Date.now() - start) / 1000;
      show(Math.min(95, 3 + 92 * (1 - Math.exp(-t / 3.2))));
    }, 120);
    window.addEventListener('pagehide', function () { clearInterval(timer); show(100); });
  });

  // Back button returns a cached page: reset the overlay.
  window.addEventListener('pageshow', function (e) {
    if (!e.persisted) return;
    busy = false;
    box.hidden = true;
    document.body.classList.remove('chk-lock');
    form.querySelectorAll('button').forEach(function (b) { b.disabled = false; });
    show(0);
  });
})();
