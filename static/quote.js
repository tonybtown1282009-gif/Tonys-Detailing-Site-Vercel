/* Tony's Detailing — multi-step quote form. Posts to /api/quote. */
(function () {
  'use strict';
  var d = document;
  var root = d.getElementById('qf');
  if (!root) return;
  var form = root.querySelector('form');
  var steps = Array.prototype.slice.call(form.querySelectorAll('.qf-step'));
  var btnNext = form.querySelector('[data-next]');
  var btnBack = form.querySelector('[data-back]');
  var btnSubmit = form.querySelector('[data-submit]');
  var bar = root.querySelector('.qf-bar i');
  var dots = root.querySelectorAll('.qf-dots span');
  var titleEl = root.querySelector('[data-step-title]');
  var numEl = root.querySelector('[data-step-num]');
  var current = 0;
  var zips = null;
  var started = false;

  function track(event, data) {
    window.dataLayer = window.dataLayer || [];
    var o = { event: event };
    for (var k in data) o[k] = data[k];
    window.dataLayer.push(o);
  }

  // ── Helpers ──
  function digits(v) { return (v || '').replace(/\D/g, ''); }
  function validPhone(v) { var x = digits(v); if (x.length === 11 && x[0] === '1') x = x.slice(1); return x.length === 10; }
  function validEmail(v) { return /^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/.test((v || '').trim()); }
  function validZip(v) { return /^\d{5}$/.test((v || '').trim()); }
  function fieldOf(input) { return input.closest('.fld'); }
  function setErr(input, bad) { var f = fieldOf(input); if (f) f.classList.toggle('err', bad); input.setAttribute('aria-invalid', bad ? 'true' : 'false'); }

  function checkInput(input) {
    var v = input.value, kind = input.dataset.validate, bad = false;
    if (input.required && !v.trim()) bad = true;
    else if (kind === 'phone') bad = !validPhone(v);
    else if (kind === 'email') bad = !validEmail(v);
    else if (kind === 'zip') bad = !validZip(v);
    setErr(input, bad);
    return !bad;
  }

  function checkStep(i) {
    var ok = true, first = null;
    steps[i].querySelectorAll('input[required]').forEach(function (inp) {
      if (!checkInput(inp)) { ok = false; first = first || inp; }
    });
    var grp = steps[i].querySelector('[data-group="services"]');
    if (grp) {
      var any = !!form.querySelector('input[name="services"]:checked');
      grp.classList.toggle('err', !any);
      if (!any) { ok = false; first = first || grp.querySelector('input'); }
    }
    if (first) first.focus({ preventScroll: false });
    return ok;
  }

  function show(i, focus) {
    current = i;
    steps.forEach(function (s, n) { s.classList.toggle('active', n === i); });
    btnBack.hidden = i === 0;
    btnNext.hidden = i === steps.length - 1;
    btnSubmit.hidden = i !== steps.length - 1;
    bar.style.width = ((i + 1) / steps.length * 100) + '%';
    dots.forEach(function (dt, n) { dt.classList.toggle('on', n <= i); });
    titleEl.textContent = steps[i].dataset.title;
    numEl.textContent = i + 1;
    if (focus) {
      var top = root.getBoundingClientRect().top;
      if (top < 0 || top > window.innerHeight * 0.5) root.scrollIntoView({ behavior: 'smooth', block: 'start' });
      var lg = steps[i].querySelector('legend');
      if (lg) lg.focus({ preventScroll: true });
    }
    if (i === 1) loadZips();
    if (focus) track('quote_step', { quote_step: i + 1 });
  }

  // ── Conditional questions ──
  function syncConditionals() {
    form.querySelectorAll('.cond').forEach(function (c) {
      var on = !!form.querySelector('input[name="services"][value="' + c.dataset.when + '"]:checked');
      c.classList.toggle('show', on);
    });
    var grp = form.querySelector('[data-group="services"]');
    if (grp && form.querySelector('input[name="services"]:checked')) grp.classList.remove('err');
  }

  function selectService(slug) {
    if (!slug) return;
    var box = form.querySelector('input[name="services"][data-slug="' + slug + '"]');
    if (box) { box.checked = true; syncConditionals(); }
  }

  // ── ZIP / service area note ──
  function loadZips() {
    if (zips) return;
    zips = {};
    fetch('/static/data/service-zips.json').then(function (r) { return r.json(); })
      .then(function (j) { zips = j; zipNote(); }).catch(function () {});
  }
  function zipNote() {
    var inp = form.querySelector('input[name="zip"]'), note = form.querySelector('[data-zip-note]');
    if (!inp || !note) return;
    var z = inp.value.trim(), msg = '';
    if (validZip(z) && zips && Object.keys(zips).length) {
      var mi = zips[z];
      if (mi === undefined || mi > 25) {
        msg = "That ZIP looks outside our usual service area — send your request anyway and we'll let you know if we can make the trip.";
      } else if (mi > 15) {
        msg = "You're in our extended area — a small travel fee may apply, and a Full Detail is the minimum service.";
      }
    }
    note.querySelector('span').textContent = msg;
    note.classList.toggle('show', !!msg);
  }

  // ── Input behaviour ──
  form.addEventListener('input', function (e) {
    var t = e.target;
    if (!started) { started = true; track('quote_start', {}); }
    if (t.name === 'phone') {
      var x = digits(t.value);
      if (x.length === 11 && x[0] === '1') x = x.slice(1);
      x = x.slice(0, 10);
      var out = x;
      if (x.length > 6) out = '(' + x.slice(0, 3) + ') ' + x.slice(3, 6) + '-' + x.slice(6);
      else if (x.length > 3) out = '(' + x.slice(0, 3) + ') ' + x.slice(3);
      if (t.value !== out && document.activeElement === t && e.inputType !== 'deleteContentBackward') t.value = out;
    }
    if (t.name === 'zip' || t.name === 'vehicle_year') t.value = digits(t.value).slice(0, t.name === 'zip' ? 5 : 4);
    if (t.name === 'zip') zipNote();
    if (fieldOf(t) && fieldOf(t).classList.contains('err')) checkInput(t);
  });
  form.addEventListener('change', function (e) { if (e.target.name === 'services') syncConditionals(); });
  form.addEventListener('focusout', function (e) {
    var t = e.target;
    if (t.matches && t.matches('input[required]') && t.value) checkInput(t);
  });
  form.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && e.target.tagName === 'INPUT' && current < steps.length - 1) {
      e.preventDefault();
      btnNext.click();
    }
  });

  btnNext.addEventListener('click', function () { if (checkStep(current)) show(current + 1, true); });
  btnBack.addEventListener('click', function () { show(current - 1, true); });

  // ── Submit ──
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    for (var i = 0; i < steps.length; i++) {
      if (!checkStep(i)) { show(i, true); checkStep(i); return; }
    }
    var utm = '';
    try { utm = sessionStorage.getItem('td_utm') || ''; } catch (err) { /* ignore */ }
    form.querySelector('input[name="utm"]').value = utm;
    var src = form.querySelector('input[name="source_page"]');
    if (d.referrer && src.value.indexOf('ref=') < 0) {
      try { var r = new URL(d.referrer); if (r.host !== location.host) src.value += ' (ref=' + r.host + ')'; } catch (err) { /* ignore */ }
    }

    var label = btnSubmit.textContent;
    btnSubmit.disabled = true;
    btnSubmit.textContent = 'Sending…';
    var data = new FormData(form);

    fetch('/api/quote', { method: 'POST', body: data })
      .then(function (res) { return res.json().then(function (j) { return { status: res.status, body: j }; }); })
      .then(function (r) {
        if (r.body && r.body.ok) {
          var first = (data.get('first_name') || '').trim();
          var how = data.get('contact_method');
          var msg = 'Thanks' + (first ? ', ' + first : '') + '! Tony’s Detailing has your quote request and will follow up within 24 hours';
          msg += how === 'Text Message' ? ' by text.' : how === 'Email' ? ' by email.' : how === 'Phone Call' ? ' with a call.' : '.';
          root.querySelector('[data-done-msg]').textContent = msg;
          root.classList.add('done');
          root.scrollIntoView({ behavior: 'smooth', block: 'start' });
          var services = data.getAll('services').join(', ');
          track('quote_submitted', { quote_services: services });
          if (typeof window.gtag === 'function') window.gtag('event', 'generate_lead', { services: services });
          if (typeof window.fbq === 'function') window.fbq('track', 'Lead', { content_name: services });
          return;
        }
        if (r.status === 400 && r.body && r.body.errors) {
          btnSubmit.disabled = false; btnSubmit.textContent = label;
          var order = ['first_name', 'phone', 'email', 'zip', 'services'];
          for (var k = 0; k < order.length; k++) {
            if (r.body.errors[order[k]]) {
              var inp = form.querySelector('[name="' + order[k] + '"]');
              var step = steps.indexOf(inp.closest('.qf-step'));
              show(step, true);
              if (order[k] === 'services') inp.closest('[data-group]').classList.add('err'); else setErr(inp, true);
              return;
            }
          }
        }
        throw new Error('delivery');
      })
      .catch(function () { fail(data); });
  });

  function fail(data) {
    var summary = 'Hi Tony, quote request: ' + [
      (data.get('first_name') + ' ' + data.get('last_name')).trim(),
      [data.get('vehicle_year'), data.get('vehicle_make'), data.get('vehicle_model')].join(' ').trim(),
      data.getAll('services').join(', '),
      'ZIP ' + data.get('zip')
    ].filter(Boolean).join(' · ');
    var sms = root.querySelector('[data-sms]'), mail = root.querySelector('[data-mailto]');
    if (sms) sms.href = 'sms:+12169034783?&body=' + encodeURIComponent(summary);
    if (mail) mail.href = 'mailto:tonysdetailing.net@gmail.com?subject=' + encodeURIComponent('Quote request') + '&body=' + encodeURIComponent(summary);
    root.classList.add('failed');
    root.scrollIntoView({ behavior: 'smooth', block: 'start' });
    track('quote_failed', {});
  }

  // ── Preselect + "Get a Quote" buttons ──
  var params = new URLSearchParams(location.search);
  selectService(root.dataset.preselect);
  selectService(params.get('service'));

  d.addEventListener('click', function (e) {
    var a = e.target.closest('[data-quote]');
    if (!a) return;
    e.preventDefault();
    selectService(a.dataset.quote);
    var mnav = d.getElementById('mnav');
    if (mnav && mnav.classList.contains('open')) d.getElementById('burger').click();
    d.getElementById('quote').scrollIntoView({ behavior: 'smooth', block: 'start' });
    track('quote_cta', { quote_service: a.dataset.quote || '' });
    setTimeout(function () {
      var target = steps[current].querySelector('input:not([type=hidden])');
      if (target && current === 0 && !target.value) target.focus({ preventScroll: true });
    }, 450);
  });

  show(0, false);
})();
