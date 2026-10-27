# Restart Add-Ins

Restart Add-Ins adds a **Restart Add-Ins** button to the Solid tab and the Scripts and Add-Ins panel. Click it to stop and start every user add-in that is currently running.

The button reloads add-ins you linked with **My Add-Ins**, add-ins in your Fusion add-ins folder, and add-ins installed from the Autodesk App Store. Fusion's built-in add-ins and sample add-ins stay as they are. Add-ins that are already stopped stay stopped.

Restart Add-Ins itself stays loaded. The button is still on the toolbar after the restart, so you can click it again. A progress bar names each add-in as it stops and starts. A message appears only when an add-in fails to restart. The Text Commands window still lists what restarted.

Use it after editing another add-in when Fusion should load that new code. Python modules from the restarted add-in are cleared before it starts, so the new files are imported.

## Install

1. In Fusion, open **Utilities → Scripts and Add-Ins** (or press `Shift+S`).
2. On the **Add-Ins** tab, click the **+** next to **My Add-Ins**.
3. Select the `add-ins/RestartAddIns/addin` folder.
4. Run **Restart Add-Ins**. It also starts with Fusion.

The command is on the Design workspace **Solid** tab and on the **Scripts and Add-Ins** panel in each workspace, next to **Scripts and Add-Ins**. That panel is also **Utilities → ADD-INS**. This needs the Fusion scripts API from October 2023 or later.
