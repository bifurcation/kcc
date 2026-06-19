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

  const dqs = C.dqs || [];
  const teams = C.teams.map(t => {
    const lc = t.emphasize ? '#D32F2F' : GREY;
    if (!t.emphasize) {
      return {
        label: t.name, data: t.times,
        borderColor: lc, backgroundColor: lc,
        pointBackgroundColor: lc, pointBorderColor: lc, pointBorderWidth: 0,
        borderWidth: 1, pointRadius: 0,
        pointStyle: 'circle', fill: false, spanGaps: false, order: 1,
      };
    }
    const dqIdx = new Set(dqs.map((d,i) => d!=null?i:-1).filter(i=>i>=0));
    const data = t.times.map((v,i) => v!==null ? v : (dqs[i]!=null ? dqs[i][0] : null));
    return {
      label: t.name, data,
      borderColor: lc, backgroundColor: lc,
      pointBackgroundColor: data.map((v,i) => dqIdx.has(i) ? 'transparent' : lc),
      pointBorderColor: data.map((v,i) => dqIdx.has(i) ? lc : lc),
      pointBorderWidth: data.map((v,i) => dqIdx.has(i) ? 2 : 0),
      borderWidth: 4,
      pointRadius: data.map((v,i) => v===null ? 0 : dqIdx.has(i) ? 4 : 2),
      pointStyle: data.map((v,i) => dqIdx.has(i) ? 'crossRot' : 'circle'),
      fill: false, spanGaps: false, order: 0,
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
