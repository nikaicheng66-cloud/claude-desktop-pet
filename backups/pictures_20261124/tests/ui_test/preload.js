// Stands in for the pet's preload and server: nothing here reaches the real pet.
window.__sent = [];
window.__ipc = {};
window.__dropAudio = [];
class FakeWS {
  constructor(url) {
    this.url = url;
    this.readyState = 1;
    FakeWS.last = this;
    setTimeout(() => this.onopen && this.onopen({}), 0);
  }

  send(data) { try { window.__sent.push(JSON.parse(data)); } catch (e) { /* binary */ } }

  close() { this.readyState = 3; if (this.onclose) this.onclose({}); }

  addEventListener() {}

  removeEventListener() {}
}
FakeWS.CONNECTING = 0; FakeWS.OPEN = 1; FakeWS.CLOSING = 2; FakeWS.CLOSED = 3;
window.WebSocket = FakeWS;

const noop = () => () => {};
window.api = new Proxy({}, {
  get: (_t, key) => {
    if (key === 'dropAudio') {
      return async (files) => { window.__dropAudio.push(files.map((f) => f.name)); return { ok: true, message: '' }; };
    }
    if (key === 'getConfigFiles') return async () => [];
    return noop;
  },
});
window.electron = {
  process: { platform: 'win32' },
  desktopCapturer: { getSources: async () => [] },
  ipcRenderer: {
    on: (channel, fn) => { (window.__ipc[channel] = window.__ipc[channel] || []).push(fn); },
    once: () => {},
    send: () => {},
    invoke: async () => null,
    removeListener: () => {},
    removeAllListeners: () => {},
  },
};
