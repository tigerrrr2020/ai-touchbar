import Foundation

enum AgentState {
    static func display(_ raw: String?) -> DemoState? {
        switch raw {
        case "思考": return .thinking
        case "命令": return .command
        case "改文件": return .file
        case "等待审批": return .approval
        case "完成": return .complete
        default: return nil
        }
    }
}

struct KimiGrace {
    private(set) var lastActive: DemoState?
    private(set) var confirmedAt: TimeInterval?
    private var selection: KimiSelection?
    private var resolvedSessionID: String?
    static let seconds: TimeInterval = 10

    var rawState: DemoState? { lastActive }

    func visible(now: TimeInterval) -> DemoState? {
        guard let state = lastActive else { return nil }
        if state == .complete { return state }
        guard let confirmedAt, now >= confirmedAt, now - confirmedAt <= Self.seconds else { return nil }
        return state
    }

    mutating func update(_ raw: String?, now: TimeInterval) -> DemoState? {
        if let state = AgentState.display(raw) {
            lastActive = state
            confirmedAt = state == .complete ? nil : now
            return state
        }
        if raw == "不可用", lastActive != .complete, let state = visible(now: now) {
            return state
        }
        lastActive = nil
        confirmedAt = nil
        return nil
    }

    mutating func update(_ raw: String?, selection requested: KimiSelection, resolvedID: String?,
                         reason: String, now: TimeInterval) -> DemoState? {
        if selection != requested || (reason != "unavailable" && resolvedSessionID != resolvedID) {
            lastActive = nil; confirmedAt = nil
        }
        selection = requested
        if reason != "unavailable" { resolvedSessionID = resolvedID }
        if requested == .off || !["active", "completed", "unavailable"].contains(reason) {
            return update("空闲", now: now)
        }
        return update(reason == "unavailable" ? "不可用" : raw, now: now)
    }
}
