// Home-page carousel: fades every 5s, pauses on hover/touch, swipe + arrows.
(function () {
  var root = document.querySelector('.carousel');
  if (!root) return;
  var slides = root.querySelectorAll('.car-slide');
  var dots = root.querySelectorAll('.car-dots button');
  if (slides.length < 2) return;
  var i = 0, timer = null;
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function show(n) {
    slides[i].classList.remove('on'); slides[i].setAttribute('aria-hidden', 'true');
    if (dots[i]) dots[i].classList.remove('on');
    i = (n + slides.length) % slides.length;
    slides[i].classList.add('on'); slides[i].setAttribute('aria-hidden', 'false');
    if (dots[i]) dots[i].classList.add('on');
  }
  function play() { if (!reduce) { stop(); timer = setInterval(function () { show(i + 1); }, 5000); } }
  function stop() { if (timer) clearInterval(timer); timer = null; }

  root.querySelector('.prev').addEventListener('click', function () { show(i - 1); play(); });
  root.querySelector('.next').addEventListener('click', function () { show(i + 1); play(); });
  dots.forEach(function (d, n) { d.addEventListener('click', function () { show(n); play(); }); });
  root.addEventListener('mouseenter', stop);
  root.addEventListener('mouseleave', play);
  document.addEventListener('visibilitychange', function () { document.hidden ? stop() : play(); });

  var x0 = null;
  root.addEventListener('touchstart', function (e) { x0 = e.touches[0].clientX; stop(); }, { passive: true });
  root.addEventListener('touchend', function (e) {
    if (x0 === null) return;
    var dx = e.changedTouches[0].clientX - x0; x0 = null;
    if (Math.abs(dx) > 40) show(dx < 0 ? i + 1 : i - 1);
    play();
  });
  play();
})();
