// Adapted from AI Agent Usage Widget, commit 15dd9ff0bbe8ecdeae00e2d9ec2dd23e0dad8d81.
// Copyright and MIT license: ../UPSTREAM-LICENSE
import AppKit
import CoreFoundation
import Darwin

private typealias SetPresenceFn = @convention(c) (CFString, Bool) -> Void

private let setPresence: SetPresenceFn? = {
    let path = "/System/Library/PrivateFrameworks/DFRFoundation.framework/DFRFoundation"
    guard let handle = dlopen(path, RTLD_NOW),
          let symbol = dlsym(handle, "DFRElementSetControlStripPresenceForIdentifier") else { return nil }
    return unsafeBitCast(symbol, to: SetPresenceFn.self)
}()

enum ControlStrip {
    static var identifier: String { (Bundle.main.bundleIdentifier ?? "local.codex.touchbar-native-live") + ".item" }
    static var supported: Bool {
        let itemClass: AnyObject = NSTouchBarItem.self
        let barClass: AnyObject = NSTouchBar.self
        return setPresence != nil
            && itemClass.responds(to: NSSelectorFromString("addSystemTrayItem:"))
            && itemClass.responds(to: NSSelectorFromString("removeSystemTrayItem:"))
            && barClass.responds(to: NSSelectorFromString("presentSystemModalTouchBar:systemTrayItemIdentifier:"))
            && barClass.responds(to: NSSelectorFromString("minimizeSystemModalTouchBar:"))
    }
    @discardableResult static func install(_ item: NSTouchBarItem) -> Bool {
        guard supported else { return false }
        let cls: AnyObject = NSTouchBarItem.self
        _ = cls.perform(NSSelectorFromString("addSystemTrayItem:"), with: item)
        setPresence?(identifier as CFString, true)
        return true
    }
    static func remove(_ item: NSTouchBarItem?) {
        let cls: AnyObject = NSTouchBarItem.self
        if let item, cls.responds(to: NSSelectorFromString("removeSystemTrayItem:")) {
            _ = cls.perform(NSSelectorFromString("removeSystemTrayItem:"), with: item)
        }
        setPresence?(identifier as CFString, false)
    }
    static func present(_ bar: NSTouchBar) -> Bool {
        let cls: AnyObject = NSTouchBar.self
        let selector = NSSelectorFromString("presentSystemModalTouchBar:systemTrayItemIdentifier:")
        guard cls.responds(to: selector) else { return false }
        _ = cls.perform(selector, with: bar, with: identifier as NSString)
        return true
    }
    static func minimize(_ bar: NSTouchBar?) {
        guard let bar else { return }
        let cls: AnyObject = NSTouchBar.self
        let selector = NSSelectorFromString("minimizeSystemModalTouchBar:")
        if cls.responds(to: selector) { _ = cls.perform(selector, with: bar) }
    }
}
