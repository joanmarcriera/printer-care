# DCP-T780DW web UI: the rear-label password is rejected

Task <https://familia.riera.co.uk/tasks/3709>. **Read-only page.** Nothing here was run against the printer; every step below is
something you do yourself, in a browser or on the printer panel, one at a time. No curl, no scripts, no scanning.

## What Brother says (checked 2026-11-15, HTTP 200 on each)
Brother's own DCP-T780DW online guide was not found by search. The closest official pages are the sister inkjet-tank guide
(DCP-T830DW), whose model lists name the DCP-T780DW where menus differ:

- Default password: "located on the back of the machine and marked 'Pwd'"; also printed in the Network Configuration Report.
  Brother recommends changing it at once; the machine may force a change at first login. Several wrong entries lock you out "for a
  while" (lockout is configurable in Web Based Management).
  <https://support.brother.com/g/s/id/htmldoc/mfc/cv_dcpt830dw/uke/html/GUID-01123D26-62DC-4557-9436-E6056568F2F8_1.html>
- Network Reset "resets all information except the administrator password"; to reset the administrator password use the Factory
  Reset feature.
  <https://support.brother.com/g/s/id/htmldoc/mfc/cv_dcpt830dw/use/html/GUID-93C1500F-FCE9-481C-9499-A8720AC668E4_1.html>
- Reset menu for the DCP-T780DW group: Settings > Initial Setup > Reset, choose the reset, confirm by holding the right arrow for two
  seconds; the machine restarts. The password effect of each reset is described on the "Reset Functions Overview" page the guide links to.
  <https://support.brother.com/g/s/id/htmldoc/mfc/cv_dcpt830dw/uke/html/GUID-5D434F10-E0FA-4715-BC9F-19F3A57426C9_1.html>

## Likely causes, most to least likely (causes 1 to 3 are my inference, not a Brother statement)
1. **The password was already changed.** Anyone who completed first-login setup replaced the label password; the label is then stale.
   Check the family password manager and ask who set up the printer.
2. **Look-alike characters.** The label password mixes case and characters such as `0/O`, `1/l/I`. Type it slowly; paste nothing.
3. **Wrong address or page.** Use `https://colour.lab.riera.co.uk` (hostname, not the stale `.243` address; see
   <https://familia.riera.co.uk/tasks/3708>). Accept the self-signed certificate warning. A different device on that IP shows a different login.
4. **Temporary lockout** after several wrong tries (Brother page above). Stop typing, wait, then try once.
5. **Label from a different unit** (replaced machine, second-hand label). Compare the serial on the label with the one on the Network Configuration Report.

## Safe checklist (in order, stop when it works)
1. On the printer panel print the **Network Configuration Report** (uses one sheet and a little ink; the menu name is a guess, take what
   the panel shows). Confirm the IP and the "Pwd" line match the rear label.
2. In a browser, open `https://colour.lab.riera.co.uk`, one attempt with the **Network Configuration Report** password.
3. If you saw a lockout message, stop and wait (Brother says only "for a while"; 30 minutes is my guess), then one more attempt.
   Accept the self-signed certificate warning for this one host only.
4. Try the label password once more from a different browser or private window (rules out a saved wrong password being auto-filled).
5. Still failing: decide whether you need the web UI at all. The cutover and soak work reads the printer over IPP and SNMP and does not need it.
6. Only if you do need it: Marc decides on a reset, below.

## Reset from the panel (Marc's decision; changes printer state)
- Prefer **Network Reset** only if the problem is the network side; it keeps the administrator password, so it does **not** fix a wrong password.
- To clear the administrator password use the Factory Reset option under Settings > Initial Setup > Reset (menu names per the pages above;
  confirm on the panel). It erases all settings, including Wi-Fi: the printer leaves the network, so the Pi queues, the Prometheus soak
  probes and the colour-wifi queue stop until you rejoin Wi-Fi and give it its `colour.lab.riera.co.uk` address again.
- Before resetting, write down: Wi-Fi name and password, any fixed-IP/DHCP reservation, and the F2 soak status (a reset restarts the soak evidence for this printer).

## What not to do
- Do not keep guessing: repeated wrong passwords trigger the lockout.
- Do not factory-reset to "see what happens": it drops the printer off Wi-Fi.
- Do not search for or download "default password lists" or reset tools: the Brother default is per-unit, from the label, and third-party tools are untrusted.
- Do not script login attempts (curl, loops) against the printer.
- Do not share a photo of the rear label; it carries the password and serial.
