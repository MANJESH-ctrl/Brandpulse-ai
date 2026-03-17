/* ══════════════════════════════════════════════════════
   BRANDPULSE AI — App Logic
══════════════════════════════════════════════════════ */


const State = {
  currentPage: 'dashboard',
  lastJobId: localStorage.getItem('lastJobId') || null,
  pollingTimer: null,
  charts: {},
};


// Chart.js global defaults
Chart.defaults.font.family = "'IBM Plex Mono', 'Courier New', monospace";
Chart.defaults.font.size = 11;
Chart.defaults.color = '#888888';


const C = {
  pos:    '#16a34a',
  neg:    '#dc2626',
  neu:    '#6b7280',
  text:   '#0a0a0a',
  border: '#e2e2e2',
  bg:     '#ffffff',
  bgAlt:  '#f7f7f7',
};


// ══════════════════════════════════════════════════════
// ROUTER
// ══════════════════════════════════════════════════════


function navigate(page) {
  if (page !== 'analyze' && State.pollingTimer) {
    clearInterval(State.pollingTimer);
    State.pollingTimer = null;
    }
  
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  
  
    const el = document.getElementById(`page-${page}`);
    if (el) el.classList.add('active');
  
  
    document.querySelectorAll(`[data-page="${page}"]`).forEach(t => t.classList.add('active'));
  
  
    State.currentPage = page;
    document.getElementById('footer-page').textContent = page.toUpperCase();
  
  
    if (page === 'dashboard') loadDashboard();
    if (page === 'brands')    loadBrandsPage();
    if (page === 'alerts')    loadAlertsPage();
    if (page === 'results' && State.lastJobId) {
        document.getElementById('result-job-input').value = State.lastJobId;
        // only auto-load if no active polling (job is done)
        if (!State.pollingTimer) {
            loadResults();
        } else {
            setMsg('results-msg', 'info', 'Analysis still running — results will load automatically when done.');
        }
    }
  }

// ══════════════════════════════════════════════════════
// CLOCK + HEALTH
// ══════════════════════════════════════════════════════


function startClock() {
  function tick() {
    const d = new Date();
    const h = String(d.getHours()).padStart(2, '0');
    const m = String(d.getMinutes()).padStart(2, '0');
    document.getElementById('footer-clock').textContent = `${h}:${m}`;
  }
  tick();
  setInterval(tick, 60000); 
}


async function checkHealth() {
  const alive = await API.health();
  const dot   = document.getElementById('footer-dot');
  const lbl   = document.getElementById('footer-api');
  const hdr   = document.getElementById('header-api-status');


  if (alive) {
    dot.classList.remove('offline');
    lbl.textContent = 'API: Connected';
    hdr.textContent = '● Connected';
    hdr.style.color = '#4ade80';
  } else {
    dot.classList.add('offline');
    lbl.textContent = 'API: Offline';
    hdr.textContent = '● Offline';
    hdr.style.color = '#f87171';
  }
}


// ══════════════════════════════════════════════════════
// DASHBOARD
// ══════════════════════════════════════════════════════


