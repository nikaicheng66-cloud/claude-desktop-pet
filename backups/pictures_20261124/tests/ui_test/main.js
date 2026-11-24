// Loads the built renderer in a hidden window with a fake server and preload, runs test.js in it.
const { app, BrowserWindow, session } = require('electron');
const path = require('path');
const fs = require('fs');

app.setPath('userData', path.join(__dirname, 'profile'));
const renderer = process.argv[process.argv.length - 1];
const resultFile = path.join(__dirname, 'result.json');

app.whenReady().then(async () => {
  // no microphone, camera or anything else for this hidden window
  session.defaultSession.setPermissionRequestHandler((_wc, _perm, cb) => cb(false));
  session.defaultSession.setPermissionCheckHandler(() => false);
  const win = new BrowserWindow({
    show: false,
    width: 1400,
    height: 900,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: false,
      sandbox: false,
      nodeIntegration: false,
      backgroundThrottling: false,
    },
  });
  const errors = [];
  win.webContents.on('console-message', (_e, level, message) => {
    if (level >= 3) errors.push(String(message).slice(0, 300));
  });
  await win.loadFile(renderer);
  let result;
  try {
    result = await win.webContents.executeJavaScript(fs.readFileSync(path.join(__dirname, 'test.js'), 'utf-8'));
  } catch (e) {
    result = { crashed: String(e) };
  }
  fs.writeFileSync(resultFile, JSON.stringify({ result, errors }, null, 1), 'utf-8');
  app.quit();
});
setTimeout(() => { fs.writeFileSync(resultFile, '{"timeout":true}'); app.exit(1); }, 90000);
