# hid_mk87.ps1 - MK87 (VID 0C45 / PID 8047) direct HID tool. All HID logic lives in C#.
# Actions:
#   -Action info                     list interfaces + caps
#   -Action readeff                  GET_LED_EFFECT -> 16-byte payload hex (2 reads)
#   -Action frame     [-Cmd N -Len M] one command, print full response frame
#   -Action sendhex   -Hex <32 hex>  write SET_LED_EFFECT, print ack + readback
#   -Action sweep     -Modes "1,23,254"  for each mode: write, read back x2, then restore baseline
# Frame formats:
#   request  = [reportID 0][0xAA][cmd][len][addrLo][addrHi][0][last][0] + data at offset 8
#   response = [reportID 0][0x55][cmd][len][addrLo][addrHi][..][..] + data at offset 8
param(
  [string]$Action = 'info',
  [string]$Hex = '',
  [string]$Modes = '1,23,254,26,28,20,21',
  [int]$Cmd = 19,
  [int]$Len = 0,
  [int]$HoldMs = 250
)

$ErrorActionPreference = 'Stop'
$src = @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

public class Mk87 {
    const uint GENERIC_READ = 0x80000000, GENERIC_WRITE = 0x40000000;
    const uint FILE_SHARE_READ = 1, FILE_SHARE_WRITE = 2, OPEN_EXISTING = 3;
    const uint FILE_FLAG_OVERLAPPED = 0x40000000;
    const uint DIGCF_PRESENT = 0x02, DIGCF_DEVICEINTERFACE = 0x10;
    const uint WAIT_OBJECT_0 = 0, ERROR_IO_PENDING = 997;
    public const ushort VID = 0x0C45, PID = 0x8047;
    public const int CMD_GET_LED_EFFECT = 19, CMD_SET_LED_EFFECT = 35;

    [StructLayout(LayoutKind.Sequential)]
    struct SP_DEVICE_INTERFACE_DATA { public uint cbSize; public Guid g; public uint Flags; public IntPtr Reserved; }
    [StructLayout(LayoutKind.Sequential)]
    struct HIDD_ATTRIBUTES { public uint Size; public ushort VendorID; public ushort ProductID; public ushort VersionNumber; }
    [StructLayout(LayoutKind.Sequential)]
    struct OVERLAPPED { public IntPtr Internal; public IntPtr InternalHigh; public uint Offset; public uint OffsetHigh; public IntPtr hEvent; }

