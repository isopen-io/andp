// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "MeeshySDK",
    platforms: [.iOS(.v16), .macOS(.v13)],
    products: [
        .library(name: "MeeshySDK", targets: ["MeeshySDK"]),
        .library(name: "MeeshyUI", targets: ["MeeshyUI"]),
    ],
    dependencies: [],
    targets: [
        .target(name: "MeeshySDK", dependencies: []),
        .target(name: "MeeshyUI", dependencies: ["MeeshySDK"]),
    ]
)
