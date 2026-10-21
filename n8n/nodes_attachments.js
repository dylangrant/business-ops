// Turns the /summary attachments ([{filename, mimeType, data}]) into n8n binary properties attachment_0..N.
const out = [];
for (const item of $input.all()) {
  const binary = {};
  (item.json.attachments || []).forEach((a, i) => {
    binary['attachment_' + i] = { data: a.data, mimeType: a.mimeType, fileName: a.filename };
  });
  const json = { ...item.json };
  delete json.attachments; // keep the base64 out of the json passed to Gmail
  out.push({ json, binary });
}
return out;
