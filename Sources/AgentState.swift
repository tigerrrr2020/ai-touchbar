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
}
