// Nextcloud folder browser for the event form.
(function () {
  var sel = document.getElementById('nc-instance');
  var folderInput = document.getElementById('nc-folder');
  var btn = document.getElementById('nc-browse-btn');
  var panel = document.getElementById('nc-panel');
  var list = document.getElementById('nc-list');
  var cur = document.getElementById('nc-cur');
  var pick = document.getElementById('nc-pick');
  if (!sel || !btn || !panel) return;
  var path = '';

  function load(p) {
    path = p || '';
    cur.textContent = '/' + path;
    list.innerHTML = '<div class="note">Memuatkan…</div>';
    fetch('/admin/nc/browse?instance=' + encodeURIComponent(sel.value) +
          '&path=' + encodeURIComponent(path))
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.error) { list.innerHTML = '<div class="error">' + d.error + '</div>'; return; }
        var html = '';
        if (path) html += '<a href="#" data-path="' + (d.parent || '') + '" class="nc-item">⬆ ..</a>';
        if (!d.folders.length) html += '<div class="note">(tiada subfolder)</div>';
        d.folders.forEach(function (f) {
          html += '<a href="#" data-path="' + f.path.replace(/"/g, '&quot;') +
                  '" class="nc-item">📁 ' + f.name + '</a>';
        });
        list.innerHTML = html;
      })
      .catch(function () { list.innerHTML = '<div class="error">Ralat sambungan</div>'; });
  }

  btn.addEventListener('click', function () {
    panel.classList.toggle('hidden');
    if (!panel.classList.contains('hidden')) load(folderInput.value.trim());
  });
  list.addEventListener('click', function (e) {
    var a = e.target.closest('.nc-item');
    if (!a) return;
    e.preventDefault();
    load(a.getAttribute('data-path'));
  });
  pick.addEventListener('click', function () {
    folderInput.value = path;
    panel.classList.add('hidden');
  });
  sel.addEventListener('change', function () {
    if (!panel.classList.contains('hidden')) load('');
  });
})();
