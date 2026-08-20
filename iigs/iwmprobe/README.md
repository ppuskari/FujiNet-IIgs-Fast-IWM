# IWMPROBE

`IWMPROBE P0.2A` is the host-side bridge between the standard 4 us SmartPort baseline and the paired 2 us Fast-IWM experiment.

It does not benchmark data transfer. It verifies that the stock Apple IIgs can select IWM mode bit 3 (2 us bit cells), observe the change through the status register, and restore the pre-test IWM mode before returning to GS/OS.

Build locally with Windows PowerShell 5.1:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\Build-IWMProbe-P02A.ps1
```
