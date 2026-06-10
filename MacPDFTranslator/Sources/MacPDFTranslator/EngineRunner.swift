import Foundation

// Событие JSON-протокола движка (engine/translate_pdf.py)
enum EngineEvent: Equatable {
    case stageStart(stage: String)
    case progress(stage: String, done: Int, total: Int, etaSec: Double, tps: Double?)
    case done(output: String)
    case error(code: String, message: String)
}

enum EngineEventParser {
    static func parse(line: String) -> EngineEvent? {
        guard let data = line.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let event = obj["event"] as? String
        else { return nil }

        switch event {
        case "stage_start":
            guard let stage = obj["stage"] as? String else { return nil }
            return .stageStart(stage: stage)
        case "progress":
            guard let stage = obj["stage"] as? String,
                  let done = obj["done"] as? Int,
                  let total = obj["total"] as? Int
            else { return nil }
            let eta = (obj["eta_sec"] as? Double) ?? Double(obj["eta_sec"] as? Int ?? 0)
            let tps = obj["tps"] as? Double
            return .progress(stage: stage, done: done, total: total, etaSec: eta, tps: tps)
        case "done":
            guard let output = obj["output"] as? String else { return nil }
            return .done(output: output)
        case "error":
            return .error(code: (obj["code"] as? String) ?? "unknown",
                          message: (obj["message"] as? String) ?? "Неизвестная ошибка")
        default:
            return nil
        }
    }
}

// Поиск движка: ищет engine/translate_pdf.py вверх от текущей папки и от бандла
enum EngineLocator {
    static func locate() -> (python: URL, script: URL)? {
        var candidates = [
            URL(fileURLWithPath: FileManager.default.currentDirectoryPath),
            Bundle.main.bundleURL,
        ]
        candidates += candidates.map { $0.deletingLastPathComponent() }

        for start in candidates {
            var dir = start
            for _ in 0..<6 {
                let script = dir.appendingPathComponent("engine/translate_pdf.py")
                let python = dir.appendingPathComponent("engine/.venv/bin/python")
                if FileManager.default.fileExists(atPath: script.path),
                   FileManager.default.fileExists(atPath: python.path) {
                    return (python, script)
                }
                dir.deleteLastPathComponent()
                if dir.path == "/" { break }
            }
        }
        return nil
    }
}

// Запускает python-движок и транслирует JSON-lines stdout в события
final class EngineRunner {
    private var process: Process?
    private var buffer = ""

    var isRunning: Bool { process?.isRunning ?? false }

    func start(python: URL, script: URL, arguments: [String],
               onEvent: @escaping @Sendable (EngineEvent) -> Void,
               onExit: @escaping @Sendable (Int32) -> Void) throws {
        let process = Process()
        process.executableURL = python
        process.arguments = [script.path] + arguments
        process.currentDirectoryURL = script.deletingLastPathComponent()

        let stdout = Pipe()
        process.standardOutput = stdout
        process.standardError = Pipe()  // stderr движка в UI не показываем

        stdout.fileHandleForReading.readabilityHandler = { [weak self] handle in
            guard let self else { return }
            let chunk = String(data: handle.availableData, encoding: .utf8) ?? ""
            self.buffer += chunk
            while let nl = self.buffer.firstIndex(of: "\n") {
                let line = String(self.buffer[..<nl]).trimmingCharacters(in: .whitespaces)
                self.buffer = String(self.buffer[self.buffer.index(after: nl)...])
                if !line.isEmpty, let event = EngineEventParser.parse(line: line) {
                    DispatchQueue.main.async { onEvent(event) }
                }
            }
        }

        process.terminationHandler = { proc in
            stdout.fileHandleForReading.readabilityHandler = nil
            DispatchQueue.main.async { onExit(proc.terminationStatus) }
        }

        self.buffer = ""
        self.process = process
        try process.run()
    }

    func cancel() {
        process?.terminate()
        process = nil
    }
}
