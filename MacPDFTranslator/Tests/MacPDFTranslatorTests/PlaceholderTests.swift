import XCTest
@testable import MacPDFTranslator

final class EngineEventParserTests: XCTestCase {
    func testParseStageStart() {
        let event = EngineEventParser.parse(line: #"{"event":"stage_start","stage":"ocr"}"#)
        XCTAssertEqual(event, .stageStart(stage: "ocr"))
    }

    func testParseProgressWithTPS() {
        let line = #"{"event":"progress","stage":"translate","done":12,"total":80,"eta_sec":140.5,"tps":42.5}"#
        let event = EngineEventParser.parse(line: line)
        XCTAssertEqual(event, .progress(stage: "translate", done: 12, total: 80,
                                        etaSec: 140.5, tps: 42.5))
    }

    func testParseProgressIntegerETA() {
        let line = #"{"event":"progress","stage":"render","done":1,"total":2,"eta_sec":0}"#
        let event = EngineEventParser.parse(line: line)
        XCTAssertEqual(event, .progress(stage: "render", done: 1, total: 2,
                                        etaSec: 0, tps: nil))
    }

    func testParseDone() {
        let event = EngineEventParser.parse(line: #"{"event":"done","output":"/tmp/out.pdf"}"#)
        XCTAssertEqual(event, .done(output: "/tmp/out.pdf"))
    }

    func testParseError() {
        let line = #"{"event":"error","code":"ollama_unreachable","message":"нет связи"}"#
        let event = EngineEventParser.parse(line: line)
        XCTAssertEqual(event, .error(code: "ollama_unreachable", message: "нет связи"))
    }

    func testGarbageLinesIgnored() {
        XCTAssertNil(EngineEventParser.parse(line: "Consider using pymupdf_layout"))
        XCTAssertNil(EngineEventParser.parse(line: "{\"event\":\"unknown\"}"))
        XCTAssertNil(EngineEventParser.parse(line: ""))
    }

    @MainActor
    func testETAFormatting() {
        XCTAssertEqual(TranslationViewModel.formatETA(25), "00:25")
        XCTAssertEqual(TranslationViewModel.formatETA(140.5), "02:21")
        XCTAssertEqual(TranslationViewModel.formatETA(0), "")
    }

    @MainActor
    func testDurationFormatting() {
        XCTAssertEqual(TranslationViewModel.formatDuration(0), "00:00")
        XCTAssertEqual(TranslationViewModel.formatDuration(83), "01:23")
        XCTAssertEqual(TranslationViewModel.formatDuration(1260), "21:00")
        XCTAssertEqual(TranslationViewModel.formatDuration(3600), "1:00:00")
        XCTAssertEqual(TranslationViewModel.formatDuration(7325), "2:02:05")
        XCTAssertEqual(TranslationViewModel.formatDuration(-5), "")
    }
}
