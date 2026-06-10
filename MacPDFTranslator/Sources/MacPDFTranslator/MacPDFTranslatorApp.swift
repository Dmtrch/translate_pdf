import SwiftUI
import AppKit

@main
struct MacPDFTranslatorApp: App {
    // Бинарник запускается без .app-бандла: без activation policy окно
    // не получает клавиатурный фокус и ввод уходит в терминал
    init() {
        NSApplication.shared.setActivationPolicy(.regular)
        DispatchQueue.main.async {
            NSApp.activate(ignoringOtherApps: true)
        }
    }

    var body: some Scene {
        WindowGroup("MacPDF Translator") {
            ContentView()
                .frame(minWidth: 640, minHeight: 480)
        }
        .windowResizability(.contentSize)
    }
}
