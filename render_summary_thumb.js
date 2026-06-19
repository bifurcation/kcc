#!/usr/bin/env node
'use strict';
const { ChartJSNodeCanvas } = require('chartjs-node-canvas');
const fs = require('fs');

const outFile = process.argv[2];
let raw = '';
process.stdin.on('data', chunk => raw += chunk);
process.stdin.on('end', async () => {
  const S = JSON.parse(raw);

  const errorBarPlugin = {
    id: 'errorBars',
    afterDatasetsDraw(chart) {
      const ctx = chart.ctx;
      chart.data.datasets.forEach((ds, di) => {
        if (!ds.errorBars) return;
        const meta = chart.getDatasetMeta(di);
        if (meta.hidden) return;
        meta.data.forEach(pt => {
          if (!pt || isNaN(pt.x) || isNaN(pt.y)) return;
          const eb = ds.errorBars[Math.round(chart.scales.x.getValueForPixel(pt.x))];
          if (!eb) return;
          const x = pt.x;
          const yLo = chart.scales.y.getPixelForValue(eb.lo);
          const yHi = chart.scales.y.getPixelForValue(eb.hi);
          const cap = 3;
          ctx.save();
          ctx.strokeStyle = ds.borderColor;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(x, yLo); ctx.lineTo(x, yHi);
          ctx.moveTo(x - cap, yLo); ctx.lineTo(x + cap, yLo);
          ctx.moveTo(x - cap, yHi); ctx.lineTo(x + cap, yHi);
          ctx.stroke();
          ctx.restore();
        });
      });
    }
  };

  const datasets = S.datasets.map(ds => ({
    label: ds.label, data: ds.data.filter(p => p !== null), errorBars: ds.errorBars,
    borderColor: ds.borderColor, backgroundColor: ds.borderColor,
    pointRadius: 3, pointStyle: 'circle',
  }));

  const canvas = new ChartJSNodeCanvas({ width: 640, height: 300, backgroundColour: 'white' });
  const buf = await canvas.renderToBuffer({
    type: 'scatter',
    data: { datasets },
    options: {
      animation: false,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        title:  { display: false },
        tooltip: { enabled: false },
      },
      scales: {
        x: {
          display: false,
          type: 'linear',
          min: -0.5,
          max: S.labels.length - 0.5,
        },
        y: { display: false, min: S.yMin, max: S.yMax },
      },
    },
    plugins: [errorBarPlugin],
  });
  fs.writeFileSync(outFile, buf);
});
