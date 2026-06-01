(function () {
  const data = window.__MT_DATA__;
  if (!data || typeof data !== 'object') return;

  const ACCENT_1 = '#a855f7';
  const ACCENT_2 = '#06b6d4';
  const GRID = 'rgba(139, 148, 158, 0.12)';
  const TICK = '#8b949e';

  const MULTI_COLORS = [
    '#6366f1', '#06b6d4', '#f59e0b', '#ef4444', '#10b981',
    '#8b5cf6', '#ec4899', '#64748b', '#0ea5e9', '#84cc16',
  ];

  // Max skills drawn in a single line chart; larger groups split across charts.
  const MAX_SKILLS_PER_CHART = 5;

  const TOOLTIP = {
    backgroundColor: '#0d1117',
    borderColor: '#30363d',
    borderWidth: 1,
    titleColor: '#e6edf3',
    bodyColor: '#8b949e',
    padding: 10,
    displayColors: true,
  };

  function setText(key, value) {
    document.querySelectorAll('[data-mt="' + key + '"]').forEach(function (el) {
      el.textContent = value;
    });
  }

  function fmtInt(n) {
    return (n || 0).toLocaleString('en-US');
  }

  function fmtLines(v) {
    if (v >= 1000) return (v / 1000).toFixed(v >= 10000 ? 0 : 1) + 'k';
    return v;
  }

  function makeXGradient(ctx, area, c1, c2) {
    const g = ctx.createLinearGradient(area.left, 0, area.right, 0);
    g.addColorStop(0, c1); g.addColorStop(1, c2);
    return g;
  }

  // --- Hero ---------------------------------------------------------------

  const generated = new Date((data.timestamp || 0) * 1000);
  const generatedStr = isNaN(generated.getTime())
    ? 'generated locally'
    : 'generated ' + generated.toLocaleDateString(undefined, {
        year: 'numeric', month: 'short', day: 'numeric',
      });

  setText('user', data.user || 'anonymous engineer');
  setText('generated', generatedStr);
  setText('hcShort', data.hc ? data.hc.slice(0, 12) : '');
  setText('hcFull', data.hc || '');
  setText('iso', isNaN(generated.getTime()) ? '' : generated.toISOString());

  setText('totalSkills', fmtInt(Object.keys(data.merged_skills || {}).length));
  setText('totalRepos', fmtInt(data.total_repos));
  setText('totalLines', fmtInt(data.total_lines_added));
  setText('span', data.active_span || '—');

  // --- Tabs ---------------------------------------------------------------

  const tabs = document.querySelectorAll('.tab');
  const panels = document.querySelectorAll('.tab-panel');
  tabs.forEach(function (tab) {
    tab.addEventListener('click', function () {
      const key = tab.dataset.tab;
      tabs.forEach(function (t) {
        const active = t === tab;
        t.classList.toggle('active', active);
        t.setAttribute('aria-selected', active ? 'true' : 'false');
      });
      panels.forEach(function (p) {
        p.hidden = p.dataset.panel !== key;
      });
    });
  });

  // --- Skills tab ---------------------------------------------------------

  const skills = data.merged_skills || {};
  const skillQtr = data.skill_qtr_lines || {};
  const quarters = data.quarters || [];
  const skillEntries = Object.keys(skills)
    .map(function (k) { return [k, skills[k]]; })
    .sort(function (a, b) { return b[1] - a[1]; });

  function skillHasData(skill) {
    var m = skillQtr[skill] || {};
    return quarters.some(function (q) { return (m[q] || 0) > 0; });
  }

  function renderGroupChart(container, name, groupSkills, colorOffset) {
    var head = document.createElement('div');
    head.className = 'detail-head';
    var title = document.createElement('h3');
    title.className = 'detail-title';
    title.textContent = name;
    head.appendChild(title);
    container.appendChild(head);

    var wrap = document.createElement('div');
    wrap.className = 'chart-wrap';
    var canvas = document.createElement('canvas');
    wrap.appendChild(canvas);
    container.appendChild(wrap);

    var datasets = groupSkills.map(function (skill, i) {
      var color = MULTI_COLORS[(colorOffset + i) % MULTI_COLORS.length];
      return {
        label: skill,
        data: quarters.map(function (q) { return (skillQtr[skill] || {})[q] || 0; }),
        borderColor: color,
        backgroundColor: color,
        pointRadius: 3,
        pointHoverRadius: 5,
        borderWidth: 2,
        tension: 0.3,
        fill: false,
      };
    });

    new Chart(canvas, {
      type: 'line',
      data: { labels: quarters, datasets: datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 600, easing: 'easeOutQuart' },
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: {
            display: true,
            position: 'top',
            labels: { color: '#e6edf3', usePointStyle: true, pointStyle: 'circle', padding: 14, font: { size: 12 } },
          },
          tooltip: Object.assign({}, TOOLTIP, {
            callbacks: {
              label: function (item) { return item.dataset.label + ': ' + fmtInt(item.raw) + ' lines'; },
            },
          }),
        },
        scales: {
          x: {
            grid: { display: false },
            border: { display: false },
            ticks: { color: TICK, font: { size: 11 } },
          },
          y: {
            grid: { color: GRID, drawTicks: false },
            border: { display: false },
            ticks: {
              color: TICK, font: { size: 11 },
              callback: function (v) { return fmtLines(v); },
            },
          },
        },
      },
    });
  }

  if (skillEntries.length === 0) {
    document.getElementById('skills-empty').hidden = false;
  } else {
    // Skill chips: a static at-a-glance list (most important first).
    var chipBox = document.getElementById('skill-chips');
    skillEntries.forEach(function (e) {
      var chip = document.createElement('span');
      chip.className = 'chip';
      var label = document.createElement('span');
      label.textContent = e[0];
      chip.appendChild(label);
      chipBox.appendChild(chip);
    });

    // Only skills with quarterly activity can be charted.
    var activeSkills = {};
    skillEntries.forEach(function (e) {
      if (skillHasData(e[0])) activeSkills[e[0]] = true;
    });

    // Use server-provided groups; otherwise fall back to one default group.
    var rawGroups = (data.skill_groups && data.skill_groups.length)
      ? data.skill_groups
      : [{ name: 'Skills', skills: skillEntries.map(function (e) { return e[0]; }) }];

    var groups = rawGroups.map(function (g) {
      return {
        name: g.name,
        skills: (g.skills || []).filter(function (s) { return activeSkills[s]; }),
      };
    }).filter(function (g) { return g.skills.length; });

    // Split any group with more than MAX_SKILLS_PER_CHART skills into multiple
    // line charts so a single chart never gets too crowded.
    var chartPanels = [];
    groups.forEach(function (g) {
      if (g.skills.length <= MAX_SKILLS_PER_CHART) {
        chartPanels.push({ name: g.name, skills: g.skills });
        return;
      }
      var nParts = Math.ceil(g.skills.length / MAX_SKILLS_PER_CHART);
      for (var p = 0; p < nParts; p++) {
        chartPanels.push({
          name: p === 0 ? g.name : g.name + ' [contd.]',
          skills: g.skills.slice(p * MAX_SKILLS_PER_CHART, (p + 1) * MAX_SKILLS_PER_CHART),
        });
      }
    });

    if (!chartPanels.length) {
      document.getElementById('skills-empty').hidden = false;
    } else {
      var container = document.getElementById('skill-group-charts');
      var colorIdx = 0;
      chartPanels.forEach(function (panel) {
        renderGroupChart(container, panel.name, panel.skills, colorIdx);
        colorIdx += panel.skills.length;
      });
    }
  }

  // --- Languages tab ------------------------------------------------------

  var langStats = data.lang_qtr_added || {};
  var langNames = Object.keys(langStats);

  var langDetailChart = null;

  function renderLangDetail(name) {
    var buckets = langStats[name] || {};
    var series = quarters.map(function (q) { return buckets[q] || 0; });
    var hasData = series.some(function (v) { return v > 0; });

    document.getElementById('lang-detail-name').textContent = name;

    var wrap = document.getElementById('chart-lang-detail').parentElement;
    var empty = document.getElementById('lang-detail-empty');

    if (!hasData) {
      wrap.style.display = 'none';
      empty.hidden = false;
      if (langDetailChart) { langDetailChart.destroy(); langDetailChart = null; }
      return;
    }
    wrap.style.display = '';
    empty.hidden = true;

    if (langDetailChart) {
      langDetailChart.data.datasets[0].data = series;
      langDetailChart.update();
      return;
    }

    langDetailChart = new Chart(document.getElementById('chart-lang-detail'), {
      type: 'line',
      data: {
        labels: quarters,
        datasets: [{
          data: series,
          borderColor: ACCENT_2,
          backgroundColor: ACCENT_2,
          pointRadius: 4,
          pointHoverRadius: 6,
          borderWidth: 2,
          tension: 0.3,
          fill: false,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 500, easing: 'easeOutQuart' },
        plugins: {
          legend: { display: false },
          tooltip: Object.assign({}, TOOLTIP, {
            displayColors: false,
            callbacks: {
              label: function (item) { return fmtInt(item.raw) + ' lines'; },
            },
          }),
        },
        scales: {
          x: {
            grid: { display: false },
            border: { display: false },
            ticks: { color: TICK, font: { size: 11 } },
          },
          y: {
            grid: { color: GRID, drawTicks: false },
            border: { display: false },
            ticks: {
              color: TICK, font: { size: 11 },
              callback: function (v) { return fmtLines(v); },
            },
          },
        },
      },
    });
  }

  var activeLangEl = null;
  function markActiveLang(name) {
    if (activeLangEl) activeLangEl.classList.remove('active');
    activeLangEl = document.querySelector('.chip[data-lang="' + CSS.escape(name) + '"]');
    if (activeLangEl) activeLangEl.classList.add('active');
  }

  if (quarters.length === 0 || langNames.length === 0) {
    document.getElementById('langs-empty').hidden = false;
    document.getElementById('chart-langs').parentElement.style.display = 'none';
    document.getElementById('chart-lang-detail').parentElement.style.display = 'none';
    document.getElementById('lang-detail-empty').hidden = false;
  } else {
    var langTotals = langNames.map(function (name) {
      var total = 0;
      var m = langStats[name];
      Object.keys(m).forEach(function (q) { total += m[q] || 0; });
      return [name, total];
    });
    langTotals.sort(function (a, b) { return b[1] - a[1]; });

    var topLangs = langTotals.filter(function (e) { return e[1] > 0; }).slice(0, 7);

    // Multi-series line chart: all top languages over quarters
    new Chart(document.getElementById('chart-langs'), {
      type: 'line',
      data: {
        labels: quarters,
        datasets: topLangs.map(function (entry, i) {
          var name = entry[0];
          var color = MULTI_COLORS[i % MULTI_COLORS.length];
          return {
            label: name,
            data: quarters.map(function (q) { return (langStats[name] || {})[q] || 0; }),
            borderColor: color,
            backgroundColor: color,
            pointRadius: 3,
            pointHoverRadius: 5,
            borderWidth: 2,
            tension: 0.3,
            fill: false,
          };
        }),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 700, easing: 'easeOutQuart' },
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: {
            display: true,
            position: 'top',
            labels: { color: '#e6edf3', usePointStyle: true, pointStyle: 'circle', padding: 16, font: { size: 12 } },
          },
          tooltip: Object.assign({}, TOOLTIP, {
            callbacks: {
              label: function (item) { return item.dataset.label + ': ' + fmtInt(item.raw) + ' lines'; },
            },
          }),
        },
        scales: {
          x: {
            grid: { display: false },
            border: { display: false },
            ticks: { color: TICK, font: { size: 11 } },
          },
          y: {
            grid: { color: GRID, drawTicks: false },
            border: { display: false },
            ticks: {
              color: TICK, font: { size: 11 },
              callback: function (v) { return fmtLines(v); },
            },
          },
        },
      },
    });

    var langChipBox = document.getElementById('lang-chips');
    function addLangChip(name, value) {
      var chip = document.createElement('span');
      chip.className = 'chip';
      chip.dataset.lang = name;
      var label = document.createElement('span');
      label.textContent = name;
      var score = document.createElement('span');
      score.className = 'score';
      score.textContent = fmtInt(value);
      chip.appendChild(label);
      chip.appendChild(score);
      chip.addEventListener('click', function () {
        renderLangDetail(name);
        markActiveLang(name);
      });
      langChipBox.appendChild(chip);
    }
    langTotals.forEach(function (e) { addLangChip(e[0], e[1]); });

    renderLangDetail(topLangs[0][0]);
    markActiveLang(topLangs[0][0]);
  }
})();
