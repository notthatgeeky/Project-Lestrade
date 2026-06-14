/**
 * Sherlock Dashboard — Lightweight Chart (Canvas-based)
 *
 * A simple, dependency-free line chart for the confidence timeline.
 * No external charting library needed.
 */

class ScoreChart {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    this.ctx = this.canvas.getContext('2d');
    this.series = new Map(); // participantId → {name, color, points: [{x, y}]}
    this.maxPoints = 300; // ~5 minutes at 1 update/sec
    this.startTime = null;

    // Color palette for participants
    this.colors = [
      '#6366f1', // indigo
      '#10b981', // emerald
      '#f59e0b', // amber
      '#ef4444', // rose
      '#38bdf8', // sky
      '#a78bfa', // violet
      '#f472b6', // pink
      '#34d399', // teal
    ];
    this.colorIndex = 0;

    // Handle resize
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(this.canvas.parentElement);
    this.resize();
  }

  resize() {
    const parent = this.canvas.parentElement;
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = parent.clientWidth * dpr;
    this.canvas.height = parent.clientHeight * dpr;
    this.canvas.style.width = parent.clientWidth + 'px';
    this.canvas.style.height = parent.clientHeight + 'px';
    this.ctx.scale(dpr, dpr);
    this.width = parent.clientWidth;
    this.height = parent.clientHeight;
    this.render();
  }

  addPoint(participantId, name, score, timestampMs) {
    if (!this.startTime) this.startTime = timestampMs;

    if (!this.series.has(participantId)) {
      this.series.set(participantId, {
        name: name,
        color: this.colors[this.colorIndex % this.colors.length],
        points: [],
      });
      this.colorIndex++;
    }

    const series = this.series.get(participantId);
    series.name = name; // Update in case of rename
    const x = (timestampMs - this.startTime) / 1000; // seconds
    series.points.push({ x, y: score });

    // Trim old points
    if (series.points.length > this.maxPoints) {
      series.points.shift();
    }

    this.render();
  }

  render() {
    const ctx = this.ctx;
    const w = this.width;
    const h = this.height;

    if (!w || !h) return;

    // Margins
    const ml = 45, mr = 120, mt = 15, mb = 30;
    const cw = w - ml - mr;
    const ch = h - mt - mb;

    // Clear
    ctx.clearRect(0, 0, w, h);

    // Find x range
    let maxX = 60; // minimum 60 seconds
    for (const [, series] of this.series) {
      for (const pt of series.points) {
        if (pt.x > maxX) maxX = pt.x;
      }
    }

    // ─── Grid ────────────────────────
    ctx.strokeStyle = 'rgba(255,255,255,0.05)';
    ctx.lineWidth = 1;

    // Horizontal grid lines (0%, 25%, 50%, 75%, 100%)
    for (let i = 0; i <= 4; i++) {
      const y = mt + ch - (i / 4) * ch;
      ctx.beginPath();
      ctx.moveTo(ml, y);
      ctx.lineTo(ml + cw, y);
      ctx.stroke();

      // Y-axis labels
      ctx.fillStyle = 'rgba(255,255,255,0.3)';
      ctx.font = '10px Inter, sans-serif';
      ctx.textAlign = 'right';
      ctx.fillText(`${i * 25}%`, ml - 8, y + 3);
    }

    // Confidence band backgrounds
    const bands = [
      { lo: 0, hi: 0.40, color: 'rgba(107,114,128,0.03)' },
      { lo: 0.40, hi: 0.65, color: 'rgba(245,158,11,0.03)' },
      { lo: 0.65, hi: 0.85, color: 'rgba(99,102,241,0.04)' },
      { lo: 0.85, hi: 1.00, color: 'rgba(16,185,129,0.05)' },
    ];

    for (const band of bands) {
      const y1 = mt + ch - band.hi * ch;
      const y2 = mt + ch - band.lo * ch;
      ctx.fillStyle = band.color;
      ctx.fillRect(ml, y1, cw, y2 - y1);
    }

    // ─── Data Lines ──────────────────
    let legendY = mt + 5;
    for (const [pid, series] of this.series) {
      if (series.points.length < 2) continue;

      // Line
      ctx.strokeStyle = series.color;
      ctx.lineWidth = 2;
      ctx.lineJoin = 'round';
      ctx.beginPath();

      for (let i = 0; i < series.points.length; i++) {
        const pt = series.points[i];
        const px = ml + (pt.x / maxX) * cw;
        const py = mt + ch - pt.y * ch;

        if (i === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      }
      ctx.stroke();

      // Gradient fill under line
      ctx.globalAlpha = 0.08;
      ctx.lineTo(ml + (series.points[series.points.length - 1].x / maxX) * cw, mt + ch);
      ctx.lineTo(ml + (series.points[0].x / maxX) * cw, mt + ch);
      ctx.closePath();
      ctx.fillStyle = series.color;
      ctx.fill();
      ctx.globalAlpha = 1;

      // Current value dot
      const last = series.points[series.points.length - 1];
      const lx = ml + (last.x / maxX) * cw;
      const ly = mt + ch - last.y * ch;

      ctx.beginPath();
      ctx.arc(lx, ly, 4, 0, Math.PI * 2);
      ctx.fillStyle = series.color;
      ctx.fill();
      ctx.strokeStyle = '#0a0b10';
      ctx.lineWidth = 2;
      ctx.stroke();

      // Legend (right side)
      ctx.fillStyle = series.color;
      ctx.beginPath();
      ctx.arc(ml + cw + 14, legendY + 6, 4, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = 'rgba(255,255,255,0.7)';
      ctx.font = '11px Inter, sans-serif';
      ctx.textAlign = 'left';

      const legendName = series.name.length > 12
        ? series.name.substring(0, 12) + '…'
        : series.name;
      ctx.fillText(`${legendName}`, ml + cw + 22, legendY + 10);

      ctx.fillStyle = 'rgba(255,255,255,0.4)';
      ctx.fillText(`${(last.y * 100).toFixed(0)}%`, ml + cw + 22, legendY + 22);

      legendY += 32;
    }

    // ─── X-axis labels ───────────────
    ctx.fillStyle = 'rgba(255,255,255,0.3)';
    ctx.font = '10px Inter, sans-serif';
    ctx.textAlign = 'center';

    const tickCount = Math.min(6, Math.floor(maxX / 30));
    for (let i = 0; i <= tickCount; i++) {
      const sec = Math.round((i / tickCount) * maxX);
      const px = ml + (sec / maxX) * cw;
      const label = sec < 60 ? `${sec}s` : `${Math.floor(sec / 60)}m${sec % 60 ? (sec % 60) + 's' : ''}`;
      ctx.fillText(label, px, h - 8);
    }
  }
}

// Export for use in app.js
window.ScoreChart = ScoreChart;
