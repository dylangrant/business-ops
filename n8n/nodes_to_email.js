// Gmail message (simple: false) -> the service's Email shape. Only fields the rules need.
const m = $input.item.json;
const from = (m.from && m.from.value && m.from.value[0] && m.from.value[0].address) || m.from?.text || '';
const html = m.html || '';
const links = [...html.matchAll(/href="(https?:[^"]+)"/g)].map((x) => x[1]).filter((u) => !/unsubscribe|privacy|facebook|twitter|instagram/i.test(u)).slice(0, 10);
return { json: { email: { id: m.id, sender: from, subject: m.subject || '', date: new Date(m.date).toISOString().slice(0, 10), text: (m.text || '').slice(0, 20000), links } } };
