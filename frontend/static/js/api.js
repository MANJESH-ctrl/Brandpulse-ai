/* ══════════════════════════════════════════════════════
   BRANDPULSE AI — API Client
══════════════════════════════════════════════════════ */

const API = (() => {
  const BASE = '';
  const TIMEOUT = 30000;

  async function _fetch(method, path, body = null) {
    const opts = {
      method,
      headers: { 'Content-Type': 'application/json' },
    };
    if (body !== null) opts.body = JSON.stringify(body);

    try {
      const resp = await fetch(`${BASE}${path}`, opts);
      const data = await resp.json();
      if (!resp.ok) return { error: data.detail || `HTTP ${resp.status}` };
      return data;
    } catch (e) {
      return { error: e.message };
    }
  }

  return {
    // ── Health ──────────────────────────────────────────
    async health() {
      try {
        const r = await fetch('/health');
        const d = await r.json();
        return d.status === 'healthy';
      } catch { return false; }
    },

    // ── Analysis ────────────────────────────────────────
    async startAnalysis(brandName, keywords, platforms, limit) {
      return _fetch('POST', '/api/analyze', {
        brand_name: brandName,
        keywords:   keywords || '',
        platforms,
        limit_per_platform: limit,
      });
    },

    async getJobStatus(jobId) {
      return _fetch('GET', `/api/status/${jobId}`);
    },

    async getCollectedPosts(jobId) {
      return _fetch('GET', `/api/posts/${jobId}`);
    },

    // ── Results ──────────────────────────────────────────
    async getResult(jobId) {
      return _fetch('GET', `/api/results/${jobId}`);
    },

    async getPlatformSentiment(jobId) {
      return _fetch('GET', `/api/results/${jobId}/posts/sentiment`);
    },

    // ── Brands ───────────────────────────────────────────
    async listBrands() {
      const r = await _fetch('GET', '/api/brands');
      return Array.isArray(r) ? r : [];
    },

    async getBrandHistory(brandName) {
      const r = await _fetch('GET', `/api/brands/${encodeURIComponent(brandName)}`);
      return Array.isArray(r) ? r : [];
    },

    async getBrandTrend(brandName) {
      const r = await _fetch('GET', `/api/brands/${encodeURIComponent(brandName)}/trend`);
      return Array.isArray(r) ? r : [];
    },

    async compareBrands(brandNames) {
      return _fetch('POST', '/api/brands/compare', brandNames);
    },

    // ── Alerts ───────────────────────────────────────────
    async getAlerts(brandName = null, unackOnly = false) {
      const params = new URLSearchParams();
      if (brandName) params.append('brand_name', brandName);
      if (unackOnly) params.append('unacknowledged_only', 'true');
      const query = params.toString();
      const r = await _fetch('GET', `/api/alerts${query ? '?' + query : ''}`);
      return Array.isArray(r) ? r : [];
    },

    async acknowledgeAlert(alertId) {
      return _fetch('PATCH', `/api/alerts/${alertId}/acknowledge`);
    },
  };
})();
