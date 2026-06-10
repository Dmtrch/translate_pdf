import Foundation
import Observation

struct Language: Identifiable, Hashable {
    let code: String
    let name: String
    var id: String { code }
}

// 8 языков из PRD; для языка оригинала добавляется «Авто»
enum Languages {
    static let all: [Language] = [
        Language(code: "en", name: "Английский"),
        Language(code: "ru", name: "Русский"),
        Language(code: "zh", name: "Китайский"),
        Language(code: "de", name: "Немецкий"),
        Language(code: "fr", name: "Французский"),
        Language(code: "it", name: "Итальянский"),
        Language(code: "es", name: "Испанский"),
        Language(code: "ja", name: "Японский"),
    ]
    static let source = [Language(code: "auto", name: "Авто")] + all
}

@MainActor
@Observable
final class TranslationViewModel {
    enum Phase: Equatable {
        case idle
        case running(stage: String)
        case finished(output: String)
        case failed(message: String)
    }

    var inputPath = ""
    var outputPath = ""
    var srcLang = "auto"
    var dstLang = "ru"
    var model = OllamaClient.defaultModel

    var phase: Phase = .idle
    // Бар 1 «Распознавание»: этапы parse + ocr; бар 2 «Перевод»: translate + render
    var recognitionProgress = 0.0
    var recognitionETA = ""
    var translationProgress = 0.0
    var translationETA = ""
    // Общее время от кнопки «Начать перевод» до сохранения итогового файла
    var totalTime = ""

    private let runner = EngineRunner()
    private var startTime: Date?

    var isRunning: Bool {
        if case .running = phase { return true }
        return false
    }

    var canStart: Bool {
        !isRunning && !inputPath.isEmpty && !outputPath.isEmpty
    }

    // Автоимя выходного файла: <имя>_translated.pdf в той же папке (PRD 3.1)
    func setInput(path: String) {
        inputPath = path
        let url = URL(fileURLWithPath: path)
        let name = url.deletingPathExtension().lastPathComponent + "_translated.pdf"
        outputPath = url.deletingLastPathComponent().appendingPathComponent(name).path
    }

    func start() {
        guard let engine = EngineLocator.locate() else {
            phase = .failed(message: "Движок не найден: рядом с приложением нет engine/translate_pdf.py и engine/.venv")
            return
        }
        recognitionProgress = 0
        translationProgress = 0
        recognitionETA = ""
        translationETA = ""
        totalTime = ""
        startTime = Date()
        phase = .running(stage: "parse")

        let arguments = [inputPath, "-o", outputPath,
                         "--from", srcLang, "--to", dstLang, "--model", model]
        do {
            try runner.start(python: engine.python, script: engine.script,
                             arguments: arguments) { [weak self] event in
                Task { @MainActor in self?.handle(event: event) }
            } onExit: { [weak self] status in
                Task { @MainActor in self?.handleExit(status: status) }
            }
        } catch {
            phase = .failed(message: "Не удалось запустить движок: \(error.localizedDescription)")
        }
    }

    func cancel() {
        runner.cancel()
        phase = .idle
    }

    private func handle(event: EngineEvent) {
        switch event {
        case .stageStart(let stage):
            phase = .running(stage: stage)
            if stage == "render" { translationETA = "" }

        case .progress(let stage, let done, let total, let etaSec, _):
            let fraction = total > 0 ? Double(done) / Double(total) : 0
            switch stage {
            case "parse", "ocr":
                recognitionProgress = fraction
                recognitionETA = Self.formatETA(etaSec)
            case "translate":
                recognitionProgress = 1.0
                recognitionETA = ""
                // render оставляем последние 5% бара
                translationProgress = fraction * 0.95
                translationETA = Self.formatETA(etaSec)
            case "render":
                translationProgress = 0.95 + fraction * 0.05
            default:
                break
            }

        case .done(let output):
            recognitionProgress = 1.0
            translationProgress = 1.0
            recognitionETA = ""
            translationETA = ""
            // done приходит после doc.save в движке — файл уже на диске
            if let startTime {
                totalTime = Self.formatDuration(Date().timeIntervalSince(startTime))
            }
            phase = .finished(output: output)

        case .error(_, let message):
            phase = .failed(message: message)
        }
    }

    private func handleExit(status: Int32) {
        // Ненулевой выход без события error (например, python упал)
        if isRunning && status != 0 {
            phase = .failed(message: "Движок завершился с ошибкой (код \(status))")
        }
    }

    // Форматирование ETA в «ММ:СС» (PRD 3.3)
    static func formatETA(_ seconds: Double) -> String {
        guard seconds > 0 else { return "" }
        let total = Int(seconds.rounded())
        return String(format: "%02d:%02d", total / 60, total % 60)
    }

    // Общая длительность: «ММ:СС», от часа — «Ч:ММ:СС»
    static func formatDuration(_ seconds: Double) -> String {
        guard seconds >= 0 else { return "" }
        let total = Int(seconds.rounded())
        if total >= 3600 {
            return String(format: "%d:%02d:%02d",
                          total / 3600, (total % 3600) / 60, total % 60)
        }
        return String(format: "%02d:%02d", total / 60, total % 60)
    }
}
