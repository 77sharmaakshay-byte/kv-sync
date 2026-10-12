/* Nyay Sahayak — Nainital HC cause list + cases. Koi server nahi: data/ ki JSON files (GitHub roz banata hai). */
(function () {
  'use strict';
  var view = document.getElementById('view');
  var cache = { index: null, lists: {}, cases: {} };
  var WEEK = ['Ravivaar', 'Somvaar', 'Mangalvaar', 'Budhvaar', 'Guruvaar', 'Shukravaar', 'Shanivaar'];
  var MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function store(k, v) {
    try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; }
    return v;
  }
  function getJSON(path) {
    return fetch(path, { cache: 'no-cache' }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); });
  }
  function index() {
    return cache.index ? Promise.resolve(cache.index) : getJSON('data/index.json').then(function (d) { cache.index = d; return d; });
  }
  function list(date) {
    if (cache.lists[date]) return Promise.resolve(cache.lists[date]);
    return getJSON('data/causelist/' + date + '.json').then(function (d) { cache.lists[date] = d; return d; });
  }
  function caseDoc(id) {
    if (cache.cases[id]) return Promise.resolve(cache.cases[id]);
    return getJSON('data/cases/' + id + '.json').then(function (d) { cache.cases[id] = d; return d; });
  }
  function fmtDate(iso, long) {
    if (!iso) return '';
    var d = new Date(iso + 'T00:00:00');
    var s = d.getDate() + ' ' + MON[d.getMonth()];
    return long ? WEEK[d.getDay()] + ', ' + s + ' ' + d.getFullYear() : s;
  }
  function dayWord(iso) { // list ki tareekh: aaj / kal / '13 Oct'
    var t = new Date(), pad = function (n) { return (n < 10 ? '0' : '') + n; };
    var ymd = function (d) { return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); };
    if (iso === ymd(t)) return 'aaj';
    t.setDate(t.getDate() + 1);
    return iso === ymd(t) ? 'kal' : fmtDate(iso);
  }
  function dmy(iso) { return iso ? iso.split('-').reverse().join('.') : ''; }
  function caseId(no) { return (no || '').replace(/\//g, '-'); }
  function words(q) { return (q || '').toUpperCase().split(/\s+/).filter(Boolean); }
  function hit(e, ws) {
    var hay = ((e.raw || '') + ' ' + (e.case_no || '')).toUpperCase();
    return ws.every(function (w) { return hay.indexOf(w) >= 0; });
  }
  function hl(text, ws) {
    var out = esc(text);
    ws.forEach(function (w) {
      if (w.length < 2) return;
      out = out.replace(new RegExp('(' + esc(w).replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi'), '<mark>$1</mark>');
    });
    return out;
  }
  function courtName(c) { return c.court_no ? 'Court No. ' + c.court_no : (c.judges[0] || c.bench || 'Registrar'); }
  function benchText(c) { return (c.court_no ? c.judges.join(' + ') : '') + (c.judges.length > 1 ? ' · Division Bench' : ''); }
  function setTab(name) {
    Array.prototype.forEach.call(document.querySelectorAll('.nav a'), function (a) {
      a.classList.toggle('on', a.getAttribute('data-tab') === name);
      if (a.getAttribute('data-tab') === name) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
  }
  function render(html) { view.innerHTML = html; view.scrollTop = 0; }
  function fail(err) {
    render('<div class="pad"><div class="empty">Data nahi khula (' + esc(err && err.message) +
      '). Internet check karke dobara kholo.</div></div>');
  }
  var ICON_SEARCH = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>';
  var ICON_BACK = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 6l-6 6 6 6"/></svg>';
  var ICON_NEXT = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg>';
  var ICON_DOWN = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v11M7 10l5 5 5-5M5 20h14"/></svg>';

  function rowHtml(e, ws, linkable) {
    var party = [e.pet, e.res].filter(Boolean).join(' v. ');
    var body = '<span class="item">' + esc(e.item) + '</span><span class="body">' +
      '<span class="no">' + hl(e.case_no || '', ws) + '</span>' +
      '<span class="party">' + hl(party, ws) + '</span>' +
      (e.adv ? '<span class="adv">' + hl(e.adv, ws) + '</span>' : '') +
      '<span class="chips">' + (e.section ? '<span class="chip">' + esc(e.section) + '</span>' : '') +
      (e.apps && e.apps.length ? '<span class="chip warn">' + e.apps.length + ' application</span>' : '') +
      (linkable ? '<span class="chip good">Poori jaankari</span>' : '') + '</span></span>';
    return '<a class="row" href="#/case/' + esc(caseId(e.case_no)) + '">' + body + '</a>';
  }

  function courtsHtml(data, ws, known) {
    var total = 0, courts = 0, html = '';
    data.courts.forEach(function (c) {
      var rows = c.entries.filter(function (e) { return !ws.length || hit(e, ws); });
      if (!rows.length) return;
      total += rows.length; courts += 1;
      html += '<section class="court"><div class="court-h"><div><strong>' + esc(courtName(c)) + '</strong><span>' +
        esc(benchText(c)) + '</span></div><span class="chip">' + esc(c.time || '') + '</span></div>' +
        rows.map(function (e) { return rowHtml(e, ws, known[caseId(e.case_no)]); }).join('') + '</section>';
    });
    return { html: html, total: total, courts: courts };
  }

  // ---------- Aaj ----------
  function viewHome() {
    setTab('home');
    var name = store('ns-name');
    index().then(function (idx) {
      var date = idx.dates[0];
      if (!date) return render('<div class="pad"><div class="empty">Abhi koi cause list nahi aayi.</div></div>');
      return list(date).then(function (data) {
        var known = {}; idx.cases.forEach(function (c) { known[c.id] = 1; });
        var head = '<header class="hero"><div class="kicker">Nyay Sahayak</div><h1>' +
          (name ? 'Namaste, ' + esc(name.split(' ')[0]) + ' ji' : 'Namaste') + '</h1><div class="sub">' +
          esc(fmtDate(date, true)) + ' · Nainital High Court</div></header>';
        if (!name) {
          return render(head + '<div class="pad"><div class="card key"><span class="lbl brand">Pehle ek kaam</span>' +
            '<p class="p">Apna naam likho jaisa cause list mein aata hai (jaise "Bhagwat Mehra"). Phir roz aapke cases yahan apne aap dikhenge.</p>' +
            '<a class="btn" href="#/settings">Naam likho</a></div><a class="btn ghost" href="#/list">Poori cause list dekho</a></div>');
        }
        var r = courtsHtml(data, words(name), known);
        render(head + '<div class="pad"><div class="count"><b>' + r.total + '</b><span>case ' + esc(dayWord(date)) + ' · ' + r.courts +
          ' court mein</span></div>' + (r.html || '<div class="empty">' + esc(dayWord(date)) + ' ki list mein "' + esc(name) +
          '" nahi mila. Naam ki spelling "Main" tab mein jaancho.</div>') +
          '<p class="muted">Court ki PDF cause list se. Update: ' + esc((idx.generated_at || '').replace('T', ' ').slice(0, 16)) +
          ' UTC. Jaane se pehle court ki list se ek baar mila lein.</p></div>');
      });
    }).catch(fail);
  }

  // ---------- Cause list ----------
  function viewList(params) {
    setTab('list');
    index().then(function (idx) {
      var date = params.d || idx.dates[0];
      var q = params.q != null ? params.q : (store('ns-name') || '');
      if (!date) return render('<div class="pad"><div class="empty">Abhi koi cause list nahi aayi.</div></div>');
      return list(date).then(function (data) {
        var known = {}; idx.cases.forEach(function (c) { known[c.id] = 1; });
        var days = idx.dates.slice(0, 7).map(function (d) {
          return '<button type="button" class="day' + (d === date ? ' on' : '') + '" data-day="' + d + '">' +
            esc(fmtDate(d)) + '<small>' + esc(WEEK[new Date(d + 'T00:00:00').getDay()]) + '</small></button>';
        }).join('');
        render('<header class="hero"><div class="kicker">Nainital High Court</div><h1>Cause list</h1>' +
          '<div class="days" role="group" aria-label="Tareekh">' + days + '</div>' +
          '<label class="search">' + ICON_SEARCH + '<input id="q" type="search" autocomplete="off" ' +
          'aria-label="Advocate ka naam, case number ya party" placeholder="Advocate, case no. ya party" value="' + esc(q) + '"></label>' +
          '</header><div class="pad" id="res"></div>');
        var input = document.getElementById('q');
        var res = document.getElementById('res');
        function draw() {
          var ws = words(input.value);
          var r = courtsHtml(data, ws, known);
          res.innerHTML = '<div class="count"><b>' + r.total + '</b><span>case · ' + r.courts + ' court · ' +
            esc(fmtDate(date, true)) + '</span></div>' + (r.html || '<div class="empty">"' + esc(input.value) +
            '" is din ki list mein nahi mila. Sirf surname ya case number likh kar dekho.</div>');
        }
        input.addEventListener('input', draw);
        Array.prototype.forEach.call(document.querySelectorAll('.day'), function (b) {
          b.addEventListener('click', function () { go('#/list?d=' + b.getAttribute('data-day') + '&q=' + encodeURIComponent(input.value)); });
        });
        draw();
      });
    }).catch(fail);
  }

  // ---------- Mere cases ----------
  function viewMine() {
    setTab('mine');
    var name = store('ns-name');
    if (!name) return render('<header class="hero"><h1>Mere cases</h1></header><div class="pad"><div class="empty">Pehle "Main" tab mein apna naam likho.</div><a class="btn" href="#/settings">Naam likho</a></div>');
    index().then(function (idx) {
      var dates = idx.dates.slice(0, 14);
      return Promise.all(dates.map(function (d) { return list(d).catch(function () { return null; }); })).then(function (lists) {
        var ws = words(name), seen = {}, items = [];
        idx.cases.forEach(function (c) {
          if (ws.every(function (w) { return (c.advocates.join(' ') + ' ' + c.title).toUpperCase().indexOf(w) >= 0; })) {
            seen[c.id] = { id: c.id, no: c.case_no, title: c.title, next: c.next_date, listed: [], full: true };
          }
        });
        lists.forEach(function (data) {
          if (!data) return;
          data.courts.forEach(function (c) {
            c.entries.forEach(function (e) {
              if (!e.case_no || !hit(e, ws)) return;
              var id = caseId(e.case_no);
              var x = seen[id] || (seen[id] = { id: id, no: e.case_no, title: [e.pet, e.res].filter(Boolean).join(' v. '), listed: [] });
              x.listed.push({ date: data.date, court: courtName(c), item: e.item });
            });
          });
        });
        Object.keys(seen).forEach(function (k) { items.push(seen[k]); });
        items.sort(function (a, b) { return ((b.listed[0] || {}).date || '').localeCompare((a.listed[0] || {}).date || ''); });
        render('<header class="hero"><div class="kicker">' + esc(name) + '</div><h1>Mere cases</h1><div class="sub">' +
          items.length + ' case · pichhle ' + dates.length + ' din ki cause list + court record se</div></header><div class="pad">' +
          items.map(function (x) {
            var l = x.listed[0];
            return '<a class="card" style="text-decoration:none;color:inherit" href="#/case/' + esc(x.id) + '"><div style="display:flex;justify-content:space-between;gap:8px"><b>' +
              esc(x.no) + '</b>' + (l ? '<span class="chip brand">' + esc(fmtDate(l.date)) + ' · item ' + esc(l.item) + '</span>' :
              (x.next ? '<span class="chip blue">Agli: ' + esc(dmy(x.next)) + '</span>' : '<span class="chip warn">Tareekh nahi</span>')) +
              '</div><span>' + esc(x.title) + '</span>' + (l ? '<span class="muted">' + esc(l.court) + '</span>' : '') +
              (x.full ? '<span class="chips"><span class="chip good">Poori jaankari</span></span>' : '') + '</a>';
          }).join('') + '</div>');
      });
    }).catch(fail);
  }

  // ---------- Case ----------
  function viewCase(id, params) {
    setTab('mine');
    var tab = params.t || 'saar';
    index().then(function (idx) {
      var known = idx.cases.some(function (c) { return c.id === id; });
      if (!known) return caseFromLists(idx, id);
      return caseDoc(id).then(function (c) { caseFull(c, tab, idx); });
    }).catch(fail);
  }

  function caseFromLists(idx, id) {
    var no = id.replace(/-/g, '/');
    return Promise.all(idx.dates.slice(0, 14).map(function (d) { return list(d).catch(function () { return null; }); })).then(function (lists) {
      var found = [];
      lists.forEach(function (data) {
        if (!data) return;
        data.courts.forEach(function (c) { c.entries.forEach(function (e) { if (e.case_no === no) found.push({ d: data.date, c: c, e: e }); }); });
      });
      var e = found[0] && found[0].e;
      render('<header class="hero"><a class="back" href="#/list">' + ICON_BACK + 'Cause list</a><h1>' + esc(e ? [e.pet, e.res].filter(Boolean).join(' v. ') : no) +
        '</h1><div class="sub">' + esc(no) + '</div></header><div class="pad">' +
        found.map(function (f) {
          return '<div class="card"><span class="lbl brand">' + esc(fmtDate(f.d, true)) + '</span><b>' + esc(courtName(f.c)) + ' · item ' + esc(f.e.item) +
            '</b><span class="muted">' + esc(benchText(f.c)) + '</span>' + (f.e.section ? '<span class="chips"><span class="chip">' + esc(f.e.section) + '</span></span>' : '') +
            (f.e.adv ? '<p class="p"><b>Vakeel:</b> ' + esc(f.e.adv) + '</p>' : '') +
            (f.e.apps.length ? '<p class="p"><b>Applications:</b> ' + esc(f.e.apps.join('; ')) + '</p>' : '') + '</div>';
        }).join('') +
        '<div class="empty">Is case ka poora court record (parties, tareekhein, orders) abhi app mein nahi. GitHub par Actions → "Case lookup" → ' +
        esc(no) + ' daalo; 4–5 minute mein yahan aa jaayega.</div></div>');
    });
  }

  function caseFull(c, tab, idx) {
    var pet = (c.petitioners[0] || {}), res = (c.respondents[0] || {});
    var title = [pet.name, res.name].filter(Boolean).join(' v. ') + (c.respondents.length > 1 ? ' & Ors.' : '');
    var n = c.notes || {};
    var tabs = [['saar', 'Saar'], ['dates', 'Tareekhein'], ['orders', 'Orders · ' + c.orders.length]];
    if (n.pros || n.cons) tabs.push(['analysis', 'Vishleshan']);
    if (n.similar) tabs.push(['similar', 'Milte-julte']);
    var latest = (idx.dates || [])[0];
    var html = '<header class="hero"><a class="back" href="#/mine">' + ICON_BACK + 'Mere cases</a><div class="chips">' +
      (c.decision_date ? '<span class="chip good">Disposed · ' + esc(dmy(c.decision_date)) + '</span>' : '<span class="chip warn">Pending</span>') +
      (n.badge ? '<span class="chip good">' + esc(n.badge) + '</span>' : '') + (c.bench_type ? '<span class="chip dark">' + esc(c.bench_type) + '</span>' : '') +
      '</div><h1 style="font-size:25px">' + esc(title) + '</h1><div class="sub">' + esc(c.case_no) + ' · CNR ' + esc(c.cnr) + '</div>' +
      (c.next_date ? '<div class="today"><b>' + esc(fmtDate(c.next_date)) + '</b><span>Agli tareekh' + (c.next_date === latest ? ' · aaj' : '') +
        '<small>' + esc(c.coram || '') + ' · ' + esc(c.stage || '') + '</small></span></div>' : '') +
      '</header><div class="tabs" role="tablist">' + tabs.map(function (t) {
        return '<button type="button" role="tab" data-t="' + t[0] + '" class="' + (t[0] === tab ? 'on' : '') + '" aria-selected="' + (t[0] === tab) + '">' + esc(t[1]) + '</button>';
      }).join('') + '</div><div class="pad">';
    if (tab === 'saar') {
      if (n.summary) html += '<div class="card key"><span class="lbl brand">Case kya hai</span><p class="p">' + esc(n.summary) + '</p>' + (n.source ? '<span class="muted">Srot: ' + esc(n.source) + '</span>' : '') + '</div>';
      if (n.status) html += '<div class="card"><span class="lbl">Abhi kya sthiti hai</span><p class="p">' + esc(n.status) + '</p></div>';
      html += '<div class="card"><span class="lbl">Paksh</span>' +
        c.petitioners.map(function (p, i) { return '<p class="p"><b>Petitioner' + (c.petitioners.length > 1 ? ' ' + (i + 1) : '') + ':</b> ' + esc(p.name) + (p.advocate ? '<br><span class="muted">' + esc(p.advocate) + '</span>' : '') + '</p>'; }).join('') +
        c.respondents.map(function (p, i) { return '<p class="p"><b>Respondent ' + (i + 1) + ':</b> ' + esc(p.name) + (p.advocate ? '<br><span class="muted">' + esc(p.advocate) + '</span>' : '') + '</p>'; }).join('') + '</div>';
      html += '<div class="card"><span class="lbl">Record</span><p class="p">Filing: ' + esc(c.filing.no) + ' · ' + esc(dmy(c.filing.date)) +
        '<br>Registration: ' + esc(dmy(c.registered)) + '<br>Act: ' + esc((c.acts[0] || {}).act || '-') + '</p></div>';
      if (!n.summary && c.orders.length) {
        var last = c.orders[c.orders.length - 1];
        html += '<div class="card"><span class="lbl">Aakhri order · ' + esc(dmy(last.date)) + '</span><p class="p" style="white-space:pre-wrap">' + esc(last.text.slice(0, 900)) + (last.text.length > 900 ? '…' : '') + '</p></div>';
      }
    } else if (tab === 'dates') {
      var ev = (n.timeline || []).concat(c.history.map(function (h) { return { date: dmy(h.hearing_date || h.business_on_date), text: h.purpose || '' }; }));
      html += '<div class="card">' + ev.map(function (e) {
        return '<div class="tl"><span class="rail"><span class="dot"></span><span class="line"></span></span><span class="txt"><b>' + esc(e.date || 'Tareekh nahi likhi') + '</b><span>' + esc(e.text) + '</span></span></div>';
      }).join('') + '</div>';
    } else if (tab === 'orders') {
      html += c.orders.slice().reverse().map(function (o, i) {
        return '<details class="order"' + (i === 0 ? ' open' : '') + '><summary><b>' + esc(dmy(o.date) || 'Order') + '</b><span class="muted">' + esc(o.judge || '') + '</span></summary><pre>' + esc(o.text) + '</pre></details>';
      }).join('') || '<div class="empty">Abhi koi order nahi aaya.</div>';
    } else if (tab === 'analysis') {
      html += pts(n.pros_title || 'Paksh mein', 'good', '+', n.pros) + pts(n.cons_title || 'Saamne wala kya keh sakta hai', 'bad', '–', n.cons) +
        (n.todo ? '<div class="card dark"><span class="lbl light">Court le jaana</span>' + n.todo.map(function (t) { return '<div class="pt"><span class="mark dark">✓</span><span>' + esc(t) + '</span></div>'; }).join('') + '</div>' : '') +
        '<p class="muted">' + esc(n.disclaimer || 'Sirf court ke orders aur database se. Advocate ka review zaroori. Koi jeetne ka % nahi.') + '</p>';
    } else if (tab === 'similar') {
      html += n.similar.map(function (j, i) {
        var open = j.key ? '<a class="card link" href="#/j/' + esc(j.key) + '?from=' + esc(c.id) + '&i=' + i + '">' : '<div class="card">';
        return open + '<div class="chips"><span class="chip ' + (j.court === 'Supreme Court' ? 'dark' : 'blue') + '">' + esc(j.court) + '</span><span class="chip ' + (j.verified ? 'good' : 'warn') + '">' + esc(j.tag) + '</span></div>' +
          '<b class="serif" style="font-size:18px">' + esc(j.title) + '</b><span class="muted">' + esc(j.cite) + '</span><p class="p">' + esc(j.why) + '</p>' +
          (j.quote ? '<p class="p serif quote">' + esc(j.quote) + '</p>' : '') +
          (j.key ? '<span class="go">Poora faisla padho · PDF ' + ICON_NEXT + '</span></a>' : '</div>');
      }).join('');
    }
    render(html + '</div>');
    Array.prototype.forEach.call(document.querySelectorAll('.tabs button'), function (b) {
      b.addEventListener('click', function () { go('#/case/' + c.id + '?t=' + b.getAttribute('data-t')); });
    });
  }
  function pts(title, kind, sign, list) {
    if (!list || !list.length) return '';
    return '<div class="card"><span class="lbl ' + kind + '">' + esc(title) + '</span>' + list.map(function (p) {
      return '<div class="pt"><span class="mark ' + kind + '">' + sign + '</span><span>' + esc(p) + '</span></div>';
    }).join('') + '</div>';
  }

  // ---------- Judgment (milta-julta faisla) ----------
  function viewJudgment(key, params) {
    setTab('mine');
    var from = params.from ? caseDoc(params.from).catch(function () { return null; }) : Promise.resolve(null);
    Promise.all([getJSON('judgments/' + encodeURIComponent(key) + '.json'), from]).then(function (r) {
      var d = r[0], c = r[1], rel = c && c.notes && c.notes.similar ? c.notes.similar[+params.i || 0] : null, n = d.note || {};
      var back = c ? '<a class="back" href="#/case/' + esc(c.id) + '?t=similar">' + ICON_BACK + esc(c.case_no) + '</a>' : '<a class="back" href="#/mine">' + ICON_BACK + 'Mere cases</a>';
      var cite = [d.neutral_citation, d.report_citation, d.case_no && !d.neutral_citation ? d.case_no : null].filter(Boolean).join(' · ');
      var html = '<header class="hero">' + back + '<div class="chips"><span class="chip ' + (d.court === 'Supreme Court' ? 'dark' : 'blue') + '">' + esc(d.court) + '</span>' +
        (rel ? '<span class="chip ' + (rel.verified ? 'good' : 'warn') + '">' + esc(rel.tag) + '</span>' : '') + '</div>' +
        '<h1 style="font-size:25px">' + esc(n.title || (rel && rel.title) || d.title) + '</h1><div class="sub">' + esc(cite) + ' · ' + esc(dmy(d.date)) + '</div></header><div class="pad">';
      if (rel) html += '<div class="card key"><span class="lbl brand">Aapke case se rishta</span><p class="p">' + esc(rel.why) + '</p>' + (rel.quote ? '<p class="p serif quote">' + esc(rel.quote) + '</p>' : '') + '</div>';
      if (n.summary) html += '<div class="card"><span class="lbl">Faisla ek nazar mein</span><p class="p">' + esc(n.summary) + '</p>' + (n.held ? '<p class="p"><b>Court ne kaha:</b> ' + esc(n.held) + '</p>' : '') + '</div>';
      html += pts('Aapke kaam ki baat', 'good', '+', n.use) + pts('Dhyaan rahe', 'bad', '!', n.caution);
      html += '<div class="card"><span class="lbl">Record</span><p class="p">' + [['Court', d.court], ['Tareekh', dmy(d.date)], ['Bench', n.bench || d.judges], ['Citation', cite], ['Nateeja', d.disposal], ['Pages', d.pages]]
        .filter(function (x) { return x[1]; }).map(function (x) { return '<b>' + x[0] + ':</b> ' + esc(x[1]); }).join('<br>') + '</p></div>';
      var paras = {}; d.paras.forEach(function (p) { paras[p.no] = p.text; });
      (n.key_paras || []).forEach(function (no) {
        if (paras[no]) html += '<div class="card"><span class="lbl brand">Para ' + esc(no) + '</span><p class="p serif">' + esc(paras[no]) + '</p></div>';
      });
      (n.quotes || []).forEach(function (q) {
        html += '<div class="card"><span class="lbl brand">' + esc(q.ref) + '</span><p class="p serif">“' + esc(q.text) + '”</p></div>';
      });
      if (d.pdf) html += '<a class="btn" href="judgments/' + esc(d.pdf) + '" download="' + esc(d.pdf_name) + '">' + ICON_DOWN + 'Download PDF</a>' +
        '<a class="btn ghost" href="judgments/' + esc(d.pdf) + '" target="_blank" rel="noopener">PDF kholo</a>';
      html += '<details class="order"><summary><b>Poora faisla (text)</b><span class="muted">' + d.paras.length + ' para</span></summary><pre>' +
        esc(d.head) + '\n\n' + d.paras.map(function (p) { return p.no + '. ' + esc(p.text); }).join('\n\n') + '</pre></details>';
      html += '<p class="muted">' + esc(n.disclaimer || 'Text PDF se nikala gaya hai; court mein PDF (asli copy) hi padhein.') + ' Srot: ' + esc(d.source) + '.</p>';
      render(html + '</div>');
    }).catch(fail);
  }

  // ---------- Main (settings) ----------
  function viewSettings() {
    setTab('settings');
    var name = store('ns-name') || '';
    render('<header class="hero"><h1>Main</h1><div class="sub">Ye jaankari sirf is phone par rehti hai.</div></header><div class="pad">' +
      '<form id="f" class="card"><label class="field"><span>Mera naam (jaisa cause list mein aata hai)</span>' +
      '<input id="name" autocomplete="name" placeholder="Jaise: Bhagwat Mehra" value="' + esc(name) + '"></label>' +
      '<button class="btn" type="submit">Save karo</button></form>' +
      '<div class="card"><span class="lbl">Phone par app ki tarah</span><p class="p"><b>iPhone:</b> Safari → Share → "Add to Home Screen".<br><b>Android:</b> Chrome → ⋮ menu → "Add to Home screen" / "Install app".</p></div>' +
      '<p class="muted">Cause list roz subah 6, 8 aur 10 baje apne aap update hoti hai.</p></div>');
    document.getElementById('f').addEventListener('submit', function (ev) {
      ev.preventDefault();
      store('ns-name', document.getElementById('name').value.trim());
      go('#/');
    });
  }

  // Router: '#/...' links; kuch jagah (jaise embedded frame) URL hash nahi badalta, isliye apna 'cur' bhi.
  var cur = location.hash || '#/';
  function go(h) {
    cur = h;
    try { history.replaceState(null, '', h); } catch (e) { /* frame mein mana ho to bhi chale */ }
    route();
  }
  document.addEventListener('click', function (ev) {
    var a = ev.target.closest && ev.target.closest('a[href^="#/"]');
    if (!a) return;
    ev.preventDefault();
    go(a.getAttribute('href'));
  });
  function route() {
    var h = cur.replace(/^#/, '') || '/';
    var parts = h.split('?'), path = parts[0], params = {};
    (parts[1] || '').split('&').forEach(function (kv) { if (!kv) return; var p = kv.split('='); params[p[0]] = decodeURIComponent(p[1] || ''); });
    if (path === '/' || path === '') return viewHome();
    if (path === '/list') return viewList(params);
    if (path === '/mine') return viewMine();
    if (path === '/settings') return viewSettings();
    if (path.indexOf('/case/') === 0) return viewCase(path.slice(6), params);
    if (path.indexOf('/j/') === 0) return viewJudgment(decodeURIComponent(path.slice(3)), params);
    viewHome();
  }
  window.addEventListener('hashchange', function () { cur = location.hash || '#/'; route(); });
  route();
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () { navigator.serviceWorker.register('sw.js').catch(function () {}); });
  }
})();
