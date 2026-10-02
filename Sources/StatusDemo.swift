import AppKit
import Foundation

enum DemoState: String, CaseIterable {
    case thinking, command, file, approval, complete, hidden
    var label: String {
        switch self {
        case .thinking: return "思考"
        case .command: return "命令"
        case .file: return "改文件"
        case .approval: return "等待审批"
        case .complete: return "完成"
        case .hidden: return "隐藏"
        }
    }
}

final class StatusDemo {
    static let frameCount = 12
    static let framesPerSecond = 6
    static let cycleSeconds = 48
    let assets: URL
    private var frames: [String: NSImage] = [:]
    init(assets: URL) { self.assets = assets }
    func image(_ state: DemoState, tick: Int, kimi: Bool = false) -> NSImage? {
        guard state != .hidden else { return nil }
        let file = String(format: "%@%@-%02d.json", kimi ? "kimi-" : "", state.rawValue, tick % Self.frameCount)
        if let image = frames[file] { return image }
        let url = assets.appendingPathComponent(file)
        guard let data = try? Data(contentsOf: url),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let encoded = object["icon_data"] as? String,
              let png = Data(base64Encoded: encoded) else { return nil }
        guard let image = NSImage(data: png) else { return nil }
        frames[file] = image
        return image
    }
    func state(at elapsed: TimeInterval) -> DemoState {
        guard elapsed < Double(Self.cycleSeconds) else { return .hidden }
        let second = Int(max(0, elapsed).rounded(.down))
        if second < 12 { return .thinking }
        if second < 20 { return .command }
        if second < 28 { return .file }
        if second < 36 { return .approval }
        if second < 44 { return .complete }
        return .hidden
    }
}
