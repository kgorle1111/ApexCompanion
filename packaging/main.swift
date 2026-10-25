// ApexCompanion host. A compiled main executable (not a shell script) so macOS attributes Screen
// Recording to this signed app, and it stays alive as the parent of the coach: TCC resolves the
// *responsible* process, which must be running for the coach's screenshots to count as ours.
// It also owns the menu bar item: reads the coach's state.json, writes control.json.
import AppKit
import CoreGraphics

let argv = CommandLine.arguments
if argv.count > 1 {
    switch argv[1] {
    case "--preflight": print(CGPreflightScreenCaptureAccess()); exit(0)
    case "--request": print(CGRequestScreenCaptureAccess()); exit(0)
    default: break
    }
}

let env = ProcessInfo.processInfo.environment
let home: URL = {
    if let h = env["APEX_HOME"], !h.isEmpty { return URL(fileURLWithPath: h) }
    return FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Library/Application Support/ApexCompanion")
}()
let stateURL = home.appendingPathComponent("state.json")
let controlURL = home.appendingPathComponent("control.json")

func readJSON(_ url: URL) -> [String: Any]? {
    guard let d = try? Data(contentsOf: url) else { return nil }
    return (try? JSONSerialization.jsonObject(with: d)) as? [String: Any]
}

/// The coach's last report, or nil when no session is live (missing, stale >60 s, or stopped).
/// "error" is the exception: the coach gave up and exited, so it never refreshes; it stays shown
/// until the next session's launcher deletes state.json.
struct Live {
    let state: String, goal: String, focusedMin: Int, muted: Bool, paused: Bool, limitMin: Int?, lastLine: String

    init?(_ d: [String: Any]?, now: Double = Date().timeIntervalSince1970) {
        guard let d, let t = d["t"] as? Double, let state = d["state"] as? String,
              state == "error" || (now - t <= 60 && state != "stopped") else { return nil }
        self.state = state
        lastLine = ((d["last_line"] as? String) ?? "").components(separatedBy: .controlCharacters).joined(separator: " ")
        goal = (d["goal"] as? String) ?? ""
        focusedMin = Int(((d["focused_s"] as? Double) ?? 0) / 60)
        muted = (d["muted"] as? Bool) ?? false
        paused = state == "paused" || ((d["paused_until"] as? Double) ?? 0) > now
        // Session length: ends_at minus the session's start (t - elapsed_s), rounded to minutes.
        if let ends = d["ends_at"] as? Double, let el = d["elapsed_s"] as? Double {
            limitMin = Int(((ends - (t - el)) / 60).rounded())
        } else { limitMin = nil }
    }

    var failed: Bool { state == "error" }

    var title: String {
        if failed { return "⚠︎" }
        let m = "\(focusedMin)m"
        let base: String
        switch state {
        case "meeting": base = "◉ in a call"
        case "starting": base = "◉ …"
        case "distracted": base = "◉ \(m) ·"
        default: base = paused ? "⏸ \(m)" : "◉ \(m)"
        }
        return muted ? base + " 🔇" : base
    }
}

enum Control: String { case pause, resume, mute, unmute, stop }

/// Atomically rewrites the full control.json (temp file in the same dir, 0600, then rename),
/// keeping the current values of the fields this action does not change.
@discardableResult
func writeControl(_ action: Control) -> Bool {
    var c: [String: Any] = ["paused_until": NSNull(), "muted": false, "stop": false]
    if let cur = readJSON(controlURL) { for k in Array(c.keys) { if let v = cur[k] { c[k] = v } } }
    switch action {
    case .pause: c["paused_until"] = Int(Date().timeIntervalSince1970) + 900
    case .resume: c["paused_until"] = NSNull()
    case .mute: c["muted"] = true
    case .unmute: c["muted"] = false
    case .stop: c["stop"] = true
    }
    guard let data = try? JSONSerialization.data(withJSONObject: c, options: [.sortedKeys]) else { return false }
    try? FileManager.default.createDirectory(at: home, withIntermediateDirectories: true)
    let tmp = home.appendingPathComponent(".control.json.\(getpid()).tmp").path
    unlink(tmp)
    let fd = open(tmp, O_WRONLY | O_CREAT | O_EXCL, 0o600)
    guard fd >= 0 else { return false }
    let n = data.withUnsafeBytes { write(fd, $0.baseAddress, $0.count) }
    close(fd)
    guard n == data.count, rename(tmp, controlURL.path) == 0 else { unlink(tmp); return false }
    return true
}

