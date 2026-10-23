import AppKit
import Foundation

enum KimiSelection: Equatable {
    case auto
    case pinned(UUID)
    case off

    var mode: String {
        switch self { case .auto: return "auto"; case .pinned: return "pinned"; case .off: return "off" }
    }
    var sessionID: String? {
        if case .pinned(let id) = self { return id.uuidString.lowercased() }
        return nil
    }
}

struct LiveStatusSnapshot {
    let kimi: String?
    let codex: String?
    let codexThreadID: String?
    let generation: UInt64
    let kimiSelection: KimiSelection
    let kimiResolvedSessionID: String?
    let kimiReason: String
}

struct CodexTask: Decodable {
    let id: String
    let title: String
}

struct KimiTask: Decodable {
    let id: String
    let title: String
    let active: Bool
    static let demoTasks = [
        KimiTask(id: "11111111-1111-4111-8111-111111111111", title: "模拟任务 A · 11111111", active: true),
        KimiTask(id: "22222222-2222-4222-8222-222222222222", title: "模拟任务 B · 22222222", active: true)
    ]

    static func demoStatus(selection: KimiSelection) -> (raw: String, reason: String, resolvedID: String?) {
        if selection == .off { return ("空闲", "off", nil) }
        guard let pin = selection.sessionID else { return ("未知", "ambiguous", nil) }
        guard let index = demoTasks.firstIndex(where: { $0.id == pin }) else { return ("未知", "not_found", nil) }
        return (index == 0 ? "命令" : "改文件", "active", pin)
    }
}

struct BridgeResponse: Decodable {
    let kimi: String?
    let codex: String?
    let codexThreadID: String?
    let threads: [CodexTask]?
    let ok: Bool?
    let tasks: [KimiTask]?
    let truncated: Bool?
    let reason: String?
    let kimiMode: String?
    let kimiSessionID: String?
    let kimiResolvedSessionID: String?
    let kimiReason: String?
    enum CodingKeys: String, CodingKey {
        case kimi, codex, threads, ok, tasks, truncated, reason
        case codexThreadID = "codex_thread_id"
        case kimiMode = "kimi_mode", kimiSessionID = "kimi_session_id"
        case kimiResolvedSessionID = "kimi_resolved_session_id", kimiReason = "kimi_reason"
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
    private var kimiSelection: KimiSelection = .auto
    private var generation: UInt64 = 0
    var onStatus: ((LiveStatusSnapshot) -> Void)?

    init(resources: URL) { helper = resources.appendingPathComponent("helper/status_bridge.py") }

    static func validUUID(_ value: String) -> Bool {
        value.range(of: "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", options: .regularExpression) != nil
    }

    static func acceptsCallback(requestGeneration: UInt64, currentGeneration: UInt64,
                                requestThreadID: String?, currentThreadID: String?, stopped: Bool,
                                requestKimi: KimiSelection = .auto, currentKimi: KimiSelection = .auto) -> Bool {
        !stopped && requestGeneration == currentGeneration && requestThreadID == currentThreadID && requestKimi == currentKimi
    }

