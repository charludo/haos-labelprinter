# Install and setup guide

This guide takes you from nothing to a printed label. No coding needed.

## What you need

- A Brother P-touch printer. Only the **PT-P710BT** is verified. See [COMPATIBILITY.md](COMPATIBILITY.md).
- Brother TZe tape in the printer.
- Home Assistant with [HACS](https://hacs.xyz) installed. This was tested on Home Assistant 2026.10.4. Other versions have not been tested.
- A way to connect the printer: a USB port, a Bluetooth adapter, or a second Linux computer (for the bridge).
- Internet access, once, so fonts and icons can be downloaded.

## 1. Install with HACS

1. Open **HACS** in the Home Assistant sidebar.
2. Click the three dots at the top right, then **Custom repositories**.
3. In **Repository** paste `https://github.com/thatgoodpickle/haos-labelprinter`.
4. In **Type** choose **Integration**. Click **Add**.
5. Search for **Brother P-touch** and open it.
6. Click **Download**. While only pre-releases exist, turn on **Show beta versions** in that dialog first, then pick the newest version.
7. **Restart Home Assistant** (Settings > System > Restart).

## 2. Add the integration

1. Go to **Settings > Devices & services**.
2. A USB printer may already show up under **Discovered**. If so, click **Configure** and finish.
3. Otherwise click **Add integration**, search for **Brother P-touch**, and choose how the printer is connected. The next chapters explain each way.

## 3a. Connect by USB

1. Plug the printer into the Home Assistant computer and switch it on.
2. Choose **USB** in the setup. Leave the serial number empty unless you have several printers.

If Home Assistant says it cannot talk to the printer, check the cable, that the printer is on, and that the cassette is in with the cover closed. On some setups (a container) the USB device must be passed through to Home Assistant.

## 3b. Connect by Bluetooth

The Home Assistant computer needs a Bluetooth adapter that Home Assistant can use. If it cannot, use USB or the bridge.

1. Switch the printer on. Disconnect any phone from it: the printer talks to one device at a time.
2. In the setup choose **Bluetooth**. Home Assistant scans for about 10 seconds.
3. Pick your printer from the list. Printers are listed first (the name looks like PT-P710BT and four digits).
4. If it is not paired yet, Home Assistant pairs it for you. If a PIN is asked, it is `0000`.
5. Finish the setup.

You can also pair from the label editor: open **Labels**, open the printer drawer, and use the scan and pair buttons. This is new and has not yet been tried on a real printer, so please report how it goes.

If it does not connect, the **Connect** button retries and tells you what is wrong (printer asleep, used by a phone, not paired, Bluetooth off). The printer switches itself off after a while, and it cannot be woken from Home Assistant: **press the power button on the printer first**, then press **Connect**.

In **Settings > Devices & services > Brother P-touch > Configure** there is a **Bluetooth wake time** setting. It is how long Home Assistant keeps trying to reach the printer, which gives you time to press the printer's power button. `0` tries once.

More about Bluetooth: [BLUETOOTH.md](BLUETOOTH.md).

## 3c. Connect through the network bridge

Use this if the printer is far from Home Assistant, or Home Assistant cannot reach it. The bridge is a small program that runs on any Linux computer next to the printer.

1. Get the project files onto that computer (download the repository).
2. Run the bridge. Pick the line that matches your connection and replace `SECRET` with a password you make up:

   ```
   python3 bridge/ptouch_bridge.py --usb --token SECRET
   python3 bridge/ptouch_bridge.py --bluetooth AA:BB:CC:DD:EE:FF --token SECRET
   python3 bridge/ptouch_bridge.py --device /dev/usb/lp0 --token SECRET
   ```

3. For Bluetooth, the printer must be paired with that computer first (`bluetoothctl`, then `scan on`, `pair`, `trust`).
4. Optional, to keep it running with Docker (from the repository folder):

   ```
   docker build -f bridge/Dockerfile -t ptouch-bridge .
   docker run -d --restart unless-stopped --device /dev/bus/usb -p 8765:8765 -e PTOUCH_BRIDGE_TOKEN=SECRET ptouch-bridge --usb
   ```

5. Or with systemd: copy `bridge/ptouch-bridge.service`, edit the path, the transport flag and the token inside it, then enable it.
6. In Home Assistant choose **Bridge**, enter `http://<computer-address>:8765` and the token.

Always set a token. Anyone who can reach the bridge can print.

## 4. Make your first label

1. Open **Labels** in the sidebar (admin users only).
2. Click **New**, then **From template**. Pick one.
3. Edit the text. Click **Print**.

If the label comes out mirrored or upside down, go to the integration, click **Configure**, and change **Orientation**.

## Updating

1. In HACS open **Brother P-touch** and click **Update** (turn on **Show beta versions** if the update is a pre-release).
2. Restart Home Assistant.
3. Hard-refresh your browser (Ctrl+Shift+R, or Cmd+Shift+R on a Mac).
4. In the Home Assistant Companion app, clear the app cache (Settings > Companion app > Troubleshooting), or the old editor may stay on screen. The exact menu depends on the app version.

## Removing

1. Go to **Settings > Devices & services > Brother P-touch**, open the menu and choose **Delete**.
2. In HACS open **Brother P-touch**, choose **Remove**, and restart Home Assistant.
3. Stop the bridge if you used one.
