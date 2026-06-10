import XCTest
@testable import MacPDFTranslator

final class EngineRunnerTests: XCTestCase {
    // Mock-движок: shell-скрипт печатает события протокола, включая мусорную строку
    func testRunnerParsesMockEngineOutput() throws {
        let script = FileManager.default.temporaryDirectory
            .appendingPathComponent("mock_engine_\(UUID().uuidString).sh")
        let body = """
        echo '{"event":"stage_start","stage":"parse"}'
        echo 'Consider using the pymupdf_layout package'
        echo '{"event":"progress","stage":"parse","done":1,"total":2,"eta_sec":1.5}'
        echo '{"event":"done","output":"/tmp/result.pdf"}'
        """
        try body.write(to: script, atomically: true, encoding: .utf8)
        defer { try? FileManager.default.removeItem(at: script) }

        let runner = EngineRunner()
        var events: [EngineEvent] = []
        let exited = expectation(description: "process exited")

        try runner.start(python: URL(fileURLWithPath: "/bin/bash"),
                         script: script, arguments: []) { event in
            DispatchQueue.main.async { events.append(event) }
        } onExit: { status in
            XCTAssertEqual(status, 0)
            exited.fulfill()
        }

        wait(for: [exited], timeout: 10)
        // События приходят через main queue — даём очереди разрядиться
        let drained = expectation(description: "main queue drained")
        DispatchQueue.main.async { drained.fulfill() }
        wait(for: [drained], timeout: 2)

        XCTAssertEqual(events, [
            .stageStart(stage: "parse"),
            .progress(stage: "parse", done: 1, total: 2, etaSec: 1.5, tps: nil),
            .done(output: "/tmp/result.pdf"),
        ])
    }

    func testCancelTerminatesProcess() throws {
        let script = FileManager.default.temporaryDirectory
            .appendingPathComponent("mock_sleep_\(UUID().uuidString).sh")
        try "sleep 30".write(to: script, atomically: true, encoding: .utf8)
        defer { try? FileManager.default.removeItem(at: script) }

        let runner = EngineRunner()
        let exited = expectation(description: "terminated")
        try runner.start(python: URL(fileURLWithPath: "/bin/bash"),
                         script: script, arguments: []) { _ in
        } onExit: { status in
            XCTAssertNotEqual(status, 0)  // SIGTERM
            exited.fulfill()
        }
        runner.cancel()
        wait(for: [exited], timeout: 10)
    }
}