    static func matchesKimiResponse(_ response: BridgeResponse?, selection: KimiSelection) -> Bool {
        guard let response, response.kimiMode == selection.mode, response.kimiSessionID == selection.sessionID,
              let reason = response.kimiReason,
              ["active", "completed", "idle", "no_tasks", "ambiguous", "not_found", "unavailable", "off", "invalid_selection"].contains(reason)
        else { return false }
        if let resolved = response.kimiResolvedSessionID {
            guard validUUID(resolved), resolved == resolved.lowercased() else { return false }
            if let pinned = selection.sessionID, resolved != pinned { return false }
        }
        if reason == "active" || reason == "completed" || (selection.mode == "pinned" && reason == "idle") {
            guard response.kimiResolvedSessionID != nil else { return false }
        }
        return selection != .off || (reason == "off" && response.kimiResolvedSessionID == nil)
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
        let active = processIsStatusPoll ? process : nil
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

    func setKimiSelection(_ selection: KimiSelection) {
        lock.lock()
        guard kimiSelection != selection else { lock.unlock(); return }
        kimiSelection = selection
        generation &+= 1
        let active = processIsStatusPoll ? process : nil
        let shouldPoll = !stopped && !paused
        lock.unlock()
        if let active, active.isRunning { active.terminate() }
        if shouldPoll { queue.async { [weak self] in self?.poll() } }
    }

    func loadKimiTasks(_ completion: @escaping ([KimiTask]?, Bool, String) -> Void) {
        lock.lock(); let pin = kimiSelection.sessionID; lock.unlock()
        queue.async { [weak self] in
            guard let self else { return }
            var arguments = ["--kimi-tasks"]
            if let pin { arguments += ["--kimi-session", pin] }
            let data = self.runBridge(arguments, timeout: 2, isStatusPoll: false)
            let response = data.flatMap { try? JSONDecoder().decode(BridgeResponse.self, from: $0) }
            guard response?.ok == true, let tasks = response?.tasks, tasks.count <= 40,
                  tasks.allSatisfy({ Self.validUUID($0.id) && $0.id == $0.id.lowercased() }),
                  Set(tasks.map(\.id)).count == tasks.count else {
                DispatchQueue.main.async { completion(nil, false, response?.reason ?? "unavailable") }
                return
            }
            let clean = tasks.map { KimiTask(id: $0.id, title: String($0.title.prefix(90)), active: $0.active) }
            DispatchQueue.main.async { completion(clean, response?.truncated ?? false, response?.reason ?? "idle") }
        }
    }

    private func poll() {
        lock.lock()
        guard !stopped && !paused && !busy else { lock.unlock(); return }
        busy = true
        let threadID = selectedThreadID
        let requestedKimi = kimiSelection
        let requestGeneration = generation
        lock.unlock()
        defer { lock.lock(); busy = false; lock.unlock() }
        var args = ["--status", "--kimi-mode", requestedKimi.mode]
        if let pin = requestedKimi.sessionID { args += ["--kimi-session", pin] }
        if let threadID { args += ["--codex-thread", threadID] }
        let data = runBridge(args, timeout: 3, isStatusPoll: true, expectedGeneration: requestGeneration)
        let response = data.flatMap { try? JSONDecoder().decode(BridgeResponse.self, from: $0) }
        lock.lock()
        let stillCurrent = Self.acceptsCallback(requestGeneration: requestGeneration, currentGeneration: generation,
                                                requestThreadID: threadID, currentThreadID: selectedThreadID, stopped: stopped,
                                                requestKimi: requestedKimi, currentKimi: kimiSelection)
        lock.unlock()
        guard stillCurrent else { return }
        let codexResponseMatches = response?.codexThreadID == threadID
        let kimiResponseMatches = Self.matchesKimiResponse(response, selection: requestedKimi)
        let failedKimiReason = response == nil ? "unavailable" : "invalid_selection"
        let snapshot = LiveStatusSnapshot(
            kimi: kimiResponseMatches ? response?.kimi : (response == nil ? "不可用" : "未知"),
            codex: codexResponseMatches ? response?.codex : "不可用",
            codexThreadID: threadID,
            generation: requestGeneration,
            kimiSelection: requestedKimi,
            kimiResolvedSessionID: kimiResponseMatches ? response?.kimiResolvedSessionID : nil,
            kimiReason: kimiResponseMatches ? response?.kimiReason ?? "unavailable" : failedKimiReason
        )
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            self.lock.lock()
            let current = Self.acceptsCallback(requestGeneration: snapshot.generation, currentGeneration: self.generation,
                                               requestThreadID: snapshot.codexThreadID, currentThreadID: self.selectedThreadID,
                                               stopped: self.stopped, requestKimi: snapshot.kimiSelection, currentKimi: self.kimiSelection)
            self.lock.unlock()
            if current { self.onStatus?(snapshot) }
        }
    }

    private func runBridge(_ arguments: [String], timeout: TimeInterval, isStatusPoll: Bool,
                           expectedGeneration: UInt64? = nil) -> Data? {
        lock.lock(); let cancelled = stopped || (expectedGeneration != nil && expectedGeneration != generation); lock.unlock()
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
        lock.lock(); process = child; processIsStatusPoll = isStatusPoll
        let cancel = stopped || (expectedGeneration != nil && expectedGeneration != generation)
        lock.unlock()
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
