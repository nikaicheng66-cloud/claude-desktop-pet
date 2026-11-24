(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const out = {};
  const until = async (fn, ms = 4000) => {
    const t = Date.now();
    while (Date.now() - t < ms) { const v = fn(); if (v) return v; await sleep(50); }
    return fn();
  };
  const mode = (m) => (window.__ipc['mode-changed'] || []).forEach((h) => h(null, m));
  const picture = (w, h, name = 'shot.png', type = 'image/png', clear = false) => new Promise((resolve) => {
    const c = document.createElement('canvas'); c.width = w; c.height = h;
    const x = c.getContext('2d');
    if (!clear) { x.fillStyle = '#fff'; x.fillRect(0, 0, w, h); }
    x.fillStyle = '#c00'; x.font = Math.round(h / 8) + 'px sans-serif'; x.fillText('hello', w / 2, h / 2);
    c.toBlob((b) => resolve(new File([b], name, { type })), type);
  });
  const size = async (dataUrl) => {
    const b = await createImageBitmap(await (await fetch(dataUrl)).blob());
    return [b.width, b.height];
  };
  const transfer = (...files) => { const dt = new DataTransfer(); files.forEach((f) => dt.items.add(f)); return dt; };
  const inputs = () => window.__sent.filter((m) => m.type === 'text-input');
  const lastInput = () => inputs().pop();
  const type = (input, text) => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, text);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  };
  const enter = (input) => input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
  const pendingCount = () => document.querySelectorAll('[data-pending-pictures] img').length;
  const note = () => (document.getElementById('audio-drop-note') || {}).textContent || '';

  await sleep(1500);
  mode('pet');
  const bubble = await until(() => document.querySelector('[data-pet-bubble]'));
  out.bubble_shown = !!bubble;
  if (!bubble) return out;
  const input = bubble.querySelector('input:not([type=file])');
  const fileInput = bubble.querySelector('input[type=file]');
  out.picture_button = !!bubble.querySelector('button[aria-label="给小克看图片"]');

  // 1. paste a big screenshot, type a question, Enter
  const big = await picture(2560, 1440);
  const paste = new ClipboardEvent('paste', { clipboardData: transfer(big), bubbles: true, cancelable: true });
  input.dispatchEvent(paste);
  await until(() => pendingCount() === 1);
  out.paste_pending = pendingCount();
  out.paste_prevented = paste.defaultPrevented;
  out.paste_placeholder = input.placeholder;
  type(input, '图上写了什么');
  await sleep(100);
  let n = inputs().length;
  enter(input);
  await until(() => inputs().length > n);
  let m = lastInput();
  out.paste_sent = m && {
    text: m.text,
    n: m.images.length,
    source: m.images[0].source,
    mime: m.images[0].mime_type,
    head: m.images[0].data.slice(0, 23),
    size: await size(m.images[0].data),
    kb: Math.round(m.images[0].data.length / 1024),
    keys: Object.keys(m.images[0]).sort().join(','),
  };
  await sleep(300);
  out.after_send = {
    pending: pendingCount(),
    input: input.value,
    sent_thumbs: bubble.querySelectorAll('[data-sent-pictures] img').length,
    pill: [...bubble.querySelectorAll('div')].some((d) => d.textContent === '图上写了什么'),
  };

  // 2. a text paste is left alone
  const dtText = new DataTransfer(); dtText.setData('text/plain', 'just words');
  const pasteText = new ClipboardEvent('paste', { clipboardData: dtText, bubbles: true, cancelable: true });
  input.dispatchEvent(pasteText);
  await sleep(200);
  out.text_paste = { prevented: pasteText.defaultPrevented, pending: pendingCount() };

  // 3. drop two pictures on the bubble: they wait there
  const tall = await picture(1080, 2400, 'phone.jpg', 'image/jpeg');
  const seeThrough = await picture(800, 600, 'logo.png', 'image/png', true);
  const r = bubble.getBoundingClientRect();
  const px = r.left + 30;
  const py = r.top + r.height - 12;
  const drag = (kind, dt, x, y) => new DragEvent(kind, { dataTransfer: dt, bubbles: true, cancelable: true, clientX: x, clientY: y });
  const dt2 = transfer(seeThrough, tall);
  out.bubble_is_under_point = !!(document.elementFromPoint(px, py) || document.body).closest('[data-pet-bubble]');
  (document.elementFromPoint(px, py) || bubble).dispatchEvent(drag('dragover', dt2, px, py));
  await sleep(150);
  out.drop_hint = note();
  n = inputs().length;
  (document.elementFromPoint(px, py) || bubble).dispatchEvent(drag('drop', dt2, px, py));
  await until(() => pendingCount() === 2);
  out.drop_on_bubble = { pending: pendingCount(), sent_at_once: inputs().length - n };

  // 4. take one away with its x, add one with the picker, Enter with no words
  const xs = bubble.querySelectorAll('[data-pending-pictures] button');
  xs[xs.length - 1].click();
  await until(() => pendingCount() === 1);
  out.after_remove = pendingCount();
  fileInput.files = transfer(await picture(640, 480, 'small.png')).files;
  fileInput.dispatchEvent(new Event('change', { bubbles: true }));
  await until(() => pendingCount() === 2);
  out.after_pick = pendingCount();
  n = inputs().length;
  enter(input);
  await until(() => inputs().length > n);
  m = lastInput();
  out.two_sent = m && {
    text: m.text,
    n: m.images.length,
    sources: m.images.map((i) => i.source),
    sizes: await Promise.all(m.images.map((i) => size(i.data))),
  };
  if (m) { // the see-through PNG must come out on white, not black
    const b = await createImageBitmap(await (await fetch(m.images[0].data)).blob());
    const c = document.createElement('canvas'); c.width = b.width; c.height = b.height;
    c.getContext('2d').drawImage(b, 0, 0);
    out.see_through_corner = [...c.getContext('2d').getImageData(2, 2, 1, 1).data].slice(0, 3);
  }

  // 5. more than four at once, and one that is not really a picture
  const many = [];
  for (let i = 0; i < 6; i += 1) many.push(await picture(2000, 1500, 'p' + i + '.png'));
  // two first, then four more: attached in two goes, they must still share one budget
  fileInput.files = transfer(many[0], many[1]).files;
  fileInput.dispatchEvent(new Event('change', { bubbles: true }));
  await until(() => pendingCount() === 2);
  fileInput.files = transfer(many[2], many[3], many[4], many[5]).files;
  fileInput.dispatchEvent(new Event('change', { bubbles: true }));
  await until(() => pendingCount() === 4);
  await sleep(300);
  out.six_picked = { pending: pendingCount(), note: bubble.textContent.includes('超过四张') };
  n = inputs().length;
  enter(input);
  await until(() => inputs().length > n);
  m = lastInput();
  const fourSizes = await Promise.all(m.images.map((i) => size(i.data)));
  out.four_sent = { n: m.images.length, sizes: fourSizes, pixels_total: fourSizes.reduce((t, [w, h]) => t + w * h, 0), budget: 1280 * 720 };
  await sleep(200);
  const broken = new File([new Uint8Array([1, 2, 3, 4, 5])], 'broken.png', { type: 'image/png' });
  fileInput.files = transfer(broken).files;
  fileInput.dispatchEvent(new Event('change', { bubbles: true }));
  await sleep(600);
  out.broken_picked = { pending: pendingCount(), note: bubble.textContent.includes('放不进来') };

  // 6. plain typing still works as before
  type(input, '你好');
  await sleep(100);
  n = inputs().length;
  enter(input);
  await until(() => inputs().length > n);
  m = lastInput();
  out.plain_text = m && { text: m.text, n: m.images.length };

  // 7. window mode: a drop anywhere is taken (pet mode: only on her / the bubble, that code is unchanged)
  mode('window');
  await until(() => !document.querySelector('[data-pet-bubble]'));
  n = inputs().length;
  const song = new File([new Uint8Array(2000)], 'talk.mp3', { type: 'audio/mpeg' });
  const dt3 = transfer(await picture(1920, 1080, 'wide.png'), song);
  document.body.dispatchEvent(drag('dragover', dt3, 300, 300));
  await sleep(150);
  out.mixed_hint = note();
  document.body.dispatchEvent(drag('drop', dt3, 300, 300));
  await until(() => inputs().length > n);
  m = lastInput();
  out.dropped_to_look = m && { text: m.text, n: m.images.length, source: m.images[0].source, size: await size(m.images[0].data) };
  out.audio_still_goes_to_audio = window.__dropAudio;
  n = inputs().length;
  document.body.dispatchEvent(drag('drop', transfer(broken), 300, 300));
  await sleep(700);
  out.broken_dropped = { note: note(), sent: inputs().length - n };
  out.text_inputs_total = inputs().length;
  return out;
})()
