/* Tony's Detailing — v3 site chrome: nav, mobile menu, hero video, CTA bar, call tracking. */
(function () {
  'use strict';
  var d = document;

  // Mobile menu
  var burger = d.getElementById('burger'), mnav = d.getElementById('mnav');
  function setMenu(open) {
    if (!burger || !mnav) return;
    mnav.classList.toggle('open', open);
    d.body.classList.toggle('menu-open', open);
    burger.setAttribute('aria-expanded', open ? 'true' : 'false');
    burger.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
  }
  if (burger) burger.addEventListener('click', function () { setMenu(!mnav.classList.contains('open')); });
  if (mnav) mnav.addEventListener('click', function (e) { if (e.target.closest('a')) setMenu(false); });
  d.addEventListener('keydown', function (e) { if (e.key === 'Escape') { setMenu(false); closeDd(); } });

  // Desktop services dropdown (click/tap + keyboard; hover handled in CSS)
  var dds = d.querySelectorAll('.nav-dd');
  function closeDd() { dds.forEach(function (dd) { dd.classList.remove('open'); dd.querySelector('button').setAttribute('aria-expanded', 'false'); }); }
  dds.forEach(function (dd) {
    var b = dd.querySelector('button');
    b.addEventListener('click', function (e) {
      e.stopPropagation();
      var open = !dd.classList.contains('open');
      closeDd();
      dd.classList.toggle('open', open);
      b.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  });
  d.addEventListener('click', function (e) { if (!e.target.closest('.nav-dd')) closeDd(); });

  // Hero video: only after load, only with motion allowed and no data saver.
  var video = d.querySelector('.hero-media video');
  if (video) {
    var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var conn = navigator.connection || {};
    var slow = conn.saveData || /(^|-)2g$|^3g$/.test(conn.effectiveType || '');
    var portrait = window.matchMedia('(orientation: portrait)').matches;
    var src = portrait ? (video.dataset.srcVertical || '') : (video.dataset.src || '');
    if (!reduce && !slow && src) {
      window.addEventListener('load', function () {
        video.src = src;
        video.addEventListener('playing', function () { video.classList.add('playing'); }, { once: true });
        video.addEventListener('error', function () { video.remove(); }, { once: true });
        var p = video.play();
        if (p && p.catch) p.catch(function () {});
      });
    } else {
      video.remove();
    }
  }

  // Sticky mobile CTA hides while the quote form is on screen.
  var mcta = d.getElementById('mcta'), qsec = d.getElementById('quote');
  if (mcta && qsec && 'IntersectionObserver' in window) {
    new IntersectionObserver(function (es) {
      es.forEach(function (en) { mcta.classList.toggle('hide', en.isIntersecting); });
    }, { threshold: 0.08 }).observe(qsec);
  }

  // Phone-click conversion (same Google Ads action as the v2 site).
  d.addEventListener('click', function (e) {
    var a = e.target.closest('a[href^="tel:"]');
    if (a && typeof window.gtag === 'function') {
      window.gtag('event', 'conversion', { send_to: 'AW-18237414368/t4VuCLPxv8gcEOC3o_hD' });
    }
  });

  // Remember ad / campaign parameters for the quote form (per tab session).
  try {
    var qs = new URLSearchParams(location.search), keep = [];
    ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'].forEach(function (k) {
      if (qs.get(k)) keep.push(k.replace('utm_', '') + '=' + qs.get(k));
    });
    if (qs.get('fbclid')) keep.push('fbclid');
    if (qs.get('gclid')) keep.push('gclid');
    if (keep.length) {
      sessionStorage.setItem('td_utm', keep.join('; ') + '; landing=' + location.pathname);
    }
  } catch (err) { /* storage unavailable — fine */ }
})();
