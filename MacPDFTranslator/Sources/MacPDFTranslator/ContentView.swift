import AppKit
import SwiftUI
import UniformTypeIdentifiers

// Главный экран по wireframe из PRD (раздел 4)
struct ContentView: View {
    @State private var viewModel = TranslationViewModel()
    @State private var ollama = OllamaClient()
    @State private var dropTargeted = false

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            filesSection
            languagesSection
            ollamaSection
            actionSection
            progressSection
            statusSection
            Spacer(minLength: 0)
        }
        .padding(20)
        .frame(minWidth: 640, minHeight: 480)
        .onDrop(of: [.fileURL], isTargeted: $dropTargeted) { providers in
            handleDrop(providers)
        }
        .overlay {
            if dropTargeted {
                RoundedRectangle(cornerRadius: 8)
                    .strokeBorder(Color.accentColor, lineWidth: 3)
                    .padding(4)
            }
        }
        .task { await ollama.refresh() }
    }

    // MARK: - Файлы

    private var filesSection: some View {
        Grid(alignment: .leading, horizontalSpacing: 8, verticalSpacing: 8) {
            GridRow {
                Text("Исходный файл:")
                TextField("Перетащите PDF или нажмите «Обзор…»", text: $viewModel.inputPath)
                    .textFieldStyle(.roundedBorder)
                Button("Обзор…") { pickInput() }
            }
            GridRow {
                Text("Выходной файл:")
                TextField("Путь для сохранения результата", text: $viewModel.outputPath)
                    .textFieldStyle(.roundedBorder)
                Button("Изменить…") { pickOutput() }
            }
        }
        .disabled(viewModel.isRunning)
    }

    // MARK: - Языки

    private var languagesSection: some View {
        HStack(spacing: 24) {
            Picker("Язык оригинала:", selection: $viewModel.srcLang) {
                ForEach(Languages.source) { Text($0.name).tag($0.code) }
            }
            .fixedSize()
            Picker("Язык перевода:", selection: $viewModel.dstLang) {
                ForEach(Languages.all) { Text($0.name).tag($0.code) }
            }
            .fixedSize()
        }
        .disabled(viewModel.isRunning)
    }

    // MARK: - Ollama

    private var ollamaSection: some View {
        GroupBox("Настройки локальной модели (Ollama)") {
            HStack(spacing: 16) {
                Picker("Модель:", selection: $viewModel.model) {
                    if ollama.models.isEmpty {
                        Text(viewModel.model).tag(viewModel.model)
                    }
                    ForEach(ollama.models, id: \.self) { Text($0).tag($0) }
                }
                .fixedSize()
                .disabled(viewModel.isRunning)

                HStack(spacing: 6) {
                    Circle()
                        .fill(ollama.isConnected ? Color.green : Color.red)
                        .frame(width: 9, height: 9)
                    Text(ollama.isConnected ? "Подключено (127.0.0.1)" : "Нет подключения")
                        .foregroundStyle(.secondary)
                }

                Button {
                    Task { await ollama.refresh() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .help("Обновить список моделей")

                Spacer()
            }
            .padding(.vertical, 4)
        }
    }

    // MARK: - Запуск

    private var actionSection: some View {
        HStack {
            Button(viewModel.isRunning ? "Отменить" : "Начать перевод") {
                if viewModel.isRunning {
                    viewModel.cancel()
                } else {
                    viewModel.start()
                }
            }
            .controlSize(.large)
            .buttonStyle(.borderedProminent)
            .tint(viewModel.isRunning ? .red : .accentColor)
            .disabled(!viewModel.isRunning && !viewModel.canStart)
            Spacer()
        }
    }

    // MARK: - Прогресс

    private var progressSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Прогресс:")
            progressRow(title: "Распознавание:",
                        value: viewModel.recognitionProgress,
                        eta: viewModel.recognitionETA)
            progressRow(title: "Перевод:",
                        value: viewModel.translationProgress,
                        eta: viewModel.translationETA)
        }
    }

    private func progressRow(title: String, value: Double, eta: String) -> some View {
        HStack(spacing: 10) {
            Text(title).frame(width: 110, alignment: .leading)
            ProgressView(value: value)
            Text(progressLabel(value: value, eta: eta))
                .font(.caption.monospacedDigit())
                .foregroundStyle(.secondary)
                .frame(width: 120, alignment: .leading)
        }
    }

    private func progressLabel(value: Double, eta: String) -> String {
        let percent = "\(Int((value * 100).rounded()))%"
        if !eta.isEmpty { return "\(percent) (ETA: \(eta))" }
        if value <= 0 { return "Ожидание" }
        return percent
    }

    // MARK: - Статус / ошибки

    @ViewBuilder
    private var statusSection: some View {
        switch viewModel.phase {
        case .idle:
            EmptyView()
        case .running(let stage):
            Label(stageDescription(stage), systemImage: "gearshape.arrow.triangle.2.circlepath")
                .foregroundStyle(.secondary)
        case .finished(let output):
            HStack {
                Label("Готово: \(output)", systemImage: "checkmark.circle.fill")
                    .foregroundStyle(.green)
                if !viewModel.totalTime.isEmpty {
                    Text("Общее время: \(viewModel.totalTime)")
                        .font(.callout.monospacedDigit())
                        .foregroundStyle(.secondary)
                }
                Button("Показать в Finder") {
                    NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: output)])
                }
            }
        case .failed(let message):
            Label(message, systemImage: "exclamationmark.triangle.fill")
                .foregroundStyle(.red)
                .textSelection(.enabled)
        }
    }

    private func stageDescription(_ stage: String) -> String {
        switch stage {
        case "parse": return "Извлечение структуры документа…"
        case "ocr": return "Распознавание текста…"
        case "translate": return "Перевод текста…"
        case "render": return "Сборка итогового PDF…"
        default: return "Обработка…"
        }
    }

    // MARK: - Выбор файлов

    private func pickInput() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.pdf]
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK, let url = panel.url {
            viewModel.setInput(path: url.path)
        }
    }

    private func pickOutput() {
        let panel = NSSavePanel()
        panel.allowedContentTypes = [.pdf]
        if !viewModel.outputPath.isEmpty {
            let current = URL(fileURLWithPath: viewModel.outputPath)
            panel.directoryURL = current.deletingLastPathComponent()
            panel.nameFieldStringValue = current.lastPathComponent
        }
        if panel.runModal() == .OK, let url = panel.url {
            viewModel.outputPath = url.path
        }
    }

    private func handleDrop(_ providers: [NSItemProvider]) -> Bool {
        guard let provider = providers.first else { return false }
        _ = provider.loadObject(ofClass: URL.self) { url, _ in
            guard let url, url.pathExtension.lowercased() == "pdf" else { return }
            DispatchQueue.main.async {
                viewModel.setInput(path: url.path)
            }
        }
        return true
    }
}

#Preview {
    ContentView()
}