    [DllImport("hid.dll")] static extern void HidD_GetHidGuid(out Guid g);
    [DllImport("hid.dll")] static extern bool HidD_GetAttributes(IntPtr h, ref HIDD_ATTRIBUTES a);
    [DllImport("hid.dll")] static extern bool HidD_GetPreparsedData(IntPtr h, out IntPtr pp);
    [DllImport("hid.dll")] static extern bool HidD_FreePreparsedData(IntPtr pp);
    [DllImport("hid.dll")] static extern int HidP_GetCaps(IntPtr pp, IntPtr caps);
    [DllImport("setupapi.dll", CharSet = CharSet.Unicode)] static extern IntPtr SetupDiGetClassDevsW(ref Guid g, IntPtr e, IntPtr h, uint f);
    [DllImport("setupapi.dll")] static extern bool SetupDiEnumDeviceInterfaces(IntPtr s, IntPtr d, ref Guid g, uint i, ref SP_DEVICE_INTERFACE_DATA did);
    [DllImport("setupapi.dll", CharSet = CharSet.Unicode)] static extern bool SetupDiGetDeviceInterfaceDetailW(IntPtr s, ref SP_DEVICE_INTERFACE_DATA did, IntPtr detail, uint size, ref uint need, IntPtr info);
    [DllImport("setupapi.dll")] static extern bool SetupDiDestroyDeviceInfoList(IntPtr s);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)] static extern IntPtr CreateFileW(string p, uint a, uint sh, IntPtr sa, uint d, uint fl, IntPtr t);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool WriteFile(IntPtr h, byte[] b, uint n, out uint w, IntPtr ov);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool ReadFile(IntPtr h, byte[] b, uint n, out uint r, ref OVERLAPPED ov);
    [DllImport("kernel32.dll", SetLastError = true)] static extern IntPtr CreateEventW(IntPtr a, bool manual, bool init, IntPtr name);
    [DllImport("kernel32.dll", SetLastError = true)] static extern uint WaitForSingleObject(IntPtr h, uint ms);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool GetOverlappedResult(IntPtr h, ref OVERLAPPED ov, out uint n, bool wait);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool ResetEvent(IntPtr h);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool CancelIoEx(IntPtr h, ref OVERLAPPED ov);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool CloseHandle(IntPtr h);

    class Iface {
        public string Path; public ushort Vid, Pid, UsagePage, Usage;
        public int InLen, OutLen;
        IntPtr rd = IntPtr.Zero, wr = IntPtr.Zero, ev = IntPtr.Zero, probe = IntPtr.Zero;

        public Iface(string path) {
            Path = path;
            probe = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, IntPtr.Zero, OPEN_EXISTING, 0, IntPtr.Zero);
            if (probe == new IntPtr(-1)) throw new Exception("open fail");
            HIDD_ATTRIBUTES at = new HIDD_ATTRIBUTES();
            at.Size = (uint)Marshal.SizeOf(typeof(HIDD_ATTRIBUTES));
            if (HidD_GetAttributes(probe, ref at)) { Vid = at.VendorID; Pid = at.ProductID; }
            IntPtr pp;
            if (HidD_GetPreparsedData(probe, out pp)) {
                IntPtr caps = Marshal.AllocHGlobal(256);
                if (HidP_GetCaps(pp, caps) == 0x00110000) {
                    Usage = (ushort)Marshal.ReadInt16(caps, 0);
                    UsagePage = (ushort)Marshal.ReadInt16(caps, 2);
                    InLen = (ushort)Marshal.ReadInt16(caps, 4);
                    OutLen = (ushort)Marshal.ReadInt16(caps, 6);
                }
                Marshal.FreeHGlobal(caps);
                HidD_FreePreparsedData(pp);
            }
        }

        public bool Open() {
            rd = CreateFileW(Path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, IntPtr.Zero, OPEN_EXISTING, FILE_FLAG_OVERLAPPED, IntPtr.Zero);
            wr = CreateFileW(Path, GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, IntPtr.Zero, OPEN_EXISTING, 0, IntPtr.Zero);
            ev = CreateEventW(IntPtr.Zero, true, false, IntPtr.Zero);
            return rd != new IntPtr(-1) && wr != new IntPtr(-1) && ev != IntPtr.Zero;
        }

        public string Write(byte[] report) {
            if (report.Length != OutLen) return "ERR length " + report.Length + " != " + OutLen;
            uint w;
            if (!WriteFile(wr, report, (uint)report.Length, out w, IntPtr.Zero)) return "ERR WriteFile " + Marshal.GetLastWin32Error();
            return "OK";
        }

        public byte[] Read(int timeoutMs) {
            byte[] buf = new byte[InLen];
            OVERLAPPED ov = new OVERLAPPED();
            ov.hEvent = ev;
            uint got;
            ResetEvent(ev);
            bool ok = ReadFile(rd, buf, (uint)InLen, out got, ref ov);
            if (!ok) {
                int err = Marshal.GetLastWin32Error();
                if (err != ERROR_IO_PENDING) return null;
                if (WaitForSingleObject(ev, (uint)Math.Max(10, timeoutMs)) != WAIT_OBJECT_0) {
                    CancelIoEx(rd, ref ov); ResetEvent(ev); return null;
                }
                if (!GetOverlappedResult(rd, ref ov, out got, false)) { ResetEvent(ev); return null; }
            }
            if (got == 0) return null;
            byte[] outb = new byte[got];
            Array.Copy(buf, outb, (int)got);
            return outb;
        }

        public void Close() {
            IntPtr[] hs = new IntPtr[] { rd, wr, probe };
            foreach (IntPtr h in hs) if (h != IntPtr.Zero && h != new IntPtr(-1)) CloseHandle(h);
            if (ev != IntPtr.Zero) CloseHandle(ev);
        }
    }

    static string[] EnumPaths() {
        Guid g; HidD_GetHidGuid(out g);
        IntPtr set = SetupDiGetClassDevsW(ref g, IntPtr.Zero, IntPtr.Zero, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE);
        List<string> list = new List<string>();
        if (set == new IntPtr(-1)) return list.ToArray();
        for (uint i = 0; ; i++) {
            SP_DEVICE_INTERFACE_DATA did = new SP_DEVICE_INTERFACE_DATA();
            did.cbSize = (uint)Marshal.SizeOf(typeof(SP_DEVICE_INTERFACE_DATA));
            if (!SetupDiEnumDeviceInterfaces(set, IntPtr.Zero, ref g, i, ref did)) break;
            uint need = 0;
            SetupDiGetDeviceInterfaceDetailW(set, ref did, IntPtr.Zero, 0, ref need, IntPtr.Zero);
            if (need == 0) continue;
            IntPtr detail = Marshal.AllocHGlobal((int)need);
            try {
                Marshal.WriteInt32(detail, IntPtr.Size == 8 ? 8 : 6);
                if (!SetupDiGetDeviceInterfaceDetailW(set, ref did, detail, need, ref need, IntPtr.Zero)) continue;
                int[] offs = new int[] { 8, 6, 4, 10 };
                foreach (int off in offs) {
                    if (off >= need) continue;
                    string cand = Marshal.PtrToStringUni(new IntPtr(detail.ToInt64() + off));
                    if (cand != null && cand.Length > 5 && cand[0] == '\\' && cand[1] == '\\') { list.Add(cand); break; }
                }
            } finally { Marshal.FreeHGlobal(detail); }
        }
        SetupDiDestroyDeviceInfoList(set);
        return list.ToArray();
    }

    static List<Iface> All() {
        List<Iface> res = new List<Iface>();
        foreach (string p in EnumPaths()) {
            Iface it = null;
            try { it = new Iface(p); } catch { continue; }
            if (it.Vid == VID && it.Pid == PID) res.Add(it); else it.Close();
        }
        return res;
    }

    static Iface Proto() {
        List<Iface> all = All();
        foreach (Iface x in all) if (x.UsagePage == 0xFF68) return x;
        foreach (Iface x in all) if (x.OutLen > 1 && x.UsagePage != 0xFF67) return x;
        return null;
    }

    public static string Hex(byte[] b) {
        if (b == null) return "";
        StringBuilder sb = new StringBuilder(b.Length * 3);
        for (int i = 0; i < b.Length; i++) { if (i > 0) sb.Append(' '); sb.Append(b[i].ToString("x2")); }
        return sb.ToString();
    }

    static string HexRange(byte[] b, int from, int count) {
        if (b == null || from >= b.Length) return "";
        int n = Math.Min(b.Length - from, count);
        byte[] s = new byte[n];
        Array.Copy(b, from, s, 0, n);
        return Hex(s);
    }

    static byte[] Report(int cmd, int len, int addr, byte[] data, bool last, int outLen) {
        byte[] buf = new byte[outLen];
        buf[0] = 0;
        buf[1] = 0xAA;
        buf[2] = (byte)cmd;
        buf[3] = (byte)len;
        buf[4] = (byte)(addr & 0xFF);
        buf[5] = (byte)((addr >> 8) & 0xFF);
        buf[7] = (byte)(last ? 1 : 0);
        if (data != null) Array.Copy(data, 0, buf, 9, Math.Min(data.Length, outLen - 9));
        return buf;
    }

    static byte[] Exchange(Iface it, byte[] report, int expectCmd, int timeoutMs) {
        for (int d = 0; d < 15; d++) if (it.Read(10) == null) break;
        for (int attempt = 0; attempt < 3; attempt++) {
            string w = it.Write(report);
            if (w.StartsWith("ERR")) return null;
            DateTime t0 = DateTime.Now;
            while (true) {
                int elapsed = (int)(DateTime.Now - t0).TotalMilliseconds;
                if (elapsed >= timeoutMs) break;
                int left = Math.Max(20, timeoutMs - elapsed);
                byte[] r = it.Read(left);
                if (r == null) break;
                if (r.Length >= 9 && r[1] == 0x55 && r[2] == (byte)expectCmd) {
                    byte[] frame = new byte[r.Length - 1];
                    Array.Copy(r, 1, frame, 0, frame.Length);
                    return frame;
                }
            }
        }
        return null;
    }

    public static string[] Info() {
        List<string> lines = new List<string>();
        foreach (Iface it in All()) {
            string mi = "MI_??";
            try { string lp = it.Path.ToLower(); mi = "MI_" + lp.Substring(lp.IndexOf("mi_") + 3, 2); } catch { }
            lines.Add(mi + " usagePage=0x" + it.UsagePage.ToString("X4") + " usage=0x" + it.Usage.ToString("X2") + " in=" + it.InLen + " out=" + it.OutLen);
        }
        return lines.ToArray();
    }

    public static string DumpFrame(int cmd, int len) {
        Iface it = Proto();
        if (it == null) return "ERR:no-device";
        if (!it.Open()) { it.Close(); return "ERR:open"; }
        try {
            byte[] f = Exchange(it, Report(cmd, len, 0, null, true, it.OutLen), cmd, 800);
            if (f == null) return "TIMEOUT";
            int l = f.Length > 3 ? f[2] : -1;
            return "frame = " + Hex(f) + "  | lenbyte=" + l + " | payload = " + HexRange(f, 8, Math.Max(0, Math.Min(l, 16)));
        } finally { it.Close(); }
    }

    static string EffRead(Iface it) {
        byte[] f = Exchange(it, Report(CMD_GET_LED_EFFECT, 16, 0, null, true, it.OutLen), CMD_GET_LED_EFFECT, 700);
        if (f == null) return "TIMEOUT";
        return HexRange(f, 8, 16);
    }

    public static string[] ReadEff() {
        List<string> o = new List<string>();
        Iface it = Proto();
        if (it == null) return new string[] { "ERR:no-device" };
        if (!it.Open()) { it.Close(); return new string[] { "ERR:open" }; }
        try {
            o.Add("read1 = " + EffRead(it));
            System.Threading.Thread.Sleep(150);
            o.Add("read2 = " + EffRead(it));
        } finally { it.Close(); }
        return o.ToArray();
    }

    public static string[] SendHex(string hex) {
        List<string> o = new List<string>();
        hex = hex.Replace(" ", "").Replace("-", "").Trim();
        if (hex.Length != 32) return new string[] { "ERR:need 32 hex chars" };
        byte[] data = new byte[16];
        for (int i = 0; i < 16; i++) data[i] = Convert.ToByte(hex.Substring(i * 2, 2), 16);
        Iface it = Proto();
        if (it == null) return new string[] { "ERR:no-device" };
        if (!it.Open()) { it.Close(); return new string[] { "ERR:open" }; }
        try {
            string before = EffRead(it);
            byte[] f = Exchange(it, Report(CMD_SET_LED_EFFECT, 16, 0, data, true, it.OutLen), CMD_SET_LED_EFFECT, 800);
            System.Threading.Thread.Sleep(260);
            string after = EffRead(it);
            o.Add("sent   = " + Hex(data));
            o.Add("ack    = " + (f == null ? "NONE" : HexRange(f, 8, 16)));
            o.Add("before = " + before);
            o.Add("after  = " + after);
        } finally { it.Close(); }
        return o.ToArray();
    }

    public static string[] Sweep(int[] modes, int holdMs) {
        List<string> o = new List<string>();
        Iface it = Proto();
        if (it == null) return new string[] { "ERR:no-device" };
        if (!it.Open()) { it.Close(); return new string[] { "ERR:open" }; }
        try {
            string baseHex = EffRead(it).Replace(" ", "");
            o.Add("baseline = " + baseHex);
            if (baseHex.Length < 32) { o.Add("ERR:baseline unreadable"); return o.ToArray(); }
            byte[] baseBytes = new byte[16];
            for (int i = 0; i < 16; i++) baseBytes[i] = Convert.ToByte(baseHex.Substring(i * 2, 2), 16);
            foreach (int m in modes) {
                byte[] b = (byte[])baseBytes.Clone();
                b[0] = (byte)m;
                b[4] = 0xFF; b[13] = 0x00; b[14] = 0xAA; b[15] = 0x55;
                if (m == 254) { b[5] = 0xFF; b[6] = 0x00; b[7] = 0x00; b[12] = 0x01; }
                byte[] f = Exchange(it, Report(CMD_SET_LED_EFFECT, 16, 0, b, true, it.OutLen), CMD_SET_LED_EFFECT, 800);
                string ack = (f == null) ? "NONE" : HexRange(f, 8, 16);
                System.Threading.Thread.Sleep(holdMs);
                string r1 = EffRead(it);
                System.Threading.Thread.Sleep(250);
                string r2 = EffRead(it);
                o.Add("mode=" + m.ToString().PadRight(3) + " ack=" + ack + " read1=" + r1 + " read2=" + r2);
            }
            byte[] rb = new byte[16];
            Array.Copy(baseBytes, rb, 16);
            rb[4] = 0xFF; rb[14] = 0xAA; rb[15] = 0x55;
            Exchange(it, Report(CMD_SET_LED_EFFECT, 16, 0, rb, true, it.OutLen), CMD_SET_LED_EFFECT, 800);
            System.Threading.Thread.Sleep(300);
            o.Add("restored = " + EffRead(it));
        } finally { it.Close(); }
        return o.ToArray();
    }
}
'@

if (-not ('Mk87' -as [type])) { Add-Type -TypeDefinition $src -Language CSharp }

switch ($Action) {
  'info'    { [Mk87]::Info() }
  'readeff' { [Mk87]::ReadEff() }
  'frame'   { [Mk87]::DumpFrame($Cmd, $(if ($Len -gt 0) { $Len } else { 16 })) }
  'sendhex' { [Mk87]::SendHex($Hex) }
  'sweep'   {
    $arr = @()
    foreach ($s in $Modes.Split(',')) { $arr += [int]$s.Trim() }
    [Mk87]::Sweep([int[]]$arr, $HoldMs)
  }
  default   { Write-Output "unknown action: $Action" }
}
