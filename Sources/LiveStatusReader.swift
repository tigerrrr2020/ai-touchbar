import AppKit
import Foundation

struct LiveStatusSnapshot {
    let kimi: String?
    let codex: String?
    let codexThreadID: String?
    let generation: UInt64
}

struct CodexTask: Decodable {
    let id: String
    let title: String
}

struct BridgeResponse: Decodable {
    let kimi: String?
    let codex: String?
    let codexThreadID: String?
    let threads: [CodexTask]?
    let ok: Bool?
    enum CodingKeys: String, CodingKey {
        case kimi, codex, threads, ok
        case codexThreadID = "codex_thread_id"
    }
}

final class LiveStatusReader {
    private let helper: URL
    private let queue = DispatchQueue(label: "local.codex.touchbar.live-status", qos: .utility)
    private let lock = NSLock()
    private var timer: DispatchSourceTimer?
    private var process: Process?
    private var stopped = false
    private var paused = true
    private var busy = false
    private var processIsStatusPoll = false
    private var selectedThreadID: String?
    private var generation: UInt64 = 0
    var onStatus: ((LiveStatusSnapshot) -> Void)?

    init(resources: URL) { helper = resources.appendingPathComponent("helper/status_bridge.py") }

    static func validUUID(_ value: String) -> Bool {
        value.range(of: "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", options: .regularExpression) != nil
    }

    static func acceptsCallback(requestGeneration: UInt64, currentGeneration: UInt64,
                                requestThreadID: String?, currentThreadID: String?, stopped: Bool) -> Bool {
        !stopped && requestGeneration == currentGeneration && requestThreadID == currentThreadID
    }

    func start() {
        lock.lock()
        guard !stopped && paused else { lock.unlock(); return }
        generation &+= 1
        stopped = false
        paused = false
        let source = DispatchSource.makeTimerSource(queue: queue)
        timer = source
        source.schedule(deadline: .now(), repeating: 2)
        source.setEventHandler { [weak self] in self?.poll() }
        source.resume()
        lock.unlock()
    }

    func stop() {
        lock.lock()
        stopped = true; paused = true; generation &+= 1
        let active = process
        let source = timer
        timer = nil
        lock.unlock()
        source?.cancel()
        if let active, active.isRunning { active.terminate() }
    }

    func pause() {
        lock.lock()
        paused = true
        generation &+= 1
        let active = processIsStatusPoll ? process : nil
        let source = timer
        timer = nil
        lock.unlock()
        source?.cancel()
        if let active, active.isRunning { active.terminate() }
    }

    func setCodexThread(_ threadID: String?) {
        let validID = threadID.flatMap { Self.validUUID($0) ? $0.lowercased() : nil }
        lock.lock()
        guard selectedThreadID != validID else { lock.unlock(); return }
        selectedThreadID = validID
        generation &+= 1
        let active = process
        let shouldPoll = !stopped && !paused
        lock.unlock()
        if let active, active.isRunning { active.terminate() }
        if shouldPoll { queue.async { [weak self] in self?.poll() } }
    }

    func loadTasks(_ completion: @escaping ([CodexTask]?) -> Void) {
        queue.async { [weak self] in
            guard let self else { return }
            let data = self.runBridge(["--tasks"], timeout: 2, isStatusPoll: false)
            let response = data.flatMap { try? JSONDecoder().decode(BridgeResponse.self, from: $0) }
            guard response?.ok == true, let tasks = response?.threads else {
                DispatchQueue.main.async { completion(nil) }
                return
            }
            let clean = tasks.filter { Self.validUUID($0.id) }
                .map { CodexTask(id: $0.id.lowercased(), title: String($0.title.prefix(72))) }
            DispatchQueue.main.async { completion(clean) }
        }
    }

    private func poll() {
        lock.lock()
        guard !stopped && !paused && !busy else { lock.unlock(); return }
        busy = true
        let threadID = selectedThreadID
        let requestGeneration = generation
        lock.unlock()
        defer { lock.lock(); busy = false; lock.unlock() }
        var args = ["--status"]
        if let threadID { args += ["--codex-thread", threadID] }
        let data = runBridge(args, timeout: 3, isStatusPoll: true)
        let response = data.flatMap { try? JSONDecoder().decode(BridgeResponse.self, from: $0) }
        lock.lock()
        let stillCurrent = Self.acceptsCallback(requestGeneration: requestGeneration, currentGeneration: generation,
                                                requestThreadID: threadID, currentThreadID: selectedThreadID, stopped: stopped)
        lock.unlock()
        guard stillCurrent else { return }
        let codexResponseMatches = response?.codexThreadID == threadID
        let snapshot = LiveStatusSnapshot(
            kimi: response?.kimi,
            codex: codexResponseMatches ? response?.codex : "不可用",
            codexThreadID: threadID,
            generation: requestGeneration
        )
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            self.lock.lock()
            let current = Self.acceptsCallback(requestGeneration: snapshot.generation, currentGeneration: self.generation,
                                               requestThreadID: snapshot.codexThreadID, currentThreadID: self.selectedThreadID,
                                               stopped: self.stopped)
            self.lock.unlock()
            if current { self.onStatus?(snapshot) }
        }
    }

    private func runBridge(_ arguments: [String], timeout: TimeInterval, isStatusPoll: Bool) -> Data? {
        lock.lock(); let cancelled = stopped; lock.unlock()
        guard !cancelled else { return nil }
        let output = FileManager.default.temporaryDirectory.appendingPathComponent("touchbar-status-\(UUID().uuidString).json")
        FileManager.default.createFile(atPath: output.path, contents: nil)
        guard let handle = try? FileHandle(forWritingTo: output) else { try? FileManager.default.removeItem(at: output); return nil }
        let child = Process()
        child.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        child.arguments = [helper.path] + arguments
        let inherited = ProcessInfo.processInfo.environment
        var environment: [String: String] = [:]
        for key in ["HOME", "PATH", "TMPDIR", "LANG", "LC_CTYPE", "LC_ALL", "CODEX_HOME", "KIMI_CODE_HOME", "KIMI_SHARE_DIR"] {
            environment[key] = inherited[key]
        }
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        child.environment = environment
        child.standardOutput = handle
        child.standardError = FileHandle.nullDevice
        do { try child.run() } catch { try? handle.close(); try? FileManager.default.removeItem(at: output); return nil }
        lock.lock(); process = child; processIsStatusPoll = isStatusPoll; let cancel = stopped; lock.unlock()
        if cancel { child.terminate() }
        let timely = QuotaReader.waitBounded(child, timeout: timeout)
        try? handle.close()
        let size = ((try? FileManager.default.attributesOfItem(atPath: output.path)[.size]) as? NSNumber)?.intValue ?? 16385
        let data = timely && child.terminationStatus == 0 && size <= 16384 ? try? Data(contentsOf: output) : nil
        try? FileManager.default.removeItem(at: output)
        lock.lock()
        if process === child { process = nil; processIsStatusPoll = false }
        lock.unlock()
        return data
    }
}
