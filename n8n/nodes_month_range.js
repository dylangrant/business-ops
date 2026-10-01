// Last calendar month as Gmail search bounds + 'YYYY-MM'. Manual runs can pass {month: 'YYYY-MM'}.
const pad = (n) => String(n).padStart(2, '0');
const asked = $input.first().json.month || ($input.first().json.query || {}).month;
let y, m;
if (asked && /^\d{4}-\d{2}$/.test(asked)) { [y, m] = asked.split('-').map(Number); }
else { const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - 1); y = d.getFullYear(); m = d.getMonth() + 1; }
const next = m === 12 ? [y + 1, 1] : [y, m + 1];
return [{ json: { month: `${y}-${pad(m)}`, after: `${y}/${pad(m)}/01`, before: `${next[0]}/${pad(next[1])}/01` } }];
