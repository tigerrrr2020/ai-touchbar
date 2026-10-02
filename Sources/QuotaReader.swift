import AppKit
import Darwin
import Foundation

final class QuotaReader {
    let helper: URL
    let output: URL
    private let queue = DispatchQueue(label: "local.codex.touchbar.quota", qos: .utility)
    private let lock = NSLock()
    private var running = false
    private var stopped = false
    private var process: Process?
    var onImage: ((NSImage?, String) -> Void)?

    init(resources: URL, demoOnly: Bool = false) {
        helper = resources.appendingPathComponent("helper/quota_bridge.py")
        output = FileManager.default.temporaryDirectory.appendingPathComponent("touchbar-native-quota-\(UUID().uuidString).png")
        self.demoOnly = demoOnly
    }

    let demoOnly: Bool

    func refresh() {
        lock.lock()
        guard !running && !stopped else { lock.unlock(); return }
        running = true
        lock.unlock()
        queue.async {
            defer {
                self.lock.lock(); self.running = false; self.process = nil; self.lock.unlock()
            }
            self.lock.lock(); let cancelledBeforeStart = self.stopped; self.lock.unlock()
            guard !cancelledBeforeStart else { return }
            let runner = Process()
            runner.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
            runner.arguments = self.demoOnly ? [self.helper.path, "--preview"] : [self.helper.path]
            let sourceEnvironment = ProcessInfo.processInfo.environment
            var env = [String: String]()
            for key in ["HOME", "PATH", "TMPDIR", "LANG", "LC_CTYPE", "LC_ALL", "SHELL",
                        "CODEX_HOME", "KIMI_CODE_HOME", "KIMI_SHARE_DIR",
                        "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy",
                        "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"] {
                env[key] = sourceEnvironment[key]
            }
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            env["TOUCHBAR_QUOTA_OUT"] = self.output.path
            runner.environment = env
            let stdoutURL = FileManager.default.temporaryDirectory.appendingPathComponent("touchbar-native-output-\(UUID().uuidString).json")
            FileManager.default.createFile(atPath: stdoutURL.path, contents: nil)
            guard let stdout = try? FileHandle(forWritingTo: stdoutURL) else {
                DispatchQueue.main.async { self.onImage?(nil, "额度不可用") }
                return
            }
            runner.standardOutput = stdout
            runner.standardError = FileHandle.nullDevice
            do {
                try runner.run()
                self.lock.lock(); self.process = runner; let cancelledAfterStart = self.stopped; self.lock.unlock()
                if cancelledAfterStart { runner.terminate() }
                let completedInTime = Self.waitBounded(runner, timeout: 28)
                try? stdout.close()
                let fileSize = ((try? FileManager.default.attributesOfItem(atPath: stdoutURL.path)[.size]) as? NSNumber)?.intValue ?? 262145
                let payload = fileSize <= 262144 ? try? Data(contentsOf: stdoutURL) : nil
                let image = completedInTime && runner.terminationStatus == 0 ? Self.decodePayload(payload) : nil
                try? FileManager.default.removeItem(at: stdoutURL)
                try? FileManager.default.removeItem(at: self.output)
                DispatchQueue.main.async { self.onImage?(image, image == nil ? (completedInTime ? "额度未知" : "额度查询超时") : "额度已更新") }
            } catch {
                try? stdout.close()
                try? FileManager.default.removeItem(at: stdoutURL)
                try? FileManager.default.removeItem(at: self.output)
                DispatchQueue.main.async { self.onImage?(nil, "额度不可用") }
            }
        }
    }

    func stop() {
        lock.lock(); stopped = true; let current = process; lock.unlock()
        if let current, current.isRunning { current.terminate() }
        try? FileManager.default.removeItem(at: output)
    }

    static func decodePayload(_ data: Data?) -> NSImage? {
        guard let data, data.count <= 262144,
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let encoded = object["icon_data"] as? String,
              let png = Data(base64Encoded: encoded), png.count >= 24,
              png.prefix(8) == Data([137, 80, 78, 71, 13, 10, 26, 10]),
              png[16..<20].reduce(UInt32(0), { ($0 << 8) | UInt32($1) }) == 480,
              png[20..<24].reduce(UInt32(0), { ($0 << 8) | UInt32($1) }) == 60 else { return nil }
        return NSImage(data: png)
    }

    static func waitBounded(_ process: Process, timeout: TimeInterval) -> Bool {
        let stateLock = NSLock()
        var timedOut = false
        let watchdog = DispatchWorkItem {
            guard process.isRunning else { return }
            stateLock.lock(); timedOut = true; stateLock.unlock()
            process.terminate()
            DispatchQueue.global().asyncAfter(deadline: .now() + 2) {
                if process.isRunning { kill(process.processIdentifier, SIGKILL) }
            }
        }
        DispatchQueue.global(qos: .utility).asyncAfter(deadline: .now() + timeout, execute: watchdog)
        process.waitUntilExit()
        watchdog.cancel()
        stateLock.lock(); defer { stateLock.unlock() }
        return !timedOut
    }
}
