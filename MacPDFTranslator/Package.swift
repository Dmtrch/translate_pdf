// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "MacPDFTranslator",
    platforms: [
        .macOS(.v14)
    ],
    targets: [
        .executableTarget(
            name: "MacPDFTranslator",
            path: "Sources/MacPDFTranslator"
        ),
        .testTarget(
            name: "MacPDFTranslatorTests",
            dependencies: ["MacPDFTranslator"],
            path: "Tests/MacPDFTranslatorTests"
        )
    ]
)
