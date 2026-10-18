/* Nyay Sahayak — Nainital HC cause list + cases. Koi server nahi: data/ ki JSON files (GitHub roz banata hai). */
(function () {
  'use strict';
  var view = document.getElementById('view');
  var cache = { index: null, lists: {}, cases: {}, khoj: null, api: undefined };
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
    // Beeti tareekh ki list nahi dikhaate: sirf aaj aur aage ki (purani data mein rehti hai)
    return cache.index ? Promise.resolve(cache.index) : getJSON('data/index.json').then(function (d) {
      var t = new Date(), pad = function (n) { return (n < 10 ? '0' : '') + n; };
      var today = t.getFullYear() + '-' + pad(t.getMonth() + 1) + '-' + pad(t.getDate());
      d.allDates = d.dates;
      d.dates = d.dates.filter(function (x) { return x >= today; });
      cache.index = d; return d;
    });
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
  function pickDay(dates) { // kaunsi list dikhaayein: aaj ki; shaam 3 baje ke baad agle din ki; warna sabse nayi
    var t = new Date(), pad = function (n) { return (n < 10 ? '0' : '') + n; };
    var today = t.getFullYear() + '-' + pad(t.getMonth() + 1) + '-' + pad(t.getDate());
    var up = dates.filter(function (d) { return t.getHours() >= 15 ? d > today : d >= today; }).sort();
    return up[0] || dates[0];
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
  var NAV = {
    home: ['#/', 'Aaj', '<path d="M4 11l8-7 8 7v9h-5v-6H9v6H4z"/>'],
    mycase: ['#/', 'Mera case', '<path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>'],
    khoj: ['#/khoj', 'Khoj', '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>'],
    list: ['#/list', 'Cause list', '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M8 3v4M16 3v4M4 10h16"/>'],
    mine: ['#/mine', 'Mere cases', '<path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5"/>'],
    settings: ['#/settings', 'Main', '<circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/>']
  };
  function role() { return store('ns-role') || (store('ns-name') ? 'advocate' : null); } // purane users: naam hai to advocate
  function drawNav() {
    var tabs = role() === 'party' ? ['mycase', 'khoj', 'list', 'settings'] : ['home', 'list', 'khoj', 'mine', 'settings'];
    var nav = document.querySelector('.nav');
    nav.hidden = !role();
    nav.innerHTML = tabs.map(function (t) {
      return '<a href="' + NAV[t][0] + '" data-tab="' + t + '"><svg viewBox="0 0 24 24" aria-hidden="true">' + NAV[t][2] + '</svg>' + NAV[t][1] + '</a>';
    }).join('');
  }
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

  function rowHtml(e, ws, level) { // level: 2 = record + vishleshan, 1 = sirf record, khaali = kuch nahi
    var party = [e.pet, e.res].filter(Boolean).join(' v. ');
    var body = '<span class="item">' + esc(e.item) + '</span><span class="body">' +
      '<span class="no">' + hl(e.case_no || '', ws) + '</span>' +
      '<span class="party">' + hl(party, ws) + '</span>' +
      (e.adv ? '<span class="adv">' + hl(e.adv, ws) + '</span>' : '') +
      '<span class="chips">' + (e.section ? '<span class="chip">' + esc(e.section) + '</span>' : '') +
      (e.apps && e.apps.length ? '<span class="chip warn">' + e.apps.length + ' application</span>' : '') +
      (level === 2 ? '<span class="chip good">✓ Vishleshan</span>' : level ? '<span class="chip blue">Record · vishleshan baaki</span>' :
        '<span class="chip warn">Vishleshan nahi</span>') + '</span></span>';
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

  // ---------- Pehli baar: aap kaun hain ----------
  function viewStart() {
    drawNav();
    render('<header class="hero welcome"><div class="kicker">Nyay Sahayak</div><h1>Namaste</h1>' +
      '<div class="sub">Nainital High Court · roz ki cause list, aapke cases aur unka vishleshan</div></header>' +
      '<div class="pad"><p class="p"><b>Aap kaun hain?</b> Usi hisaab se app aapko dikhayega.</p>' +
      '<button type="button" class="card pick" data-role="advocate"><span class="lbl brand">Advocate</span>' +
      '<b class="serif">Main vakeel hoon</b><span class="muted">Mere naam se roz ke cases, poori cause list, har case ka vishleshan aur milte-julte faisle.</span></button>' +
      '<button type="button" class="card pick" data-role="party"><span class="lbl brand">Party / aam vyakti</span>' +
      '<b class="serif">Mera apna case hai</b><span class="muted">Apna case number daalo: kab lagega, kis court mein, ab tak kya hua aur aage kya.</span></button>' +
      '<p class="muted">Baad mein "Main" mein badal sakte hain. Sab jaankari sirf is phone par rehti hai.</p></div>');
    Array.prototype.forEach.call(document.querySelectorAll('.pick'), function (b) {
      b.addEventListener('click', function () {
        store('ns-role', b.getAttribute('data-role'));
        drawNav();
        go(b.getAttribute('data-role') === 'party' ? '#/' : '#/settings');
      });
    });
  }

  // ---------- Party: mera case ----------
  var TYPES = ['WPSS', 'WPSB', 'WPMS', 'WPMB', 'WPCRL', 'WPPIL', 'SPA', 'BA1', 'ABA', 'C482', 'C528', 'CRLA', 'CRLR',
    'FA', 'SA', 'AO', 'CLR', 'CLCON', 'ITA', 'ARBAP'];
  function myCases() { try { return JSON.parse(store('ns-cases') || '[]'); } catch (e) { return []; } }
  function upcoming(idx, today) {
    var dates = idx.dates.filter(function (d) { return d >= today; }).sort();
    return Promise.all(dates.map(function (d) { return list(d).catch(function () { return null; }); }));
  }
  function todayIso() {
    var t = new Date(), pad = function (n) { return (n < 10 ? '0' : '') + n; };
    return t.getFullYear() + '-' + pad(t.getMonth() + 1) + '-' + pad(t.getDate());
  }
  function viewMyCase() {
    setTab('mycase');
    var mine = myCases();
    var form = '<form id="add" class="card"><span class="lbl brand">Case jodo</span><div class="trio">' +
      '<label class="field"><span>Type</span><select id="ct">' + TYPES.map(function (t) { return '<option>' + t + '</option>'; }).join('') + '</select></label>' +
      '<label class="field"><span>Number</span><input id="cn" inputmode="numeric" pattern="[0-9]*" placeholder="818" required></label>' +
      '<label class="field"><span>Saal</span><input id="cy" inputmode="numeric" pattern="[0-9]*" placeholder="2025" maxlength="4" required></label></div>' +
      '<button class="btn" type="submit">Dekho</button><span class="muted">Case number aapke vakeel ki parchi ya court ki receiving par hota hai, jaise WPSS / 818 / 2025.</span></form>';
    index().then(function (idx) {
      return upcoming(idx, todayIso()).then(function (lists) {
        var cards = mine.map(function (no) {
          var id = caseId(no), rec = idx.cases.filter(function (c) { return c.id === id; })[0], hits = [];
          lists.forEach(function (data) {
            if (!data) return;
            data.courts.forEach(function (c) { c.entries.forEach(function (e) { if (e.case_no === no) hits.push({ d: data.date, c: c, e: e }); }); });
          });
          var h = hits[0];
          return '<a class="card link mycase" href="#/case/' + esc(id) + '"><div class="mc-top"><b>' + esc(no) + '</b>' +
            (h ? '<span class="chip brand">' + esc(dayWord(h.d)) + ' lagega</span>' : rec && rec.next_date ? '<span class="chip blue">Agli: ' + esc(dmy(rec.next_date)) + '</span>' : '<span class="chip">Tareekh abhi nahi</span>') +
            '</div><span>' + esc(rec ? rec.title : (h ? [h.e.pet, h.e.res].filter(Boolean).join(' v. ') : '')) + '</span>' +
            (h ? '<div class="today"><b>' + esc(fmtDate(h.d)) + '</b><span>' + esc(courtName(h.c)) + ' · item ' + esc(h.e.item) + '<small>' + esc(benchText(h.c)) + (h.c.time ? ' · ' + esc(h.c.time) : '') + '</small></span></div>' : '') +
            '<span class="go">' + (rec ? 'Poori jaankari aur vishleshan' : 'Dekho') + ICON_NEXT + '</span></a>';
        }).join('');
        render('<header class="hero"><div class="kicker">Nainital High Court</div><h1>Mera case</h1><div class="sub">' +
          (mine.length ? mine.length + ' case · cause list aate hi yahan dikhega' : 'Apna case number daalo') + '</div></header><div class="pad">' +
          cards + form + aage(idx.dates, todayIso()) +
          '<p class="muted">Court ki cause list se (court ki site aur eCourts). Update: ' + esc((idx.generated_at || '').replace('T', ' ').slice(0, 16)) + ' UTC.</p></div>');
        bindAdd();
      });
    }).catch(function () { render('<header class="hero"><h1>Mera case</h1></header><div class="pad">' + form + '</div>'); bindAdd(); });
    function bindAdd() {
      document.getElementById('add').addEventListener('submit', function (ev) {
        ev.preventDefault();
        var no = document.getElementById('ct').value + '/' + (+document.getElementById('cn').value) + '/' + document.getElementById('cy').value.trim();
        if (!/^[A-Z0-9]+\/\d+\/\d{4}$/.test(no)) return;
        var m = myCases().filter(function (x) { return x !== no; }); m.unshift(no);
        store('ns-cases', JSON.stringify(m.slice(0, 20)));
        go('#/case/' + caseId(no));
      });
    }
  }

  // ---------- Khoj: apne case ki baat likho -> vishay, review, supporting faisle ----------
  // Hinglish shabd -> English (niyam English faislon ke shabdon par bane hain)
  var HING = [
    [/anukamp|mritak ?ashrit|ashrit/i, 'compassionate appointment dying in harness'], [/mrityu|maut|dehant|nidhan|guzar/i, 'died death harness'],
    [/naukri|niyukti/i, 'appointment'], [/aavedan|avedan|arzi|application/i, 'application'], [/\bder\b|vilamb|der se|late/i, 'delay belated'],
    [/vivahit beti|shadi ?shuda beti|married beti/i, 'married daughter'], [/bahu/i, 'daughter in law'], [/doosri patni|dusri patni|second wife/i, 'second wife'],
    [/nabalig|minor/i, 'minor years after'], [/pehle se naukri|already (in )?job|(bhai|behen|bahan|maa|mother|brother|sister|pati|husband)[^.]{0,40}(naukri|job|service|employ)|(naukri|job|service)[^.]{0,40}(bhai|behen|brother|sister)/i, 'already employed gainfully employed brother employed brother government service'],
    [/sarkari naukri|government job|govt job|sarkari job/i, 'government service'], [/pita|father|papa|pitaji/i, 'father'],
    [/garib|aarthik|paise nahi|tangi/i, 'indigent financial condition penury'], [/pension|pensan/i, 'pension rules pensionary benefits'],
    [/padonnati|pramotion|promotion|tarakki/i, 'promotion seniority departmental promotion committee'], [/varishtata|seniority/i, 'seniority list'],
    [/tabadla|transfer/i, 'transfer order transfer policy'], [/niyamit|pakka karo|regulari/i, 'regularisation services regularization rules'],
    [/dainik|daily wage|samvida|contract par|upnal|outsourc/i, 'daily wage contractual employee'], [/nilamb|suspend/i, 'suspension order placed under suspension'],
    [/barkhast|nikal diya|nikala|terminat|dismiss/i, 'termination services dismissal service disciplinary proceedings'],
    [/vetan|tankhwah|salary|pay scale/i, 'pay scale parity equal pay for equal work'], [/vasooli|recovery/i, 'recovery excess payment'],
    [/gratuity|gratuiti|leave encash/i, 'gratuity leave encashment'], [/agrim zamanat|anticipatory/i, 'anticipatory bail'],
    [/zamanat|jamanat|bail/i, 'bail section 439'], [/dahej|dowry|498/i, 'dowry prohibition 498A'], [/talak|talaq|divorce/i, 'decree of divorce'],
    [/gujara|kharcha|maintenance|bharan ?poshan/i, 'maintenance section 125 interim maintenance'], [/cheque|check bounce/i, 'negotiable instruments 138'],
    [/zameen|jameen|bhumi|khatauni|daakhil|dakhil kharij|mutation/i, 'mutation revenue records khatauni'], [/kiraye?dar|makan malik|eviction/i, 'eviction tenant landlord tenant'],
    [/hatya|murder|302/i, 'section 302'], [/balatkar|rape|376/i, 'section 376 rape'], [/ganja|charas|smack|ndps|nasha/i, 'NDPS Act'],
    [/fir (radd|quash)|quash|radd/i, 'quash first information report section 482'], [/durghatna|accident|mact/i, 'Motor Accident Claims Tribunal just compensation'],
    [/bachche ki custody|custody/i, 'custody child welfare of the child'], [/tender|theka/i, 'tender bid notice inviting tender'],
    [/bharti|recruitment|vigyapti|advertisement/i, 'eligibility qualification advertisement merit list select list'], [/aarakshan|reservation/i, 'reservation recruitment horizontal reservation']
  ];
  function expand(text) {
    var extra = HING.filter(function (h) { return h[0].test(text); }).map(function (h) { return h[1]; });
    return text + ' ' + extra.join(' ');
  }
  function ruleHit(rules, text) {
    return rules.filter(function (alt) { return alt.every(function (r) { return new RegExp(r, 'i').test(text); }); }).length;
  }
  function khojIndex() {
    return cache.khoj ? Promise.resolve(cache.khoj) : getJSON('data/khoj/index.json').then(function (d) { cache.khoj = d; return d; });
  }
  var GOOD = ['Paksh mein', 'Aanshik paksh mein', 'Nirdesh: vibhag vichaar kare'];
  function judgCard(j, label) {
    var good = GOOD.indexOf(j.tag.split(' · ')[0]) >= 0, bad = /^Khilaf/.test(j.tag);
    return '<a class="card link" href="#/kj/' + j.id + (label ? '?m=' + encodeURIComponent(label) : '') + '"><div class="chips"><span class="chip ' + (j.court === 'Supreme Court' ? 'dark' : 'blue') + '">' + esc(j.court) + '</span>' +
      '<span class="chip ' + (good ? 'good' : bad ? 'warn' : '') + '">' + esc(j.tag.split(' · ')[0]) + '</span></div>' +
      '<b class="serif" style="font-size:17px">' + esc(j.title) + '</b><span class="muted">' + esc(j.cite) + '</span>' +
      '<p class="p serif quote">' + esc(j.quote) + '</p><span class="go">Poora faisla padho' + ICON_NEXT + '</span></a>';
  }
  function sides(list) { // support / against / anya — case ke 'Faisle' tab aur saar ke liye
    var seen = {}, out = { good: [], bad: [], other: [] };
    list.forEach(function (j) {
      var k = j.title + j.cite; if (seen[k]) return; seen[k] = 1;
      var t = (j.tag || '').split(' · ')[0];
      out[j.side || (GOOD.indexOf(t) >= 0 ? 'good' : /^Khilaf/.test(t) ? 'bad' : 'other')].push(j);
    });
    return out;
  }
  function judgGroups(list, label) {
    var card = function (j) { return judgCard(j, label); };
    var seen = {}, uniq = list.filter(function (j) { var k = j.title + j.cite; if (seen[k]) return false; seen[k] = 1; return true; });
    var good = uniq.filter(function (j) { return GOOD.indexOf(j.tag.split(' · ')[0]) >= 0; });
    var bad = uniq.filter(function (j) { return /^Khilaf/.test(j.tag); });
    var other = uniq.filter(function (j) { return good.indexOf(j) < 0 && bad.indexOf(j) < 0; });
    return (good.length ? '<span class="lbl good">Aapke paksh mein ja sakte hain · ' + good.length + '</span>' + good.map(card).join('') : '') +
      (bad.length ? '<span class="lbl bad">Dhyaan rahe: in mein court ne maang nahi maani · ' + bad.length + '</span>' + bad.map(card).join('') : '') +
      (other.length ? '<span class="lbl">Anya (nipataara / nateeja saaf nahi) · ' + other.length + '</span>' + other.map(card).join('') : '');
  }
  function topicResult(t, text, others) {
    return getJSON('data/khoj/t/' + t.id + '.json').then(function (d) {
      var found = t.issues.filter(function (x) { return text && ruleHit(x.rules, text); });
      var focus = [];
      found.forEach(function (x) { focus = focus.concat((d.by_mudda[x.mudda] || []).map(function (j) { j._m = x.mudda; return j; })); });
      var html = '<div class="card key"><span class="lbl brand">' + (text ? 'Aapke case ka vishay' : 'Vishay') + '</span><div class="chips">' +
        [t.shreni, t.vishay, t.upvishay].map(function (x) { return '<span class="chip blue">' + esc(x) + '</span>'; }).join('') +
        found.map(function (x) { return '<span class="chip brand">' + esc(x.mudda) + '</span>'; }).join('') + '</div>' +
        '<span class="muted">Database mein is vishay ke ' + t.faisle + ' mukhya faisle' + (t.jaancha ? '' : ' · is vishay ka niyam abhi jaancha ja raha hai') + '</span>' +
        (others && others.length ? '<span class="muted">Ye bhi ho sakta hai: ' + others.map(function (o) { return '<a href="#/khoj/t/' + o.id + '">' + esc(o.upvishay) + '</a>'; }).join(', ') + '</span>' : '') + '</div>';
      if (t.issues.length) {
        html += '<div class="card"><span class="lbl">Case review: is vishay ke mudde</span>' + t.issues.map(function (x) {
          var on = found.indexOf(x) >= 0;
          return '<div class="pt"><span class="mark ' + (on ? 'good' : 'dark') + '">' + (on ? '✓' : '?') + '</span><span>' + esc(x.mudda) +
            ' <span class="muted">· ' + x.faisle + ' faisle · ' + (on ? 'aapki baat mein hai' : 'kya yeh aapke case mein hai? Ho to likh kar dobara khojo') + '</span></span></div>';
        }).join('') + '</div>';
      }
      html += '<div class="card dark"><span class="lbl light">Vakeel ke paas le jaana</span>' +
        ['Petition / aavedan ki copy aur uski tareekh ka saboot', 'Vibhag ka order (reject / latkaane wala) aur usmein likhi wajah',
          'Jo niyam ya GO lagta hai uski copy', 'Neeche ke faislon mein se jo aapke tathyon se milte hon']
          .map(function (x) { return '<div class="pt"><span class="mark dark">✓</span><span>' + esc(x) + '</span></div>'; }).join('') + '</div>';
      if (focus.length) {
        var g = focus.filter(function (j) { return GOOD.indexOf(j.tag.split(' · ')[0]) >= 0; }).length, b = focus.filter(function (j) { return /^Khilaf/.test(j.tag); }).length;
        html += '<div class="card key"><span class="lbl brand">Aapke sawaal par court ka rukh</span><p class="p">' + esc(found.map(function (x) { return x.mudda; }).join(', ')) +
          ' ke ' + focus.length + ' chune faislon mein: <b>' + g + '</b> mein court ne maang maani ya vibhag ko dobara vichaar karne ko kaha, <b>' + b + '</b> mein nahi maani.</p>' +
          '<span class="muted">Har faisla apne tathyon par hai — kaunsa aap par lagta hai, neeche padh kar dekho.</span></div>' +
          judgGroups(focus, found[0].mudda) +
          '<details class="order"><summary><b>Is vishay ke aur faisle</b><span class="muted">' + d.judgments.length + '</span></summary><div class="pad">' + judgGroups(d.judgments, t.upvishay) + '</div></details>';
      } else {
        html += judgGroups(d.judgments, t.upvishay);
      }
      html += '<p class="muted">Faisle niyamon se machine ne chune hain; quote faisle ka asli paragraph hai. Har faisla aapke tathyon par lagta hai ya nahi, yeh vakeel se jaanch lein. Koi jeetne ka % nahi.</p>';
      return html;
    });
  }
  // Likhi hui baat -> vishay (phone par niyam) -> us vishay ke support / against faisle, 'out' element mein
  function khojInto(idx, raw, out) {
    var text = expand(raw);
    var scored = idx.topics.map(function (t) { return { t: t, s: ruleHit(t.rules, text) + 0.5 * t.issues.filter(function (x) { return ruleHit(x.rules, text); }).length }; })
      .filter(function (x) { return x.s > 0; }).sort(function (a, b) { return b.s - a.s; });
    if (!scored.length) { out.innerHTML = '<div class="empty">Vishay pakad mein nahi aaya. Thoda aur likho: kis vibhag / kaam ka case hai, kya maanga, kis wajah se mana hua. Ya Khoj tab mein vishay chuno.</div>'; return; }
    out.innerHTML = '<div class="empty">Dhoondh rahe hain…</div>';
    topicResult(scored[0].t, text, scored.slice(1, 4).map(function (x) { return x.t; })).then(function (h) { out.innerHTML = '<div class="pad" style="padding:0">' + h + '</div>'; }).catch(fail);
  }
  // Case ke page par: orders mein vishay na mile to advocate ek-do line likhe; phone par yaad rehta hai
  function caseKhojCard(id, why) {
    var saved = store('ns-cv-' + id) || '';
    return '<form class="card key" id="ckf"><span class="lbl brand">Is case ki baat likho · support / against faisle</span>' +
      '<p class="p">' + esc(why) + '</p><label class="field"><span>Case mein kya maanga, kis baat par vivaad (Hindi-English mein)</span>' +
      '<textarea id="ckt" rows="3" placeholder="Jaise: 12 saal se daily wage par kaam, vibhag regularise nahi kar raha">' + esc(saved) + '</textarea></label>' +
      '<button class="btn" type="submit">' + ICON_SEARCH + 'Faisle dikhao</button></form><div id="ckr"></div>';
  }
  function caseKhojWire(id) {
    var f = document.getElementById('ckf');
    if (!f) return;
    var run = function () {
      var raw = document.getElementById('ckt').value.trim();
      if (!raw) return;
      store('ns-cv-' + id, raw);
      khojIndex().then(function (idx) { khojInto(idx, raw, document.getElementById('ckr')); })
        .catch(function () { document.getElementById('ckr').innerHTML = '<div class="empty">Khoj ka data abhi nahi khula. Thodi der mein dobara.</div>'; });
    };
    f.addEventListener('submit', function (ev) { ev.preventDefault(); run(); });
    if (store('ns-cv-' + id)) run();
  }

  function viewKhoj() {
    setTab('khoj');
    var draft = store('ns-khoj') || '';
    khojIndex().then(function (idx) {
      var byShreni = {};
      idx.topics.forEach(function (t) { (byShreni[t.shreni] = byShreni[t.shreni] || []).push(t); });
      render('<header class="hero"><div class="kicker">Khoj</div><h1>Apne case ki baat likho</h1>' +
        '<div class="sub">Vishay, case review aur supporting faisle — Supreme Court aur Nainital HC ke database se</div></header><div class="pad">' +
        '<form id="kf" class="card"><label class="field"><span>Case mein kya hua (Hindi-English mein, jaise bolte ho)</span>' +
        '<textarea id="kt" rows="5" placeholder="Jaise: Pita PAC mein Nayak the, 2016 mein naukri mein rehte mrityu hui. Maine anukampa naukri ka aavedan diya, Commandant ne der ka kaaran bata kar reject kar diya.">' + esc(draft) + '</textarea></label>' +
        '<button class="btn" type="submit">' + ICON_SEARCH + 'Khojo</button></form><div id="kr"></div>' +
        '<span class="lbl">Ya vishay chuno</span>' + Object.keys(byShreni).map(function (sh) {
          return '<details class="order"><summary><b>' + esc(sh) + '</b><span class="muted">' + byShreni[sh].length + ' vishay</span></summary><div class="pad">' +
            byShreni[sh].map(function (t) { return '<a class="row" href="#/khoj/t/' + t.id + '"><span class="body"><span class="no">' + esc(t.upvishay) + '</span><span class="adv">' + esc(t.vishay) + ' · ' + t.faisle + ' faisle</span></span></a>'; }).join('') + '</div></details>';
        }).join('') + '</div>');
      var kf = document.getElementById('kf');
      kf.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var raw = document.getElementById('kt').value.trim();
        store('ns-khoj', raw);
        khojInto(idx, raw, document.getElementById('kr'));
      });
    }).catch(function () { render('<div class="pad"><div class="empty">Khoj ka data abhi site par nahi hai. Thodi der mein dobara kholo.</div></div>'); });
  }
  function viewKhojJudgment(id, params) {
    setTab('khoj');
    getJSON('data/khoj/j/' + encodeURIComponent(id) + '.json').then(function (d) {
      var label = params.m || '', hits = d.hits[label] || [].concat.apply([], Object.keys(d.hits).map(function (k) { return d.hits[k]; }));
      var bySeq = {}; d.paras.forEach(function (p) { bySeq[p.seq] = p; });
      var cite = [d.cite, d.report, d.case_no && !d.cite ? d.case_no : null].filter(Boolean).join(' · ');
      var good = GOOD.indexOf(d.nateeja) >= 0, bad = /^Khilaf/.test(d.nateeja || '');
      var back = params.from ? '<a class="back" href="#/case/' + esc(params.from) + '?t=similar">' + ICON_BACK + esc(params.from.replace(/-/g, '/')) + '</a>' :
        '<a class="back" href="#/khoj">' + ICON_BACK + 'Khoj</a>';
      var html = '<header class="hero">' + back + '<div class="chips"><span class="chip ' + (d.court === 'Supreme Court' ? 'dark' : 'blue') + '">' + esc(d.court) + '</span>' +
        (d.nateeja ? '<span class="chip ' + (good ? 'good' : bad ? 'warn' : '') + '">' + esc(d.nateeja) + '</span>' : '') + '</div>' +
        '<h1 style="font-size:24px">' + esc(d.title) + '</h1><div class="sub">' + esc(cite) + ' · ' + esc(dmy(d.date)) + '</div></header><div class="pad">';
      var seen = {};
      var top = hits.filter(function (q) { if (seen[q] || !bySeq[q]) return false; seen[q] = 1; return true; });
      if (top.length) html += '<span class="lbl brand">' + esc(label ? label + ' — faisle mein kya kaha' : 'Kaam ke paragraph') + '</span>' +
        top.map(function (q) { var p = bySeq[q]; return '<div class="card key"><span class="lbl">' + (p.no ? 'Para ' + esc(p.no) : 'Paragraph') + '</span><p class="p serif">' + esc(p.text) + '</p></div>'; }).join('');
      html += '<div class="card"><span class="lbl">Record</span><p class="p">' + [['Court', d.court], ['Tareekh', dmy(d.date)], ['Bench', d.judges], ['Citation', cite],
        ['Court ka nateeja', d.disposal], ['Pages', d.pages]].filter(function (x) { return x[1]; }).map(function (x) { return '<b>' + x[0] + ':</b> ' + esc(x[1]); }).join('<br>') + '</p></div>';
      html += '<details class="order" open><summary><b>Poora faisla</b><span class="muted">' + d.paras.length + ' hisse</span></summary><div class="ft">' +
        d.paras.map(function (p) { return '<p class="p serif' + (seen[p.seq] ? ' hit' : '') + '">' + (p.no ? '<b>' + esc(p.no) + '.</b> ' : '') + esc(p.text) + '</p>'; }).join('') + '</div></details>';
      html += '<p class="muted">Text court ki PDF se nikala gaya hai; court mein asli copy hi padhein. Faisla machine ne chuna hai — aapke tathyon par lagta hai ya nahi, vakeel se jaanch lein.</p>';
      render(html + '</div>');
    }).catch(fail);
  }
  function viewKhojTopic(id) {
    setTab('khoj');
    khojIndex().then(function (idx) {
      var t = idx.topics.filter(function (x) { return x.id === id; })[0];
      if (!t) return viewKhoj();
      return topicResult(t, '', []).then(function (h) {
        render('<header class="hero"><a class="back" href="#/khoj">' + ICON_BACK + 'Khoj</a><div class="kicker">' + esc(t.shreni + ' · ' + t.vishay) + '</div><h1>' + esc(t.upvishay) + '</h1></header><div class="pad">' + h + '</div>');
      });
    }).catch(fail);
  }

  // ---------- Aaj ----------
  function viewHome() {
    setTab('home');
    var name = store('ns-name');
    index().then(function (idx) {
      var date = pickDay(idx.dates);
      if (!date) return render('<div class="pad"><div class="empty">Aaj ya aage ki cause list abhi nahi aayi. Court shaam ko agle din ki list daalta hai; aate hi yahan dikhegi.</div></div>');
      return list(date).then(function (data) {
        var known = {}; idx.cases.forEach(function (c) { known[c.id] = c.a || 1; });
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
          aage(idx.dates, date) + '<p class="muted">Court ki PDF cause list se. Update: ' + esc((idx.generated_at || '').replace('T', ' ').slice(0, 16)) +
          ' UTC. Jaane se pehle court ki list se ek baar mila lein.</p></div>');
      });
    }).catch(fail);
  }

  function aage(dates, shown) { // aage ki tareekhon ki list bhi aa chuki ho to link
    var later = dates.filter(function (d) { return d > shown; }).sort();
    if (!later.length) return '';
    return '<p class="p">Aage ki list bhi aa gayi: ' + later.map(function (d) {
      return '<a href="#/list?d=' + d + '">' + esc(fmtDate(d)) + '</a>';
    }).join(' · ') + '</p>';
  }

  // ---------- Cause list ----------
  function viewList(params) {
    setTab('list');
    index().then(function (idx) {
      var date = params.d || pickDay(idx.dates);
      var q = params.q != null ? params.q : (store('ns-name') || '');
      if (!date) return render('<div class="pad"><div class="empty">Aaj ya aage ki cause list abhi nahi aayi. Court shaam ko agle din ki list daalta hai; aate hi yahan dikhegi.</div></div>');
      return list(date).then(function (data) {
        var known = {}; idx.cases.forEach(function (c) { known[c.id] = c.a || 1; });
        var days = idx.dates.slice().sort().slice(0, 7).map(function (d) {
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
      var dates = (idx.allDates || idx.dates).slice(0, 14);
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
  // ---------- 'Abhi vishleshan karo': GitHub par record + vishleshan (scripts/maango_api.py ke zariye) ----------
  function apiUrl() {
    return cache.api !== undefined ? Promise.resolve(cache.api) :
      getJSON('config.json').then(function (d) { return (cache.api = d.api || ''); }, function () { return (cache.api = ''); });
  }
  function maangoCard(no, what) {
    var t = +store('ns-maango-' + caseId(no)) || 0, recent = Date.now() - t < 3 * 3600 * 1000;
    return '<div class="card key" id="maango"><span class="lbl brand">' + esc(what) + '</span>' +
      (recent ? '<p class="p">Maang ' + new Date(t).toLocaleTimeString('hi-IN', { hour: '2-digit', minute: '2-digit' }) +
        ' baje bheji. Court se record aur vishleshan ~20-30 minute mein yahin aa jaayega; app dobara kholiye.</p>' :
        '<p class="p">Dabaiye: court se poora record, saare orders, vishay-mudde aur milte-julte faisle (asli paragraph ke saath) yahin aa jaayenge.</p>' +
        '<button type="button" class="btn" id="maango-btn" data-no="' + esc(no) + '">Abhi vishleshan karo</button>') + '</div>';
  }
  function maangoWire() {
    var b = document.getElementById('maango-btn');
    if (!b) return;
    b.addEventListener('click', function () {
      var no = b.getAttribute('data-no'), box = document.getElementById('maango');
      b.disabled = true; b.textContent = 'Bhej rahe hain…';
      apiUrl().then(function (api) {
        if (!api) throw new Error('band');
        return fetch(api.replace(/\/$/, '') + '/maango', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ case: no }) }).then(function (r) { return r.json(); });
      }).then(function (d) {
        if (d.ok) store('ns-maango-' + caseId(no), String(Date.now()));
        box.innerHTML = '<span class="lbl brand">' + (d.ok ? 'Maang bhej di' : 'Abhi nahi hua') + '</span><p class="p">' + esc(d.msg) + '</p>';
      }).catch(function (err) {
        box.innerHTML = '<span class="lbl brand">Abhi nahi hua</span><p class="p">' + (err.message === 'band' ?
          'Yeh button abhi chalu nahi hua. Aaj aur aage ki list ke saare cases apne aap line mein hain; jaldi yahan aa jaayenge.' :
          'Server se jud nahi paaye (pehli baar ~1 minute lagta hai). Thodi der baad dobara dabaiye.') + '</p>';
      });
    });
  }

  function viewCase(id, params) {
    setTab(role() === 'party' ? 'mycase' : 'mine');
    var tab = params.t || 'saar';
    index().then(function (idx) {
      var known = idx.cases.some(function (c) { return c.id === id; });
      if (!known) return caseFromLists(idx, id);
      return caseDoc(id).then(function (c) { caseFull(c, tab, idx); });
    }).catch(fail);
  }

  function caseFromLists(idx, id) {
    var no = id.replace(/-/g, '/');
    return Promise.all((idx.allDates || idx.dates).slice(0, 14).map(function (d) { return list(d).catch(function () { return null; }); })).then(function (lists) {
      var found = [];
      lists.forEach(function (data) {
        if (!data) return;
        data.courts.forEach(function (c) { c.entries.forEach(function (e) { if (e.case_no === no) found.push({ d: data.date, c: c, e: e }); }); });
      });
      var e = found[0] && found[0].e;
      render('<header class="hero"><a class="back" href="' + (role() === 'party' ? '#/' : '#/list') + '">' + ICON_BACK + (role() === 'party' ? 'Mera case' : 'Cause list') + '</a><h1>' + esc(e ? [e.pet, e.res].filter(Boolean).join(' v. ') : no) +
        '</h1><div class="sub">' + esc(no) + '</div></header><div class="pad">' +
        found.map(function (f) {
          return '<div class="card"><span class="lbl brand">' + esc(fmtDate(f.d, true)) + '</span><b>' + esc(courtName(f.c)) + ' · item ' + esc(f.e.item) +
            '</b><span class="muted">' + esc(benchText(f.c)) + '</span>' + (f.e.section ? '<span class="chips"><span class="chip">' + esc(f.e.section) + '</span></span>' : '') +
            (f.e.adv ? '<p class="p"><b>Vakeel:</b> ' + esc(f.e.adv) + '</p>' : '') +
            (f.e.apps.length ? '<p class="p"><b>Applications:</b> ' + esc(f.e.apps.join('; ')) + '</p>' : '') + '</div>';
        }).join('') +
        (found.length ? '' : '<div class="empty">Yeh case aaj ya aage ki cause list mein abhi nahi hai. Jaise hi court ise list karega, yahan tareekh, court aur item number aa jaayega.</div>') +
        caseKhojCard(id, 'Is case ka court record abhi app mein nahi. Case ki baat likhiye, isi vishay ke faisle turant dikh jaayenge.') +
        maangoCard(no, 'Is case ka poora record aur vishleshan abhi nahi hai') + '</div>');
      maangoWire();
      caseKhojWire(id);
    });
  }

  function caseFull(c, tab, idx) {
    var pet = (c.petitioners[0] || {}), res = (c.respondents[0] || {});
    var title = [pet.name, res.name].filter(Boolean).join(' v. ') + (c.respondents.length > 1 ? ' & Ors.' : '');
    var n = c.notes || {};
    var tabs = [['saar', 'Saar'], ['dates', 'Tareekhein'], ['orders', 'Orders · ' + c.orders.length]];
    if (n.pros || n.cons || n.issues) tabs.push(['analysis', 'Vishleshan']);
    if (n.similar && n.similar.length) tabs.push(['similar', 'Support / Against']);
    var latest = (idx.dates || [])[0];
    var html = '<header class="hero"><a class="back" href="' + (role() === 'party' ? '#/' : '#/mine') + '">' + ICON_BACK + (role() === 'party' ? 'Mera case' : 'Mere cases') + '</a><div class="chips">' +
      (c.decision_date ? '<span class="chip good">Disposed · ' + esc(dmy(c.decision_date)) + '</span>' : '<span class="chip warn">Pending</span>') +
      (n.badge ? '<span class="chip good">' + esc(n.badge) + '</span>' : '') + (c.bench_type ? '<span class="chip dark">' + esc(c.bench_type) + '</span>' : '') +
      '</div><h1 style="font-size:25px">' + esc(title) + '</h1><div class="sub">' + esc(c.case_no) + ' · CNR ' + esc(c.cnr) + '</div>' +
      (c.next_date ? '<div class="today"><b>' + esc(fmtDate(c.next_date)) + '</b><span>Agli tareekh' + (c.next_date === latest ? ' · aaj' : '') +
        '<small>' + esc(c.coram || '') + ' · ' + esc(c.stage || '') + '</small></span></div>' : '') +
      '</header><div class="tabs" role="tablist">' + tabs.map(function (t) {
        return '<button type="button" role="tab" data-t="' + t[0] + '" class="' + (t[0] === tab ? 'on' : '') + '" aria-selected="' + (t[0] === tab) + '">' + esc(t[1]) + '</button>';
      }).join('') + '</div><div class="pad">';
    if (tab === 'saar') {
      if (n.similar && n.similar.some(function (j) { return j.id; })) {
        var sg = sides(n.similar);
        html += '<a class="card link key" href="#/case/' + esc(c.id) + '?t=similar"><span class="lbl brand">Database se faisle' + (n.vishay ? ' · ' + esc(n.vishay.upvishay) : '') + '</span>' +
          '<div class="chips"><span class="chip good">Support · ' + sg.good.length + '</span><span class="chip warn">Against · ' + sg.bad.length + '</span>' +
          (sg.other.length ? '<span class="chip">Anya · ' + sg.other.length + '</span>' : '') + '</div><span class="go">Faisle dekho' + ICON_NEXT + '</span></a>';
      }
      if (!(n.similar && n.similar.length) && !n.pros) html += caseKhojCard(c.id, 'Court ke orders mein abhi sirf tareekhein / kaam-kaaj hai, case ka vishay nahi likha — isliye machine faisle nahi chun paayi. Ek-do line likhiye, turant isi vishay ke SC aur Nainital HC ke faisle (court ne maana / nahi maana) yahin aa jaayenge.');
      else if (n.free) html += caseKhojCard(c.id, 'Neeche ke faisle orders ke shabdon se mile hain (kamzor milaan). Case ki baat likhenge to vishay ke hisaab se pakke faisle aayenge.');
      if (!(n.similar && n.similar.length) && !n.pros && !c.orders.length) html += maangoCard(c.case_no, 'Is case ka order abhi app mein nahi');
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
      if (n.vishay) html += '<div class="card key"><span class="lbl brand">Case ka vishay' + (n.auto ? ' · machine' : '') + '</span><div class="chips">' +
        [n.vishay.shreni, n.vishay.vishay, n.vishay.upvishay].map(function (x) { return '<span class="chip blue">' + esc(x) + '</span>'; }).join('') +
        (n.vishay.mudde || []).map(function (x) { return '<span class="chip brand">' + esc(x) + '</span>'; }).join('') + '</div>' +
        (n.vishay.aur && n.vishay.aur.length ? '<span class="muted">Ye bhi ho sakta hai: ' + esc(n.vishay.aur.join(', ')) + '</span>' : '') + '</div>';
      if (n.issues && n.issues.length) html += '<div class="card"><span class="lbl">' + esc(n.issues_title || 'Aam mudde') + '</span>' +
        n.issues.map(function (x) {
          return '<div class="pt"><span class="mark ' + (x.is_case_mein ? 'good' : 'dark') + '">' + (x.is_case_mein ? '✓' : '·') + '</span><span>' + esc(x.mudda) +
            ' <span class="muted">· ' + x.faisle + ' faisle' + (x.is_case_mein ? ' · is case ke orders mein bhi' : '') + '</span></span></div>';
        }).join('') + (n.similar ? '<a class="go" href="#/case/' + esc(c.id) + '?t=similar">Support / against faisle dekho' + ICON_NEXT + '</a>' : '') + '</div>';
      html += pts(n.pros_title || 'Paksh mein', 'good', '+', n.pros) + pts(n.cons_title || 'Saamne wala kya keh sakta hai', 'bad', '–', n.cons) +
        (n.todo ? '<div class="card dark"><span class="lbl light">Court le jaana</span>' + n.todo.map(function (t) { return '<div class="pt"><span class="mark dark">✓</span><span>' + esc(t) + '</span></div>'; }).join('') + '</div>' : '') +
        '<p class="muted">' + esc(n.disclaimer || 'Sirf court ke orders aur database se. Advocate ka review zaroori. Koi jeetne ka % nahi.') + '</p>';
    } else if (tab === 'similar') {
      var oldCard = function (j, i) { // haath ke notes (app/notes) ka purana roop
        var open = j.key ? '<a class="card link" href="#/j/' + esc(j.key) + '?from=' + esc(c.id) + '&i=' + i + '">' : '<div class="card">';
        return open + '<div class="chips"><span class="chip ' + (j.court === 'Supreme Court' ? 'dark' : 'blue') + '">' + esc(j.court) + '</span><span class="chip ' + (j.verified ? 'good' : 'warn') + '">' + esc(j.tag) + '</span></div>' +
          '<b class="serif" style="font-size:18px">' + esc(j.title) + '</b><span class="muted">' + esc(j.cite) + '</span><p class="p">' + esc(j.why) + '</p>' +
          (j.quote ? '<p class="p serif quote">' + esc(j.quote) + '</p>' : '') +
          (j.key ? '<span class="go">Poora faisla padho · PDF ' + ICON_NEXT + '</span></a>' : '</div>');
      };
      if (!n.similar.some(function (j) { return j.id; })) html += n.similar.map(oldCard).join('');
      else {
        var g = sides(n.similar), card = function (j) {
          return judgCard(j, j.mudda).replace('href="#/kj/' + j.id + (j.mudda ? '?m=' + encodeURIComponent(j.mudda) : ''),
            'href="#/kj/' + j.id + '?' + (j.mudda ? 'm=' + encodeURIComponent(j.mudda) + '&' : '') + 'from=' + encodeURIComponent(c.id));
        };
        html += '<p class="muted">Isi vishay' + (n.vishay && n.vishay.mudde && n.vishay.mudde.length ? ' aur mudde (' + esc(n.vishay.mudde.join(', ')) + ')' : '') +
          ' ke SC aur Nainital HC ke faisle, court ke nateeje ke hisaab se. Faisle par dabaiye: poora text, kaam ka paragraph upar.</p>' +
          '<span class="lbl good">Support: in mein court ne maang maani · ' + g.good.length + '</span>' +
          (g.good.map(card).join('') || '<div class="empty">Is vishay mein database se abhi aisa faisla nahi mila.</div>') +
          '<span class="lbl bad">Against: in mein court ne maang nahi maani · ' + g.bad.length + '</span>' +
          (g.bad.map(card).join('') || '<div class="empty">Is vishay mein database se abhi aisa faisla nahi mila.</div>') +
          (g.other.length ? '<span class="lbl">Anya (wapas / nipataara) · ' + g.other.length + '</span>' + g.other.map(card).join('') : '') +
          '<p class="muted">' + esc(n.disclaimer || '') + '</p>';
      }
    }
    render(html + '</div>');
    maangoWire();
    caseKhojWire(c.id);
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
    var party = role() === 'party', mine = myCases();
    render('<header class="hero"><h1>Main</h1><div class="sub">Ye jaankari sirf is phone par rehti hai.</div></header><div class="pad">' +
      (party ? '<div class="card"><span class="lbl">Mere case</span>' + (mine.length ? mine.map(function (no) {
        return '<div class="mc-top"><b>' + esc(no) + '</b><button type="button" class="chip warn rm" data-no="' + esc(no) + '">Hatao</button></div>';
      }).join('') : '<span class="muted">Abhi koi case nahi jodha.</span>') + '</div>' :
      '<form id="f" class="card"><label class="field"><span>Mera naam (jaisa cause list mein aata hai)</span>' +
      '<input id="name" autocomplete="name" placeholder="Jaise: Bhagwat Mehra" value="' + esc(name) + '"></label>' +
      '<button class="btn" type="submit">Save karo</button></form>') +
      '<div class="card"><span class="lbl">Main kaun hoon</span><p class="p">' + (party ? 'Party / aam vyakti' : 'Advocate') + '</p>' +
      '<button type="button" id="sw" class="btn ghost">' + (party ? 'Advocate wala app dikhao' : 'Party (apna case) wala app dikhao') + '</button></div>' +
      '<div class="card"><span class="lbl">Phone par app ki tarah</span><p class="p"><b>iPhone:</b> Safari → Share → "Add to Home Screen".<br><b>Android:</b> Chrome → ⋮ menu → "Add to Home screen" / "Install app".</p></div>' +
      '<p class="muted">Cause list apne aap aati hai: court ki site se shaam 5 se 9 baje tak har ghante (agle din ki) aur subah; eCourts se subah 6, 8, 10 aur shaam 6, 7 baje.</p></div>');
    var f = document.getElementById('f');
    if (f) f.addEventListener('submit', function (ev) {
      ev.preventDefault();
      store('ns-name', document.getElementById('name').value.trim());
      go('#/');
    });
    document.getElementById('sw').addEventListener('click', function () {
      store('ns-role', party ? 'advocate' : 'party'); drawNav(); go('#/');
    });
    Array.prototype.forEach.call(document.querySelectorAll('.rm'), function (b) {
      b.addEventListener('click', function () {
        store('ns-cases', JSON.stringify(myCases().filter(function (x) { return x !== b.getAttribute('data-no'); })));
        viewSettings();
      });
    });
  }

  // Router: '#/...' links; kuch jagah (jaise embedded frame) URL hash nahi badalta, isliye apna 'cur' bhi.
  // App kholne par hamesha shuru (Home) se — pichhli baar jahan band kiya tha wahan se nahi.
  var cur = '#/';
  try { history.replaceState(null, '', location.pathname + location.search); } catch (e) { /* frame */ }
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
    if (!role() && path !== '/start') return viewStart();
    if (path === '/start') return viewStart();
    if (path === '/' || path === '') return role() === 'party' ? viewMyCase() : viewHome();
    if (path === '/list') return viewList(params);
    if (path === '/khoj') return viewKhoj();
    if (path.indexOf('/khoj/t/') === 0) return viewKhojTopic(path.slice(8));
    if (path.indexOf('/kj/') === 0) return viewKhojJudgment(path.slice(4), params);
    if (path === '/mine') return viewMine();
    if (path === '/settings') return viewSettings();
    if (path.indexOf('/case/') === 0) return viewCase(path.slice(6), params);
    if (path.indexOf('/j/') === 0) return viewJudgment(decodeURIComponent(path.slice(3)), params);
    viewHome();
  }
  window.addEventListener('hashchange', function () { cur = location.hash || '#/'; route(); });
  // Phone app ko band karne ki jagah peeche rakh deta hai; 5 minute se zyada peeche raha to wapas aane par
  // Home se, aur data (cause list) naya.
  var hiddenAt = 0;
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) { hiddenAt = Date.now(); return; }
    if (hiddenAt && Date.now() - hiddenAt > 5 * 60 * 1000) {
      cache = { index: null, lists: {}, cases: {} };
      go('#/');
    }
  });
  window.addEventListener('pageshow', function (ev) { if (ev.persisted) { cache = { index: null, lists: {}, cases: {} }; go('#/'); } });
  drawNav();
  route();
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () { navigator.serviceWorker.register('sw.js').catch(function () {}); });
  }
})();
