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
    private let codexQuotaView = NSImageView()
    private let kimiQuotaView = NSImageView()
    private var lastQuotaImage: NSImage?
    private let codexQuotaUnknown = NSTextField(labelWithString: "额度未知")
    private let kimiQuotaUnknown = NSTextField(labelWithString: "额度未知")
    private let codexImage = NSImageView()
    private let kimiImage = NSImageView()
    private let title = NSTextField(labelWithString: "正在读取额度和实时状态…")
    private let taskPicker = NSPopUpButton(frame: .zero, pullsDown: false)
    private let pickerStatus = NSTextField(labelWithString: "Codex：未选择任务（手动监看）")
    private let kimiPicker = NSPopUpButton(frame: .zero, pullsDown: false)
    private let kimiPickerStatus = NSTextField(labelWithString: "Kimi：正在连接本地服务…")
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
    private var kimiSelection: KimiSelection = .auto
    private var kimiTasks: [KimiTask] = []
    private var kimiListAvailable = false
    private var kimiListTruncated = false
    private var kimiReason = "unavailable"

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
            self.lastQuotaImage = image
            self.codexQuotaView.image = Self.quotaHalf(image, codex: true)
            self.kimiQuotaView.image = Self.quotaHalf(image, codex: false)
            self.codexQuotaView.isHidden = image == nil
            self.kimiQuotaView.isHidden = image == nil
            self.codexQuotaUnknown.isHidden = image != nil
            self.kimiQuotaUnknown.isHidden = image != nil
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
        if demoOnly {
            setKimiTasks(KimiTask.demoTasks, truncated: false, reason: "ambiguous")
            pickerStatus.stringValue = "离线示例模式未读取 Codex 任务列表"
            replay()
        }
        else {
            live.loadTasks { [weak self] tasks in self?.setTasks(tasks) }
            refreshKimiTasks()
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
        menu.addItem(withTitle: "打开 TB 操作框", action: #selector(openPreview), keyEquivalent: "")
        menu.addItem(withTitle: "显示 Touch Bar", action: #selector(showTouchBar), keyEquivalent: "")
        menu.addItem(withTitle: "隐藏 Touch Bar", action: #selector(hideTouchBar), keyEquivalent: "")
        menu.addItem(.separator())
        menu.addItem(withTitle: "退出", action: #selector(quit), keyEquivalent: "")
        menu.items.forEach { $0.target = self }
        item.menu = menu
        statusItem = item
    }

    private func setupPreview() {
        let window = TBOperationWindow(contentRect: NSRect(x: 0, y: 0, width: 640, height: 320), styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.title = "TB 操作框"
        window.center()
        let content = NSView(frame: window.contentView!.bounds)
        content.autoresizingMask = [.width, .height]; window.contentView = content
        func makeHeading(_ text: String, x: CGFloat, y: CGFloat, width: CGFloat) {
            let heading = NSTextField(labelWithString: text)
            heading.frame = NSRect(x: x, y: y, width: width, height: 18)
            heading.font = .systemFont(ofSize: 13, weight: .semibold)
            content.addSubview(heading)
        }
        func makeSeparator(y: CGFloat) {
            let separator = NSBox(frame: NSRect(x: 24, y: y, width: 592, height: 1))
            separator.boxType = .separator
            content.addSubview(separator)
        }
        func styleNote(_ field: NSTextField) {
            field.font = .systemFont(ofSize: 11); field.textColor = .secondaryLabelColor
            field.lineBreakMode = .byTruncatingTail
        }
        // 实时概览：每个模型一张卡片，上方为该模型额度（整图裁半），下方为状态动画。
        // 新增模型时向 providerCards 追加一张卡片即可，卡片横向等宽排列。
        makeHeading("实时概览", x: 24, y: 282, width: 592)
        title.frame = NSRect(x: 24, y: 260, width: 592, height: 16)
        styleNote(title); content.addSubview(title)
        let providerCards: [(quota: NSImageView, status: NSImageView, statusWidth: CGFloat, unknown: NSTextField)] = [
            (codexQuotaView, codexImage, 100, codexQuotaUnknown),
            (kimiQuotaView, kimiImage, 80, kimiQuotaUnknown),
        ]
        for (index, card) in providerCards.enumerated() {
            let cardView = NSView(frame: NSRect(x: 24 + CGFloat(index) * 304, y: 118, width: 288, height: 132))
            cardView.wantsLayer = true; cardView.layer?.backgroundColor = NSColor.black.cgColor; cardView.layer?.cornerRadius = 8
            content.addSubview(cardView)
            card.quota.frame = NSRect(x: 24, y: 56, width: 240, height: 60)
            card.quota.imageScaling = .scaleProportionallyDown; card.quota.isHidden = true
            cardView.addSubview(card.quota)
            card.status.frame = NSRect(x: (288 - card.statusWidth) / 2, y: 16, width: card.statusWidth, height: 30)
            card.status.imageScaling = .scaleProportionallyDown
            cardView.addSubview(card.status)
            card.unknown.frame = NSRect(x: 24, y: 72, width: 240, height: 28)
            card.unknown.font = .monospacedSystemFont(ofSize: 12, weight: .medium)
            card.unknown.textColor = .white; card.unknown.alignment = .center
            cardView.addSubview(card.unknown)
        }
        makeSeparator(y: 108)
        // 监看任务：标题与刷新按钮同一行；Codex／Kimi 下拉框同一行，
        // 各自的归属与状态说明跟在对应下拉框下方（截断时悬停看全文）。
        // 刷新按钮同时刷新两个列表、各自保留选择；Touch Bar 显示／隐藏只在图钉菜单里。
        makeHeading("监看任务", x: 24, y: 80, width: 200)
        let refresh = NSButton(title: "刷新列表", target: self, action: #selector(refreshAllTasks))
        refresh.bezelStyle = .rounded
        refresh.toolTip = "同时刷新 Codex 与 Kimi 任务列表，保留当前选择"
        refresh.frame = NSRect(x: 528, y: 75, width: 88, height: 28); content.addSubview(refresh)
        taskPicker.frame = NSRect(x: 24, y: 42, width: 288, height: 28)
        taskPicker.target = self; taskPicker.action = #selector(selectTask(_:)); content.addSubview(taskPicker)
        taskPicker.toolTip = ""
        kimiPicker.frame = NSRect(x: 328, y: 42, width: 288, height: 28)
        kimiPicker.target = self; kimiPicker.action = #selector(selectKimiTask(_:)); content.addSubview(kimiPicker)
        pickerStatus.frame = NSRect(x: 24, y: 20, width: 288, height: 16)
        styleNote(pickerStatus); content.addSubview(pickerStatus)
        kimiPickerStatus.frame = NSRect(x: 328, y: 20, width: 288, height: 16)
        styleNote(kimiPickerStatus)
        content.addSubview(kimiPickerStatus)
        rebuildKimiPicker()
        self.window = window
    }

    /// 额度整图为 480×60：左半 Codex、右半 Kimi（helper 固定布局）。
    /// 操作框按模型裁半分行显示；Touch Bar 仍使用整图。
    private static func quotaHalf(_ image: NSImage?, codex: Bool) -> NSImage? {
        guard let image else { return nil }
        let half = NSImage(size: NSSize(width: 240, height: 60))
        half.lockFocus()
        image.draw(in: NSRect(x: 0, y: 0, width: 240, height: 60),
                   from: NSRect(x: codex ? 0 : 240, y: 0, width: 240, height: 60),
                   operation: .sourceOver, fraction: 1)
        half.unlockFocus()
        return half
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

    /// 离线示例模式（--demo）启动时自动播放一轮；正常模式无入口。
    private func replay() {
        liveReader?.pause(); kimiGrace = KimiGrace(); liveCodex = nil
        testStartedAt = ProcessInfo.processInfo.systemUptime
        startAnimationTimer()
        renderTestFrame()
    }
    private func useLive() {
        stateTimer?.invalidate(); stateTimer = nil; testStartedAt = nil
        if demoOnly {
            kimiGrace = KimiGrace(); liveCodex = nil
            updateLiveDisplay()
            return
        }
        tick = 0; kimiGrace = KimiGrace(); liveCodex = nil
        liveReader?.start(); refreshTasks(); refreshKimiTasks(); updateLiveDisplay()
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

    /// 操作框里唯一的刷新入口：两个列表都刷，各自保留当前选择。
    @objc private func refreshAllTasks() {
        refreshTasks(); refreshKimiTasks()
    }

    @objc private func selectKimiTask(_ sender: NSPopUpButton) {
        let value = sender.selectedItem?.representedObject as? String
        let next: KimiSelection
        if value == "off" { next = .off }
        else if let value, LiveStatusReader.validUUID(value), let id = UUID(uuidString: value) { next = .pinned(id) }
        else { next = .auto }
        guard next != kimiSelection else { return }
        kimiSelection = next
        // Clear synchronously, before the new helper request can be queued.
        kimiGrace = KimiGrace()
        kimiRaw = next == .off ? "空闲" : "未知"
        kimiReason = next == .off ? "off" : "idle"
        if demoOnly {
            stateTimer?.invalidate(); stateTimer = nil; testStartedAt = nil; liveCodex = nil
        } else { liveReader?.setKimiSelection(next) }
        updateKimiPickerLabel()
        updateLiveDisplay()
    }

    @objc private func refreshKimiTasks() {
        if demoOnly { setKimiTasks(KimiTask.demoTasks, truncated: false, reason: "ambiguous"); return }
        liveReader?.loadKimiTasks { [weak self] tasks, truncated, reason in
            self?.setKimiTasks(tasks, truncated: truncated, reason: reason)
        }
    }

    private func setKimiTasks(_ value: [KimiTask]?, truncated: Bool, reason: String) {
        kimiTasks = value ?? []
        kimiListAvailable = value != nil
        kimiListTruncated = truncated
        if value == nil || value?.isEmpty == true { kimiReason = reason }
        rebuildKimiPicker()
    }

    private func rebuildKimiPicker() {
        kimiPicker.removeAllItems()
        for (label, value) in [("Kimi：自动 · 唯一活跃任务", "auto"), ("Kimi：不监看", "off")] {
            let item = NSMenuItem(title: label, action: nil, keyEquivalent: "")
            item.representedObject = value; kimiPicker.menu?.addItem(item)
        }
        for task in kimiTasks {
            let item = NSMenuItem(title: (task.active ? "● " : "") + task.title, action: nil, keyEquivalent: "")
            item.representedObject = task.id; kimiPicker.menu?.addItem(item)
        }
        if let pin = kimiSelection.sessionID, !kimiTasks.contains(where: { $0.id == pin }) {
            let item = NSMenuItem(title: "所选 Kimi 任务暂不在列表 · \(pin.prefix(8))", action: nil, keyEquivalent: "")
            item.representedObject = pin; kimiPicker.menu?.addItem(item)
        }
        let selected = kimiSelection.sessionID ?? kimiSelection.mode
        if let item = kimiPicker.itemArray.first(where: { ($0.representedObject as? String) == selected }) {
            kimiPicker.select(item)
        }
        updateKimiPickerLabel()
    }

    private func updateKimiPickerLabel() {
        let note: String
        if kimiSelection == .off { note = "Kimi：已停用监看" }
        else if kimiReason == "unavailable" { note = "Kimi：本地服务未连接 · 点击刷新重试" }
        else if kimiReason == "not_found" { note = "Kimi：所选任务已不在当前服务列表 · 保留选择" }
        else if kimiReason == "ambiguous" && kimiSelection == .auto { note = "Kimi：多个活跃任务 · 请手动选择" }
        else if kimiReason == "ambiguous" || kimiReason == "invalid_selection" { note = "Kimi：任务身份无法确认 · 点击刷新重试" }
        else if !kimiListAvailable { note = "Kimi：未取得任务列表 · 点击刷新重试" }
        else if kimiSelection == .auto && (kimiReason == "idle" || kimiReason == "no_tasks") { note = "Kimi：暂无活跃任务" }
        else if let pin = kimiSelection.sessionID { note = "手动监看 Kimi · \(pin.prefix(8)) · \(kimiReason == "idle" ? "空闲" : "当前任务")" }
        else { note = "Kimi：自动监看唯一活跃任务" }
        kimiPickerStatus.stringValue = (demoOnly ? "模拟列表 · " : "") + note + (kimiListTruncated ? " · 仅显示前 40 项" : "")
        kimiPickerStatus.toolTip = kimiPickerStatus.stringValue
        kimiPicker.toolTip = kimiSelection.sessionID ?? "自动模式仅在任务身份唯一时显示状态"
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
        guard testStartedAt == nil, snapshot.kimiSelection == kimiSelection else { return }
        let now = ProcessInfo.processInfo.systemUptime
        kimiRaw = snapshot.kimi ?? "不可用"
        kimiReason = snapshot.kimiReason
        _ = kimiGrace.update(kimiRaw, selection: kimiSelection, resolvedID: snapshot.kimiResolvedSessionID,
                             reason: snapshot.kimiReason, now: now)
        liveCodex = AgentState.display(snapshot.codex)
        updateKimiPickerLabel()
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
        if demoOnly {
            let fixture = KimiTask.demoStatus(selection: kimiSelection)
            kimiRaw = fixture.raw; kimiReason = fixture.reason
            _ = kimiGrace.update(fixture.raw, selection: kimiSelection, resolvedID: fixture.resolvedID,
                                 reason: fixture.reason, now: ProcessInfo.processInfo.systemUptime)
            updateKimiPickerLabel()
        }
        let kimi = kimiGrace.visible(now: ProcessInfo.processInfo.systemUptime)
        codexImage.image = liveCodex.flatMap { demo?.image($0, tick: tick) }
        kimiImage.image = kimi.flatMap { demo?.image($0, tick: tick, kimi: true) }
        touchBarUI?.setQuota(lastQuotaImage)
        touchBarUI?.updateLive(codex: liveCodex, kimi: kimi, tick: tick)
        let kimiNote: String
        switch kimiReason {
        case "unavailable": kimiNote = "服务未连接"
        case "off": kimiNote = "已停用"
        case "ambiguous": kimiNote = kimiSelection == .auto ? "多任务待选择" : "任务身份不明"
        case "not_found": kimiNote = "所选任务不在列表"
        case "idle", "no_tasks": kimiNote = "无活动任务"
        case "invalid_selection": kimiNote = "任务身份不明"
        default: kimiNote = "空闲/未知"
        }
        let kimiLabel = kimi?.label ?? kimiNote
        title.stringValue = "\(demoOnly ? "离线模拟" : quotaMessage) · Codex：\(selectedThreadID == nil ? "未选择" : liveCodex?.label ?? "空闲/未知") · Kimi：\(kimiLabel)"
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
        pickerStatus.toolTip = pickerStatus.stringValue
    }

    private func showNotice(_ text: String) {
        let alert = NSAlert(); alert.messageText = "Touch Bar 原型"; alert.informativeText = text; alert.runModal()
    }
}
