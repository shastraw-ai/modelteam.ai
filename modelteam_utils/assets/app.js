(function () {
  const data = window.__MT_DATA__;
  if (!data || typeof data !== 'object') return;

  const ACCENT_1 = '#a855f7';
  const ACCENT_2 = '#06b6d4';
  const GRID = 'rgba(139, 148, 158, 0.12)';
  const TICK = '#8b949e';

  const TOOLTIP = {
    backgroundColor: '#0d1117',
    borderColor: '#30363d',
    borderWidth: 1,
    titleColor: '#e6edf3',
    bodyColor: '#8b949e',
    padding: 10,
    displayColors: false,
  };

  function setText(key, value) {
    document.querySelectorAll('[data-mt="' + key + '"]').forEach(function (el) {
      el.textContent = value;
    });
  }

  function fmtInt(n) {
    return (n || 0).toLocaleString('en-US');
  }

  function makeXGradient(ctx, area, c1, c2) {
    const g = ctx.createLinearGradient(area.left, 0, area.right, 0);
    g.addColorStop(0, c1); g.addColorStop(1, c2);
    return g;
  }

  function makeYGradient(ctx, area, c1, c2) {
    const g = ctx.createLinearGradient(0, area.bottom, 0, area.top);
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

  let skillDetailChart = null;
  let activeSkillEl = null;

  function renderSkillDetail(skill) {
    const buckets = skillQtr[skill] || {};
    const series = quarters.map(function (q) { return buckets[q] || 0; });
    const hasData = series.some(function (v) { return v > 0; });

    document.getElementById('skill-detail-name').textContent = skill;

    const wrap = document.getElementById('chart-skill-detail').parentElement;
    const empty = document.getElementById('skill-detail-empty');

    if (!hasData) {
      wrap.style.display = 'none';
      empty.hidden = false;
      if (skillDetailChart) { skillDetailChart.destroy(); skillDetailChart = null; }
      return;
    }
    wrap.style.display = '';
    empty.hidden = true;

    if (skillDetailChart) {
      skillDetailChart.data.datasets[0].data = series;
      skillDetailChart.update();
      return;
    }

    skillDetailChart = new Chart(document.getElementById('chart-skill-detail'), {
      type: 'bar',
      data: {
        labels: quarters,
        datasets: [{
          data: series,
          backgroundColor: function (ctx) {
            const c = ctx.chart;
            const a = c.chartArea;
            if (!a) return ACCENT_1;
            return makeYGradient(c.ctx, a, ACCENT_2, ACCENT_1);
          },
          borderRadius: 4,
          borderSkipped: false,
          barPercentage: 0.62,
          categoryPercentage: 0.86,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 500, easing: 'easeOutQuart' },
        plugins: {
          legend: { display: false },
          tooltip: Object.assign({}, TOOLTIP, {
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
              callback: function (v) {
                if (v >= 1000) return (v / 1000).toFixed(v >= 10000 ? 0 : 1) + 'k';
                return v;
              },
            },
          },
        },
      },
    });
  }

  function markActiveSkill(skill) {
    if (activeSkillEl) activeSkillEl.classList.remove('active');
    activeSkillEl = document.querySelector('.chip[data-skill="' + CSS.escape(skill) + '"]');
    if (activeSkillEl) activeSkillEl.classList.add('active');
  }

  if (skillEntries.length === 0) {
    document.getElementById('skills-empty').hidden = false;
    document.getElementById('chart-skills').parentElement.style.display = 'none';
    document.getElementById('chart-skill-detail').parentElement.style.display = 'none';
    document.getElementById('skill-detail-empty').hidden = false;
  } else {
    const topN = skillEntries.slice(0, 25);
    const rest = skillEntries.slice(25);

    const skillsCanvas = document.getElementById('chart-skills');

    new Chart(skillsCanvas, {
      type: 'bar',
      data: {
        labels: topN.map(function (e) { return e[0]; }),
        datasets: [{
          data: topN.map(function (e) { return e[1]; }),
          backgroundColor: function (ctx) {
            const chart = ctx.chart;
            const area = chart.chartArea;
            if (!area) return ACCENT_1;
            return makeXGradient(chart.ctx, area, ACCENT_1, ACCENT_2);
          },
          borderRadius: 4,
          borderSkipped: false,
          barPercentage: 0.78,
          categoryPercentage: 0.86,
        }],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 700, easing: 'easeOutQuart' },
        onHover: function (e, els) {
          e.native.target.style.cursor = els.length ? 'pointer' : 'default';
        },
        onClick: function (evt, els, chart) {
          if (!els.length) return;
          const skill = chart.data.labels[els[0].index];
          renderSkillDetail(skill);
          markActiveSkill(skill);
        },
        plugins: {
          legend: { display: false },
          tooltip: Object.assign({}, TOOLTIP, {
            callbacks: {
              label: function (item) { return 'score ' + fmtInt(item.raw); },
            },
          }),
        },
        scales: {
          x: {
            grid: { color: GRID, drawTicks: false },
            border: { display: false },
            ticks: { color: TICK, font: { size: 11 } },
          },
          y: {
            grid: { display: false },
            border: { display: false },
            ticks: { color: '#e6edf3', font: { size: 13 } },
          },
        },
      },
    });

    const chipBox = document.getElementById('skill-chips');
    function addChip(name, value) {
      const chip = document.createElement('span');
      chip.className = 'chip';
      chip.dataset.skill = name;
      const label = document.createElement('span');
      label.textContent = name;
      const score = document.createElement('span');
      score.className = 'score';
      score.textContent = fmtInt(value);
      chip.appendChild(label);
      chip.appendChild(score);
      chip.addEventListener('click', function () {
        renderSkillDetail(name);
        markActiveSkill(name);
      });
      chipBox.appendChild(chip);
    }
    topN.forEach(function (e) { addChip(e[0], e[1]); });
    rest.forEach(function (e) { addChip(e[0], e[1]); });

    const initialSkill = (skillEntries.find(function (e) {
      const m = skillQtr[e[0]] || {};
      return Object.keys(m).some(function (q) { return (m[q] || 0) > 0; });
    }) || skillEntries[0])[0];
    renderSkillDetail(initialSkill);
    markActiveSkill(initialSkill);
  }

  // --- Languages tab ------------------------------------------------------

  const langStats = data.lang_qtr_added || {};
  const langNames = Object.keys(langStats);

  let langDetailChart = null;

  function renderLangDetail(name) {
    const buckets = langStats[name] || {};
    const series = quarters.map(function (q) { return buckets[q] || 0; });
    const hasData = series.some(function (v) { return v > 0; });

    document.getElementById('lang-detail-name').textContent = name;

    const wrap = document.getElementById('chart-lang-detail').parentElement;
    const empty = document.getElementById('lang-detail-empty');

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
      type: 'bar',
      data: {
        labels: quarters,
        datasets: [{
          data: series,
          backgroundColor: function (ctx) {
            const c = ctx.chart;
            const a = c.chartArea;
            if (!a) return ACCENT_2;
            return makeYGradient(c.ctx, a, ACCENT_2, ACCENT_1);
          },
          borderRadius: 4,
          borderSkipped: false,
          barPercentage: 0.62,
          categoryPercentage: 0.86,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 500, easing: 'easeOutQuart' },
        plugins: {
          legend: { display: false },
          tooltip: Object.assign({}, TOOLTIP, {
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
              callback: function (v) {
                if (v >= 1000) return (v / 1000).toFixed(v >= 10000 ? 0 : 1) + 'k';
                return v;
              },
            },
          },
        },
      },
    });
  }

  let activeLangEl = null;
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
    const langTotals = langNames.map(function (name) {
      let total = 0;
      const m = langStats[name];
      Object.keys(m).forEach(function (q) { total += m[q] || 0; });
      return [name, total];
    });
    langTotals.sort(function (a, b) { return b[1] - a[1]; });

    const topN = langTotals.slice(0, 25);
    const rest = langTotals.slice(25);

    new Chart(document.getElementById('chart-langs'), {
      type: 'bar',
      data: {
        labels: topN.map(function (e) { return e[0]; }),
        datasets: [{
          data: topN.map(function (e) { return e[1]; }),
          backgroundColor: function (ctx) {
            const c = ctx.chart;
            const a = c.chartArea;
            if (!a) return ACCENT_2;
            return makeXGradient(c.ctx, a, ACCENT_1, ACCENT_2);
          },
          borderRadius: 4,
          borderSkipped: false,
          barPercentage: 0.78,
          categoryPercentage: 0.86,
        }],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 700, easing: 'easeOutQuart' },
        onHover: function (e, els) {
          e.native.target.style.cursor = els.length ? 'pointer' : 'default';
        },
        onClick: function (evt, els, chart) {
          if (!els.length) return;
          const name = chart.data.labels[els[0].index];
          renderLangDetail(name);
          markActiveLang(name);
        },
        plugins: {
          legend: { display: false },
          tooltip: Object.assign({}, TOOLTIP, {
            callbacks: {
              label: function (item) { return fmtInt(item.raw) + ' lines'; },
            },
          }),
        },
        scales: {
          x: {
            grid: { color: GRID, drawTicks: false },
            border: { display: false },
            ticks: {
              color: TICK, font: { size: 11 },
              callback: function (v) {
                if (v >= 1000) return (v / 1000).toFixed(v >= 10000 ? 0 : 1) + 'k';
                return v;
              },
            },
          },
          y: {
            grid: { display: false },
            border: { display: false },
            ticks: { color: '#e6edf3', font: { size: 13 } },
          },
        },
      },
    });

    const langChipBox = document.getElementById('lang-chips');
    function addLangChip(name, value) {
      const chip = document.createElement('span');
      chip.className = 'chip';
      chip.dataset.lang = name;
      const label = document.createElement('span');
      label.textContent = name;
      const score = document.createElement('span');
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
    topN.forEach(function (e) { addLangChip(e[0], e[1]); });
    rest.forEach(function (e) { addLangChip(e[0], e[1]); });

    renderLangDetail(topN[0][0]);
    markActiveLang(topN[0][0]);
  }
})();