/// pid of the running apex.py from the launcher's pidfile, verified (pid reuse guard).
func coachPid() -> pid_t? {
    guard let s = try? String(contentsOf: home.appendingPathComponent("coach.pid"), encoding: .utf8),
          let pid = pid_t(s.trimmingCharacters(in: .whitespacesAndNewlines)), pid > 0, kill(pid, 0) == 0 else { return nil }
    let ps = Process(), out = Pipe()
    ps.executableURL = URL(fileURLWithPath: "/bin/ps")
    ps.arguments = ["-p", "\(pid)", "-o", "command="]
    ps.standardOutput = out
    guard (try? ps.run()) != nil else { return nil }
    ps.waitUntilExit()
    let cmd = String(data: out.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
    return cmd.contains("apex.py") ? pid : nil
}

final class Host: NSObject, NSApplicationDelegate, NSMenuDelegate {
    let demo: Bool
    var children: [Process] = []
    var quitting = false
    let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)

    init(demo: Bool) { self.demo = demo }

    func runLauncher(pickPersona: Bool = false) {
        if demo { print("demo: would run launcher (pickPersona=\(pickPersona))"); return }
        guard let script = Bundle.main.path(forResource: "launcher", ofType: "sh") else { return }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/bash")
        p.arguments = [script]
        var e = env
        e["APEX_APP_BIN"] = Bundle.main.executablePath
        e["APEX_HOST"] = "1"
        if pickPersona { e["APEX_PICK_PERSONA"] = "1" }
        p.environment = e
        // The menu bar item outlives the launcher (so another session can be started); the app
        // only exits on Quit, once its children are gone.
        p.terminationHandler = { [weak self] done in
            DispatchQueue.main.async {
                guard let self else { return }
                self.children.removeAll { $0 === done }
                if self.quitting && self.children.isEmpty { NSApp.terminate(nil) }
            }
        }
        do { try p.run(); children.append(p) } catch { NSLog("ApexCompanion: launcher failed: \(error)") }
    }

    func applicationDidFinishLaunching(_ n: Notification) {
        item.button?.font = NSFont.monospacedDigitSystemFont(ofSize: NSFont.systemFontSize, weight: .regular)
        let menu = NSMenu()
        menu.delegate = self
        item.menu = menu
        refresh()
        let timer = Timer(timeInterval: 2, repeats: true) { [weak self] _ in self?.refresh() }
        RunLoop.main.add(timer, forMode: .common)   // .common: keeps ticking while the menu is open
        runLauncher()
    }

    // Double-clicking the app while it is coaching lands here (no second process is started):
    // the launcher sees the live pidfile and shows the Stop / Switch / Edit sites menu.
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        runLauncher()
        return false
    }

    func refresh() {
        let title = Live(readJSON(stateURL))?.title ?? "◉ Apex"
        if item.button?.title != title {
            item.button?.title = title
            if demo { print("title: \(title)"); fflush(stdout) }
        }
    }

    func menuNeedsUpdate(_ menu: NSMenu) {
        menu.removeAllItems()
        for i in Host.menuItems(Live(readJSON(stateURL))) {
            if i.title.isEmpty { menu.addItem(.separator()); continue }
            let mi = NSMenuItem(title: i.title, action: i.action, keyEquivalent: "")
            mi.target = i.action == nil ? nil : self
            mi.isEnabled = i.action != nil
            menu.addItem(mi)
        }
    }

    /// The menu as (title, action) rows; "" is a separator, nil action is a disabled label.
    static func menuItems(_ live: Live?) -> [(title: String, action: Selector?)] {
        var rows: [(title: String, action: Selector?)] = []
        if let l = live, l.failed {
            let why = l.lastLine.count > 60 ? l.lastLine.prefix(59) + "…" : l.lastLine
            rows.append((why.isEmpty ? "The coach stopped after repeated errors" : "Stopped: \(why)", nil))
            rows.append(("", nil))
            rows.append(("Start a session…", #selector(Host.startSession)))
            rows.append(("Start with another persona…", #selector(Host.startWithPicker)))
        } else if let l = live {
            let goal = l.goal.count > 60 ? l.goal.prefix(59) + "…" : l.goal
            rows.append((goal.isEmpty ? "No goal set" : "Working on: \(goal)", nil))
            rows.append((l.limitMin.map { "Focused \(l.focusedMin) of \($0) min" } ?? "\(l.focusedMin) min focused", nil))
            rows.append(("", nil))
            rows.append(l.paused ? ("Resume", #selector(Host.resume)) : ("Pause 15 minutes", #selector(Host.pause)))
            rows.append(l.muted ? ("Unmute voice", #selector(Host.unmute)) : ("Mute voice", #selector(Host.mute)))
            rows.append(("Edit my sites…", #selector(Host.editSites)))
            rows.append(("", nil))
            rows.append(("Stop session", #selector(Host.stopSession)))
        } else {
            rows.append(("Start a session…", #selector(Host.startSession)))
            rows.append(("Start with another persona…", #selector(Host.startWithPicker)))
        }
        rows.append(("", nil))
        rows.append(("Quit ApexCompanion", #selector(Host.quit)))
        return rows
    }

    @objc func pause() { writeControl(.pause) }
    @objc func resume() { writeControl(.resume) }
    @objc func mute() { writeControl(.mute) }
    @objc func unmute() { writeControl(.unmute) }
    @objc func stopSession() { writeControl(.stop) }
    @objc func startSession() { runLauncher() }
    @objc func startWithPicker() { runLauncher(pickPersona: true) }
    @objc func editSites() {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/open")
        p.arguments = ["-e", home.appendingPathComponent("sites.txt").path]
        try? p.run()
    }

    @objc func quit() {
        quitting = true
        // A failed (exited) coach counts as no coach: there is nothing to stop.
        guard coachPid() != nil || Live(readJSON(stateURL)).map({ !$0.failed }) == true else {
            // No coach: a launcher still in setup/dialogs must not go on to start one without us.
            children.forEach { $0.terminate() }
            NSApp.terminate(nil); return
        }
        writeControl(.stop)
        if children.isEmpty { NSApp.terminate(nil); return }
        // kn: fixed 10 s / 20 s fallbacks in case the coach ignores control.json; tune if real stops take longer.
        DispatchQueue.main.asyncAfter(deadline: .now() + 10) { if let pid = coachPid() { kill(pid, SIGINT) } }
        DispatchQueue.main.asyncAfter(deadline: .now() + 20) { NSApp.terminate(nil) }
    }
}

// Hidden test flags (no launcher is started):
//   --print-menu                 print the title + menu rows for APEX_HOME/state.json, exit
//   --write-control-test ACTION  apply pause|resume|mute|unmute|stop to control.json, print it, exit
//   --menubar-demo               show only the status item, polling APEX_HOME/state.json
if argv.count > 1 && argv[1] == "--print-menu" {
    let live = Live(readJSON(stateURL))
    print("title: \(live?.title ?? "◉ Apex")")
    for r in Host.menuItems(live) { print(r.title.isEmpty ? "---" : (r.action == nil ? "[\(r.title)]" : r.title)) }
    exit(0)
}
if argv.count > 2 && argv[1] == "--write-control-test" {
    guard let a = Control(rawValue: argv[2]), writeControl(a),
          let s = try? String(contentsOf: controlURL, encoding: .utf8) else { print("write failed"); exit(1) }
    print(s); exit(0)
}

let app = NSApplication.shared
let host = Host(demo: argv.count > 1 && argv[1] == "--menubar-demo")
app.delegate = host
app.setActivationPolicy(.accessory)
app.run()
