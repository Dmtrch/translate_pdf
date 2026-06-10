import Foundation
import Observation

// Статус подключения к локальному серверу Ollama и список моделей
@MainActor
@Observable
final class OllamaClient {
    static let defaultModel = "bob-hymt:latest"

    var models: [String] = []
    var isConnected = false
    var checking = false

    private let url = URL(string: "http://localhost:11434/api/tags")!

    func refresh() async {
        checking = true
        defer { checking = false }
        do {
            var request = URLRequest(url: url)
            request.timeoutInterval = 3
            let (data, _) = try await URLSession.shared.data(for: request)
            struct Tags: Decodable {
                struct Model: Decodable { let name: String }
                let models: [Model]
            }
            let tags = try JSONDecoder().decode(Tags.self, from: data)
            models = tags.models.map(\.name)
            isConnected = true
        } catch {
            models = []
            isConnected = false
        }
    }
}
