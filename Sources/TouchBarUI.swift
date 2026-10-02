import AppKit

final class TouchBarUI: NSObject, NSTouchBarDelegate {
    static let quotaID = NSTouchBarItem.Identifier("local.codex.touchbar.quota")
    static let codexID = NSTouchBarItem.Identifier("local.codex.touchbar.codex")
    static let kimiID = NSTouchBarItem.Identifier("local.codex.touchbar.kimi")
    let quotaView = NSImageView()
    private let quotaContainer = NSStackView()
    private let quotaUnknown = NSTextField(labelWithString: "额度未知")
    private let codexView = NSImageView()
    private let kimiView = NSImageView()
    private let codexContainer = NSStackView()
    private let kimiContainer = NSStackView()
    private let codexTest = NSTextField(labelWithString: "TEST")
    private let kimiTest = NSTextField(labelWithString: "TEST")
    private let demo: StatusDemo
    let bar = NSTouchBar()
    var trayItem: NSCustomTouchBarItem?

    init(demo: StatusDemo) {
        self.demo = demo
        super.init()
        bar.delegate = self
        bar.defaultItemIdentifiers = [Self.quotaID]
        quotaView.imageScaling = .scaleProportionallyDown
        quotaContainer.orientation = .horizontal
        quotaUnknown.font = .monospacedSystemFont(ofSize: 10, weight: .medium)
        quotaContainer.addArrangedSubview(quotaView)
        quotaContainer.addArrangedSubview(quotaUnknown)
        codexView.imageScaling = .scaleProportionallyDown
        kimiView.imageScaling = .scaleProportionallyDown
        configureStatus(codexContainer, view: codexView, marker: codexTest)
        configureStatus(kimiContainer, view: kimiView, marker: kimiTest)
    }
    private func configureStatus(_ stack: NSStackView, view: NSImageView, marker: NSTextField) {
        stack.orientation = .horizontal
        stack.alignment = .centerY
        stack.spacing = 3
        marker.font = .monospacedSystemFont(ofSize: 8, weight: .bold)
        marker.textColor = .systemYellow
        stack.addArrangedSubview(view)
        stack.addArrangedSubview(marker)
    }
    func setQuota(_ image: NSImage?) {
        quotaView.image = image
        quotaView.isHidden = image == nil
        quotaUnknown.isHidden = image != nil
    }
    func updateDemo(_ state: DemoState, tick: Int) {
        updateLive(codex: state == .hidden ? nil : state, kimi: state == .hidden ? nil : state, tick: tick)
        codexTest.isHidden = state == .hidden; kimiTest.isHidden = state == .hidden
    }
    func updateLive(codex: DemoState?, kimi: DemoState?, tick: Int) {
        codexTest.isHidden = true; kimiTest.isHidden = true
        codexView.image = codex.flatMap { demo.image($0, tick: tick) }
        kimiView.image = kimi.flatMap { demo.image($0, tick: tick, kimi: true) }
        var ids: [NSTouchBarItem.Identifier] = [Self.quotaID]
        if codex != nil { ids.append(Self.codexID) }
        if kimi != nil { ids.append(Self.kimiID) }
        if bar.defaultItemIdentifiers != ids { bar.defaultItemIdentifiers = ids }
    }
    func makeTrayItem() -> NSTouchBarItem {
        let item = NSCustomTouchBarItem(identifier: NSTouchBarItem.Identifier(ControlStrip.identifier))
        let button = NSButton(image: trayIcon(), target: self, action: #selector(restoreTouchBar))
        button.frame = NSRect(x: 0, y: 0, width: 36, height: 30)
        button.isBordered = false
        button.imagePosition = .imageOnly
        button.imageScaling = .scaleProportionallyDown
        button.setAccessibilityLabel("显示 AI Touch Bar")
        button.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([
            button.widthAnchor.constraint(equalToConstant: 36),
            button.heightAnchor.constraint(equalToConstant: 30),
        ])
        item.view = button
        trayItem = item
        return item
    }
    private func trayIcon() -> NSImage {
        let image: NSImage
        if let url = Bundle.main.url(forResource: "menubar-pin", withExtension: "svg"),
           let bundled = NSImage(contentsOf: url) {
            image = bundled
        } else {
            image = NSImage(systemSymbolName: "pin.fill", accessibilityDescription: "显示 AI Touch Bar")
                ?? NSImage(size: NSSize(width: 18, height: 18))
        }
        image.size = NSSize(width: 18, height: 18)
        image.isTemplate = true
        return image
    }
    @objc private func restoreTouchBar() { _ = show() }
    func show() -> Bool {
        if trayItem != nil { return ControlStrip.present(bar) }
        let item = trayItem ?? (makeTrayItem() as? NSCustomTouchBarItem)
        guard let item, ControlStrip.install(item) else { return false }
        guard ControlStrip.present(bar) else { ControlStrip.remove(item); trayItem = nil; return false }
        return true
    }
    func hide() {
        guard trayItem != nil else { return }
        ControlStrip.minimize(bar)
        ControlStrip.remove(trayItem)
        trayItem = nil
    }
    func touchBar(_ touchBar: NSTouchBar, makeItemForIdentifier identifier: NSTouchBarItem.Identifier) -> NSTouchBarItem? {
        let item = NSCustomTouchBarItem(identifier: identifier)
        if identifier == Self.quotaID {
            quotaContainer.translatesAutoresizingMaskIntoConstraints = false
            quotaView.translatesAutoresizingMaskIntoConstraints = false
            item.view = quotaContainer
            NSLayoutConstraint.activate([
                quotaView.widthAnchor.constraint(equalToConstant: 240),
                quotaView.heightAnchor.constraint(equalToConstant: 30),
                quotaContainer.widthAnchor.constraint(equalToConstant: 240),
                quotaContainer.heightAnchor.constraint(equalToConstant: 30),
            ])
            return item
        }
        let view: NSStackView
        let image: NSImageView
        let width: CGFloat
        if identifier == Self.codexID { view = codexContainer; image = codexView; width = 100 }
        else if identifier == Self.kimiID { view = kimiContainer; image = kimiView; width = 80 }
        else { return nil }
        view.translatesAutoresizingMaskIntoConstraints = false
        image.translatesAutoresizingMaskIntoConstraints = false
        item.view = view
        NSLayoutConstraint.activate([
            image.widthAnchor.constraint(equalToConstant: width),
            image.heightAnchor.constraint(equalToConstant: 30),
            view.heightAnchor.constraint(equalToConstant: 30),
        ])
        return item
    }
}
