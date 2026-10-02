import AppKit
import Foundation

enum PrototypeChecks {
    static func run(resources: URL) {
        guard let pinURL = Bundle.main.url(forResource: "menubar-pin", withExtension: "svg"),
              let pin = NSImage(contentsOf: pinURL) else {
            preconditionFailure("menu bar SVG icon could not be loaded")
        }
        pin.size = NSSize(width: 18, height: 18)
        pin.isTemplate = true
        precondition(pin.isTemplate && pin.size == NSSize(width: 18, height: 18))
        precondition(pin.tiffRepresentation != nil, "menu bar SVG icon could not be rasterized")
        precondition(TBOperationWindow.isCloseShortcut(modifierFlags: .command, characters: "w"))
        precondition(TBOperationWindow.isCloseShortcut(modifierFlags: [.command, .capsLock], characters: "w"))
        precondition(!TBOperationWindow.isCloseShortcut(modifierFlags: .command, characters: "q"))
        precondition(!TBOperationWindow.isCloseShortcut(modifierFlags: [.command, .shift], characters: "w"))
        precondition(!TBOperationWindow.isCloseShortcut(modifierFlags: [], characters: "w"))
        let demo = StatusDemo(assets: resources.appendingPathComponent("status-assets"))
        testTouchBarTray(demo: demo)
        precondition(demo.state(at: 0) == .thinking)
        precondition(demo.state(at: 12) == .command)
        precondition(demo.state(at: 20) == .file)
        precondition(demo.state(at: 28) == .approval)
        precondition(demo.state(at: 36) == .complete)
        precondition(demo.state(at: 44) == .hidden && demo.state(at: 48) == .hidden)
        for state in DemoState.allCases where state != .hidden {
            for frame in 0..<StatusDemo.frameCount {
                precondition(demo.image(state, tick: frame) != nil)
                precondition(demo.image(state, tick: frame, kimi: true) != nil)
            }
        }
        precondition(QuotaReader.decodePayload(Data("not-json".utf8)) == nil)
        precondition(QuotaReader.decodePayload(Data("{}".utf8)) == nil)
        precondition(QuotaReader.decodePayload(Data(repeating: 32, count: 262145)) == nil)
        testLiveState()
        testOfflineQuota(resources: resources)
        testDeadline()
        print("Self-test passed: menu icon, window close shortcut, Touch Bar tray button, quota preview, status frames, live state/grace, malformed JSON, timeout")
    }

    private static func testTouchBarTray(demo: StatusDemo) {
        _ = NSApplication.shared
        let ui = TouchBarUI(demo: demo)
        guard let button = (ui.makeTrayItem() as? NSCustomTouchBarItem)?.view as? NSButton,
              let action = button.action else {
            preconditionFailure("Touch Bar tray item must expose an actionable button")
        }
        guard button.frame.size == NSSize(width: 36, height: 30) else { fatalError("Touch Bar tray button size was \(button.frame.size)") }
        guard button.image?.size == NSSize(width: 18, height: 18) else { fatalError("Touch Bar tray image size was \(String(describing: button.image?.size))") }
        guard button.image?.isTemplate == true && button.imagePosition == .imageOnly else { fatalError("Touch Bar tray image is not a centered template") }
        guard button.target as? TouchBarUI === ui && ui.responds(to: action) else { fatalError("Touch Bar tray action target is not wired to TouchBarUI") }
    }

    private static func testLiveState() {
        precondition(AgentState.display("思考") == .thinking)
        precondition(AgentState.display("等待审批") == .approval)
        precondition(AgentState.display("未知") == nil)
        let decoded = try? JSONDecoder().decode(BridgeResponse.self, from: Data("{\"kimi\":\"未知\",\"codex\":\"思考\",\"codex_thread_id\":\"abc\"}".utf8))
        precondition(decoded?.kimi == "未知" && decoded?.codex == "思考")
        precondition((try? JSONDecoder().decode(BridgeResponse.self, from: Data("not-json".utf8))) == nil)
        precondition(LiveStatusReader.acceptsCallback(requestGeneration: 4, currentGeneration: 4,
                                                      requestThreadID: "a", currentThreadID: "a", stopped: false))
        precondition(!LiveStatusReader.acceptsCallback(requestGeneration: 4, currentGeneration: 5,
                                                       requestThreadID: "a", currentThreadID: "a", stopped: false))
        precondition(!LiveStatusReader.acceptsCallback(requestGeneration: 4, currentGeneration: 4,
                                                       requestThreadID: "a", currentThreadID: "b", stopped: false))
        var grace = KimiGrace()
        precondition(grace.update("命令", now: 100) == .command)
        precondition(grace.update("不可用", now: 109) == .command)
        precondition(grace.visible(now: 110.01) == nil, "grace must expire from last confirmed success")
        precondition(grace.update("未知", now: 109) == nil, "successful ambiguous response must clear immediately")
        precondition(grace.update("改文件", now: 120) == .file)
        precondition(grace.update("完成", now: 121) == .complete)
        precondition(grace.visible(now: 999) == .complete)
        precondition(grace.update("空闲", now: 122) == nil)
    }

    private static func testOfflineQuota(resources: URL) {
        let helper = resources.appendingPathComponent("helper/quota_bridge.py")
        let pipe = Pipe()
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        process.arguments = [helper.path, "--preview"]
        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        process.environment = environment
        process.standardOutput = pipe
        process.standardError = FileHandle.nullDevice
        do { try process.run() } catch { preconditionFailure("offline quota helper failed to start: \(error)") }
        precondition(QuotaReader.waitBounded(process, timeout: 8), "offline quota helper timed out")
        let output = pipe.fileHandleForReading.readDataToEndOfFile()
        precondition(process.terminationStatus == 0 && QuotaReader.decodePayload(output) != nil,
                     "offline quota helper output was invalid")
    }

    private static func testDeadline() {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/sleep")
        process.arguments = ["5"]
        do { try process.run() } catch { preconditionFailure("timeout fixture failed to start: \(error)") }
        precondition(!QuotaReader.waitBounded(process, timeout: 0.1), "deadline failed to stop a slow child")
        precondition(!process.isRunning, "timed-out child remained alive")
    }
}
