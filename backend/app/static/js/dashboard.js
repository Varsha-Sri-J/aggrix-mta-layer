/**
 * AGGRIX Real-Time Analytics & Live Dashboard Controller
 * Connects REST Analytics APIs and Server-Sent Events (SSE) Stream
 */

(function() {
  'use strict';

  // State
  const state = {
    token: sessionStorage.getItem('aggrix_token') || localStorage.getItem('aggrix_token') || '',
    user: null,
    tenants: [],
    selectedTenantId: null,
    dateRange: 'all',
    currency: '',
    eventSource: null,
    lastEventId: null,
    eventCount: 0,
    reconnectAttempts: 0,
    reconnectTimer: null,
    currentOverview: null,
  };

  // DOM Elements
  const els = {
    connectionPill: document.getElementById('connection-status-pill'),
    statusLabel: document.getElementById('status-label'),
    tenantSelect: document.getElementById('tenant-select'),
    dateFilterGroup: document.getElementById('date-filter-group'),
    currencySelect: document.getElementById('currency-select'),
    lastUpdatedText: document.getElementById('last-updated-text'),
    roleAvatar: document.getElementById('role-avatar'),
    roleTitle: document.getElementById('role-title'),
    btnAuthSwitch: document.getElementById('btn-auth-switch'),
    // KPI elements
    kpiGross: document.getElementById('kpi-gross-revenue'),
    kpiNet: document.getElementById('kpi-net-sales'),
    kpiOrders: document.getElementById('kpi-total-orders'),
    kpiAov: document.getElementById('kpi-aov'),
    kpiCustomers: document.getElementById('kpi-active-customers'),
    kpiPendingOrders: document.getElementById('kpi-pending-orders'),
    kpiPendingAmount: document.getElementById('kpi-pending-amount'),
    kpiCardGross: document.getElementById('kpi-card-gross'),
    kpiCardOrders: document.getElementById('kpi-card-orders'),
    // Charts
    svgRevenueChart: document.getElementById('svg-revenue-chart'),
    svgStatusDonut: document.getElementById('svg-status-donut'),
    donutTotalOrders: document.getElementById('donut-total-orders'),
    statusLegendList: document.getElementById('status-legend-list'),
    chartRevenueLoading: document.getElementById('chart-revenue-loading'),
    topProductsList: document.getElementById('top-products-list'),
    // Feed
    recentOrdersFeed: document.getElementById('recent-orders-feed'),
    feedEmptyState: document.getElementById('feed-empty-state'),
    feedEventCount: document.getElementById('feed-event-count'),
    // Modal
    modalBackdrop: document.getElementById('auth-modal-backdrop'),
    btnCloseModal: document.getElementById('btn-close-modal'),
    tabBtnLogin: document.getElementById('tab-btn-login'),
    tabBtnToken: document.getElementById('tab-btn-token'),
    formLogin: document.getElementById('form-login'),
    formToken: document.getElementById('form-token'),
    loginEmail: document.getElementById('login-email'),
    loginPassword: document.getElementById('login-password'),
    rawTokenInput: document.getElementById('raw-token-input'),
    toastContainer: document.getElementById('toast-container'),
  };

  // Helpers
  function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    els.toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  function escapeHTML(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function formatMoney(amount, currency = 'USD') {
    return ChartsEngine.formatMoney(amount, currency || 'USD');
  }

  function getDateBounds(rangeKey) {
    if (rangeKey === 'all') return { start_date: null, end_date: null };
    const now = new Date();
    const end = now.toISOString().split('T')[0];
    const days = rangeKey === '7d' ? 7 : 30;
    const past = new Date(now.getTime() - days * 24 * 60 * 60 * 1000);
    const start = past.toISOString().split('T')[0];
    return { start_date: start, end_date: end };
  }

  function getAuthHeaders() {
    const headers = { 'Accept': 'application/json' };
    if (state.token) {
      headers['Authorization'] = `Bearer ${state.token}`;
    }
    return headers;
  }

  // API Calls
  async function apiFetch(endpoint) {
    const res = await fetch(endpoint, { headers: getAuthHeaders() });
    if (res.status === 401) {
      setConnectionStatus('disconnected', 'Unauthorized');
      openAuthModal();
      throw new Error('Authentication required');
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'API request failed' }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  }

  // Check Current User Profile
  async function fetchUserProfile() {
    if (!state.token) return null;
    try {
      const data = await apiFetch('/api/v1/auth/me');
      state.user = data;
      if (els.roleTitle) els.roleTitle.textContent = data.role.replace('_', ' ').toUpperCase();
      if (els.roleAvatar) els.roleAvatar.textContent = data.email.charAt(0).toUpperCase();
      return data;
    } catch (e) {
      console.warn('Failed to fetch user profile:', e);
      return null;
    }
  }

  // Load Authorized Tenants
  async function loadTenants() {
    try {
      const res = await apiFetch('/api/v1/analytics/tenants');
      state.tenants = res.tenants || [];
      els.tenantSelect.innerHTML = '';

      if (state.tenants.length === 0) {
        els.tenantSelect.innerHTML = '<option value="">No authorized stores found</option>';
        return;
      }

      state.tenants.forEach(t => {
        const opt = document.createElement('option');
        opt.value = t.id;
        opt.textContent = `${t.name} (${t.domain})`;
        els.tenantSelect.appendChild(opt);
      });

      // Default selection
      if (!state.selectedTenantId || !state.tenants.some(t => t.id === state.selectedTenantId)) {
        state.selectedTenantId = state.tenants[0].id;
      }
      els.tenantSelect.value = state.selectedTenantId;
    } catch (err) {
      console.error('Failed to load tenants:', err);
    }
  }

  // Load Overview Metrics
  async function loadOverview() {
    if (!state.selectedTenantId) return;

    try {
      els.lastUpdatedText.textContent = 'Refreshing...';
      const bounds = getDateBounds(state.dateRange);
      const params = new URLSearchParams();
      if (bounds.start_date) params.append('start_date', bounds.start_date);
      if (bounds.end_date) params.append('end_date', bounds.end_date);
      if (state.currency) params.append('currency', state.currency);

      const queryStr = params.toString() ? `?${params.toString()}` : '';

      // Concurrent overview + daily metrics
      const [overviewData, dailyData] = await Promise.all([
        apiFetch(`/api/v1/analytics/tenants/${state.selectedTenantId}/overview${queryStr}`),
        apiFetch(`/api/v1/analytics/tenants/${state.selectedTenantId}/daily${queryStr}&page_size=100`).catch(() => ({ data: [] })),
      ]);

      state.currentOverview = overviewData;
      renderKPIs(overviewData.summary);
      renderStatusDistribution(overviewData.status_distribution);
      renderTopProducts(overviewData.top_products);
      renderRecentFeedInitial(overviewData.recent_orders);

      if (els.chartRevenueLoading) els.chartRevenueLoading.style.display = 'none';
      ChartsEngine.renderRevenueChart(els.svgRevenueChart, dailyData.data || [], state.currency || 'USD');

      const now = new Date();
      els.lastUpdatedText.textContent = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`;
    } catch (err) {
      console.error('Failed to load overview:', err);
      showToast(`Error: ${err.message}`, 'error');
      els.lastUpdatedText.textContent = 'Sync failed';
    }
  }

  // Render KPI Cards
  function renderKPIs(summary) {
    if (!summary) return;
    const curr = summary.currency || state.currency || 'USD';

    // Gross Sales
    if (summary.gross_sales !== null && summary.gross_sales !== undefined) {
      els.kpiGross.textContent = formatMoney(summary.gross_sales, curr);
    } else {
      els.kpiGross.textContent = 'Multi-Curr';
    }

    // Net Sales
    if (summary.net_sales !== null && summary.net_sales !== undefined) {
      els.kpiNet.textContent = formatMoney(summary.net_sales, curr);
    } else {
      els.kpiNet.textContent = 'Multi-Curr';
    }

    // Total Orders
    els.kpiOrders.textContent = (summary.total_orders || 0).toLocaleString();

    // Average Order Value
    if (summary.average_order_value !== null && summary.average_order_value !== undefined) {
      els.kpiAov.textContent = formatMoney(summary.average_order_value, curr);
    } else {
      els.kpiAov.textContent = 'N/A';
    }

    // Active Customers
    els.kpiCustomers.textContent = (summary.active_customers_count || 0).toLocaleString();

    // Pending Orders & Sales
    els.kpiPendingOrders.textContent = (summary.pending_orders_count || 0).toLocaleString();
    if (summary.pending_sales !== null && summary.pending_sales !== undefined) {
      els.kpiPendingAmount.textContent = `(${formatMoney(summary.pending_sales, curr)})`;
    } else {
      els.kpiPendingAmount.textContent = '';
    }
  }

  // Render Status Distribution Donut & Legend
  function renderStatusDistribution(statuses) {
    if (!statuses) return;
    ChartsEngine.renderStatusDonut(els.svgStatusDonut, statuses);

    const total = statuses.reduce((acc, s) => acc + (s.orders_count || 0), 0);
    els.donutTotalOrders.textContent = total.toLocaleString();

    els.statusLegendList.innerHTML = '';
    statuses.forEach(s => {
      const row = document.createElement('div');
      row.className = 'status-legend-row';
      row.innerHTML = `
        <div class="status-label-group">
          <span class="status-dot-indicator status-dot-${s.status}"></span>
          <span class="status-name" style="text-transform: capitalize;">${s.status}</span>
        </div>
        <div class="status-values">
          <span class="status-count-val">${s.orders_count.toLocaleString()}</span>
          <span class="status-pct-val">(${s.percentage}%)</span>
        </div>
      `;
      els.statusLegendList.appendChild(row);
    });
  }

  // Render Top Products
  function renderTopProducts(products) {
    if (!products || products.length === 0) {
      els.topProductsList.innerHTML = '<div class="empty-state">No product transactions recorded yet</div>';
      return;
    }

    const maxSales = Math.max(...products.map(p => parseFloat(p.gross_sales || 0)), 1);
    els.topProductsList.innerHTML = '';

    products.forEach(p => {
      const row = document.createElement('div');
      row.className = 'product-row';
      const pct = Math.min(100, Math.round((parseFloat(p.gross_sales || 0) / maxSales) * 100));

      const pName = escapeHTML(p.product_name || 'Item');
      const pSku = escapeHTML(p.product_sku || 'SKU');
      row.innerHTML = `
        <div class="product-row-top">
          <div class="product-name-sku">
            <span class="product-name" title="${pName}">${pName}</span>
            <span class="product-sku">${pSku}</span>
          </div>
          <span class="product-sales">${formatMoney(p.gross_sales, p.currency)}</span>
        </div>
        <div class="product-progress-track">
          <div class="product-progress-bar" style="width: ${pct}%"></div>
        </div>
      `;
      els.topProductsList.appendChild(row);
    });
  }

  // Render Initial Recent Orders Feed
  function renderRecentFeedInitial(orders) {
    if (!orders || orders.length === 0) {
      if (els.feedEmptyState) els.feedEmptyState.style.display = 'flex';
      return;
    }

    if (els.feedEmptyState) els.feedEmptyState.style.display = 'none';
    els.recentOrdersFeed.innerHTML = '';

    orders.forEach(order => {
      appendOrderFeedItem(order, false);
    });
  }

  // Append a Single Order Card to Feed
  function appendOrderFeedItem(order, isLiveNew = true) {
    if (els.feedEmptyState) els.feedEmptyState.style.display = 'none';

    const item = document.createElement('div');
    item.className = `feed-item ${isLiveNew ? 'new-event-flash' : ''}`;

    const dateStr = order.created_at ? new Date(order.created_at).toLocaleTimeString() : 'Just now';
    const rawStatus = order.status || 'pending';
    const statusClass = `status-badge-${encodeURIComponent(rawStatus)}`;
    const orderId = escapeHTML(order.external_order_id || String(order.id).substring(0, 8));
    const custName = order.customer_name ? `${escapeHTML(order.customer_name)} • ` : '';

    item.innerHTML = `
      <div class="feed-item-left">
        <span class="feed-status-badge ${statusClass}">${escapeHTML(rawStatus)}</span>
        <div class="feed-order-meta">
          <span class="feed-order-id">${orderId}</span>
          <span class="feed-order-time">${custName}${dateStr}</span>
        </div>
      </div>
      <div class="feed-item-right">
        <span class="feed-order-amount">${formatMoney(order.total_amount, order.currency)}</span>
      </div>
    `;

    if (isLiveNew) {
      els.recentOrdersFeed.prepend(item);
      // Flash KPI cards
      flashElement(els.kpiCardGross);
      flashElement(els.kpiCardOrders);
      // Prune feed to top 30
      if (els.recentOrdersFeed.children.length > 30) {
        els.recentOrdersFeed.lastElementChild.remove();
      }
    } else {
      els.recentOrdersFeed.appendChild(item);
    }
  }

  function flashElement(el) {
    if (!el) return;
    el.classList.add('flash-update');
    setTimeout(() => el.classList.remove('flash-update'), 1200);
  }

  // ==========================================================================
  // Real-Time Server-Sent Events (SSE) Client
  // ==========================================================================
  function setConnectionStatus(status, label) {
    els.connectionPill.className = `connection-status-pill ${status}`;
    els.statusLabel.textContent = label;
  }

  function connectSSE() {
    if (state.eventSource) {
      state.eventSource.close();
      state.eventSource = null;
    }

    if (!state.token) {
      setConnectionStatus('disconnected', 'No Auth Token');
      return;
    }

    setConnectionStatus('reconnecting', 'Connecting...');

    const params = new URLSearchParams();
    params.append('token', state.token);
    if (state.selectedTenantId) {
      params.append('tenant_id', state.selectedTenantId);
    }
    if (state.lastEventId) {
      params.append('last_event_id', state.lastEventId);
    }

    const streamUrl = `/api/v1/analytics/stream?${params.toString()}`;
    const es = new EventSource(streamUrl);
    state.eventSource = es;

    es.addEventListener('open', () => {
      state.reconnectAttempts = 0;
      setConnectionStatus('connected', 'LIVE STREAM');
    });

    es.addEventListener('connected', (event) => {
      try {
        const payload = JSON.parse(event.data);
        console.log('[SSE] Stream connected acknowledgment:', payload);
      } catch (e) {}
    });

    // Handle order lifecycle events
    const orderEvents = ['order.created', 'order.paid', 'order.fulfilled', 'order.cancelled'];
    orderEvents.forEach(eventType => {
      es.addEventListener(eventType, (e) => {
        handleIncomingLiveEvent(eventType, e);
      });
    });

    es.onerror = (err) => {
      console.warn('[SSE] Connection interrupted:', err);
      setConnectionStatus('reconnecting', 'Reconnecting...');
      es.close();
      state.eventSource = null;

      // Exponential backoff reconnection
      const delay = Math.min(10000, 1000 * Math.pow(1.5, state.reconnectAttempts));
      state.reconnectAttempts++;
      clearTimeout(state.reconnectTimer);
      state.reconnectTimer = setTimeout(() => {
        connectSSE();
      }, delay);
    };
  }

  function handleIncomingLiveEvent(eventType, e) {
    try {
      const data = JSON.parse(e.data);
      if (e.lastEventId) {
        state.lastEventId = e.lastEventId;
      }

      state.eventCount++;
      els.feedEventCount.textContent = state.eventCount.toString();

      // Append to live feed
      appendOrderFeedItem({
        id: data.order_id,
        external_order_id: data.external_order_id,
        status: data.status,
        total_amount: data.total_amount,
        currency: data.currency,
        created_at: data.created_at,
      }, true);

      // Dynamically increment KPI metrics in real time
      if (state.currentOverview && state.currentOverview.summary) {
        const summary = state.currentOverview.summary;
        if (eventType === 'order.created') {
          summary.total_orders = (summary.total_orders || 0) + 1;
          if (summary.gross_sales !== null) {
            summary.gross_sales = (parseFloat(summary.gross_sales) + parseFloat(data.total_amount)).toFixed(2);
          }
          summary.pending_orders_count = (summary.pending_orders_count || 0) + 1;
          renderKPIs(summary);
        } else if (eventType === 'order.paid') {
          if (summary.net_sales !== null) {
            summary.net_sales = (parseFloat(summary.net_sales) + parseFloat(data.total_amount)).toFixed(2);
          }
          summary.pending_orders_count = Math.max(0, (summary.pending_orders_count || 1) - 1);
          renderKPIs(summary);
        }
      }
    } catch (parseErr) {
      console.error('[SSE] Failed to process live event:', parseErr);
    }
  }

  // ==========================================================================
  // Auth Modal & Controls
  // ==========================================================================
  function openAuthModal() {
    els.modalBackdrop.classList.remove('hidden');
  }

  function closeAuthModal() {
    els.modalBackdrop.classList.add('hidden');
  }

  function initEventListeners() {
    // Tenant Switcher
    els.tenantSelect.addEventListener('change', (e) => {
      state.selectedTenantId = e.target.value;
      loadOverview();
      connectSSE();
    });

    // Date Filter Buttons
    els.dateFilterGroup.addEventListener('click', (e) => {
      const btn = e.target.closest('.date-btn');
      if (!btn) return;
      els.dateFilterGroup.querySelectorAll('.date-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.dateRange = btn.dataset.range;
      loadOverview();
    });

    // Currency Switcher
    els.currencySelect.addEventListener('change', (e) => {
      state.currency = e.target.value;
      loadOverview();
    });

    // Auth Switch Button
    els.btnAuthSwitch.addEventListener('click', openAuthModal);
    els.btnCloseModal.addEventListener('click', closeAuthModal);

    // Modal tabs
    els.tabBtnLogin.addEventListener('click', () => {
      els.tabBtnLogin.classList.add('active');
      els.tabBtnToken.classList.remove('active');
      els.formLogin.classList.remove('hidden');
      els.formToken.classList.add('hidden');
    });

    els.tabBtnToken.addEventListener('click', () => {
      els.tabBtnToken.classList.add('active');
      els.tabBtnLogin.classList.remove('active');
      els.formToken.classList.remove('hidden');
      els.formLogin.classList.add('hidden');
    });

    // Direct Login Form
    els.formLogin.addEventListener('submit', async (e) => {
      e.preventDefault();
      const email = els.loginEmail.value.trim();
      const password = els.loginPassword.value;

      try {
        const res = await fetch('/api/v1/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password }),
        });

        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: 'Login failed' }));
          throw new Error(err.detail || 'Authentication failed');
        }

        const data = await res.json();
        state.token = data.access_token;
        sessionStorage.setItem('aggrix_token', state.token);
        closeAuthModal();
        showToast('Authenticated successfully', 'success');

        await fetchUserProfile();
        await loadTenants();
        await loadOverview();
        connectSSE();
      } catch (err) {
        showToast(err.message, 'error');
      }
    });

    // Raw Token Form
    els.formToken.addEventListener('submit', async (e) => {
      e.preventDefault();
      const rawToken = els.rawTokenInput.value.trim();
      if (!rawToken) return;

      state.token = rawToken;
      sessionStorage.setItem('aggrix_token', state.token);
      closeAuthModal();
      showToast('JWT Token configured', 'success');

      await fetchUserProfile();
      await loadTenants();
      await loadOverview();
      connectSSE();
    });
  }

  // Auto-Initialization
  async function init() {
    initEventListeners();

    // Check URL parameters for initial token or tenant
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has('token')) {
      state.token = urlParams.get('token');
      sessionStorage.setItem('aggrix_token', state.token);
    }
    if (urlParams.has('tenant_id')) {
      state.selectedTenantId = urlParams.get('tenant_id');
    }

    if (state.token) {
      await fetchUserProfile();
      await loadTenants();
      await loadOverview();
      connectSSE();
    } else {
      // Auto-prompt modal if not authenticated
      openAuthModal();
    }
  }

  // Launch on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
