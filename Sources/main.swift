import AppKit
import Foundation

if CommandLine.arguments.contains("--probe") {
    print("Touch Bar bridge selectors available: \(ControlStrip.supported)")
    exit(0)
}
if CommandLine.arguments.contains("--self-test") {
    guard let resources = Bundle.main.resourceURL else { fatalError("app resources unavailable") }
    PrototypeChecks.run(resources: resources)
    exit(0)
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let delegate = NativeUI()
app.delegate = delegate
app.run()
