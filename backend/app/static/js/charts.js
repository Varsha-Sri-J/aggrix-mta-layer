/**
 * AGGRIX Real-Time Analytics Charts Library
 * Zero-dependency SVG Area and Donut Chart Engine
 */

const ChartsEngine = (function() {
  'use strict';

  /**
   * Formats a monetary number into standard currency string
   */
  function formatMoney(amount, currency = 'USD') {
    const symbols = { USD: '$', EUR: '€', GBP: '£' };
    const sym = symbols[currency] || (currency ? currency + ' ' : '$');
    const num = parseFloat(amount || 0);
    return `${sym}${num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }

  /**
   * Renders a responsive SVG Timeseries Area Chart for Revenue Trajectory
   * @param {SVGSVGElement} svg
   * @param {Array} data - Array of daily metrics objects: { metric_date, gross_sales, net_sales }
   * @param {string} currency
   */
  function renderRevenueChart(svg, data, currency = 'USD') {
    if (!svg) return;
    svg.innerHTML = '';

    if (!data || data.length === 0) {
      const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      text.setAttribute('x', '400');
      text.setAttribute('y', '130');
      text.setAttribute('text-anchor', 'middle');
      text.setAttribute('fill', '#64748b');
      text.setAttribute('font-size', '14');
      text.textContent = 'No chronological metrics available for the selected filters';
      svg.appendChild(text);
      return;
    }

    // Sort chronologically ascending
    const sorted = [...data].sort((a, b) => new Date(a.metric_date) - new Date(b.metric_date));

    const width = 800;
    const height = 260;
    const padding = { top: 25, right: 30, bottom: 40, left: 65 };

    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;

    // Determine max value for Y-axis scale
    let maxVal = 0;
    sorted.forEach(d => {
      const gross = parseFloat(d.gross_sales || 0);
      const net = parseFloat(d.net_sales || 0);
      if (gross > maxVal) maxVal = gross;
      if (net > maxVal) maxVal = net;
    });

    if (maxVal <= 0) maxVal = 1000;
    // Add 10% headroom
    maxVal = maxVal * 1.1;

    // Defs for gradients and filters
    const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
    defs.innerHTML = `
      <linearGradient id="grossGradient" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#3b82f6" stop-opacity="0.45" />
        <stop offset="100%" stop-color="#3b82f6" stop-opacity="0.0" />
      </linearGradient>
      <linearGradient id="netGradient" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#10b981" stop-opacity="0.35" />
        <stop offset="100%" stop-color="#10b981" stop-opacity="0.0" />
      </linearGradient>
      <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
        <feGaussianBlur stdDeviation="3" result="glow" />
        <feComposite in="SourceGraphic" in2="glow" operator="over" />
      </filter>
    `;
    svg.appendChild(defs);

    // Coordinate mapping functions
    const getX = (index) => {
      if (sorted.length === 1) return padding.left + chartWidth / 2;
      return padding.left + (index / (sorted.length - 1)) * chartWidth;
    };

    const getY = (val) => {
      const clamped = Math.max(0, parseFloat(val || 0));
      return padding.top + chartHeight - (clamped / maxVal) * chartHeight;
    };

    // Draw horizontal grid lines and Y-axis labels
    const gridCount = 4;
    for (let i = 0; i <= gridCount; i++) {
      const yVal = (maxVal / gridCount) * i;
      const yPos = getY(yVal);

      // Line
      const gridLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      gridLine.setAttribute('x1', padding.left);
      gridLine.setAttribute('y1', yPos);
      gridLine.setAttribute('x2', width - padding.right);
      gridLine.setAttribute('y2', yPos);
      gridLine.setAttribute('stroke', 'rgba(255, 255, 255, 0.05)');
      gridLine.setAttribute('stroke-dasharray', '4 4');
      svg.appendChild(gridLine);

      // Y-axis label
      const yLabel = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      yLabel.setAttribute('x', padding.left - 10);
      yLabel.setAttribute('y', yPos + 4);
      yLabel.setAttribute('text-anchor', 'end');
      yLabel.setAttribute('fill', '#64748b');
      yLabel.setAttribute('font-size', '10');
      yLabel.setAttribute('font-family', 'var(--font-mono)');
      yLabel.textContent = yVal >= 1000 ? `${(yVal / 1000).toFixed(0)}k` : yVal.toFixed(0);
      svg.appendChild(yLabel);
    }

    // Build path points
    let grossPathD = '';
    let grossAreaD = '';
    let netPathD = '';
    let netAreaD = '';

    sorted.forEach((d, i) => {
      const x = getX(i);
      const yGross = getY(d.gross_sales);
      const yNet = getY(d.net_sales);

      if (i === 0) {
        grossPathD += `M ${x} ${yGross}`;
        grossAreaD += `M ${x} ${getY(0)} L ${x} ${yGross}`;
        netPathD += `M ${x} ${yNet}`;
        netAreaD += `M ${x} ${getY(0)} L ${x} ${yNet}`;
      } else {
        grossPathD += ` L ${x} ${yGross}`;
        grossAreaD += ` L ${x} ${yGross}`;
        netPathD += ` L ${x} ${yNet}`;
        netAreaD += ` L ${x} ${yNet}`;
      }
    });

    const lastX = getX(sorted.length - 1);
    const bottomY = getY(0);
    grossAreaD += ` L ${lastX} ${bottomY} Z`;
    netAreaD += ` L ${lastX} ${bottomY} Z`;

    // Render Area Fills
    const grossArea = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    grossArea.setAttribute('d', grossAreaD);
    grossArea.setAttribute('fill', 'url(#grossGradient)');
    svg.appendChild(grossArea);

    const netArea = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    netArea.setAttribute('d', netAreaD);
    netArea.setAttribute('fill', 'url(#netGradient)');
    svg.appendChild(netArea);

    // Render Stroke Lines
    const grossLine = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    grossLine.setAttribute('d', grossPathD);
    grossLine.setAttribute('fill', 'none');
    grossLine.setAttribute('stroke', '#3b82f6');
    grossLine.setAttribute('stroke-width', '2.5');
    grossLine.setAttribute('stroke-linecap', 'round');
    svg.appendChild(grossLine);

    const netLine = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    netLine.setAttribute('d', netPathD);
    netLine.setAttribute('fill', 'none');
    netLine.setAttribute('stroke', '#10b981');
    netLine.setAttribute('stroke-width', '2');
    netLine.setAttribute('stroke-linecap', 'round');
    svg.appendChild(netLine);

    // Draw X-axis date ticks (sample 5 to 7 labels)
    const tickStep = Math.max(1, Math.floor(sorted.length / 6));
    sorted.forEach((d, i) => {
      if (i % tickStep === 0 || i === sorted.length - 1) {
        const x = getX(i);
        const dateText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        dateText.setAttribute('x', x);
        dateText.setAttribute('y', height - padding.bottom + 18);
        dateText.setAttribute('text-anchor', 'middle');
        dateText.setAttribute('fill', '#94a3b8');
        dateText.setAttribute('font-size', '10');
        dateText.setAttribute('font-family', 'var(--font-mono)');

        // Format date string (e.g., '10/24')
        const parts = String(d.metric_date).split('-');
        dateText.textContent = parts.length === 3 ? `${parts[1]}/${parts[2]}` : d.metric_date;
        svg.appendChild(dateText);
      }
    });

    // Draw interactive points with title tooltips
    sorted.forEach((d, i) => {
      const x = getX(i);
      const yGross = getY(d.gross_sales);

      const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      circle.setAttribute('cx', x);
      circle.setAttribute('cy', yGross);
      circle.setAttribute('r', sorted.length > 30 ? '2.5' : '4');
      circle.setAttribute('fill', '#3b82f6');
      circle.setAttribute('stroke', '#0a0e17');
      circle.setAttribute('stroke-width', '2');
      circle.style.cursor = 'pointer';

      const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
      title.textContent = `${d.metric_date}\nGross: ${formatMoney(d.gross_sales, currency)}\nNet: ${formatMoney(d.net_sales, currency)}\nOrders: ${d.orders_count}`;
      circle.appendChild(title);

      svg.appendChild(circle);
    });
  }

  /**
   * Renders an interactive SVG Donut Chart for order status breakdown
   * @param {SVGSVGElement} svg
   * @param {Array} statuses - Array of { status, orders_count, percentage }
   */
  function renderStatusDonut(svg, statuses) {
    if (!svg) return;
    svg.innerHTML = '';

    const totalOrders = statuses.reduce((acc, s) => acc + (s.orders_count || 0), 0);
    const size = 200;
    const center = size / 2;
    const radius = 70;
    const strokeWidth = 24;
    const circumference = 2 * Math.PI * radius;

    if (totalOrders === 0) {
      const emptyCircle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      emptyCircle.setAttribute('cx', center);
      emptyCircle.setAttribute('cy', center);
      emptyCircle.setAttribute('r', radius);
      emptyCircle.setAttribute('fill', 'none');
      emptyCircle.setAttribute('stroke', 'rgba(255, 255, 255, 0.08)');
      emptyCircle.setAttribute('stroke-width', strokeWidth);
      svg.appendChild(emptyCircle);
      return;
    }

    const colorMap = {
      pending: '#f59e0b',
      paid: '#3b82f6',
      fulfilled: '#10b981',
      cancelled: '#f43f5e',
    };

    let cumulativeOffset = 0;

    statuses.forEach((s) => {
      if (s.orders_count <= 0) return;

      const portion = s.orders_count / totalOrders;
      const strokeDash = portion * circumference;
      const strokeGap = circumference - strokeDash;

      const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      circle.setAttribute('cx', center);
      circle.setAttribute('cy', center);
      circle.setAttribute('r', radius);
      circle.setAttribute('fill', 'none');
      circle.setAttribute('stroke', colorMap[s.status] || '#6366f1');
      circle.setAttribute('stroke-width', strokeWidth);
      circle.setAttribute('stroke-dasharray', `${strokeDash} ${strokeGap}`);
      circle.setAttribute('stroke-dashoffset', -cumulativeOffset);
      circle.style.transition = 'stroke-dasharray 0.5s ease, stroke-dashoffset 0.5s ease';

      const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
      title.textContent = `${s.status.toUpperCase()}: ${s.orders_count.toLocaleString()} (${s.percentage}%)`;
      circle.appendChild(title);

      svg.appendChild(circle);
      cumulativeOffset += strokeDash;
    });
  }

  return {
    formatMoney,
    renderRevenueChart,
    renderStatusDonut,
  };
})();
