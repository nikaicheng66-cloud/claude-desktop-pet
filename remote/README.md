# Xiaoke remote (phone web app)

See what Xiaoke is doing from your phone, type instructions to her, and switch her on or off remotely.

## Parts
- `remote_server.py`: a small always-on service on the PC (port 12480, Python standard library only). It only accepts this PC and Tailscale addresses, and every request needs a token (`token.txt`, created on the first run).
- `index.html` / `manifest.json` / `icon.svg`: the web app on the phone.
- `start_remote.vbs`: starts the service without a window.
- `install_remote.ps1`: one-time setup for starting at login and the firewall rule.
- New endpoints on the Xiaoke server: `/deskpet/remote/state` (status) and `/deskpet/remote/say` (send an instruction). They listen on this PC only; this service relays to them.

## Instructions sent from the phone
They count as text typed into Xiaoke's input box on the PC. Not-listening mode does not block them, and they are never held back as the first half of a sentence.

## Setup
1. Install Tailscale on the PC and the phone and sign in to the same account on both.
2. Right-click `install_remote.ps1` and choose Run with PowerShell (it asks for administrator rights). It shows the token and the address to open on the phone.
3. Restart Xiaoke once so the new endpoints are live.
4. On the phone, open `http://<the PC's Tailscale IP>:12480`, enter the token, then "Add to Home Screen".

## Common questions
- New token: delete `token.txt` and restart the service (sign in to Windows again, or run `start_remote.vbs`).
- Service log: `remote.log`.
