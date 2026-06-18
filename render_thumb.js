#!/usr/bin/env node
'use strict';
const { ChartJSNodeCanvas } = require('chartjs-node-canvas');
const fs = require('fs');

const outFile = process.argv[2];
let raw = '';
process.stdin.on('data', chunk => raw += chunk);
process.stdin.on('end', async () => {
  const C = JSON.parse(raw);
  const GREY = '#b3b3b3';

  const band = [
    { label: 'Fastest', data: C.fastest, borderColor: 'rgba(150,150,150,0.5)',
      borderWidth: 1, pointStyle: false, fill: false, order: 100, spanGaps: true },
    { label: 'Slowest', data: C.slowest, borderColor: 'rgba(150,150,150,0.5)',
      borderWidth: 1, pointStyle: false, fill: '-1',
      backgroundColor: 'rgba(170,170,170,0.45)', order: 100, spanGaps: true },
  ];

  const teams = C.teams.map(t => {
    const lc = t.emphasize ? '#D32F2F' : GREY;
    return {
      label: t.name, data: t.times,
      borderColor: lc, backgroundColor: lc,
      pointBackgroundColor: lc, pointBorderColor: lc, pointBorderWidth: 0,
      borderWidth: t.emphasize ? 4 : 1,
      pointRadius: t.emphasize ? 2 : 0,
      pointStyle: 'circle', fill: false, spanGaps: false,
      order: t.emphasize ? 0 : 1,
    };
  });

  const canvas = new ChartJSNodeCanvas({ width: 480, height: 300, backgroundColour: 'white' });
  const buf = await canvas.renderToBuffer({
    type: 'line',
    data: { labels: C.regattas, datasets: [...band, ...teams] },
    options: {
      animation: false,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        title:  { display: false },
        tooltip: { enabled: false },
      },
      scales: {
        x: { display: false },
        y: { display: false },
      },
    },
  });
  fs.writeFileSync(outFile, buf);
});
