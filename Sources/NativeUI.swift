import AppKit
import Foundation

final class TBOperationWindow: NSWindow {
    static func isCloseShortcut(modifierFlags: NSEvent.ModifierFlags, characters: String?) -> Bool {
        let shortcutModifiers: NSEvent.ModifierFlags = [.command, .control, .option, .shift]
        return modifierFlags.intersection(shortcutModifiers) == .command && characters?.lowercased() == "w"
    }

    override func performKeyEquivalent(with event: NSEvent) -> Bool {
        if Self.isCloseShortcut(modifierFlags: event.modifierFlags, characters: event.charactersIgnoringModifiers) {
            performClose(nil)
            return true
        }
        return super.performKeyEquivalent(with: event)
    }
}

final class NativeUI: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem?
    private var window: NSWindow?
    private let quotaImage = NSImageView()
    private let quotaUnknown = NSTextField(labelWithString: "额度未知")
    private let codexImage = NSImageView()
    private let kimiImage = NSImageView()
    private let title = NSTextField(labelWithString: "正在读取额度和实时状态…")
    private let taskPicker = NSPopUpButton(frame: .zero, pullsDown: false)
    private let pickerStatus = NSTextField(labelWithString: "Codex：未选择任务（手动监看）")
    private var stateTimer: Timer?
    private var refreshTimer: Timer?
    private var tick = 0
    private var testStartedAt: TimeInterval?
    private var touchBarUI: TouchBarUI?
    private var reader: QuotaReader?
    private var liveReader: LiveStatusReader?
    private var demo: StatusDemo?
    private var demoOnly = false
    private var quotaMessage = "额度读取中"
    private var tasks: [CodexTask] = []
    private var taskListAvailable = false
    private var selectedThreadID: String?
    private var kimiGrace = KimiGrace()
    private var liveCodex: DemoState?
    private var kimiRaw = "不可用"

    func applicationDidFinishLaunching(_ note: Notification) {
        guard let resources = Bundle.main.resourceURL else { NSApp.terminate(nil); return }
        demoOnly = CommandLine.arguments.contains("--demo")
        let statusDemo = StatusDemo(assets: resources.appendingPathComponent("status-assets"))
        demo = statusDemo
        let quota = QuotaReader(resources: resources, demoOnly: demoOnly)
        reader = quota
        let barUI = TouchBarUI(demo: statusDemo)
        touchBarUI = barUI
        let live = LiveStatusReader(resources: resources)
        liveReader = live
        quota.onImage = { [weak self, weak barUI] image, message in
            guard let self else { return }
            self.quotaImage.image = image
            self.quotaImage.isHidden = image == nil
            self.quotaUnknown.isHidden = image != nil
            self.quotaMessage = message
            barUI?.setQuota(image)
            self.updateLiveDisplay()
        }
        live.onStatus = { [weak self] snapshot in self?.accept(snapshot) }
        setupMenuBar()
        setupPreview()
        quota.refresh()
        refreshTimer = Timer.scheduledTimer(withTimeInterval: 10, repeats: true) { [weak quota] _ in quota?.refresh() }
        openPreview()
        if demoOnly { replay() }
        else {
            live.loadTasks { [weak self] tasks in self?.setTasks(tasks) }
            live.start()
            updateLiveDisplay()
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
    func applicationWillTerminate(_ notification: Notification) {
        stateTimer?.invalidate(); refreshTimer?.invalidate()
        touchBarUI?.hide()
        liveReader?.stop(); reader?.stop()
    }

    private func setupMenuBar() {
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        if let url = Bundle.main.url(forResource: "menubar-pin", withExtension: "svg"),
           let image = NSImage(contentsOf: url) {
            image.size = NSSize(width: 18, height: 18)
            image.isTemplate = true
            item.button?.image = image
            item.button?.toolTip = "Touch Bar 原生状态"
            item.button?.setAccessibilityLabel("Touch Bar 原生状态")
        } else {
            item.button?.title = "AI"
        }
        let menu = NSMenu()
        menu.addItem(withTitle: "打开TB 操作框", action: #selector(openPreview), keyEquivalent: "")
        menu.addItem(withTitle: "显示Touch Bar", action: #selector(showTouchBar), keyEquivalent: "")
        menu.addItem(withTitle: "隐藏Touch Bar", action: #selector(hideTouchBar), keyEquivalent: "")
        menu.addItem(.separator())
        menu.addItem(withTitle: "退出", action: #selector(quit), keyEquivalent: "")
        menu.items.forEach { $0.target = self }
        item.menu = menu
        statusItem = item
    }

    private func setupPreview() {
        let window = TBOperationWindow(contentRect: NSRect(x: 0, y: 0, width: 640, height: 412), styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.title = "TB 操作框"
        window.center()
        let content = NSView(frame: window.contentView!.bounds)
        content.autoresizingMask = [.width, .height]; window.contentView = content
        let overviewHeading = NSTextField(labelWithString: "实时概览")
        overviewHeading.frame = NSRect(x: 24, y: 373, width: 592, height: 18)
        overviewHeading.font = .systemFont(ofSize: 13, weight: .semibold); content.addSubview(overviewHeading)
        title.frame = NSRect(x: 24, y: 349, width: 592, height: 16)
        title.font = .systemFont(ofSize: 11); title.textColor = .secondaryLabelColor; content.addSubview(title)
        let preview = NSView(frame: NSRect(x: 24, y: 210, width: 592, height: 128))
        preview.wantsLayer = true; preview.layer?.backgroundColor = NSColor.black.cgColor; preview.layer?.cornerRadius = 8
        content.addSubview(preview)
        quotaImage.frame = NSRect(x: 16, y: 56, width: 480, height: 60)
        quotaImage.imageScaling = .scaleProportionallyDown; quotaImage.isHidden = true; preview.addSubview(quotaImage)
        quotaUnknown.frame = NSRect(x: 16, y: 72, width: 300, height: 28)
        quotaUnknown.font = .monospacedSystemFont(ofSize: 12, weight: .medium); quotaUnknown.textColor = .white; preview.addSubview(quotaUnknown)
        codexImage.frame = NSRect(x: 16, y: 12, width: 100, height: 30)
        kimiImage.frame = NSRect(x: 256, y: 12, width: 80, height: 30)
        codexImage.imageScaling = .scaleProportionallyDown; kimiImage.imageScaling = .scaleProportionallyDown
        preview.addSubview(codexImage); preview.addSubview(kimiImage)
        let monitorHeading = NSTextField(labelWithString: "监看任务")
        monitorHeading.frame = NSRect(x: 24, y: 178, width: 592, height: 18)
        monitorHeading.font = .systemFont(ofSize: 13, weight: .semibold); content.addSubview(monitorHeading)
        taskPicker.frame = NSRect(x: 24, y: 142, width: 452, height: 28)
        taskPicker.target = self; taskPicker.action = #selector(selectTask(_:)); content.addSubview(taskPicker)
        taskPicker.toolTip = ""
        let refresh = NSButton(title: "刷新 Codex 任务", target: self, action: #selector(refreshTasks))
        refresh.frame = NSRect(x: 488, y: 142, width: 128, height: 28); content.addSubview(refresh)
        pickerStatus.frame = NSRect(x: 24, y: 119, width: 592, height: 16)
        pickerStatus.font = .systemFont(ofSize: 11); pickerStatus.textColor = .secondaryLabelColor; content.addSubview(pickerStatus)
        let touchBarHeading = NSTextField(labelWithString: "Touch Bar 显示")
        touchBarHeading.frame = NSRect(x: 24, y: 82, width: 280, height: 18)
        touchBarHeading.font = .systemFont(ofSize: 13, weight: .semibold); content.addSubview(touchBarHeading)
        let statusHeading = NSTextField(labelWithString: "状态测试")
        statusHeading.frame = NSRect(x: 340, y: 82, width: 276, height: 18)
        statusHeading.font = .systemFont(ofSize: 13, weight: .semibold); content.addSubview(statusHeading)
        let show = NSButton(title: "显示 Touch Bar", target: self, action: #selector(showTouchBar))
        let hide = NSButton(title: "隐藏", target: self, action: #selector(hideTouchBar))
        show.frame = NSRect(x: 24, y: 47, width: 124, height: 28)
        hide.frame = NSRect(x: 156, y: 47, width: 92, height: 28)
        content.addSubview(show); content.addSubview(hide)
        let test = NSButton(title: "测试模拟（48 秒）", target: self, action: #selector(replay))
        test.frame = NSRect(x: 340, y: 47, width: 154, height: 28); content.addSubview(test)
        let live = NSButton(title: "切回实时状态", target: self, action: #selector(useLive))
        live.frame = NSRect(x: 502, y: 47, width: 114, height: 28); content.addSubview(live)
        let testNote = NSTextField(labelWithString: "仅播放动画，不执行任务或消耗额度。")
        testNote.frame = NSRect(x: 340, y: 22, width: 276, height: 14)
        testNote.font = .systemFont(ofSize: 11); testNote.textColor = .secondaryLabelColor; content.addSubview(testNote)
        self.window = window
    }

    @objc private func openPreview() { window?.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true) }
    @objc private func showTouchBar() {
        guard ControlStrip.supported else { showNotice("此 macOS 未提供原型所需的 Touch Bar 接口。预览仍可使用。"); return }
        let conflicts = NSWorkspace.shared.runningApplications.filter {
            let id = $0.bundleIdentifier ?? ""
            let name = $0.localizedName ?? ""
            return id.contains("touchbar-native-preview") || id.contains("touchbar-native-live")
                || name.localizedCaseInsensitiveContains("BetterTouchTool") || id.localizedCaseInsensitiveContains("bettertouchtool")
        }
        let others = conflicts.filter { $0.processIdentifier != ProcessInfo.processInfo.processIdentifier }
        if !others.isEmpty { showNotice("请先正常退出 BTT 或其他 Touch Bar 原型宿主，再试用。此原型不会关闭或修改它们。"); return }
        guard touchBarUI?.show() == true else { showNotice("Touch Bar 无法显示；原生预览仍可使用。"); return }
    }
    @objc private func hideTouchBar() { touchBarUI?.hide() }
    @objc private func quit() { NSApp.terminate(nil) }

    @objc private func replay() {
        liveReader?.pause(); kimiGrace = KimiGrace(); liveCodex = nil
        testStartedAt = ProcessInfo.processInfo.systemUptime
        startAnimationTimer()
        renderTestFrame()
    }
    @objc private func useLive() {
        stateTimer?.invalidate(); stateTimer = nil; testStartedAt = nil
        if demoOnly {
            kimiGrace = KimiGrace(); liveCodex = nil
            touchBarUI?.updateLive(codex: nil, kimi: nil, tick: tick)
            title.stringValue = "离线额度示例 · --demo 禁用实时状态查询"
            return
        }
        tick = 0; kimiGrace = KimiGrace(); liveCodex = nil
        liveReader?.start(); refreshTasks(); updateLiveDisplay()
    }
    @objc private func selectTask(_ sender: NSPopUpButton) {
        guard !demoOnly else { pickerStatus.stringValue = "离线示例模式未读取 Codex 任务列表"; return }
        selectedThreadID = sender.selectedItem?.representedObject as? String
        liveCodex = nil
        updatePickerLabel()
        liveReader?.setCodexThread(selectedThreadID); updateLiveDisplay()
    }
    @objc private func refreshTasks() {
        guard !demoOnly else { pickerStatus.stringValue = "离线示例模式未读取 Codex 任务列表"; return }
        liveReader?.loadTasks { [weak self] in self?.setTasks($0) }
    }

    private func setTasks(_ value: [CodexTask]?) {
        guard let value else {
            taskListAvailable = false
            pickerStatus.stringValue = "Codex 任务列表不可用 · 点击刷新重试"
            return
        }
        tasks = value; taskListAvailable = true
        taskPicker.removeAllItems()
        taskPicker.menu?.addItem(NSMenuItem(title: "不监看 Codex 任务", action: nil, keyEquivalent: ""))
        taskPicker.lastItem?.representedObject = nil
        for task in tasks {
            let item = NSMenuItem(title: task.title, action: nil, keyEquivalent: "")
            item.representedObject = task.id
            taskPicker.menu?.addItem(item)
        }
        if let id = selectedThreadID, !tasks.contains(where: { $0.id == id }) {
            let item = NSMenuItem(title: "所选任务暂不在列表 · \(id.prefix(8))", action: nil, keyEquivalent: "")
            item.representedObject = id; taskPicker.menu?.addItem(item)
        }
        if let selectedThreadID, let item = taskPicker.itemArray.first(where: { ($0.representedObject as? String) == selectedThreadID }) {
            taskPicker.select(item)
        } else {
            selectedThreadID = nil
            taskPicker.selectItem(at: 0)
        }
        liveReader?.setCodexThread(selectedThreadID)
        updatePickerLabel()
        updateLiveDisplay()
    }

    private func accept(_ snapshot: LiveStatusSnapshot) {
        guard testStartedAt == nil else { return }
        let now = ProcessInfo.processInfo.systemUptime
        kimiRaw = snapshot.kimi ?? "不可用"
        _ = kimiGrace.update(kimiRaw, now: now)
        liveCodex = AgentState.display(snapshot.codex)
        updateLiveDisplay()
    }

    private func renderTestFrame() {
        let elapsed = ProcessInfo.processInfo.systemUptime - (testStartedAt ?? 0)
        let state = demo?.state(at: elapsed) ?? .hidden
        codexImage.image = demo?.image(state, tick: tick)
        kimiImage.image = demo?.image(state, tick: tick, kimi: true)
        touchBarUI?.updateDemo(state, tick: tick)
        title.stringValue = "\(demoOnly ? "离线额度示例" : quotaMessage) · TEST：模拟 CODEX / KIMI"
        if elapsed >= Double(StatusDemo.cycleSeconds) {
            useLive()
        }
    }

    private func updateLiveDisplay() {
        guard testStartedAt == nil else { return }
        let kimi = kimiGrace.visible(now: ProcessInfo.processInfo.systemUptime)
        codexImage.image = liveCodex.flatMap { demo?.image($0, tick: tick) }
        kimiImage.image = kimi.flatMap { demo?.image($0, tick: tick, kimi: true) }
        touchBarUI?.setQuota(quotaImage.image)
        touchBarUI?.updateLive(codex: liveCodex, kimi: kimi, tick: tick)
        let kimiLabel = kimi?.label ?? (kimiRaw == "不可用" ? "不可用" : kimiRaw == "空闲" ? "空闲" : "未知/歧义")
        title.stringValue = "\(demoOnly ? "离线额度示例" : quotaMessage) · Codex：\(selectedThreadID == nil ? "未选择" : liveCodex?.label ?? "空闲/未知") · Kimi：\(kimiLabel)"
        if liveCodex != nil || kimi != nil { startAnimationTimer() }
        else { stateTimer?.invalidate(); stateTimer = nil }
    }

    private func startAnimationTimer() {
        guard stateTimer == nil else { return }
        stateTimer = Timer.scheduledTimer(withTimeInterval: 1.0 / 6.0, repeats: true) { [weak self] _ in
            guard let self else { return }
            self.tick += 1
            if self.testStartedAt != nil { self.renderTestFrame() }
            else { self.updateLiveDisplay() }
        }
    }

    private func updatePickerLabel() {
        if !taskListAvailable { pickerStatus.stringValue = "Codex 任务列表不可用 · 点击刷新重试"; taskPicker.toolTip = "" }
        else if let id = selectedThreadID, let task = tasks.first(where: { $0.id == id }) {
            pickerStatus.stringValue = "手动监看 Codex；切换对话页面不会自动跟随。"
            taskPicker.toolTip = task.title
        } else if let id = selectedThreadID {
            pickerStatus.stringValue = "Codex：手动监看 · 任务不在列表（\(id.prefix(8))）"
            taskPicker.toolTip = "所选任务不在当前列表：\(id)"
        } else { pickerStatus.stringValue = "Codex：未选择任务（手动监看）"; taskPicker.toolTip = "" }
    }

    private func showNotice(_ text: String) {
        let alert = NSAlert(); alert.messageText = "Touch Bar 原型"; alert.informativeText = text; alert.runModal()
    }
}
