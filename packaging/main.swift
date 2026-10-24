// ApexCompanion host. A compiled main executable (not a shell script) so macOS attributes Screen
// Recording to this signed app, and it stays alive as the parent of the coach: TCC resolves the
// *responsible* process, which must be running for the coach's screenshots to count as ours.
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

final class Host: NSObject, NSApplicationDelegate {
    var children: [Process] = []

    func runLauncher() {
        guard let script = Bundle.main.path(forResource: "launcher", ofType: "sh") else { NSApp.terminate(nil); return }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/bash")
        p.arguments = [script]
        var env = ProcessInfo.processInfo.environment
        env["APEX_APP_BIN"] = Bundle.main.executablePath
        env["APEX_HOST"] = "1"
        p.environment = env
        p.terminationHandler = { [weak self] done in
            DispatchQueue.main.async {
                self?.children.removeAll { $0 === done }
                if self?.children.isEmpty ?? true { NSApp.terminate(nil) }
            }
        }
        do { try p.run(); children.append(p) } catch { if children.isEmpty { NSApp.terminate(nil) } }
    }

    func applicationDidFinishLaunching(_ n: Notification) { runLauncher() }

    // Double-clicking the app while it is coaching lands here (no second process is started):
    // the launcher sees the live pidfile and shows the Stop / Switch / Edit sites menu.
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        runLauncher()
        return false
    }
}

let app = NSApplication.shared
let host = Host()
app.delegate = host
app.setActivationPolicy(.accessory)
app.run()