async function loadDashboard() {
  const container = document.getElementById('dashboard-brands');

  // Show zeros immediately — no dashes on first load
  document.getElementById('db-total-brands').textContent  = '0';
  document.getElementById('db-total-posts').textContent   = '0';
  document.getElementById('db-active-alerts').textContent = '0';
  document.getElementById('db-avg-negative').textContent  = '—';
  document.getElementById('tk-brands').textContent        = '0';
  document.getElementById('tk-posts').textContent         = '0';
  document.getElementById('tk-alerts').textContent        = '0';
  


  const [brands, alerts] = await Promise.all([
    API.listBrands(),
    API.getAlerts(null, true),
  ]);


  // Ticker + metrics
  document.getElementById('db-total-brands').textContent  = brands.length;
  document.getElementById('db-active-alerts').textContent = alerts.length;
  document.getElementById('tk-brands').textContent        = brands.length;
  document.getElementById('tk-alerts').textContent        = alerts.length;


  const totalPosts = brands.reduce((s, b) => s + (b.total_posts_analyzed || 0), 0);
  document.getElementById('db-total-posts').textContent = totalPosts.toLocaleString();
  document.getElementById('tk-posts').textContent       = totalPosts.toLocaleString();


  const avgNeg = brands.length
    ? (brands.reduce((s, b) => s + b.avg_negative, 0) / brands.length * 100).toFixed(1) + '%'
    : '—';
  document.getElementById('db-avg-negative').textContent = avgNeg;


  if (!brands.length) {
    container.innerHTML = `<div class="status-line">No brands analyzed yet. Go to <strong>Analyze</strong> to run your first job.</div>`;
    return;
  }


  let rows = brands.map(b => {
    const pos  = (b.avg_positive * 100).toFixed(1);
    const neg  = (b.avg_negative * 100).toFixed(1);
    const neu  = (b.avg_neutral  * 100).toFixed(1);
    const crs  = b.latest_crisis_score.toFixed(3);
    const date = (b.latest_analysis_at || '').substring(0, 16).replace('T', ' ');
    const tag  = b.latest_crisis_score >= 1.0
      ? `<span class="badge badge-crisis">Crisis</span>`
      : `<span class="badge badge-pos">Normal</span>`;
    return `
      <tr>
        <td><strong>${esc(b.brand_name)}</strong></td>
        <td>${b.total_analyses}</td>
        <td>${b.total_posts_analyzed.toLocaleString()}</td>
        <td class="pos">${pos}%</td>
        <td class="neg">${neg}%</td>
        <td>${neu}%</td>
        <td>${crs}</td>
        <td>${tag}</td>
        <td>${date}</td>
        <td>
          <button class="btn btn-outline btn-sm" onclick="jumpToResults('${esc(b.brand_name)}')">Results</button>
        </td>
      </tr>`;
  }).join('');


  container.innerHTML = `
    <table class="data-table">
      <thead>
        <tr>
          <th>Brand</th><th>Runs</th><th>Posts</th>
          <th>Positive</th><th>Negative</th><th>Neutral</th>
          <th>Crisis Score</th><th>Status</th><th>Last Run</th><th></th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}


async function jumpToResults(brandName) {
  const history = await API.getBrandHistory(brandName);
  if (history.length) {
    const latest = history[0];
    State.lastJobId = latest.job_id;
    localStorage.setItem('lastJobId', latest.job_id);
  }
  navigate('results');
  if (State.lastJobId) {
    document.getElementById('result-job-input').value = State.lastJobId;
    loadResults();
  }
}


// ══════════════════════════════════════════════════════
// ANALYZE
// ══════════════════════════════════════════════════════


async function submitAnalysis() {
  const brandName = document.getElementById('brand-name-input').value.trim();
  const keywords  = document.getElementById('keywords-input').value.trim();
  const limit     = parseInt(document.getElementById('limit-input').value);
  const platforms = [...document.querySelectorAll('.platform-check:checked')].map(c => c.value);


  if (!brandName)        return setMsg('analyze-msg', 'warn', 'Brand name is required.');
  if (!platforms.length) return setMsg('analyze-msg', 'warn', 'Select at least one platform.');


  setMsg('analyze-msg', 'info', 'Submitting job...');
  document.getElementById('run-btn').disabled = true;
  setStatus('SUBMITTING');


  const result = await API.startAnalysis(brandName, keywords, platforms, limit);


  if (result.error) {
    setMsg('analyze-msg', 'danger', result.error);
    document.getElementById('run-btn').disabled = false;
    setStatus('FAILED');
    return;
  }


  const jobId = result.job_id;
  State.lastJobId = jobId;
  localStorage.setItem('lastJobId', jobId);


  document.getElementById('job-id-display').textContent = jobId;
  document.getElementById('job-id-row').style.display   = 'flex';
  setMsg('analyze-msg', 'ok', `Job started. ID: ${jobId}`);


  pollJob(jobId);
}


function pollJob(jobId) {
  if (State.pollingTimer) clearInterval(State.pollingTimer);


  const steps = {
    pending:    { pct: 5,   label: 'PENDING'    },
    collecting: { pct: 30,  label: 'COLLECTING' },
    processing: { pct: 55,  label: 'PROCESSING' },
    analyzing:  { pct: 75,  label: 'ANALYZING'  },
    done:       { pct: 100, label: 'DONE'        },
    failed:     { pct: 0,   label: 'FAILED'      },
  };


  setProgress(5, 'Starting...');


  State.pollingTimer = setInterval(async () => {
    const s = await API.getJobStatus(jobId);


    if (s.error) {
      clearInterval(State.pollingTimer);
      setMsg('analyze-msg', 'danger', `Polling error: ${s.error}`);
      return;
    }


    const step = steps[s.status] || { pct: 0, label: s.status.toUpperCase() };
    setProgress(step.pct, s.progress_message || step.label);
    setStatus(step.label);


    if (s.status === 'done') {
    clearInterval(State.pollingTimer);
    document.getElementById('run-btn').disabled = false;
    setMsg('analyze-msg', 'ok', 'Analysis complete. Loading results...');
    setTimeout(() => navigate('results'), 800);  // small delay so user sees the message
   }

    if (s.status === 'failed') {
      clearInterval(State.pollingTimer);
      document.getElementById('run-btn').disabled = false;
      setMsg('analyze-msg', 'danger', `Failed: ${s.error_message || 'Unknown error'}`);
    }


  }, 2500);
}


function setStatus(label) {
  document.getElementById('analyze-status-text').textContent = label;
}


function setProgress(pct, msg) {
  const bar = document.getElementById('progress-bar');
  const txt = document.getElementById('progress-text');
  if (bar) bar.style.width = `${pct}%`;
  if (txt) txt.textContent = msg;
}


// ══════════════════════════════════════════════════════
// RESULTS
// ══════════════════════════════════════════════════════


async function loadResults() {
  const jobId = document.getElementById('result-job-input').value.trim();
  if (!jobId) return setMsg('results-msg', 'warn', 'Enter a Job ID.');


  setMsg('results-msg', 'info', 'Loading...');
  document.getElementById('results-content').style.display = 'none';


  const result = await API.getResult(jobId);


  if (result.error) {
    setMsg('results-msg', 'danger', result.error);
    return;
  }


  document.getElementById('results-msg').innerHTML = '';
  document.getElementById('results-content').style.display = 'block';


  // Header
  document.getElementById('res-brand').textContent      = result.brand_name;
  document.getElementById('res-post-count').textContent = result.post_count.toLocaleString();
  document.getElementById('res-completed').textContent  = (result.completed_at || '').substring(0, 16).replace('T', ' ');


  // Crisis
  const crisis = document.getElementById('crisis-banner');
  if (result.crisis_triggered) {
    crisis.className = 'alert-banner danger mb12';
    crisis.textContent = `Crisis Triggered — Score: ${result.crisis_score.toFixed(3)}. Negative sentiment exceeds crisis threshold.`;
  } else if (result.crisis_score > 0.6) {
    crisis.className = 'alert-banner warn mb12';
    crisis.textContent = `Elevated Negative Sentiment — Score: ${result.crisis_score.toFixed(3)}. Below threshold but worth monitoring.`;
  } else {
    crisis.className = 'alert-banner ok mb12';
    crisis.textContent = `Sentiment Healthy — Crisis Score: ${result.crisis_score.toFixed(3)}`;
  }


  // Metrics
  const d = result.sentiment_distribution || {};
  const w = result.weighted_sentiment || {};
  document.getElementById('res-pos').textContent    = ((d.positive || 0) * 100).toFixed(1) + '%';
  document.getElementById('res-neg').textContent    = ((d.negative || 0) * 100).toFixed(1) + '%';
  document.getElementById('res-neu').textContent    = ((d.neutral  || 0) * 100).toFixed(1) + '%';
  document.getElementById('res-crisis').textContent = result.crisis_score.toFixed(3);


  // Charts row 1
  renderDonut('chart-donut', d);
  renderBar('chart-bar', d, w);


  // Charts row 2
  const aspectVisible = !!(result.aspect_results && Object.keys(result.aspect_results).length);
  const platData      = await API.getPlatformSentiment(jobId);
  const platVisible   = !!(platData.platform_sentiment && Object.keys(platData.platform_sentiment).length);

  if (aspectVisible) {
    document.getElementById('aspect-section').style.display = 'block';
    renderAspect('chart-aspect', result.aspect_results);
  }
  if (platVisible) {
    document.getElementById('platform-section').style.display = 'block';
    renderPlatform('chart-platform', platData.platform_sentiment);
  }

  const row2 = document.getElementById('charts-row2');
  row2.className     = (aspectVisible && platVisible) ? 'g2 mb12' : 'mb12';
  row2.style.display = (aspectVisible || platVisible) ? 'grid' : 'none';


  // AI Insight
  if (result.insight_summary) {
    document.getElementById('insight-section').style.display = 'block';
    document.getElementById('insight-text').innerHTML = renderMd(result.insight_summary);
  }


  // Posts
  loadPosts(jobId);
}


async function loadPosts(jobId) {
  const container = document.getElementById('posts-container');
  const data = await API.getCollectedPosts(jobId);


  if (!data.posts || !data.posts.length) {
    container.innerHTML = '<div class="status-line">No posts found.</div>';
    return;
  }


  container.innerHTML = data.posts.slice(0, 30).map(p => {
    const s     = p.sentiment || 'neutral';
    const title = esc(p.title || '');
    const text  = esc((p.text || '').substring(0, 180));
    const conf  = p.confidence ? (p.confidence * 100).toFixed(0) + '%' : '—';
    const body  = title || text;
    return `
      <div class="post-row ${s}">
        <div class="post-dot"></div>
        <div class="post-body">
          <div>${body}${(!title && text.length >= 180) ? '…' : ''}</div>
          <div class="post-meta">
            <span>${(p.platform || '').toUpperCase()}</span>
            <span>${s}</span>
            <span>conf: ${conf}</span>
            ${p.engagement_score ? `<span>eng: ${p.engagement_score.toFixed(1)}</span>` : ''}
          </div>
        </div>
      </div>`;
  }).join('');
}


// ══════════════════════════════════════════════════════
// BRANDS
// ══════════════════════════════════════════════════════


async function loadBrandsPage() {
  const brands = await API.listBrands();


  populateSelect('brand-trend-select', brands);
  populateSelect('brand-compare-select', brands);


  if (brands.length) loadBrandTrend(brands[0].brand_name);
}


function populateSelect(id, brands) {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = brands.map(b =>
    `<option value="${esc(b.brand_name)}">${esc(b.brand_name)}</option>`
  ).join('');
}


async function loadBrandTrend(brandName) {
  if (!brandName) return;
  document.getElementById('history-brand-name').textContent = brandName;


  const area = document.getElementById('trend-chart-area');
  area.innerHTML = '<div class="status-line">Loading...</div>';


  const trend = await API.getBrandTrend(brandName);


  // trend.error is always undefined — API returns [] on error
  if (!trend.length) {
    area.innerHTML = '<div class="status-line">Not enough data. Run multiple analyses over time to see a trend.</div>';
  } else {
    area.innerHTML = `
      <div class="chart-wrap">
        <div class="chart-label">Sentiment Trend — ${esc(brandName)}</div>
        <div style="position:relative;height:240px;">
          <canvas id="chart-trend"></canvas>
        </div>
      </div>`;
    renderTrend('chart-trend', trend);
  }


  const history = await API.getBrandHistory(brandName);
  renderHistoryTable(history);
}


function renderHistoryTable(history) {
  const el = document.getElementById('history-table');
  if (!history.length) {
    el.innerHTML = '<div class="status-line">No history found.</div>';
    return;
  }
  el.innerHTML = `
    <table class="data-table">
      <thead>
        <tr>
          <th>Date</th><th>Posts</th><th>Positive</th>
          <th>Negative</th><th>Neutral</th><th>Crisis Score</th><th></th>
        </tr>
      </thead>
      <tbody>
        ${history.map(h => `
          <tr>
            <td>${(h.analyzed_at || '').substring(0, 16).replace('T', ' ')}</td>
            <td>${(h.post_count || 0).toLocaleString()}</td>
            <td class="pos">${((h.positive || 0) * 100).toFixed(1)}%</td>
            <td class="neg">${((h.negative || 0) * 100).toFixed(1)}%</td>
            <td>${((h.neutral  || 0) * 100).toFixed(1)}%</td>
            <td>${(h.crisis_score || 0).toFixed(3)}</td>
            <td>
              <button class="btn btn-outline btn-sm" onclick="openJobResult('${h.job_id}')">Open</button>
            </td>
          </tr>`).join('')}
      </tbody>
    </table>`;
}


function openJobResult(jobId) {
    State.lastJobId = jobId;
    localStorage.setItem('lastJobId', jobId);
    navigate('results');
    
}


async function compareBrands() {
  const sel      = document.getElementById('brand-compare-select');
  const selected = [...sel.selectedOptions].map(o => o.value);


  if (selected.length < 2) return setMsg('compare-msg', 'warn', 'Select at least 2 brands (hold Ctrl).');
  if (selected.length > 5) return setMsg('compare-msg', 'warn', 'Maximum 5 brands.');


  document.getElementById('compare-msg').innerHTML = '';


  const result = await API.compareBrands(selected);
  if (result.error) return setMsg('compare-msg', 'danger', result.error);


  renderCompareCards(result.comparison || []);
}


function renderCompareCards(comparison) {
  const el = document.getElementById('compare-result');
  const available = comparison.filter(b => b.available);
  if (!available.length) {
    el.innerHTML = '<div class="status-line">No data available for selected brands.</div>';
    return;
  }
  const cols = Math.min(available.length, 4);
  el.innerHTML = `
    <div class="g${cols}">
      ${available.map(b => `
        <div class="metric-card ${b.crisis_triggered ? 'neg' : ''}">
          <div class="m-label">${esc(b.brand_name)}</div>
          <div class="m-value" style="color:var(--pos)">${b.positive_pct}%</div>
          <div class="m-sub">positive</div>
          <hr class="sep">
          <div style="font-size:12px;color:var(--neg);margin-bottom:3px;">Neg: ${b.negative_pct}%</div>
          <div style="font-size:12px;color:var(--muted);">Score: ${b.crisis_score.toFixed(3)}</div>
          <div style="margin-top:6px;">
            ${b.crisis_triggered
              ? '<span class="badge badge-crisis">Crisis</span>'
              : '<span class="badge badge-pos">Normal</span>'}
          </div>
          <div style="font-size:10px;color:var(--muted);margin-top:6px;">${b.post_count.toLocaleString()} posts</div>
        </div>`).join('')}
    </div>`;
}


// ══════════════════════════════════════════════════════
// ALERTS
// ══════════════════════════════════════════════════════


async function loadAlertsPage() {
  const brandFilter = document.getElementById('alert-brand-filter')?.value.trim() || '';
  const unackOnly   = document.getElementById('alert-unack-only')?.checked || false;


  const alerts    = await API.getAlerts(brandFilter || null, unackOnly);
  const container = document.getElementById('alerts-container');
  const count     = document.getElementById('alert-count');


  count.textContent = `${alerts.length} alert(s) found`;


  if (!alerts.length) {
    container.innerHTML = `
      <div class="alert-banner ok">
        No crisis alerts. All brands within normal sentiment parameters.
      </div>`;
    return;
  }


  container.innerHTML = alerts.map(a => {
    const date  = (a.triggered_at || '').substring(0, 16).replace('T', ' ');
    const acked = a.is_acknowledged;
    return `
      <div class="alert-item ${acked ? 'acked' : ''}">
        <div style="display:flex;align-items:baseline;gap:12px;margin-bottom:10px;flex-wrap:wrap;">
          <strong style="font-size:14px;letter-spacing:1px;">${esc(a.brand_name)}</strong>
          ${acked
            ? '<span class="badge" style="color:var(--muted);border-color:var(--muted);">Acknowledged</span>'
            : '<span class="badge badge-crisis">Crisis</span>'}
          <span style="font-size:11px;color:var(--muted);">${date}</span>
        </div>
        <div class="g2 mb8" style="max-width:400px;">
          <div class="metric-card neg" style="padding:10px;">
            <div class="m-label">Negative %</div>
            <div class="m-value" style="font-size:22px;">${a.spike_percentage.toFixed(1)}%</div>
          </div>
          <div class="metric-card" style="padding:10px;">
            <div class="m-label">Crisis Score</div>
            <div class="m-value" style="font-size:22px;">${a.current_score.toFixed(2)}</div>
          </div>
        </div>
        ${a.top_concern
          ? `<div style="font-size:12px;color:var(--muted);margin-bottom:8px;">Top concern: ${esc(a.top_concern)}</div>`
          : ''}
        ${!acked
          ? `<button class="btn btn-outline btn-sm" onclick="ackAlert(${a.id})">Acknowledge</button>`
          : ''}
      </div>`;
  }).join('');
}


async function ackAlert(id) {
  const r = await API.acknowledgeAlert(id);
  if (r && !r.error) loadAlertsPage();
  else setMsg('alerts-msg', 'danger', 'Failed to acknowledge alert.');
}


// ══════════════════════════════════════════════════════
// CHARTS
// ══════════════════════════════════════════════════════


function destroyChart(id) {
  if (State.charts[id]) { State.charts[id].destroy(); delete State.charts[id]; }
}


function renderDonut(id, dist) {
  destroyChart(id);
  const ctx = document.getElementById(id);
  if (!ctx) return;
  State.charts[id] = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['Positive', 'Negative', 'Neutral'],
      datasets: [{
        data: [
          +((dist.positive || 0) * 100).toFixed(1),
          +((dist.negative || 0) * 100).toFixed(1),
          +((dist.neutral  || 0) * 100).toFixed(1),
        ],
        backgroundColor: [C.pos, C.neg, C.neu],
        borderColor: C.bg,
        borderWidth: 3,
      }],
    },
    options: {
      maintainAspectRatio: false,
      cutout: '60%',
      plugins: {
        legend: { position: 'bottom', labels: { boxWidth: 12, padding: 16 } },
        tooltip: { callbacks: { label: ctx => ` ${ctx.label}: ${ctx.raw}%` } },
      },
    },
  });
}


function renderBar(id, dist, wgt) {
  destroyChart(id);
  const ctx = document.getElementById(id);
  if (!ctx) return;
  State.charts[id] = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: ['Positive', 'Negative', 'Neutral'],
      datasets: [
        {
          label: 'Raw',
          data: [+((dist.positive||0)*100).toFixed(1), +((dist.negative||0)*100).toFixed(1), +((dist.neutral||0)*100).toFixed(1)],
          backgroundColor: [`${C.pos}55`, `${C.neg}55`, `${C.neu}55`],
          borderColor:     [C.pos, C.neg, C.neu],
          borderWidth: 1,
        },
        {
          label: 'Engagement-Weighted',
          data: [+((wgt.positive||0)*100).toFixed(1), +((wgt.negative||0)*100).toFixed(1), +((wgt.neutral||0)*100).toFixed(1)],
          backgroundColor: [C.pos, C.neg, C.neu],
          borderWidth: 0,
        },
      ],
    },
    options: {
      maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, padding: 16 } } },
      scales: {
        y: { beginAtZero: true, max: 100, grid: { color: C.border }, ticks: { callback: v => v + '%' } },
        x: { grid: { display: false } },
      },
    },
  });
}


function renderAspect(id, aspects) {
  destroyChart(id);
  const ctx = document.getElementById(id);
  if (!ctx) return;
  const labels = Object.keys(aspects).map(a => a.replace(/_/g, ' ').toUpperCase());
  State.charts[id] = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: 'Positive', data: Object.values(aspects).map(a => +( a.positive*100).toFixed(1)), backgroundColor: C.pos },
        { label: 'Negative', data: Object.values(aspects).map(a => +( a.negative*100).toFixed(1)), backgroundColor: C.neg },
        { label: 'Neutral',  data: Object.values(aspects).map(a => +( a.neutral *100).toFixed(1)), backgroundColor: C.neu },
      ],
    },
    options: {
      maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, padding: 16 } } },
      scales: {
        y: { stacked: true, max: 100, grid: { color: C.border }, ticks: { callback: v => v + '%' } },
        x: { stacked: true, grid: { display: false } },
      },
    },
  });
}


function renderPlatform(id, platData) {
  destroyChart(id);
  const ctx = document.getElementById(id);
  if (!ctx) return;
  const labels = Object.keys(platData).map(p => p.toUpperCase());
  State.charts[id] = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: 'Positive', data: Object.values(platData).map(p => p.positive_pct), backgroundColor: C.pos },
        { label: 'Negative', data: Object.values(platData).map(p => p.negative_pct), backgroundColor: C.neg },
        { label: 'Neutral',  data: Object.values(platData).map(p => p.neutral_pct),  backgroundColor: C.neu },
      ],
    },
    options: {
      maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, padding: 16 } } },
      scales: {
        y: { stacked: true, max: 100, grid: { color: C.border }, ticks: { callback: v => v + '%' } },
        x: { stacked: true, grid: { display: false } },
      },
    },
  });
}


function renderTrend(id, trend) {
  destroyChart(id);
  const ctx = document.getElementById(id);
  if (!ctx) return;
  const labels = trend.map(t => t.date.substring(0, 10));
  State.charts[id] = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: 'Positive', data: trend.map(t => t.positive), borderColor: C.pos, backgroundColor: `${C.pos}15`, fill: true, tension: 0.3, borderWidth: 2, pointRadius: 3 },
        { label: 'Negative', data: trend.map(t => t.negative), borderColor: C.neg, backgroundColor: `${C.neg}15`, fill: true, tension: 0.3, borderWidth: 2, pointRadius: 3 },
        { label: 'Neutral',  data: trend.map(t => t.neutral),  borderColor: C.neu, borderDash: [4, 4], tension: 0.3, borderWidth: 1.5, pointRadius: 2 },
      ],
    },
    options: {
      maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, padding: 16 } } },
      scales: {
        y: { beginAtZero: true, max: 100, grid: { color: C.border }, ticks: { callback: v => v + '%' } },
        x: { grid: { color: C.border } },
      },
      interaction: { mode: 'index', intersect: false },
    },
  });
}


// ══════════════════════════════════════════════════════
// UTILITIES
// ══════════════════════════════════════════════════════


function setMsg(containerId, type, text) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const map = { ok: 'ok', info: 'ok', warn: 'warn', danger: 'danger' };
  el.innerHTML = `<div class="alert-banner ${map[type] || 'ok'}" style="margin-bottom:8px;">${esc(text)}</div>`;
}



function renderMd(text) {
  return text
    .split('\n\n')
    .map(block => {
      block = esc(block)
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.+?)\*/g,     '<em>$1</em>');
      if (block.trim().startsWith('- ')) {
        const items = block.split('\n')
          .filter(l => l.trim())
          .map(l => `<li>${l.replace(/^- /, '')}</li>`)
          .join('');
        return `<ul>${items}</ul>`;
      }
      return `<p>${block.replace(/\n/g, '<br>')}</p>`;
    })
    .join('');
}



function esc(str) {
  return String(str)
    .replace(/&/g,  '&amp;')
    .replace(/</g,  '&lt;')
    .replace(/>/g,  '&gt;')
    .replace(/"/g,  '&quot;')
    .replace(/'/g,  '&#39;');
}


// ══════════════════════════════════════════════════════
// INIT
// ══════════════════════════════════════════════════════


document.addEventListener('DOMContentLoaded', async () => {
  startClock();
  await checkHealth();
  setInterval(checkHealth, 30000);

  // Bind nav tabs
  document.querySelectorAll('[data-page]').forEach(el => {
    el.addEventListener('click', () => navigate(el.dataset.page));
  });

  // Range label
  const limitEl = document.getElementById('limit-input');
  const limitLb = document.getElementById('limit-label');
  if (limitEl && limitLb) {
    limitLb.textContent = limitEl.value;
    limitEl.addEventListener('input', () => { limitLb.textContent = limitEl.value; });
  }

  // Restore last job or go straight to dashboard
  if (State.lastJobId) {
    const el = document.getElementById('result-job-input');
    const jd = document.getElementById('job-id-display');
    const jr = document.getElementById('job-id-row');
    if (el) el.value = State.lastJobId;
    if (jd) jd.textContent = State.lastJobId;
    if (jr) jr.style.display = 'flex';

    // silently check if job is still in progress
    const s = await API.getJobStatus(State.lastJobId);
    if (s && !s.error && (s.status === 'collecting' || s.status === 'processing'
        || s.status === 'analyzing' || s.status === 'pending')) {
      navigate('analyze');
      setMsg('analyze-msg', 'info', `Resumed: job ${State.lastJobId} still running...`);
      pollJob(State.lastJobId);
    } else {
      navigate('dashboard');
    }
  } else {
    navigate('dashboard'); 
  }
});